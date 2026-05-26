"""This connector fetches location configuration and program metadata from Partech (Punchh) POS API.
See the Technical Reference documentation:
https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
See the Best Practices documentation:
https://fivetran.com/docs/connectors/connector-sdk/best-practices
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to Partech API
import requests

# For exponential backoff retry logic
from time import sleep

# Maximum number of retry attempts for API calls
__MAX_RETRIES = 3

# Initial delay in seconds for exponential backoff
__INITIAL_BACKOFF = 1


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
            "table": "location_configuration",
            "primary_key": ["location_id"],
        },
        {
            "table": "program_meta",
            "primary_key": ["program_type"],
        },
        {
            "table": "redeemable",
            "primary_key": ["program_type", "redeemable_id"],
        },
        {
            "table": "processing_priority_by_acquisition_type",
            "primary_key": ["program_type", "code"],
        },
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

    log.warning("Example: Source Connector: Partech (Punchh) POS API")

    base_url = configuration.get("base_url")
    location_key = configuration.get("location_key")
    business_key = configuration.get("business_key")

    try:
        sync_location_configuration(base_url, location_key, business_key)
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process
        # can resume from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        sync_program_meta(base_url, location_key, business_key, state)
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process
        # can resume from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP error occurred: {e}")
        raise
    except requests.exceptions.RequestException as e:
        log.error(f"Request error occurred: {e}")
        raise
    except Exception as e:
        log.error(f"Unexpected error occurred: {e}")
        raise


def sync_location_configuration(base_url, location_key, business_key):
    """
    Fetch location configuration from Partech API and upsert into destination.
    Args:
        base_url: The base URL of the Partech API
        location_key: The location API key
        business_key: The business key
    """
    endpoint = f"{base_url}/api/pos/locations/configuration"
    data = make_api_request(endpoint, location_key, business_key)

    if data:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="location_configuration", data=data)
        log.info(f"Synced location configuration for location_id: {data.get('location_id')}")


def sync_program_meta(base_url, location_key, business_key, state):
    """
    Fetch program metadata from Partech API and upsert into destination.
    Handles nested structures by flattening single objects and creating separate tables for arrays.
    Args:
        base_url: The base URL of the Partech API
        location_key: The location API key
        business_key: The business key
        state: The state dictionary to track sync progress
    """
    endpoint = f"{base_url}/api/pos/meta"
    data = make_api_request(endpoint, location_key, business_key)

    if not data:
        return

    # Extract and process nested data
    program_type = data.get("program_type")
    redeemables = data.pop("redeemables", [])
    multiple_redemptions = data.pop("multiple_redemptions", {})
    processing_priority = multiple_redemptions.pop("processing_priority_by_acquisition_type", [])

    # Flatten multiple_redemptions data
    flatten_multiple_redemptions(data, multiple_redemptions)

    # Upsert main program_meta table
    upsert_program_meta(data, program_type)

    # Upsert child tables
    upsert_redeemables(redeemables, program_type)
    upsert_processing_priority(processing_priority, program_type)


def flatten_multiple_redemptions(data, multiple_redemptions):
    """
    Flatten multiple_redemptions nested object into the main data dictionary.
    Converts arrays to comma-separated strings and adds prefixed fields.
    Args:
        data: The main program_meta data dictionary to update
        multiple_redemptions: The nested multiple_redemptions object
    """
    # Convert simple arrays to comma-separated strings
    auto_redemption = multiple_redemptions.pop("auto_redemption_discounts", [])
    data["auto_redemption_discounts"] = ",".join(str(x) for x in auto_redemption)

    priority_discount = multiple_redemptions.pop("processing_priority_by_discount_type", [])
    data["processing_priority_by_discount_type"] = ",".join(str(x) for x in priority_discount)

    interop_strategy = multiple_redemptions.pop("exclude_interoperability_strategy_between", [])
    data["exclude_interoperability_strategy_between"] = ",".join(str(x) for x in interop_strategy)

    # Flatten remaining fields with prefix
    for key, value in multiple_redemptions.items():
        data[f"multiple_redemptions_{key}"] = value


def upsert_program_meta(data, program_type):
    """
    Upsert program metadata into the program_meta table.
    Args:
        data: The program metadata dictionary
        program_type: The program type identifier
    """
    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="program_meta", data=data)
    log.info(f"Synced program metadata for program_type: {program_type}")


def upsert_redeemables(redeemables, program_type):
    """
    Upsert redeemables into the redeemable table with parent foreign key.
    Args:
        redeemables: List of redeemable dictionaries
        program_type: The parent program_type to link to
    """
    upsert_child_records("redeemable", redeemables, program_type, "redeemable")


def upsert_processing_priority(processing_priority, program_type):
    """
    Upsert processing priority rules into the processing_priority_by_acquisition_type table.
    Args:
        processing_priority: List of processing priority dictionaries
        program_type: The parent program_type to link to
    """
    upsert_child_records(
        "processing_priority_by_acquisition_type",
        processing_priority,
        program_type,
        "processing priority",
    )


def upsert_child_records(table_name, records, program_type, record_type_name):
    """
    Upsert child records into a table with parent foreign key.
    Args:
        table_name: The name of the destination table
        records: List of record dictionaries to upsert
        program_type: The parent program_type to link to
        record_type_name: Human-readable name for logging
    """
    for record in records:
        record["program_type"] = program_type
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table_name, data=record)
    log.info(f"Synced {len(records)} {record_type_name}s")


def make_api_request(endpoint, location_key, business_key):
    """
    Make an API request to Partech API with retry logic and exponential backoff.
    Args:
        endpoint: The API endpoint URL
        location_key: The location API key
        business_key: The business key
    Returns:
        A dictionary containing the JSON response data
    Raises:
        requests.exceptions.HTTPError: For HTTP errors that should not be retried
        requests.exceptions.RequestException: For other request errors after max retries
    """
    headers = build_auth_headers(location_key, business_key)

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(endpoint, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            handle_http_error(e, endpoint, attempt)

        except requests.exceptions.RequestException as e:
            handle_request_error(e, endpoint, attempt)

    return None


def build_auth_headers(location_key, business_key):
    """
    Build authentication headers for Partech API requests.
    Args:
        location_key: The location API key
        business_key: The business key
    Returns:
        Dictionary containing HTTP headers with authentication
    """
    return {
        "Accept": "application/json",
        "Accept-Language": "",
        "Authorization": f"Token token={location_key}, btoken={business_key}",
    }


def handle_http_error(error, endpoint, attempt):
    """
    Handle HTTP errors with appropriate retry logic for server errors.
    Args:
        error: The HTTPError exception
        endpoint: The API endpoint that failed
        attempt: Current retry attempt number
    Raises:
        requests.exceptions.HTTPError: For client errors or after max retries
    """
    # Don't retry for client errors (4xx)
    if 400 <= error.response.status_code < 500:
        log.error(f"Client error {error.response.status_code} for {endpoint}: {error}")
        raise

    # Retry for server errors (5xx)
    if attempt < __MAX_RETRIES - 1:
        backoff_time = __INITIAL_BACKOFF * (2**attempt)
        log.warning(f"Server error on attempt {attempt + 1}, retrying in {backoff_time}s: {error}")
        sleep(backoff_time)
    else:
        log.error(f"Max retries reached for {endpoint}: {error}")
        raise


def handle_request_error(error, endpoint, attempt):
    """
    Handle request errors with exponential backoff retry logic.
    Args:
        error: The RequestException
        endpoint: The API endpoint that failed
        attempt: Current retry attempt number
    Raises:
        requests.exceptions.RequestException: After max retries
    """
    if attempt < __MAX_RETRIES - 1:
        backoff_time = __INITIAL_BACKOFF * (2**attempt)
        log.warning(
            f"Request error on attempt {attempt + 1}, retrying in {backoff_time}s: {error}"
        )
        sleep(backoff_time)
    else:
        log.error(f"Max retries reached for {endpoint}: {error}")
        raise


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
