"""This connector demonstrates how to fetch shipment data from Sendcloud API and upsert it into destination using requests library.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to Sendcloud API
import requests

# For encoding Basic Authentication credentials
import base64

# For handling timestamps and dates
from datetime import datetime, timezone

# For optional parameters in type hints
from typing import Optional

# For retry logic and exponential backoff
import time

# Constants for the Sendcloud API
__PRODUCTION_BASE_URL = "https://panel.sendcloud.sc/api/v3"
__MOCK_BASE_URL = "https://stoplight.io/mocks/sendcloud/sendcloud-public-api/475741403"
__SHIPMENTS_ENDPOINT = "/shipments"
__DEFAULT_PAGE_SIZE = 40
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__ERROR_LOG_MAX_LENGTH = 500
__REQUEST_TIMEOUT_SECONDS = 30


def get_base_url(configuration: dict) -> str:
    """
    Get the appropriate base URL based on configuration.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        The base URL to use for API requests.
    """
    use_mock_server_str = configuration.get("use_mock_server", "false")
    use_mock_server = use_mock_server_str.lower() == "true"
    return __MOCK_BASE_URL if use_mock_server else __PRODUCTION_BASE_URL


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    required_configs = ["username", "password", "start_date"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate start_date format
    try:
        datetime.fromisoformat(configuration["start_date"].replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("start_date must be in ISO 8601 format (e.g., 2023-01-01)")

    # Validate use_mock_server if provided
    if "use_mock_server" in configuration:
        use_mock_server_str = configuration["use_mock_server"]
        if use_mock_server_str.lower() not in ["true", "false"]:
            raise ValueError("use_mock_server must be 'true' or 'false'")


def get_auth_header(username: str, password: str) -> str:
    """
    Create Basic Authentication header for Sendcloud API.
    Args:
        username: API username
        password: API password
    Returns:
        Authorization header value
    """
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded_credentials}"


def decode_cursor(cursor: str) -> dict:
    """
    Decode a Base64 encoded cursor string into its parameters.
    Args:
        cursor: Base64 encoded cursor string
    Returns:
        Dictionary of cursor parameters

    Example:
        decode_cursor("cj0xJnA9MzAw")
        -> Decodes Base64 to "r=1&p=300"
        -> Returns: {"r": "1", "p": "300"}
    """
    try:
        decoded = base64.b64decode(cursor).decode()
        log.info(f"Decoded cursor: {cursor} -> {decoded}")

        # Parse the query string (e.g., "o=10&r=0&p=20")
        params = {}
        for param in decoded.split("&"):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = value
        return params
    except Exception as e:
        log.warning(f"Failed to decode cursor {cursor}: {e}")
        return {}


def encode_cursor(offset: int = 0, reverse: int = 0, position: int = 0) -> str:
    """
    Encode pagination parameters into a Base64 cursor string.
    Args:
        offset: Offset value
        reverse: Reverse flag (0 or 1)
        position: Position value
    Returns:
        Base64 encoded cursor string

    Example:
        encode_cursor(offset=10, reverse=1, position=300)
        -> Encodes "o=10&r=1&p=300" to Base64
        -> Returns: "bz0xMCZyPTEmcD0zMDA="
    """
    query_string = f"o={offset}&r={reverse}&p={position}"
    encoded = base64.b64encode(query_string.encode()).decode()
    log.info(f"Encoded cursor: {query_string} -> {encoded}")
    return encoded


def handle_http_error(error: requests.exceptions.HTTPError, attempt: int):
    """
    Handle HTTP errors with retry logic or fail-fast behavior.
    Args:
        error: The HTTP error that occurred.
        attempt: Current attempt number (0-indexed).
    Raises:
        RuntimeError: For permanent errors or after exhausting retries.
    """
    status_code = error.response.status_code

    # Fail fast for permanent errors
    if status_code in [400, 401, 403, 404]:
        log.error(f"API request failed with status {status_code}: {str(error)}")
        raise RuntimeError(f"Failed to fetch shipments: {str(error)}")

    # Handle retryable errors
    is_last_attempt = attempt >= __MAX_RETRIES - 1
    if is_last_attempt:
        log.error(
            f"Failed to fetch shipments after {__MAX_RETRIES} attempts. Status: {status_code}"
        )
        if error.response is not None:
            log.error(f"Response content: {error.response.text[:__ERROR_LOG_MAX_LENGTH]}")
        raise RuntimeError(
            f"API returned {status_code} after {__MAX_RETRIES} attempts: {str(error)}"
        )

    # Retry with exponential backoff
    delay = min(60, __BASE_DELAY_SECONDS * (2**attempt))
    log.warning(
        f"Request failed with status {status_code}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
    )
    time.sleep(delay)


def handle_network_error(error: Exception, attempt: int):
    """
    Handle network errors (timeout, connection) with retry logic.
    Args:
        error: The network error that occurred.
        attempt: Current attempt number (0-indexed).
    Raises:
        RuntimeError: After exhausting all retries.
    """
    is_last_attempt = attempt >= __MAX_RETRIES - 1
    if is_last_attempt:
        log.error(f"Failed to fetch shipments after {__MAX_RETRIES} attempts: {str(error)}")
        raise RuntimeError(f"Failed to fetch shipments: {str(error)}")

    # Retry with exponential backoff
    delay = min(60, __BASE_DELAY_SECONDS * (2**attempt))
    log.warning(
        f"Connection error, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
    )
    time.sleep(delay)


def fetch_shipments_page(
    username: str,
    password: str,
    base_url: str,
    updated_after: Optional[str] = None,
    cursor: Optional[str] = None,
) -> dict:
    """
    Fetch a single page of shipments from Sendcloud API with retry logic.
    Args:
        username: API username.
        password: API password.
        base_url: Base URL for the API (production or mock).
        updated_after: ISO timestamp to filter shipments updated after this time.
        cursor: Pagination cursor for next page.
    Returns:
        Response data from API.
    Raises:
        RuntimeError: If the API request fails after all retry attempts.
    """
    url = f"{base_url}{__SHIPMENTS_ENDPOINT}"
    headers = {"Authorization": get_auth_header(username, password), "Accept": "application/json"}

    params = {"page_size": __DEFAULT_PAGE_SIZE}
    if updated_after:
        params["updated_after"] = updated_after
    if cursor:
        params["cursor"] = cursor

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()

            json_response = response.json()
            log.info("Fetched data from API")

            # Log pagination information for debugging
            if "next_cursor" in json_response:
                log.info("API provided next_cursor")
            if "pagination" in json_response:
                log.info("API provided pagination info")

            return json_response

        except requests.exceptions.HTTPError as e:
            handle_http_error(e, attempt)

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            handle_network_error(e, attempt)

    # This should never be reached due to the exception handling above, but added for type safety
    raise RuntimeError("Failed to fetch shipments: Maximum retries exceeded")


def flatten_nested_object(parent_obj: dict, key: str, prefix: str = "") -> dict:
    """
    Helper function to flatten a nested object with optional prefix.
    Args:
        parent_obj: The parent dictionary containing the nested object
        key: The key of the nested object to flatten
        prefix: Optional prefix to add to flattened keys
    Returns:
        Dictionary with flattened key-value pairs
    """
    nested_obj = parent_obj.get(key, {})
    if not nested_obj:
        return {}

    flattened = {}
    for nested_key, value in nested_obj.items():
        flattened_key = f"{prefix}{nested_key}" if prefix else nested_key
        flattened[flattened_key] = value

    return flattened


def flatten_address(address_obj: dict, prefix: str) -> dict:
    """
    Helper function to flatten address objects with consistent field naming.
    Args:
        address_obj: The address dictionary to flatten
        prefix: Prefix for the flattened fields (e.g., "from_", "to_")
    Returns:
        Dictionary with flattened address fields
    """
    if not address_obj:
        return {}

    return {
        f"{prefix}name": address_obj.get("name"),
        f"{prefix}company_name": address_obj.get("company_name"),
        f"{prefix}address_line_1": address_obj.get("address_line_1"),
        f"{prefix}house_number": address_obj.get("house_number"),
        f"{prefix}address_line_2": address_obj.get("address_line_2"),
        f"{prefix}postal_code": address_obj.get("postal_code"),
        f"{prefix}city": address_obj.get("city"),
        f"{prefix}po_box": address_obj.get("po_box"),
        f"{prefix}state_province_code": address_obj.get("state_province_code"),
        f"{prefix}country_code": address_obj.get("country_code"),
        f"{prefix}email": address_obj.get("email"),
        f"{prefix}phone_number": address_obj.get("phone_number"),
    }


def flatten_price_object(price_obj: dict, prefix: str) -> dict:
    """
    Helper function to flatten price/currency objects.
    Args:
        price_obj: The price dictionary to flatten
        prefix: Prefix for the flattened fields
    Returns:
        Dictionary with flattened price fields
    """
    if not price_obj:
        return {}

    return {
        f"{prefix}value": price_obj.get("value"),
        f"{prefix}currency": price_obj.get("currency"),
    }


def flatten_customs_information(shipment: dict) -> dict:
    """
    Helper function to flatten customs information.
    Args:
        shipment: The shipment dictionary containing customs information
    Returns:
        Dictionary with flattened customs fields
    """
    customs = shipment.get("customs_information")
    if not customs:
        return {}

    flattened = {
        "customs_invoice_number": customs.get("invoice_number"),
        "customs_export_reason": customs.get("export_reason"),
        "customs_export_type": customs.get("export_type"),
        "customs_invoice_date": customs.get("invoice_date"),
        "customs_general_notes": customs.get("general_notes"),
    }

    # Flatten customs costs using helper function
    flattened.update(
        flatten_price_object(customs.get("discount_granted", {}), "customs_discount_")
    )
    flattened.update(flatten_price_object(customs.get("freight_costs", {}), "customs_freight_"))
    flattened.update(
        flatten_price_object(customs.get("insurance_costs", {}), "customs_insurance_")
    )
    flattened.update(flatten_price_object(customs.get("other_costs", {}), "customs_other_"))

    # Flatten importer of record
    importer = customs.get("importer_of_record", {})
    flattened.update(
        {
            "customs_importer_name": importer.get("name"),
            "customs_importer_email": importer.get("email"),
        }
    )

    return flattened


def flatten_shipment_data(shipment: dict) -> dict:
    """
    Flatten nested shipment data for the main shipments table using helper functions.
    Args:
        shipment: Raw shipment data from API
    Returns:
        Flattened shipment data
    """
    # Start with basic shipment fields
    flattened = {
        "id": shipment.get("id"),
        "order_number": shipment.get("order_number"),
        "reference": shipment.get("reference"),
        "external_reference_id": shipment.get("external_reference_id"),
        "brand_id": shipment.get("brand_id"),
    }

    # Flatten delivery dates
    flattened.update(flatten_nested_object(shipment, "delivery-dates", ""))

    # Flatten ship_with information
    ship_with = shipment.get("ship_with", {})
    flattened.update({"ship_with_type": ship_with.get("type")})
    flattened.update(flatten_nested_object(ship_with, "properties", ""))

    # Flatten total order price
    flattened.update(
        flatten_price_object(shipment.get("total_order_price", {}), "total_order_price_")
    )

    # Flatten addresses using helper function
    flattened.update(flatten_address(shipment.get("from_address", {}), "from_"))
    flattened.update(flatten_address(shipment.get("to_address", {}), "to_"))

    # Flatten customs information using helper function
    flattened.update(flatten_customs_information(shipment))

    return flattened


def process_parcel_documents(shipment_id: str, parcel_id: str, documents: list):
    """
    Process and upsert parcel documents to the parcel_document table.
    Args:
        shipment_id: The shipment ID foreign key.
        parcel_id: The parcel ID foreign key.
        documents: List of document dictionaries.
    """
    for document in documents:
        doc_data = {
            "shipment_id": shipment_id,
            "parcel_id": parcel_id,
            "document_type": document.get("type"),
            "link": document.get("link"),
            "size": document.get("size"),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="parcel_document", data=doc_data)


def process_parcel_items(shipment_id: str, parcel_id: str, parcel_items: list):
    """
    Process and upsert parcel items and their properties to breakout tables.
    Args:
        shipment_id: The shipment ID foreign key.
        parcel_id: The parcel ID foreign key.
        parcel_items: List of item dictionaries.
    """
    for item in parcel_items:
        # Flatten item weight and price
        item_weight = item.get("weight", {})
        item_price = item.get("price", {})

        item_data = {
            "shipment_id": shipment_id,
            "parcel_id": parcel_id,
            "item_sku": item.get("sku"),
            "item_id": item.get("item_id"),
            "item_description": item.get("description"),
            "item_quantity": item.get("quantity"),
            "item_weight_value": item_weight.get("value"),
            "item_weight_unit": item_weight.get("unit"),
            "item_price_value": item_price.get("value"),
            "item_price_currency": item_price.get("currency"),
            "item_hs_code": item.get("hs_code"),
            "item_origin_country": item.get("origin_country"),
            "item_product_id": item.get("product_id"),
            "item_mid_code": item.get("mid_code"),
            "item_material_content": item.get("material_content"),
            "item_intended_use": item.get("intended_use"),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="parcel_item", data=item_data)

        # Process item properties
        properties = item.get("properties", {})
        for prop_name, prop_value in properties.items():
            prop_data = {
                "shipment_id": shipment_id,
                "parcel_id": parcel_id,
                "item_sku": item.get("sku"),
                "item_id": item.get("item_id"),
                "property_name": prop_name,
                "property_value": str(
                    prop_value
                ),  # Convert to string to handle different data types
            }
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="item_property", data=prop_data)


def process_parcel_label_notes(shipment_id: str, parcel_id: str, label_notes: list):
    """
    Process and upsert parcel label notes to the parcel_label_note table.
    Args:
        shipment_id: The shipment ID foreign key.
        parcel_id: The parcel ID foreign key.
        label_notes: List of label note strings.
    """
    for i, note in enumerate(label_notes):
        note_data = {
            "shipment_id": shipment_id,
            "parcel_id": parcel_id,
            "note_order": i,
            "note_text": note,
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="parcel_label_note", data=note_data)


def process_single_parcel(shipment_id: str, parcel: dict):
    """
    Process a single parcel and all its related data (documents, items, notes).
    Args:
        shipment_id: The shipment ID foreign key.
        parcel: Single parcel dictionary from API.
    """
    parcel_id = parcel.get("id")

    parcel_data = {
        "shipment_id": shipment_id,
        "parcel_id": parcel_id,
        "created_at": parcel.get("created_at"),
        "updated_at": parcel.get("updated_at"),
        "announced_at": parcel.get("announced_at"),
        "tracking_number": parcel.get("tracking_number"),
        "tracking_url": parcel.get("tracking_url"),
    }

    # Flatten parcel status
    status = parcel.get("status", {})
    parcel_data.update(
        {"status_message": status.get("message"), "status_code": status.get("code")}
    )

    # Flatten parcel dimensions
    dimensions = parcel.get("dimensions", {})
    parcel_data.update(
        {
            "dimensions_length": dimensions.get("length"),
            "dimensions_width": dimensions.get("width"),
            "dimensions_height": dimensions.get("height"),
            "dimensions_unit": dimensions.get("unit"),
        }
    )

    # Flatten parcel weight
    weight = parcel.get("weight", {})
    parcel_data.update({"weight_value": weight.get("value"), "weight_unit": weight.get("unit")})

    # Flatten additional insured price
    insured_price = parcel.get("additional_insured_price", {})
    parcel_data.update(
        {
            "insured_price_value": insured_price.get("value"),
            "insured_price_currency": insured_price.get("currency"),
        }
    )

    # Flatten additional carrier data
    carrier_data = parcel.get("additional_carrier_data", {})
    parcel_data.update(
        {
            "awb_tracking_number": carrier_data.get("awb_tracking_number"),
            "box_number": carrier_data.get("box_number"),
        }
    )

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="shipment_parcel", data=parcel_data)

    # Process parcel's nested arrays
    process_parcel_documents(shipment_id, parcel_id, parcel.get("documents", []))
    process_parcel_items(shipment_id, parcel_id, parcel.get("parcel_items", []))
    process_parcel_label_notes(shipment_id, parcel_id, parcel.get("label_notes", []))


def process_customs_tax_numbers(shipment_id: str, tax_numbers: dict):
    """
    Process and upsert customs tax numbers for sender, receiver, and importer.
    Args:
        shipment_id: The shipment ID foreign key.
        tax_numbers: Dictionary containing sender, receiver, and importer tax numbers.
    """
    # Process sender tax numbers
    sender_taxes = tax_numbers.get("sender", [])
    for tax in sender_taxes:
        tax_data = {
            "shipment_id": shipment_id,
            "tax_type": "sender",
            "tax_name": tax.get("name"),
            "tax_country_code": tax.get("country_code"),
            "tax_number": tax.get("value"),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="customs_tax_number", data=tax_data)

    # Process receiver tax numbers
    receiver_taxes = tax_numbers.get("receiver", [])
    for tax in receiver_taxes:
        tax_data = {
            "shipment_id": shipment_id,
            "tax_type": "receiver",
            "tax_name": tax.get("name"),
            "tax_country_code": tax.get("country_code"),
            "tax_number": tax.get("value"),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="customs_tax_number", data=tax_data)

    # Process importer of record tax numbers
    importer_taxes = tax_numbers.get("importer_of_record", [])
    for tax in importer_taxes:
        tax_data = {
            "shipment_id": shipment_id,
            "tax_type": "importer_of_record",
            "tax_name": tax.get("name"),
            "tax_country_code": tax.get("country_code"),
            "tax_number": tax.get("value"),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="customs_tax_number", data=tax_data)


def process_customs_information(shipment_id: str, customs: dict):
    """
    Process and upsert customs declarations and tax numbers.
    Args:
        shipment_id: The shipment ID foreign key.
        customs: Customs information dictionary.
    """
    if not customs:
        return

    # Process customs declarations
    declarations = customs.get("additional_declaration_statements", [])
    for i, declaration in enumerate(declarations):
        decl_data = {
            "shipment_id": shipment_id,
            "declaration_sequence": i,
            "declaration_text": declaration,
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="customs_declaration", data=decl_data)

    # Process tax numbers
    tax_numbers = customs.get("tax_numbers", {})
    if tax_numbers:
        process_customs_tax_numbers(shipment_id, tax_numbers)


def process_shipment_arrays(shipment_id: str, shipment: dict):
    """
    Process array fields from shipment data and upsert to breakout tables.
    Args:
        shipment_id: The shipment ID to use as foreign key
        shipment: Raw shipment data from API
    """
    # Process parcels array
    parcels = shipment.get("parcels", [])
    for parcel in parcels:
        process_single_parcel(shipment_id, parcel)

    # Process shipment errors
    errors = shipment.get("errors", [])
    for error in errors:
        error_data = {
            "shipment_id": shipment_id,
            "error_id": error.get("id"),
            "error_status": error.get("status"),
            "error_code": error.get("code"),
            "error_title": error.get("title"),
            "error_detail": error.get("detail"),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="shipment_error", data=error_data)

    # Process customs information
    customs = shipment.get("customs_information", {})
    process_customs_information(shipment_id, customs)


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    return [
        {
            "table": "shipment",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
        },
        {
            "table": "shipment_parcel",
            "primary_key": ["shipment_id", "parcel_id"],
        },
        {
            "table": "shipment_error",
            "primary_key": ["shipment_id", "error_id"],
        },
        {
            "table": "parcel_document",
            "primary_key": ["shipment_id", "parcel_id", "document_type"],
        },
        {
            "table": "parcel_item",
            "primary_key": ["shipment_id", "parcel_id", "item_sku"],
        },
        {
            "table": "customs_declaration",
            "primary_key": ["shipment_id", "declaration_sequence"],
        },
        {
            "table": "customs_tax_number",
            "primary_key": ["shipment_id", "tax_type", "tax_name", "tax_country_code"],
        },
        {
            "table": "parcel_label_note",
            "primary_key": ["shipment_id", "parcel_id", "note_order"],
        },
        {
            "table": "item_property",
            "primary_key": ["shipment_id", "parcel_id", "item_sku", "property_name"],
        },
    ]


def normalize_shipments_response(shipments):
    """
    Normalize API response to ensure shipments is always a list.
    Args:
        shipments: Response data from API (can be list or dict).
    Returns:
        List of shipment dictionaries.
    """
    if isinstance(shipments, dict):
        log.info("Mock API returned single shipment object, wrapped in list")
        return [shipments]
    elif isinstance(shipments, list):
        return shipments
    else:
        log.warning(f"Unexpected data type: {type(shipments)}, returning empty list")
        return []


def process_single_shipment(shipment, index):
    """
    Process and upsert a single shipment with all its related data.
    Args:
        shipment: Single shipment dictionary from API.
        index: Index of the shipment in the batch for logging.
    Returns:
        Boolean indicating if shipment was processed successfully.
    """
    if not isinstance(shipment, dict):
        log.warning(f"Shipment {index} is not a dictionary, skipping")
        return False

    shipment_id = shipment.get("id")
    if not shipment_id:
        log.warning(f"Shipment {index} has no ID, skipping")
        return False

    # Flatten main shipment data for the primary table
    flattened_shipment = flatten_shipment_data(shipment)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="shipment", data=flattened_shipment)

    # Process array fields and upsert to breakout tables
    process_shipment_arrays(shipment_id, shipment)

    return True


def determine_next_cursor(response_data, shipments_count, page_count):
    """
    Determine if there are more pages and what the next cursor should be.
    Args:
        response_data: API response containing pagination metadata.
        shipments_count: Number of shipments in current page.
        page_count: Current page number.
    Returns:
        Tuple of (has_more_pages, next_cursor).
    """
    # Check for next_cursor in response
    next_cursor = response_data.get("next_cursor") or response_data.get("cursor")

    # Check for pagination metadata object
    pagination_info = response_data.get("pagination", {})
    has_more_from_pagination = pagination_info.get("has_more", False)
    next_cursor_from_pagination = pagination_info.get("next_cursor")

    # Use pagination metadata if available
    if next_cursor_from_pagination:
        next_cursor = next_cursor_from_pagination

    # Determine if there are more pages
    has_more_pages = bool(next_cursor) or has_more_from_pagination

    # Fallback: if no explicit pagination info and we got a full page, assume more pages exist
    if not next_cursor and not has_more_from_pagination and shipments_count == __DEFAULT_PAGE_SIZE:
        next_offset = page_count * __DEFAULT_PAGE_SIZE
        next_cursor = encode_cursor(offset=next_offset, reverse=0, position=next_offset)
        has_more_pages = True
        log.info(f"Generated cursor for next page: offset={next_offset}")

    return has_more_pages, next_cursor


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.info("Sendcloud Shipments Connector: Starting sync")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Extract configuration parameters
    username = configuration.get("username")
    password = configuration.get("password")
    start_date = configuration.get("start_date")
    base_url = get_base_url(configuration)

    # Log which server is being used
    use_mock_server_str = configuration.get("use_mock_server", "false")
    server_type = "mock" if use_mock_server_str.lower() == "true" else "production"
    log.info(f"Using {server_type} server: {base_url}")

    # For the first sync, use start_date from configuration
    # For subsequent syncs, use the cursor from state to continue from where we left off
    last_sync_cursor = state.get("cursor", start_date)
    current_time = datetime.now(timezone.utc).isoformat()

    cursor = None
    has_more_pages = True
    page_count = 0
    total_shipments_processed = 0

    log.info(f"Starting sync from cursor: {last_sync_cursor}")

    # Pagination logic: Continue fetching pages until no more data is available
    while has_more_pages:
        page_count += 1

        # Fetch a page of shipments from Sendcloud API
        response_data = fetch_shipments_page(
            username=username,
            password=password,
            base_url=base_url,
            updated_after=last_sync_cursor,
            cursor=cursor,
        )

        # Normalize response to always get a list of shipments
        shipments = normalize_shipments_response(response_data.get("data", []))

        if not shipments:
            log.info("No more shipments to process")
            break

        log.info(f"Processing {len(shipments)} shipments from page {page_count}")

        # Process each shipment
        for i, shipment in enumerate(shipments):
            if process_single_shipment(shipment, i):
                total_shipments_processed += 1

        # Determine pagination for next iteration
        has_more_pages, cursor = determine_next_cursor(response_data, len(shipments), page_count)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        if has_more_pages:
            intermediate_state = {"cursor": current_time}
            op.checkpoint(intermediate_state)

    log.info(
        f"Sync completed. Processed {total_shipments_processed} shipments across {page_count} pages"
    )

    # Update state with the current sync time for the next run
    new_state = {"cursor": current_time}

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(new_state)

    log.info(f"Sync completed successfully. Next sync will start from: {current_time}")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
