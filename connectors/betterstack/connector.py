"""Better Stack Uptime Connector for Fivetran.
This connector syncs uptime monitoring data from Better Stack including monitors, status pages,
monitor groups, heartbeats, heartbeat groups, and on-call calendars.
See the Technical Reference documentation at:
https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
and the Best Practices documentation at:
https://fivetran.com/docs/connectors/connector-sdk/best-practices for details
"""

# For reading configuration from a JSON file
import json

# For time-related operations
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP API requests (provided by SDK runtime)
import requests

# Constants for API configuration
__BASE_URL_V2 = "https://uptime.betterstack.com/api/v2"
__BASE_URL_V3 = "https://uptime.betterstack.com/api/v3"
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 2
__PER_PAGE = 100
__REQUEST_TIMEOUT_SECONDS = 30

# Endpoint configurations with table names and API paths
__ENDPOINTS = {
    "monitors": {
        "path": "/monitors",
        "parent_table": "monitors",
        "flatten_fields": ["attributes"],
        "api_version": "v2",
    },
    "status_pages": {
        "path": "/status-pages",
        "parent_table": "status_pages",
        "flatten_fields": ["attributes"],
        "api_version": "v2",
    },
    "monitor_groups": {
        "path": "/monitor-groups",
        "parent_table": "monitor_groups",
        "flatten_fields": ["attributes"],
        "api_version": "v2",
    },
    "heartbeats": {
        "path": "/heartbeats",
        "parent_table": "heartbeats",
        "flatten_fields": ["attributes"],
        "api_version": "v2",
    },
    "heartbeat_groups": {
        "path": "/heartbeat-groups",
        "parent_table": "heartbeat_groups",
        "flatten_fields": ["attributes"],
        "api_version": "v2",
    },
    "incidents": {
        "path": "/incidents",
        "parent_table": "incidents",
        "flatten_fields": ["attributes"],
        "api_version": "v3",
        "cursor_field": "started_at",
        "child_tables": {
            "incident_monitor": {"source_field": "monitor", "parent_id_field": "incident_id"}
        },
    },
    "on_call_calendars": {
        "path": "/on-calls",
        "parent_table": "on_call_calendars",
        "flatten_fields": ["attributes"],
        "api_version": "v2",
        "cursor_field": "id",
        "child_tables": {
            "on_call_users": {
                "source_field": "on_call_users",
                "parent_id_field": "on_call_calendar_id",
            }
        },
    },
}


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
    required_configs = ["api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def get_headers(api_key: str):
    """
    Build HTTP headers for Better Stack API requests.
    Args:
        api_key: The Better Stack API key for authentication.
    Returns:
        Dictionary containing the required HTTP headers including authorization.
    """
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def calculate_retry_delay(attempt: int):
    """
    Calculate exponential backoff delay for retry attempts.
    Args:
        attempt: The current attempt number (0-indexed).
    Returns:
        Delay in seconds for the next retry.
    """
    return __BASE_DELAY_SECONDS * (2**attempt)


def is_retryable_status(status_code: int):
    """
    Check if an HTTP status code is retryable.
    Args:
        status_code: The HTTP status code to check.
    Returns:
        True if the status code indicates a transient error that should be retried.
    """
    return status_code in [429, 500, 502, 503, 504]


def handle_http_error(response, attempt: int):
    """
    Handle HTTP error responses with retry logic.
    Args:
        response: The HTTP response object.
        attempt: The current attempt number (0-indexed).
    Raises:
        RuntimeError: if the error is not retryable or max retries exceeded.
    """
    if is_retryable_status(response.status_code):
        if attempt < __MAX_RETRIES - 1:
            delay = calculate_retry_delay(attempt)
            log.warning(
                f"Request failed with status {response.status_code}, "
                f"retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
            )
            time.sleep(delay)
        else:
            log.error(
                f"Failed to fetch data after {__MAX_RETRIES} attempts. "
                f"Last status: {response.status_code} - {response.text}"
            )
            raise RuntimeError(
                f"API returned {response.status_code} after {__MAX_RETRIES} attempts: {response.text}"
            )
    else:
        log.error(f"API request failed with status {response.status_code}: {response.text}")
        raise RuntimeError(f"API returned {response.status_code}: {response.text}")


def handle_network_error(error: Exception, attempt: int):
    """
    Handle network errors with retry logic.
    Args:
        error: The network error exception.
        attempt: The current attempt number (0-indexed).
    Raises:
        RuntimeError: if max retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = calculate_retry_delay(attempt)
        log.warning(
            f"Network error occurred, retrying in {delay} seconds "
            f"(attempt {attempt + 1}/{__MAX_RETRIES}): {str(error)}"
        )
        time.sleep(delay)
    else:
        log.error(f"Network error after {__MAX_RETRIES} attempts: {str(error)}")
        raise RuntimeError(f"Network error after {__MAX_RETRIES} attempts: {str(error)}")


def make_api_request(url: str, api_key: str):
    """
    Make an API request with retry logic and exponential backoff.
    Args:
        url: The full URL to make the request to.
        api_key: The Better Stack API key for authentication.
    Returns:
        The JSON response from the API.
    Raises:
        RuntimeError: if the request fails after all retry attempts.
    """
    headers = get_headers(api_key)

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=__REQUEST_TIMEOUT_SECONDS)

            if response.status_code == 200:
                return response.json()

            handle_http_error(response, attempt)

        except (requests.Timeout, requests.ConnectionError) as e:
            handle_network_error(e, attempt)

    raise RuntimeError(f"Failed to fetch data after {__MAX_RETRIES} attempts")


def serialize_value(value):
    """
    Serialize a value to a JSON string if it is a complex type.
    Args:
        value: The value to serialize.
    Returns:
        JSON string if value is a list or dict, otherwise the original value.
    """
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def flatten_nested_dict(nested_dict: dict):
    """
    Flatten a nested dictionary and serialize complex values.
    Args:
        nested_dict: The nested dictionary to flatten.
    Returns:
        Dictionary with all values at the top level and complex types serialized.
    """
    return {key: serialize_value(value) for key, value in nested_dict.items()}


def flatten_record(record: dict, fields_to_flatten: list):
    """
    Flatten nested dictionary fields into the parent record and convert complex types to JSON strings.
    Args:
        record: The record dictionary to flatten.
        fields_to_flatten: List of field names to flatten into the parent.
    Returns:
        Flattened dictionary with nested fields merged into parent level and complex types as JSON strings.
    """
    flattened = {}

    for key, value in record.items():
        if key in fields_to_flatten and isinstance(value, dict):
            flattened.update(flatten_nested_dict(value))
        else:
            flattened[key] = serialize_value(value)

    return flattened


def fetch_paginated_data(endpoint_path: str, api_key: str, last_updated_at: str, api_version: str):
    """
    Fetch all pages of data from a paginated Better Stack API endpoint.
    Args:
        endpoint_path: The API endpoint path to fetch data from.
        api_key: The Better Stack API key for authentication.
        last_updated_at: ISO timestamp to filter records updated after this time.
        api_version: The API version to use (v2 or v3).
    Returns:
        Generator yielding records one at a time for memory efficiency.
    """
    base_url = __BASE_URL_V2 if api_version == "v2" else __BASE_URL_V3
    url = f"{base_url}{endpoint_path}"
    params = f"?per_page={__PER_PAGE}&page=1"
    next_url = f"{url}{params}"

    page_count = 0

    while next_url:
        page_count += 1
        log.info(f"Fetching page {page_count} from {endpoint_path}")

        response_data = make_api_request(next_url, api_key)

        data = response_data.get("data", [])
        for record in data:
            yield record

        pagination = response_data.get("pagination", {})
        next_url = pagination.get("next")

        if not next_url:
            log.info(f"Reached last page for {endpoint_path}")


def should_skip_record(record_cursor_value, last_cursor_value):
    """
    Check if a record should be skipped based on its cursor value.
    Args:
        record_cursor_value: The cursor value of the current record (can be None).
        last_cursor_value: The last synced cursor value from state (can be None).
    Returns:
        True if the record should be skipped, False otherwise.
    """
    if last_cursor_value and record_cursor_value:
        return record_cursor_value <= last_cursor_value
    return False


def sync_child_table(child_table_name: str, child_config: dict, record: dict, parent_id: str):
    """
    Sync child table records for a parent record.
    Args:
        child_table_name: Name of the child table.
        child_config: Configuration for the child table.
        record: The parent record containing relationship data.
        parent_id: The ID of the parent record.
    """
    source_field = child_config["source_field"]
    parent_id_field = child_config["parent_id_field"]

    relationships = record.get("relationships", {})
    child_data = relationships.get(source_field, {}).get("data", [])

    if isinstance(child_data, list):
        for child_record in child_data:
            child_record[parent_id_field] = parent_id
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=child_table_name, data=child_record)


def update_latest_timestamp(current_timestamp, latest_timestamp):
    """
    Update the latest timestamp if current is newer.
    Args:
        current_timestamp: The current record's timestamp (can be None).
        latest_timestamp: The current latest timestamp (can be None).
    Returns:
        The newer of the two timestamps (can be None).
    """
    if current_timestamp:
        if not latest_timestamp or current_timestamp > latest_timestamp:
            return current_timestamp
    return latest_timestamp


def sync_endpoint(endpoint_name: str, endpoint_config: dict, api_key: str, state: dict):
    """
    Sync data from a single Better Stack API endpoint.
    Args:
        endpoint_name: The name of the endpoint being synced.
        endpoint_config: Configuration dictionary for the endpoint.
        api_key: The Better Stack API key for authentication.
        state: The current state dictionary containing sync timestamps.
    Returns:
        The latest cursor value from the synced records.
    """
    endpoint_path = endpoint_config["path"]
    parent_table = endpoint_config["parent_table"]
    flatten_fields = endpoint_config.get("flatten_fields", [])
    child_tables = endpoint_config.get("child_tables", {})
    api_version = endpoint_config.get("api_version", "v2")
    cursor_field = endpoint_config.get("cursor_field", "updated_at")

    state_key = f"{endpoint_name}_last_updated_at"
    last_cursor_value = state.get(state_key)
    latest_cursor_value = last_cursor_value

    log.info(f"Starting sync for {endpoint_name} from {last_cursor_value or 'beginning'}")

    record_count = 0

    for record in fetch_paginated_data(
        endpoint_path, api_key, last_cursor_value or "", api_version
    ):
        record_id = record.get("id")
        flattened_record = flatten_record(record, flatten_fields)
        record_cursor_value = flattened_record.get(cursor_field)

        if should_skip_record(record_cursor_value, last_cursor_value):
            continue

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=parent_table, data=flattened_record)

        for child_table_name, child_config in child_tables.items():
            sync_child_table(child_table_name, child_config, record, record_id)

        latest_cursor_value = update_latest_timestamp(record_cursor_value, latest_cursor_value)
        record_count += 1

    log.info(f"Synced {record_count} records from {endpoint_name}")

    return latest_cursor_value


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "monitors", "primary_key": ["id"]},
        {"table": "status_pages", "primary_key": ["id"]},
        {"table": "monitor_groups", "primary_key": ["id"]},
        {"table": "heartbeats", "primary_key": ["id"]},
        {"table": "heartbeat_groups", "primary_key": ["id"]},
        {"table": "incidents", "primary_key": ["id"]},
        {"table": "incident_monitor", "primary_key": ["incident_id", "id"]},
        {"table": "on_call_calendars", "primary_key": ["id"]},
        {"table": "on_call_users", "primary_key": ["on_call_calendar_id", "id"]},
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
    log.warning("Example: Source Example : Better Stack Uptime")

    validate_configuration(configuration=configuration)

    api_key = configuration.get("api_key")

    for endpoint_name, endpoint_config in __ENDPOINTS.items():
        try:
            latest_updated_at = sync_endpoint(
                endpoint_name=endpoint_name,
                endpoint_config=endpoint_config,
                api_key=api_key,
                state=state,
            )

            state_key = f"{endpoint_name}_last_updated_at"
            state[state_key] = latest_updated_at

            # Save the progress by checkpointing the state. This is important for ensuring that
            # the sync process can resume from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation:
            # https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation
            op.checkpoint(state)

        except Exception as e:
            log.error(f"Failed to sync {endpoint_name}: {str(e)}")
            raise


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by
# Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
