"""
This is an example to extract data from Toast, technology platform primarily designed for the restaurant industry.
It provides an all-in-one point-of-sale (POS) and management system tailored to meet the unique needs
of restaurants, cafes, and similar businesses.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

import requests as rq
import traceback
from datetime import datetime, timezone, timedelta
import time
import json
import copy
import hashlib
from cryptography.fernet import Fernet

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


def update(configuration: dict, state: dict):
    """
    # Define the update function, which is a required function, and is called by Fivetran during each sync.
    # See the technical reference documentation for more details on the update function
    # https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    # The state dictionary is empty for the first sync or for any full re-sync
    :param configuration: a dictionary that holds the configuration settings for the connector.
    :param state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
    """

    try:
        domain = configuration["domain"]
        base_url = f"https://{domain}"
        key = configuration["key"]
        headers, state = make_headers(configuration, base_url, state, key)

        start_timestamp = (
            datetime.now(timezone.utc).isoformat("T", "milliseconds").replace("+00:00", "Z")
        )
        from_ts, to_ts = set_timeranges(state, configuration, start_timestamp)

        # start the sync
        sync_items(base_url, headers, from_ts, to_ts, start_timestamp, state)

    except Exception as e:
        # Return error response
        exception_message = str(e)
        stack_trace = traceback.format_exc()
        detailed_message = f"Error Message: {exception_message}\nStack Trace:\n{stack_trace}"
        raise RuntimeError(detailed_message)


def sync_items(base_url, headers, ts_from, ts_to, start_timestamp, state):
    """
    This is the main generator function for the connector.
    It calls other functions that are specific to the endpoint type.
    :param base_url: Toast API URL
    :param headers: authentication headers
    :param ts_from: Timestamp to start the current iteration
    :param ts_to: Timestamp to end the current iteration
    :param start_timestamp: timestamp that the sync was started
    :return:
    """
    more_data = True
    first_pass = True  # indicates whether to call endpoints that don't have an end timestamp

    # config endpoint is a list of tuples ("endpoint", "destination_table_name")
    config_endpoints = [
        ("/config/v2/alternatePaymentTypes", "alternate_payment_types"),
        ("/config/v2/diningOptions", "dining_option"),
        ("/config/v2/discounts", "discounts"),
        ("/config/v2/menus", "menu"),
        ("/config/v2/menuGroups", "menu_group"),
        ("/config/v2/menuItems", "menu_item"),
        ("/config/v2/restaurantServices", "restaurant_service"),
        ("/config/v2/revenueCenters", "revenue_center"),
        ("/config/v2/salesCategories", "sale_category"),
        ("/config/v2/serviceAreas", "service_area"),
        ("/config/v2/tables", "tables"),
    ]

    while more_data:
        # set timerange dicts
        timerange_params = {"startDate": ts_from, "endDate": ts_to}
        modified_params = {"modifiedStartDate": ts_from, "modifiedEndDate": ts_to}
        config_params = {"lastModified": ts_from}
        state["to_ts"] = ts_to
        log.debug(f"state updated, new state: {repr(state)}")

        # Get response from API call.
        response_page, next_token = get_api_response(
            base_url + "/partners/v1/restaurants", headers
        )

        # Process the items.
        if not response_page:
            break  # End pagination if there are no records in response.

        # Iterate over each user in the 'items' list and perform an upsert operation.
        # The 'upsert' operation inserts the data into the destination.
        restaurant_count = len(response_page)
        log.info(f"***** timerange is from {ts_from} to {ts_to} ***** ")
        for index, r in enumerate(response_page):
            id = r["restaurantGuid"]
            # rename some fields in response
            rename_fields = [("restaurantGuid", "id"), ("restaurantName", "name")]
            for old_name, new_name in rename_fields:
                r[new_name] = r.pop(old_name)
            log.info(f"***** starting restaurant {id}, {index + 1} of {restaurant_count} ***** ")
            op.upsert(table="restaurant", data=r)

            if r.get("deleted") and "id" in r:
                op.delete(table="restaurant", keys={"id": r["id"]})

            # config endpoints
            # only process these on the first pass since they don't have an end timestamp
            if first_pass:
                for endpoint, table_name in config_endpoints:
                    process_config(base_url, headers, endpoint, table_name, id, config_params)

                # no timerange_params, only sync during first pass
                for endpoint, table_name in [
                    ("/labor/v1/jobs", "job"),
                    ("/labor/v1/employees", "employee"),
                ]:
                    process_labor(base_url, headers, endpoint, table_name, id)

            # cash management endpoints
            process_cash(
                base_url, headers, "/cashmgmt/v1/entries", "cash_entry", id, timerange_params
            )
            process_cash(
                base_url, headers, "/cashmgmt/v1/deposits", "cash_deposit", id, timerange_params
            )

            # orders
            process_orders(
                base_url, headers, "/orders/v2/ordersBulk", "orders", id, timerange_params
            )

            # labor endpoints
            # these two endpoints can only retrieve 30 days at a time
            process_labor(
                base_url, headers, "/labor/v1/shifts", "shift", id, params=timerange_params
            )
            process_labor(
                base_url,
                headers,
                "/labor/v1/timeEntries",
                "time_entry",
                id,
                params=modified_params,
            )

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of interruptions.
        # checkpointing every 30 days for convenience,
        # since we can only ask for 30 days of shifts and time entries at a time
        op.checkpoint(state)
        first_pass = False

        # Determine if we should continue pagination based on the total items and the current offset.
        if ts_to < start_timestamp:
            # get new timestamps
            ts_from, ts_to = set_timeranges(state, {}, start_timestamp)
        else:
            more_data = False


def process_config(base_url, headers, endpoint, table_name, rst_id, timerange):
    """
    This is the generating function for configuration endpoints for a restaurant and timerange
    :param base_url: Toast API URL
    :param headers: authentication headers
    :param endpoint: Toast API endpoint
    :param table_name: table name to store data in destination
    :param rst_id: id for restaurant to query
    :param timerange: time range to query
    :return:
    """
    headers["Toast-Restaurant-External-ID"] = rst_id
    more_data = True
    pagination = {}
    # fields_to_extract is a mapping of fields to extract from source data.
    # Keys represent table names, and values are lists of tuples.
    # Each tuple defines a mapping for one or more fields in the table:
    # (field containing a dictionary, key to extract from dictionary, new field name).
    fields_to_extract = {
        "menu_group": [("menu", "guid", "menu_id")],
        "service_area": [("revenueCenter", "guid", "revenue_center_guid")],
        "tables": [
            ("revenueCenter", "guid", "revenue_center_guid"),
            ("serviceArea", "guid", "service_area_guid"),
        ],
    }

    while more_data:
        try:
            param_string = "&".join(f"{key}={value}" for key, value in timerange.items())
            response_page, next_token = get_api_response(
                base_url + endpoint + "?" + param_string, headers, params=pagination
            )
            log.debug(
                f"restaurant {rst_id}: response_page has {len(response_page)} items for {endpoint}"
            )
            for o in response_page:
                if fields_to_extract.get(table_name):
                    o = extract_fields(fields_to_extract[table_name], o)
                o = stringify_lists(o)
                o["restaurant_id"] = rst_id
                o = replace_guid_with_id(o)
                op.upsert(table=table_name, data=o)

            if next_token:
                pagination["pageToken"] = next_token
            else:
                more_data = False

        except Exception as e:
            # Return error response
            exception_message = str(e)
            stack_trace = traceback.format_exc()
            detailed_message = f"Error Message: {exception_message}\nStack Trace:\n{stack_trace}"
            raise RuntimeError(detailed_message)


def process_labor(base_url, headers, endpoint, table_name, rst_id, params=None):
    """
    This is the generating function for labor endpoints, for a restaurant and a timerange
    Labor endpoints do not use pagination
    Time range parameters are optional for breaks, shifts, and time entries.
    Time range parameters are not accepted for jobs and employees
    :param base_url: Toast API URL
    :param headers: authentication headers
    :param endpoint: Toast API endpoint
    :param table_name: table name to store data in destination
    :param rst_id: id for restaurant to query
    :param params: This is a dictionary of timerange parameters which can vary by endpoint
    :return:
    """
    params = params or {}
    headers["Toast-Restaurant-External-ID"] = rst_id

    # fields_to_extract is a mapping of fields to extract from source data.
    # Keys represent table names, and values are lists of tuples.
    # Each tuple defines a mapping for one or more fields in the table:
    # (field containing a dictionary, key to extract from dictionary, new field name).
    fields_to_extract = {
        "shift": [
            ("employeeReference", "guid", "employee_reference_id"),
            ("jobReference", "guid", "job_reference_id"),
        ],
        "time_entry": [
            ("employeeReference", "guid", "employee_reference_id"),
            ("jobReference", "guid", "job_reference_id"),
            ("shiftReference", "guid", "shift_reference_id"),
        ],
    }

    try:
        response_page, next_token = get_api_response(base_url + endpoint, headers, params=params)
        log.debug(
            f"restaurant {rst_id}: response_page has {len(response_page)} items for {endpoint}"
        )

        for o in response_page:
            if endpoint == "/labor/v1/timeEntries" and o.get("breaks"):
                process_child(o["breaks"], "break", "time_entry_id", o["guid"])
            elif endpoint == "/labor/v1/employees":
                process_child(
                    o.get("jobReferences", []), "employee_job_reference", "employee_id", o["guid"]
                )
                process_child(
                    o.get("wageOverrides", []), "employee_wage_override", "employee_id", o["guid"]
                )
            elif endpoint == "/labor/v1/shifts":
                o = flatten_fields(["scheduleConfig"], o)

            if table_name in fields_to_extract:
                o = extract_fields(fields_to_extract[table_name], o)

            o = stringify_lists(o)
            o["restaurant_id"] = rst_id
            o = replace_guid_with_id(o)
            op.upsert(table=table_name, data=o)

            if o.get("deleted") and "id" in o:
                op.delete(table=table_name, keys={"id": o["id"]})

    except Exception as e:
        # Return error response
        exception_message = str(e)
        stack_trace = traceback.format_exc()
        detailed_message = f"Error Message: {exception_message}\nStack Trace:\n{stack_trace}"
        raise RuntimeError(detailed_message)


def process_cash(base_url, headers, endpoint, table_name, rst_id, params):
    """
    This is the generating function for cash management endpoints, for a restaurant and a timerange
    Cash management endpoints take a single business date as a parameter,
    so this function calls the generate_business_dates function to get a list of dates
    within the provided timerange
    :param base_url: Toast API URL
    :param headers: authentication headers
    :param endpoint: Toast API endpoint
    :param table_name: table name to store data in destination
    :param rst_id: id for restaurant to query
    :param params: This is a dictionary of timerange parameters
    :return:
    """
    headers["Toast-Restaurant-External-ID"] = rst_id
    # fields_to_flatten is a mapping of fields to flatten from source data.
    # Keys represent table names, and values are lists of field names.
    # The dictionary in each field should be used to create new fields, prefixed by the original field name.
    # e.g. "info": {"id": 1, "type": "foo"}
    # would become {"info_id": 1, "info_type": "foo} and the "info" key will be popped
    fields_to_flatten = {
        "cash_deposit": ["employee", "creator"],
        "cash_entry": [
            "approverOrShiftReviewSubject",
            "creatorOrShiftReviewSubject",
            "cashDrawer",
            "employee1",
            "employee2",
            "payoutReason",
            "noSaleReason",
        ],
    }
    try:
        date_range = generate_business_dates(params["startDate"], params["endDate"])

        for d in date_range:
            response_page, next_token = get_api_response(
                base_url + endpoint + "?businessDate=" + d, headers
            )
            # log.debug(f"restaurant {rst_id}: response_page has {len(response_page)} items for {endpoint}")
            for o in response_page:
                o = flatten_fields(fields_to_flatten[table_name], o)
                o["restaurant_id"] = rst_id
                o = replace_guid_with_id(o)
                op.upsert(table=table_name, data=o)

    except Exception as e:
        # Return error response
        exception_message = str(e)
        stack_trace = traceback.format_exc()
        detailed_message = f"Error Message: {exception_message}\nStack Trace:\n{stack_trace}"
        raise RuntimeError(detailed_message)


def process_orders(base_url, headers, endpoint, table_name, rst_id, params):
    """
    This is the main generating function for the bulkOrders endpoint.
    This function upserts/deletes the orders table only.
    Other tables that are children come from process_payments or process_pricing_features.
    :param base_url: Toast API URL
    :param headers: authentication headers
    :param endpoint: Toast API endpoint
    :param table_name: table name to store data in destination
    :param rst_id: id for restaurant to query
    :param params: This is a dictionary of timerange parameters which can vary by endpoint
    """

    headers["Toast-Restaurant-External-ID"] = rst_id  # Move outside loop for efficiency
    params = params.copy()  # Avoid modifying original params
    params.update({"pageSize": 100, "page": 1})  # Set pagination defaults

    # flatten these fields, e.g. "info": {"id": 1, "type": "foo"}
    # would become {"info_id": 1, "info_type": "foo} and the "info" key will be popped
    fields_to_flatten = ["server", "createdDevice", "lastModifiedDevice"]
    # extract guids from these fields, make a new field ending in _guid, and pop the original
    fields_extract_ids = ["diningOption", "table", "serviceArea", "revenueCenter"]

    try:
        for page_num in range(1, 1_000_000):  # Prevent infinite loops; max reasonable pages
            params["page"] = page_num
            response_page, next_token = get_api_response(
                base_url + endpoint, headers, params=params
            )
            log.debug(
                f"restaurant {rst_id}: response_page has {len(response_page)} items for {endpoint}"
            )

            if not response_page:
                break  # No more data

            for order in response_page:
                order["restaurant_id"] = rst_id
                process_payments(order)
                process_pricing_features(order)

                order = flatten_fields(fields_to_flatten, order)

                for field in fields_extract_ids:
                    if order.get(field) and "guid" in order[field]:
                        order[f"{field}_guid"] = order[field]["guid"]
                        order.pop(field, None)

                order.pop("checks", None)
                order = stringify_lists(order)
                order = replace_guid_with_id(order)
                op.upsert(table=table_name, data=order)

                if order.get("deleted") and "id" in order:
                    op.delete(table=table_name, keys={"id": order["id"]})

            if len(response_page) < params["pageSize"]:
                break  # No more pages available

    except Exception as e:
        # Return error response
        exception_message = str(e)
        stack_trace = traceback.format_exc()
        detailed_message = f"Error Message: {exception_message}\nStack Trace:\n{stack_trace}"
        raise RuntimeError(detailed_message)


def process_payments(order):
    """
    This function processes payment information for an order.
    It upserts the orders_check_payment and payment tables.
    It passes the checks list to the process_child function to generate the orders_check table
    and its children.
    :param order: a single order dictionary
    """
    # flatten these fields, e.g. "info": {"id": 1, "type": "foo"}
    # would become {"info_id": 1, "info_type": "foo} and the "info" key will be popped
    fields_to_flatten = [
        "cashDrawer",
        "createdDevice",
        "lastModifiedDevice",
        "otherPayment",
        "refund",
        "server",
    ]
    if "checks" in order and order["checks"]:
        process_child(order["checks"], "orders_check", "orders_id", order["guid"])
        for check in order["checks"]:
            if "payments" in check:
                for payment in check["payments"]:
                    op.upsert(
                        table="orders_check_payment",
                        data={
                            "orders_check_id": check["guid"],
                            "payment_id": payment["guid"],
                            "orders_guid": order["guid"],
                        },
                    )
                    payment = flatten_fields(fields_to_flatten, payment)
                    payment["restaurant_id"] = order["restaurant_id"]
                    process_void_info(payment)
                    payment = replace_guid_with_id(payment)
                    op.upsert(table="payment", data=payment)


def process_pricing_features(order):
    """
    This function processes pricing features for an order.
    It upserts the orders_pricing_feature table.
    :param order: a single order dictionary
    """
    if "pricingFeatures" in order and order["pricingFeatures"]:
        for feature in order["pricingFeatures"]:
            op.upsert(
                table="orders_pricing_feature",
                data={"orders_id": order["guid"], "pricing_feature": feature},
            )
        order.pop("pricingFeatures", None)  # Remove processed field


def process_child(parent, table_name, id_field_name, id_field):
    """
    Iterates through records in parent list to generate child tables.
    If child tables also contain child records
    :param parent: parent record (list) which contains children
    :param table_name: connector table name for parent record
    :param id_field_name: id field name in parent record to tie child to parent
    :param id_field: id field value in parent record
    :return:
    """

    # dictionary of connector tables and the child fields (lists) that get their own tables
    # e.g. {"table_name": [("childField01", "child_table_name_01"), ("childField02", "child_table_name_02")] }
    relationships = {
        "orders_check": [
            ("selections", "orders_check_selection"),
            ("appliedDiscounts", "orders_check_applied_discount"),
            ("appliedServiceCharges", "orders_check_applied_service_charge"),
        ],
        "orders_check_applied_discount": [
            ("comboItems", "orders_check_applied_discount_combo_item"),
            ("triggers", "orders_check_applied_discount_trigger"),
        ],
        "orders_check_applied_service_charge": [
            ("appliedTax", "orders_check_applied_service_charge_applied_tax")
        ],
        "orders_check_selection": [
            ("appliedTaxes", "orders_check_selection_applied_tax"),
            ("modifiers", "orders_check_selection_modifier"),
            ("appliedDiscounts", "orders_check_selection_applied_discount"),
        ],
        "orders_check_selection_applied_discount": [
            ("comboItems", "orders_check_selection_applied_discount_combo_item"),
            ("triggers", "orders_check_selection_applied_discount_trigger"),
        ],
    }

    # fields_to_flatten is a mapping of fields to flatten from source data.
    # Keys represent table names, and values are lists of field names.
    # The dictionary in each field should be used to create new fields, prefixed by the original field name.
    # e.g. "info": {"id": 1, "type": "foo"}
    # would become {"info_id": 1, "info_type": "foo} and the "info" key will be popped
    fields_to_flatten = {
        "break": ["breakType"],
        "employee_wage_override": ["jobReference"],
        "orders_check": ["customer", "createdDevice", "lastModifiedDevice"],
        "orders_check_applied_discount": ["approver", "appliedDiscountReason", "discount"],
        "orders_check_applied_discount_trigger": ["selection"],
        "orders_check_applied_service_charge": ["serviceCharge"],
        "orders_check_selection": [
            "salesCategory",
            "itemGroup",
            "item",
            "diningOption",
            "refundDetails",
            "voidReason",
        ],
        "orders_check_selection_applied_discount": [
            "approver",
            "appliedDiscountReason",
            "discount",
        ],
        "orders_check_selection_applied_tax": ["taxRate"],
        "orders_check_selection_modifier": [
            "diningOption",
            "item",
            "itemGroup",
            "optionGroup",
            "salesCategory",
            "preModifier",
            "voidReason",
        ],
        "orders_check_selection_applied_discount_trigger": ["selection"],
    }

    for p in parent:
        # log.debug(f"processing {table_name}")
        p[id_field_name] = id_field
        if table_name in relationships:
            for child_key, child_table_name in relationships[table_name]:
                if len(p.get(child_key, [])) > 0:  # Use .get() to handle missing keys gracefully
                    process_child(p[child_key], child_table_name, table_name + "_id", p["guid"])
                p.pop(child_key, None)
        if table_name in fields_to_flatten:
            # log.debug(f"flattening fields in {table_name}")
            p = flatten_fields(fields_to_flatten[table_name], p)
        # check for null guids in appliedTaxes[]
        # Use deterministic ID based on parent selection + tax rate to ensure consistent identification across syncs
        if table_name == "orders_check_selection_applied_tax" and p.get("guid") is None:
            parent_id = p.get("orders_check_selection_id") or ""
            tax_rate_id = p.get("taxRate_id") or ""
            tax_name = p.get("name") or ""
            tax_rate = str(p.get("rate") or "")
            unique_string = f"{parent_id}_{tax_rate_id}_{tax_name}_{tax_rate}"
            p["guid"] = "gen-" + hashlib.md5(unique_string.encode()).hexdigest()
        if table_name == "orders_check":
            p.pop("payments", None)
        p = stringify_lists(p)
        p = replace_guid_with_id(p)
        op.upsert(table=table_name, data=p)
        # need to also handle deletes here, for child tables and their children (e.g. orders_check and orders_check_selection)

        if p.get("deleted") and "id" in p:
            op.delete(table=table_name, keys={"id": p["id"]})


def process_void_info(payment):
    """
    Processing payment["voidInfo"], heavily nested field that seemed easier to handle this way
    May revisit in the future
    :param payment: single payment record
    :return:
    """
    if payment.get("voidInfo"):
        payment["void_info_approver_guid"] = payment["voidInfo"]["voidApprover"]["guid"]
        payment["void_info_business_date"] = payment["voidInfo"]["voidBusinessDate"]
        payment["void_info_date"] = payment["voidInfo"]["voidDate"]
        if payment["voidInfo"].get("voidUser"):
            payment["void_info_user_guid"] = payment["voidInfo"]["voidUser"]["guid"]
        if payment["voidInfo"].get("voidReason"):
            payment["void_info_reason_entity_type"] = payment["voidInfo"]["voidReason"][
                "entityType"
            ]
            payment["void_info_reason_guid"] = payment["voidInfo"]["voidReason"]["guid"]
        payment.pop("voidInfo", None)


def make_headers(conf, base_url, state, key):
    """
    Create authentication headers, reusing a cached token if possible.

    :param conf: Dictionary containing authentication details.
    :param base_url: Base URL of the API.
    :param state: Dictionary storing token and expiration details.
    :param key: Encryption key (Fernet) used for token encryption/decryption.
    :return: Tuple (headers, updated_state)
    """
    fernet = Fernet(key)
    current_time = time.time()

    # Check if a valid token exists and is not expiring in the next hour
    fut_time = current_time + 3600
    if "encrypted_token" in state and "token_ttl" in state and state["token_ttl"] > fut_time:
        try:
            auth_token = fernet.decrypt(state["encrypted_token"].encode()).decode()
            log.info("encrypted_token found with at least an hour left, reusing")
            return {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}, state
        except Exception as e:
            print(f"⚠️ Token decryption failed: {e}, re-authenticating...")

    # No valid token OR token expiring within 1 hour, request a new one
    payload = {
        "clientId": conf.get("clientId"),
        "clientSecret": conf.get("clientSecret"),
        "userAccessType": conf.get("userAccessType"),
    }

    try:
        log.info("encrypted_token not found in state or is expiring soon, requesting new token")
        auth_response = rq.post(
            f"{base_url}/authentication/v1/authentication/login", json=payload, timeout=10
        )
        auth_response.raise_for_status()
        auth_page = auth_response.json()

        # Extract token safely
        auth_token = auth_page.get("token", {}).get("accessToken")
        token_expiry = auth_page.get("token", {}).get("expiresIn", 3600)  # Default to 1 hour

        if not auth_token:
            raise ValueError("Authentication failed: accessToken missing in response")

        # Encrypt and store the new token
        try:
            encrypted_token = fernet.encrypt(auth_token.encode()).decode()
            state["encrypted_token"] = encrypted_token
            state["token_ttl"] = current_time + token_expiry  # Store expiry timestamp
        except Exception as enc_error:
            print(f"⚠️ Token encryption failed: {enc_error}. Proceeding without storing.")

        return {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}, state

    except rq.exceptions.RequestException as e:
        raise RuntimeError(f"❌ Failed to authenticate: {e}")


def is_older_than_30_days(date_to_check):
    """
    Checks whether date_to_check is older than 30 days.
    Is time-zone aware and handles date_to_check being a string and not a datetime
    :param date_to_check:
    :return: boolean based on whether date is older than 30 days
    """
    now = datetime.now(timezone.utc)  # Timezone-aware UTC datetime

    # Convert to datetime if input is a string
    if isinstance(date_to_check, str):
        date_to_check = datetime.fromisoformat(date_to_check.replace("Z", "+00:00"))

    return date_to_check < now - timedelta(days=30)


def set_timeranges(state, configuration, start_timestamp):
    """
    Takes in current state and start timestamp of current sync.
    from_ts is always either the end of the last sync or the initialSyncStart found in the config file.
    If from_ts is more than 30 days ago, then set a to_ts that is 30 days later than from_ts.
    Otherwise, to_ts is the time that this sync was triggered.
    :param state:
    :param configuration:
    :param start_timestamp:
    :return: from_ts, to_ts
    """
    if "to_ts" in state:
        from_ts = state["to_ts"]
    else:
        from_ts = configuration["initialSyncStart"]

    if is_older_than_30_days(from_ts):  # Pass the string, since function handles conversion
        from_ts_dt = datetime.fromisoformat(from_ts.replace("Z", "+00:00"))
        to_ts = from_ts_dt + timedelta(days=30)
        to_ts = to_ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    else:
        to_ts = start_timestamp

    return from_ts, to_ts


def generate_business_dates(start_ts, end_ts):
    """
    Takes in start_date and end_date, and generates a list of dates in YYYYMMDD format that include those dates
    :param start_ts: ISO format datetime
    :param end_ts: ISO format datetime later than start_ts
    :return: list of YYYYMMDD dates between start_ts and end_ts, inclusive
    """

    # Replace 'Z' with '+00:00' to make it compatible with Python 3.10's fromisoformat()
    start_ts = start_ts.replace("Z", "+00:00")
    end_ts = end_ts.replace("Z", "+00:00")

    start_date = datetime.fromisoformat(start_ts)
    end_date = datetime.fromisoformat(end_ts)
    delta = end_date - start_date

    date_list = []
    for i in range(delta.days + 1):
        date_list.append((start_date + timedelta(days=i)).strftime("%Y%m%d"))

    return date_list


def get_api_response(endpoint_path, headers, **kwargs):
    """
    Sends an HTTP GET request to the provided URL with specified parameters.

    - Retries if a 401 Unauthorized response occurs (up to a limit).
    - Skips the endpoint if a 403 Forbidden response is received.
    - Handles rate-limiting (429) and retries accordingly.
    - Logs and returns API responses.

    :param endpoint_path: API URL
    :param headers: Request headers
    :param kwargs: Additional request parameters
    :return: Tuple (response JSON, next_page_token) or (None, None) if failed
    """
    timerange_data = kwargs.get("data", {})
    params = copy.deepcopy(kwargs.get("params", {}))

    max_retries_401 = 3  # Limit retries for 401 errors
    retry_count_401 = 0

    while True:
        response = rq.get(endpoint_path, headers=headers, data=timerange_data, params=params)

        # Handle 401 Unauthorized (retry up to max retries)
        if response.status_code == 401:
            if retry_count_401 >= max_retries_401:  # Fail after max retries
                log.error(f"401 Unauthorized - Max retries reached for {endpoint_path}")
                return None, None

            retry_count_401 += 1
            # reauth here?

            log.warning(f"401 Unauthorized - Retrying {retry_count_401}/{max_retries_401}")
            time.sleep(2)
            continue

        # Handle 403 Forbidden (Skip the endpoint)
        if response.status_code == 403:
            log.info(f"403 Forbidden - Skipping {endpoint_path}")
            raise PermissionError(f"403 Forbidden: Access denied to {endpoint_path}")

        # Handle 429 Too Many Requests
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            rate_limit_reset = response.headers.get("X-Toast-RateLimit-Reset")

            wait_time = None
            if retry_after:
                wait_time = int(retry_after)
            elif rate_limit_reset:
                try:
                    reset_time = int(rate_limit_reset)
                    wait_time = max(0, reset_time - int(time.time()))
                except ValueError:
                    log.warning(f"Invalid X-Toast-RateLimit-Reset value: {rate_limit_reset}")
                    wait_time = 5  # Fallback wait time

            if wait_time:
                log.info(f"Rate limit exceeded. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue  # Retry request

        # Handle 409 Conflict: Retry without pageToken
        if response.status_code == 409:
            params.pop("pageToken", None)
            log.info(f"Received 409 error, retrying {endpoint_path} without pageToken")
            continue  # Retry without pageToken

        # Handle 400 Bad Request
        if response.status_code == 400:
            log.info(f"Bad request: {response.json().get('message')}")
            return None, None

        response.raise_for_status()  # Raise error for unexpected HTTP issues

        response_page = response.json()
        response_headers = response.headers
        next_page_token = response_headers.get("Toast-Next-Page-Token")

        return response_page, next_page_token  # Return successful response


def stringify_lists(d):
    """
    The stringify_lists function changes lists to strings
    :param d: any dictionary
    :return: the dictionary with lists represented as strings
    """
    new_dict = {}
    for key, value in d.items():
        if isinstance(value, list):
            new_dict[key] = str(value)
        else:
            new_dict[key] = value
    return new_dict


def flatten_dict(parent_row: dict, dict_field: dict, prefix: str):
    """
    Flattens a field containing a dictionary into a series of fields prefixed with the original field name
    Optionally leaves off prefix for specified fields
    :param parent_row: a dictionary containing a key whose value is a dictionary
    :param dict_field: the key whose value is a dictionary
    :param prefix: the prefix to add to the name of keys in dict_field to make new keys in parent_row
    :return: parent_row with dict_field flattened into multiple fields
    """
    # dicts in these fields have unique enough names that they do not need the field prefix
    fields_to_not_prefix = ["refundDetails", "jobReference"]

    if not dict_field:  # Quick exit for empty dictionaries
        return parent_row

    dict_field = replace_guid_with_id(dict_field)
    for key, value in dict_field.items():
        if key.startswith(prefix):
            new_key = key  # Keep it unchanged
        elif key == "tipRefundAmount" and prefix == "refund":
            new_key = "refund_tip_amount"
        elif prefix in fields_to_not_prefix:
            new_key = key  # Keep it unchanged for exempted fields
        else:
            new_key = f"{prefix}_{key}"  # Build the new flattened key

        if isinstance(value, dict):  # If the value is another dictionary, recurse
            flatten_dict(parent_row, value, new_key)
        else:
            parent_row[new_key] = value  # Store the value directly if not a dictionary

    return parent_row


def replace_guid_with_id(d: dict):
    if "guid" in d:
        d["id"] = d.pop("guid")
    return d


def flatten_fields(fields: list, row: dict):
    """
    Takes in a list of fields to flatten within a row, calls flatten_dict() if any of those fields are present
    :param fields: a list of strings which could be keys in "row"
    :param row: a dictionary "row" that could have values that are dictionaries
    :return: dictionary with dictionary values flattened, if their keys are in "fields". The original keys are removed.
    """
    row = {**row}  # Ensures row modifications don't affect the original dictionary
    row = replace_guid_with_id(row)
    for field in fields:
        value = row.get(field)  # Avoids multiple dictionary lookups
        if value is not None:
            row = flatten_dict(row, value, field)
        row.pop(field, None)  # Remove the field in a single step

    return row


def extract_fields(fields: list, row: dict):
    """
    Takes in a list of fields and sub-fields within a row.
    Returns the row with sub-field extracted and field popped.
    Used instead of flatten_fields() in cases where a value has a dict with more than one key,
    but we only want one of the keys.
    :param fields: a list of tuples indicating the keys to extract and the name of the new key.
    :param row: a dictionary "row" with keys that have keys that we need to extract
    :return: dictionary with new keys, if their keys have keys that are in "fields". The original keys are removed.
    """
    row = {**row}

    for field, sub_field, new_name in fields:
        if row.get(field) and sub_field in row[field]:
            row[new_name] = row[field][sub_field]
            row.pop(field, None)

    return row


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    :param configuration: a dictionary that holds the configuration settings for the connector.
    :return: a list of tables with primary keys and any datatypes that we want to specify
    """
    if "key" not in configuration:
        raise ValueError("Could not find 'key' in configs")

    return [
        {"table": "restaurant", "primary_key": ["id"]},
        # labor tables
        {
            "table": "job",
            "primary_key": ["id"],
            "columns": {
                "createdDate": "UTC_DATETIME",
                "deletedDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "deleted": "BOOLEAN",
                "excludeFromReporting": "BOOLEAN",
                "tipped": "BOOLEAN",
            },
        },
        {
            "table": "shift",
            "primary_key": ["id"],
            "columns": {
                "createdDate": "UTC_DATETIME",
                "inDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "outDate": "UTC_DATETIME",
                "deleted": "BOOLEAN",
            },
        },
        {
            "table": "employee",
            "primary_key": ["id"],
            "columns": {
                "createdDate": "UTC_DATETIME",
                "deletedDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "deleted": "BOOLEAN",
            },
        },
        {"table": "employee_job_reference", "primary_key": ["id", "employee_id"]},
        {"table": "employee_wage_override", "primary_key": ["id", "employee_id"]},
        {
            "table": "time_entry",
            "primary_key": ["id"],
            "columns": {
                "createdDate": "UTC_DATETIME",
                "deletedDate": "UTC_DATETIME",
                "inDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "outDate": "UTC_DATETIME",
                "autoClockedOut": "BOOLEAN",
                "deleted": "BOOLEAN",
            },
        },
        {
            "table": "break",
            "primary_key": ["id"],
            "columns": {
                "inDate": "UTC_DATETIME",
                "outDate": "UTC_DATETIME",
                "auditResponse": "BOOLEAN",
                "missed": "BOOLEAN",
            },
        },
        # cash tables
        {"table": "cash_deposit", "primary_key": ["id"], "columns": {"date": "UTC_DATETIME"}},
        {"table": "cash_entry", "primary_key": ["id"], "columns": {"date": "UTC_DATETIME"}},
        # config tables
        {"table": "alternate_payment_types", "primary_key": ["id"]},
        {"table": "dining_option", "primary_key": ["id"], "columns": {"curbside": "BOOLEAN"}},
        {
            "table": "discounts",
            "primary_key": ["id"],
            "columns": {"active": "BOOLEAN", "nonExclusive": "BOOLEAN"},
        },
        {"table": "menu", "primary_key": ["id"]},
        {"table": "menu_group", "primary_key": ["id"]},
        {
            "table": "menu_item",
            "primary_key": ["id"],
            "columns": {"inheritOptionGroups": "BOOLEAN", "inheritUnitOfMeasure": "BOOLEAN"},
        },
        {"table": "restaurant_service", "primary_key": ["id"]},
        {"table": "revenue_center", "primary_key": ["id"]},
        {"table": "sale_category", "primary_key": ["id"]},
        {"table": "service_area", "primary_key": ["id"]},
        {"table": "tables", "primary_key": ["id"]},
        # orders tables
        {
            "table": "orders",
            "primary_key": ["id"],
            "columns": {
                "closedDate": "UTC_DATETIME",
                "createdDate": "UTC_DATETIME",
                "deletedDate": "UTC_DATETIME",
                "estimatedFulfillmentDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "openedDate": "UTC_DATETIME",
                "paidDate": "UTC_DATETIME",
                "promisedDate": "UTC_DATETIME",
                "voidDate": "UTC_DATETIME",
                "createdInTestMode": "BOOLEAN",
                "deleted": "BOOLEAN",
                "excessFood": "BOOLEAN",
                "voided": "BOOLEAN",
            },
        },
        {
            "table": "orders_check",
            "primary_key": ["id"],
            "columns": {
                "closedDate": "UTC_DATETIME",
                "createdDate": "UTC_DATETIME",
                "deletedDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "openedDate": "UTC_DATETIME",
                "paidDate": "UTC_DATETIME",
                "voidDate": "UTC_DATETIME",
                "deleted": "BOOLEAN",
                "taxExempt": "BOOLEAN",
                "voided": "BOOLEAN",
            },
        },
        {"table": "orders_check_applied_discount", "primary_key": ["id"]},
        {"table": "orders_check_applied_discount_combo_item", "primary_key": ["id"]},
        {
            "table": "orders_check_applied_discount_trigger",
            "primary_key": ["orders_check_applied_discount_id"],
        },
        {
            "table": "orders_check_applied_service_charge",
            "primary_key": ["id", "orders_check_id"],
            "columns": {
                "delivery": "BOOLEAN",
                "dineIn": "BOOLEAN",
                "gratuity": "BOOLEAN",
                "takeout": "BOOLEAN",
                "taxable": "BOOLEAN",
            },
        },
        {
            "table": "orders_check_payment",
            "primary_key": ["orders_check_id", "payment_id", "orders_guid"],
        },
        {
            "table": "orders_check_selection",
            "primary_key": ["id", "orders_check_id"],
            "columns": {
                "createdDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "voidDate": "UTC_DATETIME",
                "deferred": "BOOLEAN",
                "voided": "BOOLEAN",
            },
        },
        {"table": "orders_check_selection_applied_discount", "primary_key": ["id"]},
        {
            "table": "orders_check_selection_applied_discount_trigger",
            "primary_key": ["orders_check_selection_applied_discount_id"],
        },
        {
            "table": "orders_check_selection_applied_tax",
            "primary_key": ["id", "orders_check_selection_id"],
        },
        {
            "table": "orders_check_selection_modifier",
            "primary_key": ["id", "orders_check_selection_id"],
            "columns": {
                "createdDate": "UTC_DATETIME",
                "modifiedDate": "UTC_DATETIME",
                "voidDate": "UTC_DATETIME",
                "deferred": "BOOLEAN",
            },
        },
        {"table": "orders_pricing_feature", "primary_key": ["orders_id"]},
        {
            "table": "payment",
            "primary_key": ["id"],
            "columns": {
                "paidDate": "UTC_DATETIME",
                "refundDate": "UTC_DATETIME",
                "void_info_date": "UTC_DATETIME",
            },
        },
    ]


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "main":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
