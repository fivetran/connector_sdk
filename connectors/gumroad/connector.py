"""Gumroad Connector for Fivetran Connector SDK.
This connector fetches sales, products, and subscriber data from the Gumroad API and syncs it to the destination.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For date manipulation and timestamp handling
from datetime import datetime

# For implementing retry delays with exponential backoff
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to the Gumroad API (pre-installed in Fivetran environment)
import requests

# Maximum number of retry attempts for API requests
__MAX_RETRIES = 3

# Base delay in seconds for exponential backoff
__BASE_DELAY_SECONDS = 1

# Checkpoint interval for large datasets (number of records)
__CHECKPOINT_INTERVAL = 100

# Gumroad API base URL
__API_BASE_URL = "https://api.gumroad.com/v2"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector
    has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["access_token"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "sales", "primary_key": ["id"]},
        {"table": "products", "primary_key": ["id"]},
        {"table": "subscribers", "primary_key": ["id"]},
        {
            "table": "product_variants",
            "primary_key": ["product_id", "variant_title", "option_name"],
        },
        {"table": "payouts", "primary_key": ["id"]},
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.info("Starting Gumroad data sync")

    validate_configuration(configuration=configuration)

    access_token = configuration.get("access_token")

    sync_sales(access_token=access_token, state=state)
    sync_products(access_token=access_token, state=state)
    sync_subscribers(access_token=access_token, state=state)
    sync_payouts(access_token=access_token, state=state)


def sync_sales(access_token: str, state: dict):
    """
    Sync sales data from Gumroad API with incremental updates based on created_at timestamp.
    Args:
        access_token: The API access token for authentication.
        state: The state dictionary containing the last sync timestamp.
    """
    last_sales_sync = state.get("last_sales_sync")
    current_sync_time = datetime.utcnow().isoformat()

    params = {"access_token": access_token}
    if last_sales_sync:
        params["after"] = last_sales_sync[:10]

    page_key = None
    records_processed = 0

    while True:
        if page_key:
            params["page_key"] = page_key

        response_data = make_api_request(endpoint="/sales", params=params)

        if not response_data.get("success"):
            log.error(f"Failed to fetch sales: {response_data}")
            break

        sales = response_data.get("sales", [])
        if not sales:
            log.info("No sales data available")
            break

        for sale in sales:
            flattened_sale = flatten_sale(sale)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="sales", data=flattened_sale)

            records_processed += 1

            if records_processed % __CHECKPOINT_INTERVAL == 0:
                state["last_sales_sync"] = current_sync_time
                # Save the progress by checkpointing the state. This is important for ensuring
                # that the sync process can resume from the correct position in case of next
                # sync or interruptions. Learn more about how and where to checkpoint by reading
                # our best practices documentation (https://fivetran.com/docs/connectors/
                # connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)
                log.info(f"Checkpointed after processing {records_processed} sales records")

        page_key = response_data.get("next_page_key")
        if not page_key:
            break

    state["last_sales_sync"] = current_sync_time
    # Save the progress by checkpointing the state. This is important for ensuring
    # that the sync process can resume from the correct position in case of next
    # sync or interruptions. Learn more about how and where to checkpoint by reading
    # our best practices documentation (https://fivetran.com/docs/connectors/
    # connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)
    log.info(f"Completed sales sync with {records_processed} records")


def sync_products(access_token: str, state: dict):
    """
    Sync products data from Gumroad API.
    Args:
        access_token: The API access token for authentication.
        state: The state dictionary for tracking sync progress.
    """
    params = {"access_token": access_token}

    response_data = make_api_request(endpoint="/products", params=params)

    if not response_data.get("success"):
        log.error(f"Failed to fetch products: {response_data}")
        return

    products = response_data.get("products", [])
    if not products:
        log.info("No products data available")
        return

    records_processed = 0
    for product in products:
        flattened_product = flatten_product(product)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="products", data=flattened_product)

        process_product_variants(product)

        records_processed += 1

    log.info(f"Completed products sync with {records_processed} records")


def sync_subscribers(access_token: str, state: dict):
    """
    Sync subscribers data for all products from Gumroad API.
    Args:
        access_token: The API access token for authentication.
        state: The state dictionary for tracking sync progress.
    """
    products_params = {"access_token": access_token}
    products_response = make_api_request(endpoint="/products", params=products_params)

    if not products_response.get("success"):
        log.error(f"Failed to fetch products for subscribers sync: {products_response}")
        return

    products = products_response.get("products", [])
    if not products:
        log.info("No products available for subscriber sync")
        return

    total_subscribers = 0
    for product in products:
        product_id = product.get("id")
        if not product_id:
            continue

        total_subscribers += fetch_product_subscribers(
            access_token=access_token, product_id=product_id
        )

    log.info(f"Completed subscribers sync with {total_subscribers} records")


def sync_payouts(access_token: str, state: dict):
    """
    Sync payouts data from Gumroad API with incremental updates based on created_at timestamp.
    Args:
        access_token: The API access token for authentication.
        state: The state dictionary containing the last sync timestamp.
    """
    last_payouts_sync = state.get("last_payouts_sync")
    current_sync_time = datetime.utcnow().isoformat()

    params = {"access_token": access_token, "include_upcoming": "true"}
    if last_payouts_sync:
        params["after"] = last_payouts_sync[:10]

    page_key = None
    records_processed = 0

    while True:
        if page_key:
            params["page_key"] = page_key

        response_data = make_api_request(endpoint="/payouts", params=params)

        if not response_data.get("success"):
            log.error(f"Failed to fetch payouts: {response_data}")
            break

        payouts = response_data.get("payouts", [])
        if not payouts:
            log.info("No payouts data available")
            break

        for payout in payouts:
            flattened_payout = flatten_payout(payout)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="payouts", data=flattened_payout)

            records_processed += 1

            if records_processed % __CHECKPOINT_INTERVAL == 0:
                state["last_payouts_sync"] = current_sync_time
                # Save the progress by checkpointing the state. This is important for ensuring
                # that the sync process can resume from the correct position in case of next
                # sync or interruptions. Learn more about how and where to checkpoint by reading
                # our best practices documentation (https://fivetran.com/docs/connectors/
                # connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)
                log.info(f"Checkpointed after processing {records_processed} payouts records")

        page_key = response_data.get("next_page_key")
        if not page_key:
            break

    state["last_payouts_sync"] = current_sync_time
    # Save the progress by checkpointing the state. This is important for ensuring
    # that the sync process can resume from the correct position in case of next
    # sync or interruptions. Learn more about how and where to checkpoint by reading
    # our best practices documentation (https://fivetran.com/docs/connectors/
    # connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)
    log.info(f"Completed payouts sync with {records_processed} records")


def fetch_product_subscribers(access_token: str, product_id: str) -> int:
    """
    Fetch all subscribers for a specific product with pagination support.
    Args:
        access_token: The API access token for authentication.
        product_id: The product ID to fetch subscribers for.
    Returns:
        The number of subscribers processed for this product.
    """
    params = {"access_token": access_token, "paginated": "true"}

    page_key = None
    subscribers_count = 0

    while True:
        if page_key:
            params["page_key"] = page_key

        response_data = make_api_request(
            endpoint=f"/products/{product_id}/subscribers", params=params
        )

        if not response_data.get("success"):
            log.warning(f"Failed to fetch subscribers for product {product_id}: {response_data}")
            break

        subscribers = response_data.get("subscribers", [])
        if not subscribers:
            break

        for subscriber in subscribers:
            flattened_subscriber = flatten_subscriber(subscriber)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="subscribers", data=flattened_subscriber)

            subscribers_count += 1

        page_key = response_data.get("next_page_key")
        if not page_key:
            break

    return subscribers_count


def process_product_variants(product: dict):
    """
    Process and upsert product variants as separate records.
    Args:
        product: The product dictionary containing variants data.
    """
    product_id = product.get("id")
    variants = product.get("variants", [])

    if not variants or not isinstance(variants, list):
        return

    for variant in variants:
        variant_title = variant.get("title")
        options = variant.get("options", [])

        if not isinstance(options, list):
            continue

        for option in options:
            variant_record = {
                "product_id": product_id,
                "variant_title": variant_title,
                "option_name": option.get("name"),
                "price_difference": option.get("price_difference"),
                "is_pay_what_you_want": option.get("is_pay_what_you_want"),
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="product_variants", data=variant_record)


def flatten_sale(sale: dict) -> dict:
    """
    Flatten a sale record by extracting nested objects into top-level fields.
    Args:
        sale: The sale dictionary from the API response.
    Returns:
        A flattened dictionary with nested objects promoted to top-level fields.
    """
    flattened = {
        "id": sale.get("id"),
        "email": sale.get("email"),
        "seller_id": sale.get("seller_id"),
        "timestamp": sale.get("timestamp"),
        "daystamp": sale.get("daystamp"),
        "created_at": sale.get("created_at"),
        "product_name": sale.get("product_name"),
        "product_has_variants": sale.get("product_has_variants"),
        "price": sale.get("price"),
        "gumroad_fee": sale.get("gumroad_fee"),
        "subscription_duration": sale.get("subscription_duration"),
        "formatted_display_price": sale.get("formatted_display_price"),
        "formatted_total_price": sale.get("formatted_total_price"),
        "currency_symbol": sale.get("currency_symbol"),
        "amount_refundable_in_currency": sale.get("amount_refundable_in_currency"),
        "product_id": sale.get("product_id"),
        "product_permalink": sale.get("product_permalink"),
        "partially_refunded": sale.get("partially_refunded"),
        "chargedback": sale.get("chargedback"),
        "purchase_email": sale.get("purchase_email"),
        "zip_code": sale.get("zip_code"),
        "paid": sale.get("paid"),
        "has_variants": sale.get("has_variants"),
        "variants": json.dumps(sale.get("variants")) if sale.get("variants") else None,
        "variants_and_quantity": sale.get("variants_and_quantity"),
        "has_custom_fields": sale.get("has_custom_fields"),
        "custom_fields": (
            json.dumps(sale.get("custom_fields")) if sale.get("custom_fields") else None
        ),
        "order_id": sale.get("order_id"),
        "is_product_physical": sale.get("is_product_physical"),
        "purchaser_id": sale.get("purchaser_id"),
        "is_recurring_billing": sale.get("is_recurring_billing"),
        "can_contact": sale.get("can_contact"),
        "is_following": sale.get("is_following"),
        "disputed": sale.get("disputed"),
        "dispute_won": sale.get("dispute_won"),
        "is_additional_contribution": sale.get("is_additional_contribution"),
        "discover_fee_charged": sale.get("discover_fee_charged"),
        "is_gift_sender_purchase": sale.get("is_gift_sender_purchase"),
        "is_gift_receiver_purchase": sale.get("is_gift_receiver_purchase"),
        "referrer": sale.get("referrer"),
        "product_rating": sale.get("product_rating"),
        "reviews_count": sale.get("reviews_count"),
        "average_rating": sale.get("average_rating"),
        "subscription_id": sale.get("subscription_id"),
        "cancelled": sale.get("cancelled"),
        "ended": sale.get("ended"),
        "recurring_charge": sale.get("recurring_charge"),
        "license_key": sale.get("license_key"),
        "license_id": sale.get("license_id"),
        "license_disabled": sale.get("license_disabled"),
        "quantity": sale.get("quantity"),
    }

    card = sale.get("card", {})
    if card and isinstance(card, dict):
        flattened["card_visual"] = card.get("visual")
        flattened["card_type"] = card.get("type")

    affiliate = sale.get("affiliate", {})
    if affiliate and isinstance(affiliate, dict):
        flattened["affiliate_email"] = affiliate.get("email")
        flattened["affiliate_amount"] = affiliate.get("amount")

    return flattened


def flatten_product(product: dict) -> dict:
    """
    Flatten a product record by extracting key fields and converting complex objects to JSON strings.
    Args:
        product: The product dictionary from the API response.
    Returns:
        A flattened dictionary suitable for database insertion.
    """
    flattened = {
        "id": product.get("id"),
        "name": product.get("name"),
        "custom_permalink": product.get("custom_permalink"),
        "custom_receipt": product.get("custom_receipt"),
        "custom_summary": product.get("custom_summary"),
        "custom_fields": (
            json.dumps(product.get("custom_fields")) if product.get("custom_fields") else None
        ),
        "customizable_price": product.get("customizable_price"),
        "description": product.get("description"),
        "deleted": product.get("deleted"),
        "max_purchase_count": product.get("max_purchase_count"),
        "preview_url": product.get("preview_url"),
        "require_shipping": product.get("require_shipping"),
        "subscription_duration": product.get("subscription_duration"),
        "published": product.get("published"),
        "url": product.get("url"),
        "price": product.get("price"),
        "purchasing_power_parity_prices": (
            json.dumps(product.get("purchasing_power_parity_prices"))
            if product.get("purchasing_power_parity_prices")
            else None
        ),
        "currency": product.get("currency"),
        "short_url": product.get("short_url"),
        "thumbnail_url": product.get("thumbnail_url"),
        "tags": json.dumps(product.get("tags")) if product.get("tags") else None,
        "formatted_price": product.get("formatted_price"),
        "file_info": json.dumps(product.get("file_info")) if product.get("file_info") else None,
        "sales_count": product.get("sales_count"),
        "sales_usd_cents": product.get("sales_usd_cents"),
        "is_tiered_membership": product.get("is_tiered_membership"),
        "recurrences": (
            json.dumps(product.get("recurrences")) if product.get("recurrences") else None
        ),
    }

    return flattened


def flatten_subscriber(subscriber: dict) -> dict:
    """
    Flatten a subscriber record by extracting key fields.
    Args:
        subscriber: The subscriber dictionary from the API response.
    Returns:
        A flattened dictionary suitable for database insertion.
    """
    flattened = {
        "id": subscriber.get("id"),
        "product_id": subscriber.get("product_id"),
        "product_name": subscriber.get("product_name"),
        "user_id": subscriber.get("user_id"),
        "user_email": subscriber.get("user_email"),
        "purchase_ids": (
            json.dumps(subscriber.get("purchase_ids")) if subscriber.get("purchase_ids") else None
        ),
        "created_at": subscriber.get("created_at"),
        "user_requested_cancellation_at": subscriber.get("user_requested_cancellation_at"),
        "charge_occurrence_count": subscriber.get("charge_occurrence_count"),
        "recurrence": subscriber.get("recurrence"),
        "cancelled_at": subscriber.get("cancelled_at"),
        "ended_at": subscriber.get("ended_at"),
        "failed_at": subscriber.get("failed_at"),
        "free_trial_ends_at": subscriber.get("free_trial_ends_at"),
        "license_key": subscriber.get("license_key"),
        "status": subscriber.get("status"),
    }

    return flattened


def flatten_payout(payout: dict) -> dict:
    """
    Flatten a payout record by extracting key fields.
    Args:
        payout: The payout dictionary from the API response.
    Returns:
        A flattened dictionary suitable for database insertion.
    """
    flattened = {
        "id": payout.get("id"),
        "amount": payout.get("amount"),
        "currency": payout.get("currency"),
        "status": payout.get("status"),
        "created_at": payout.get("created_at"),
        "processed_at": payout.get("processed_at"),
        "payment_processor": payout.get("payment_processor"),
        "bank_account_visual": payout.get("bank_account_visual"),
        "paypal_email": payout.get("paypal_email"),
    }

    return flattened


def should_retry_request(attempt: int, error_type: str, status_code=None) -> bool:
    """
    Determine if an API request should be retried based on the error type and attempt count.
    Args:
        attempt: The current attempt number (0-indexed).
        error_type: Type of error encountered (status_code, timeout, connection).
        status_code: HTTP status code if applicable.
    Returns:
        True if the request should be retried, False otherwise.
    """
    if attempt >= __MAX_RETRIES - 1:
        return False

    if error_type == "status_code":
        return status_code in [429, 500, 502, 503, 504]

    if error_type in ["timeout", "connection"]:
        return True

    return False


def handle_retry_delay(attempt: int, error_message: str):
    """
    Handle the retry delay with exponential backoff and logging.
    Args:
        attempt: The current attempt number (0-indexed).
        error_message: The error message to log.
    """
    delay = __BASE_DELAY_SECONDS * (2**attempt)
    log.warning(
        f"{error_message}, retrying in {delay} seconds " f"(attempt {attempt + 1}/{__MAX_RETRIES})"
    )
    time.sleep(delay)


def make_api_request(endpoint: str, params: dict) -> dict:
    """
    Make an API request to Gumroad with retry logic and exponential backoff.
    Args:
        endpoint: The API endpoint path to call.
        params: The query parameters to send with the request.
    Returns:
        The JSON response as a dictionary.
    Raises:
        RuntimeError: If the API request fails after all retry attempts.
    """
    url = f"{__API_BASE_URL}{endpoint}"

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                return response.json()

            if should_retry_request(attempt, "status_code", response.status_code):
                handle_retry_delay(attempt, f"Request failed with status {response.status_code}")
                continue

            # Non-retryable status code error
            log.error(
                f"API request failed with status {response.status_code}: " f"{response.text}"
            )
            raise RuntimeError(f"API request failed: {response.status_code} - {response.text}")

        except requests.Timeout as e:
            if should_retry_request(attempt, "timeout"):
                handle_retry_delay(attempt, "Request timeout")
                continue

            log.error(f"Request timeout after {__MAX_RETRIES} attempts")
            raise RuntimeError(f"Request timeout after {__MAX_RETRIES} attempts") from e

        except requests.ConnectionError as e:
            if should_retry_request(attempt, "connection"):
                handle_retry_delay(attempt, "Connection error")
                continue

            log.error(f"Connection error after {__MAX_RETRIES} attempts")
            raise RuntimeError(f"Connection error after {__MAX_RETRIES} attempts") from e

    return {}


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from
# the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called
# by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your
# connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
