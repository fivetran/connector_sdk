"""Goshippo Connector for syncing shipment data from the Goshippo API.
This connector demonstrates how to fetch shipment data from Goshippo and upsert it into destination using the Fivetran Connector SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For time-related operations and delays
import time

# For parsing URL parameters during pagination
from urllib.parse import urlparse, parse_qs

# For making HTTP API requests
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__BASE_URL = "https://api.goshippo.com"
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 2
__REQUEST_TIMEOUT_SECONDS = 30
__CHECKPOINT_INTERVAL = 100
__PAGE_SIZE = 25


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "shipments", "primary_key": ["object_id"]},
        {"table": "shipment_rates", "primary_key": ["rate_object_id", "shipment_object_id"]},
        {"table": "shipment_parcels", "primary_key": ["parcel_object_id", "shipment_object_id"]},
        {"table": "shipment_messages", "primary_key": ["message_id"]},
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_token"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    # Validate configuration before proceeding
    validate_configuration(configuration)

    log.warning("Example: API Connector : Goshippo Shipments Connector")

    api_token = configuration.get("api_token")
    last_sync_time = state.get("last_sync_time")

    log.info(f"Starting sync with last_sync_time: {last_sync_time}")

    try:
        new_sync_time = sync_shipments(api_token, last_sync_time)

        # State checkpointing is handled within sync_shipments() after each batch/page and after the loop completes.
        # No additional checkpoint is needed here.

        log.info(f"Sync completed successfully. New sync time: {new_sync_time}")

    except (RuntimeError, requests.RequestException, ValueError, KeyError) as e:
        log.error(f"Failed to sync data: {str(e)}")
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def sync_shipments(api_token, last_sync_time):
    """
    Fetch shipments from Goshippo API with incremental sync support.
    Args:
        api_token: The API token for authentication.
        last_sync_time: ISO format timestamp to filter shipments updated after this time.
    Returns:
        str: The latest object_updated timestamp from synced shipments.
    """
    page_token = None
    has_more_data = True
    new_sync_time = last_sync_time
    records_processed = 0
    page_count = 0

    while has_more_data:
        page_count += 1
        log.info(f"Fetching page {page_count} of shipments")

        shipments_data = fetch_shipments_page(api_token, page_token)

        if not shipments_data or "results" not in shipments_data:
            log.warning("No shipments data returned from API")
            break

        results = shipments_data.get("results", [])

        if not results:
            log.info("No more shipments to process")
            break

        for shipment in results:
            shipment_updated = shipment.get("object_updated")

            # Client-side filtering for incremental sync since API doesn't support filtering
            if last_sync_time and shipment_updated and shipment_updated < last_sync_time:
                continue

            process_shipment(shipment)

            if shipment_updated and (new_sync_time is None or shipment_updated >= new_sync_time):
                new_sync_time = shipment_updated

            records_processed += 1

            if records_processed % __CHECKPOINT_INTERVAL == 0:
                checkpoint_state = {"last_sync_time": new_sync_time}
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(checkpoint_state)
                log.info(f"Checkpointed after processing {records_processed} records")

        next_url = shipments_data.get("next")
        if next_url:
            page_token = extract_page_token(next_url)
        has_more_data = bool(next_url)

    # Save the progress by checkpointing the state after the pagination loop completes.
    # This ensures that all progress is saved, even if the last batch is smaller than the checkpoint interval.
    if records_processed > 0 and records_processed % __CHECKPOINT_INTERVAL != 0:
        checkpoint_state = {"last_sync_time": new_sync_time}
        op.checkpoint(checkpoint_state)
        log.info(f"Final checkpoint after processing {records_processed} records")
    log.info(f"Total records processed: {records_processed}")
    return new_sync_time or last_sync_time


def fetch_shipments_page(api_token, page_token):
    """
    Fetch a single page of shipments from the Goshippo API with retry logic.
    Args:
        api_token: The API token for authentication.
        page_token: The page token for pagination (None for first page).
    Returns:
        dict: JSON response containing shipment data.
    """
    url = f"{__BASE_URL}/shipments"
    headers = build_headers(api_token)
    params = build_query_params(page_token)

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )
            handle_response_status(response, attempt)
            return response.json()

        except requests.HTTPError:
            # Retryable error - continue to next retry attempt
            continue
        except (requests.Timeout, requests.ConnectionError) as e:
            handle_request_exception(e, attempt)

    raise RuntimeError("Failed to fetch shipments after all retry attempts")


def handle_response_status(response, attempt):
    """
    Handle HTTP response status codes with retry logic for transient errors.
    Args:
        response: The HTTP response object.
        attempt: Current retry attempt number.
    Raises:
        requests.HTTPError: For retryable errors to trigger retry logic.
        RuntimeError: For non-retryable errors or after all retries exhausted.
    """
    if response.status_code == 200:
        return

    if response.status_code in [429, 500, 502, 503, 504]:
        if attempt < __MAX_RETRIES - 1:
            delay = calculate_retry_delay(attempt)
            log.warning(
                f"Request failed with status {response.status_code}, retrying in {delay}s (attempt {attempt + 1}/{__MAX_RETRIES})"
            )
            time.sleep(delay)
            # Raise an exception to trigger the retry logic in fetch_shipments_page
            raise requests.HTTPError(
                f"Transient error {response.status_code} on attempt {attempt + 1}"
            )
        else:
            error_message = (
                f"Failed after {__MAX_RETRIES} attempts. Status: {response.status_code}"
            )
            log.error(error_message)
            raise RuntimeError(error_message)
    else:
        error_message = f"API returned status {response.status_code}: {response.text}"
        log.error(error_message)
        raise RuntimeError(error_message)


def handle_request_exception(exception, attempt):
    """
    Handle request exceptions with retry logic.
    Args:
        exception: The exception that was raised.
        attempt: Current retry attempt number.
    """
    exception_name = type(exception).__name__
    if attempt < __MAX_RETRIES - 1:
        delay = calculate_retry_delay(attempt)
        log.warning(
            f"{exception_name}, retrying in {delay}s (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{exception_name} after {__MAX_RETRIES} attempts")
        raise


def process_shipment(shipment):
    """
    Process a single shipment and upsert it along with related data.
    Args:
        shipment: The shipment data dictionary.
    """
    shipment_record = flatten_shipment(shipment)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="shipments", data=shipment_record)

    rates = shipment.get("rates", [])
    process_rates(rates, shipment.get("object_id"))

    parcels = shipment.get("parcels", [])
    process_parcels(parcels, shipment.get("object_id"))

    messages = shipment.get("messages", [])
    process_messages(messages, shipment.get("object_id"))


def flatten_shipment(shipment):
    """
    Flatten shipment object for the main shipments table.
    Args:
        shipment: The shipment data dictionary.
    Returns:
        dict: Flattened shipment record.
    """
    flattened = {
        "object_id": shipment.get("object_id"),
        "object_created": shipment.get("object_created"),
        "object_updated": shipment.get("object_updated"),
        "object_owner": shipment.get("object_owner"),
        "status": shipment.get("status"),
        "metadata": shipment.get("metadata"),
        "shipment_date": shipment.get("shipment_date"),
        "test": shipment.get("test"),
        "order": shipment.get("order"),
        "carrier_accounts": (
            json.dumps(shipment.get("carrier_accounts", []))
            if shipment.get("carrier_accounts")
            else None
        ),
        "customs_declaration": shipment.get("customs_declaration"),
        "alternate_address_to": (
            json.dumps(shipment.get("alternate_address_to"))
            if shipment.get("alternate_address_to")
            else None
        ),
    }

    address_from = shipment.get("address_from", {})
    if isinstance(address_from, dict):
        flattened.update(
            {
                "from_name": address_from.get("name"),
                "from_company": address_from.get("company"),
                "from_street1": address_from.get("street1"),
                "from_city": address_from.get("city"),
                "from_state": address_from.get("state"),
                "from_zip": address_from.get("zip"),
                "from_country": address_from.get("country"),
                "from_phone": address_from.get("phone"),
                "from_email": address_from.get("email"),
            }
        )

    address_to = shipment.get("address_to", {})
    if isinstance(address_to, dict):
        flattened.update(
            {
                "to_name": address_to.get("name"),
                "to_company": address_to.get("company"),
                "to_street1": address_to.get("street1"),
                "to_city": address_to.get("city"),
                "to_state": address_to.get("state"),
                "to_zip": address_to.get("zip"),
                "to_country": address_to.get("country"),
                "to_phone": address_to.get("phone"),
                "to_email": address_to.get("email"),
            }
        )

    address_return = shipment.get("address_return", {})
    if isinstance(address_return, dict):
        flattened.update(
            {
                "return_name": address_return.get("name"),
                "return_company": address_return.get("company"),
                "return_street1": address_return.get("street1"),
                "return_city": address_return.get("city"),
                "return_state": address_return.get("state"),
                "return_zip": address_return.get("zip"),
                "return_country": address_return.get("country"),
                "return_phone": address_return.get("phone"),
                "return_email": address_return.get("email"),
            }
        )

    return flattened


def process_rates(rates, shipment_object_id):
    """
    Process and upsert shipment rates to the rates table.
    Args:
        rates: List of rate objects.
        shipment_object_id: The parent shipment object ID.
    """
    if not rates:
        return

    for rate in rates:
        if isinstance(rate, dict):
            rate_record = {
                "rate_object_id": rate.get("object_id"),
                "shipment_object_id": shipment_object_id,
                "amount": rate.get("amount"),
                "currency": rate.get("currency"),
                "provider": rate.get("provider"),
                "servicelevel_name": (
                    rate.get("servicelevel", {}).get("name")
                    if isinstance(rate.get("servicelevel"), dict)
                    else None
                ),
                "servicelevel_token": (
                    rate.get("servicelevel", {}).get("token")
                    if isinstance(rate.get("servicelevel"), dict)
                    else None
                ),
                "estimated_days": rate.get("estimated_days"),
                "duration_terms": rate.get("duration_terms"),
                "carrier_account": rate.get("carrier_account"),
                "object_created": rate.get("object_created"),
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="shipment_rates", data=rate_record)


def process_parcels(parcels, shipment_object_id):
    """
    Process and upsert shipment parcels to the parcels table.
    Args:
        parcels: List of parcel objects.
        shipment_object_id: The parent shipment object ID.
    """
    if not parcels:
        return

    for parcel in parcels:
        if isinstance(parcel, dict):
            parcel_record = {
                "parcel_object_id": parcel.get("object_id"),
                "shipment_object_id": shipment_object_id,
                "length": parcel.get("length"),
                "width": parcel.get("width"),
                "height": parcel.get("height"),
                "distance_unit": parcel.get("distance_unit"),
                "weight": parcel.get("weight"),
                "mass_unit": parcel.get("mass_unit"),
                "metadata": parcel.get("metadata"),
                "object_created": parcel.get("object_created"),
                "object_updated": parcel.get("object_updated"),
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="shipment_parcels", data=parcel_record)


def process_messages(messages, shipment_object_id):
    """
    Process and upsert shipment messages to the messages table.
    Args:
        messages: List of message objects.
        shipment_object_id: The parent shipment object ID.
    """
    if not messages:
        return

    for idx, message in enumerate(messages):
        if isinstance(message, dict):
            # Generate a unique message ID by combining shipment ID and index
            message_id = f"{shipment_object_id}_{idx}"

            message_record = {
                "message_id": message_id,
                "shipment_object_id": shipment_object_id,
                "source": message.get("source"),
                "code": message.get("code"),
                "text": message.get("text"),
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="shipment_messages", data=message_record)


def build_headers(api_token):
    """
    Build HTTP headers for Goshippo API requests.
    Args:
        api_token: The API token for authentication.
    Returns:
        dict: HTTP headers dictionary.
    """
    return {
        "Authorization": f"ShippoToken {api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def build_query_params(page_token):
    """
    Build query parameters for API requests.
    Args:
        page_token: The page token for pagination (None for first page).
    Returns:
        dict: Query parameters dictionary.
    """
    params = {"results": __PAGE_SIZE}

    if page_token:
        params["page_token"] = page_token

    return params


def extract_page_token(next_url):
    """
    Extract the page_token parameter from the next URL.
    Args:
        next_url: The URL containing the page_token parameter.
    Returns:
        str: The page token value or None.
    """
    if not next_url:
        return None

    try:
        parsed = urlparse(next_url)
        params = parse_qs(parsed.query)
        return params.get("page_token", [None])[0]
    except (ValueError, AttributeError, IndexError, TypeError) as e:
        log.warning(f"Failed to extract page_token from URL: {str(e)}")
        return None


def calculate_retry_delay(attempt):
    """
    Calculate exponential backoff delay for retry attempts.
    Args:
        attempt: The current attempt number (0-indexed).
    Returns:
        int: Delay in seconds.
    """
    return min(60, __BASE_DELAY_SECONDS * (2**attempt))


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
