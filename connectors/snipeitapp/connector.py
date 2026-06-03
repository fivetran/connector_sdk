"""Snipe-IT Asset Management Connector for Fivetran Connector SDK.
This connector demonstrates how to fetch asset management data from Snipe-IT API and sync it to destination.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For implementing retry delays
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

import requests  # For making HTTP API requests to Snipe-IT

# Maximum number of retry attempts for API requests
__MAX_RETRIES = 3

# Base delay in seconds for exponential backoff
__BASE_DELAY_SECONDS = 2

# Number of records per API request page
__PAGE_SIZE = 100

# Checkpoint after processing this many records
__CHECKPOINT_INTERVAL = 500

# API base path
__API_BASE_PATH = "/api/v1"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_token", "base_url"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate base_url format
    base_url = configuration.get("base_url", "")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Validate configuration to ensure base_url is present
    validate_configuration(configuration=configuration)
    return [
        {"table": "hardware", "primary_key": ["id"]},
        {"table": "users", "primary_key": ["id"]},
        {"table": "companies", "primary_key": ["id"]},
        {"table": "locations", "primary_key": ["id"]},
        {"table": "categories", "primary_key": ["id"]},
        {"table": "manufacturers", "primary_key": ["id"]},
        {"table": "suppliers", "primary_key": ["id"]},
        {"table": "models", "primary_key": ["id"]},
        {"table": "status_labels", "primary_key": ["id"]},
        {"table": "departments", "primary_key": ["id"]},
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
    log.warning("Example: Source API Example : Snipe-IT Asset Management Connector")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Extract configuration parameters
    api_token = configuration.get("api_token")
    base_url = configuration.get("base_url").rstrip("/")

    # Define table configurations with their API endpoints
    table_configs = [
        {"table_name": "hardware", "endpoint": "hardware", "sort_field": "updated_at"},
        {"table_name": "users", "endpoint": "users", "sort_field": "updated_at"},
        {"table_name": "companies", "endpoint": "companies", "sort_field": "updated_at"},
        {"table_name": "locations", "endpoint": "locations", "sort_field": "updated_at"},
        {"table_name": "categories", "endpoint": "categories", "sort_field": "updated_at"},
        {"table_name": "manufacturers", "endpoint": "manufacturers", "sort_field": "updated_at"},
        {"table_name": "suppliers", "endpoint": "suppliers", "sort_field": "updated_at"},
        {"table_name": "models", "endpoint": "models", "sort_field": "updated_at"},
        {"table_name": "status_labels", "endpoint": "statuslabels", "sort_field": "updated_at"},
        {"table_name": "departments", "endpoint": "departments", "sort_field": "updated_at"},
    ]

    # Sync each table
    for table_config in table_configs:
        table_name = table_config["table_name"]
        endpoint = table_config["endpoint"]
        sort_field = table_config["sort_field"]

        log.info(f"Starting sync for table: {table_name}")

        # Get last sync timestamp for this table from state
        state_key = f"{table_name}_last_updated_at"
        last_updated_at = state.get(state_key)

        try:
            # Sync the table data
            new_last_updated_at = sync_table(
                base_url=base_url,
                api_token=api_token,
                endpoint=endpoint,
                table_name=table_name,
                sort_field=sort_field,
                last_updated_at=last_updated_at,
                state=state,
                state_key=state_key,
            )

            # Update state with the latest timestamp for this table
            if new_last_updated_at:
                state[state_key] = new_last_updated_at

            log.info(f"Completed sync for table: {table_name}")

        except (RuntimeError, ValueError, KeyError, TypeError) as e:
            log.error(f"Failed to sync table {table_name}: {str(e)}")
            raise


def should_skip_record(last_updated_at, record_updated_at):
    """
    Determine if a record should be skipped based on incremental sync logic.
    Args:
        last_updated_at: The last synced timestamp.
        record_updated_at: The current record's updated_at timestamp.
    Returns:
        True if record should be skipped, False otherwise.
    """
    return last_updated_at and record_updated_at and record_updated_at <= last_updated_at


def process_record(record, table_name, last_updated_at, new_last_updated_at):
    """
    Process a single record by flattening and upserting it.
    Args:
        record: The record dictionary to process.
        table_name: The destination table name.
        last_updated_at: The last synced timestamp for incremental updates.
        new_last_updated_at: The current latest timestamp seen.
    Returns:
        Tuple of (should_process, updated_timestamp) where should_process is False if skipped.
    """
    flattened_record = flatten_record(record)
    record_updated_at = extract_timestamp(record, "updated_at")

    if should_skip_record(last_updated_at, record_updated_at):
        return False, new_last_updated_at

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table_name, data=flattened_record)

    # Update the latest timestamp
    if record_updated_at and (not new_last_updated_at or record_updated_at > new_last_updated_at):
        new_last_updated_at = record_updated_at

    return True, new_last_updated_at


def checkpoint_if_needed(records_processed, table_name, state, state_key, new_last_updated_at):
    """
    Checkpoint state at regular intervals.
    Args:
        records_processed: Number of records processed so far.
        table_name: The table being synced.
        state: The current state dictionary.
        state_key: The key to use for checkpointing.
        new_last_updated_at: The latest timestamp to checkpoint.
    """
    if records_processed % __CHECKPOINT_INTERVAL == 0:
        state[state_key] = new_last_updated_at
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
        log.info(f"Checkpointed {table_name} after processing {records_processed} records")


def sync_table(
    base_url, api_token, endpoint, table_name, sort_field, last_updated_at, state, state_key
):
    """
    Sync a single table from the Snipe-IT API with pagination and incremental support.
    Args:
        base_url: The base URL of the Snipe-IT instance.
        api_token: The API token for authentication.
        endpoint: The API endpoint to fetch data from.
        table_name: The destination table name.
        sort_field: The field to sort by for incremental sync.
        last_updated_at: The last synced timestamp for incremental updates.
        state: The current state dictionary.
        state_key: The key to use for checkpointing this table's state.
    Returns:
        The latest updated_at timestamp from the synced records.
    """
    offset = 0
    records_processed = 0
    new_last_updated_at = last_updated_at
    has_more_data = True

    while has_more_data:
        try:
            records = fetch_page(
                base_url=base_url,
                api_token=api_token,
                endpoint=endpoint,
                offset=offset,
                limit=__PAGE_SIZE,
                sort_field=sort_field,
                order="asc",
            )

            if not records:
                has_more_data = False
                break

            for record in records:
                was_processed, new_last_updated_at = process_record(
                    record, table_name, last_updated_at, new_last_updated_at
                )

                if was_processed:
                    records_processed += 1
                    checkpoint_if_needed(
                        records_processed, table_name, state, state_key, new_last_updated_at
                    )

            has_more_data = len(records) >= __PAGE_SIZE
            if has_more_data:
                offset += __PAGE_SIZE

        except (RuntimeError, requests.RequestException, ValueError, KeyError) as e:
            log.error(f"Error processing page at offset {offset} for {table_name}: {str(e)}")
            raise

    # Final checkpoint for this table
    if new_last_updated_at:
        state[state_key] = new_last_updated_at
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

    log.info(f"Synced {records_processed} records for {table_name}")
    return new_last_updated_at


def handle_http_error(response, attempt):
    """
    Handle HTTP error responses with appropriate retry or failure logic.
    Args:
        response: The HTTP response object.
        attempt: The current retry attempt number.
    Raises:
        RuntimeError: if the error is not retryable or max retries exceeded.
    """
    is_retryable = response.status_code in [429, 500, 502, 503, 504]
    is_auth_error = response.status_code in [401, 403]

    if is_auth_error:
        log.error(f"Authentication failed: {response.status_code} - {response.text}")
        raise RuntimeError(f"Authentication failed: {response.status_code} - {response.text}")

    if is_retryable and attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"Request failed with status {response.status_code}, "
            f"retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
        return True  # Continue retrying

    if is_retryable:
        log.error(
            f"Failed to fetch data after {__MAX_RETRIES} attempts. "
            f"Last status: {response.status_code} - {response.text}"
        )
        raise RuntimeError(
            f"API returned {response.status_code} after {__MAX_RETRIES} attempts: {response.text}"
        )

    log.error(f"API request failed: {response.status_code} - {response.text}")
    raise RuntimeError(f"API request failed: {response.status_code} - {response.text}")


def handle_network_error(error, error_type, attempt):
    """
    Handle network errors (timeout, connection) with retry logic.
    Args:
        error: The exception that was raised.
        error_type: Description of the error type (e.g., 'Request timeout', 'Connection error').
        attempt: The current retry attempt number.
    Raises:
        RuntimeError: if max retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{error_type}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
        return True  # Continue retrying

    log.error(f"{error_type} after {__MAX_RETRIES} attempts: {str(error)}")
    raise RuntimeError(f"{error_type} after {__MAX_RETRIES} attempts: {str(error)}")


def fetch_page(base_url, api_token, endpoint, offset, limit, sort_field, order):
    """
    Fetch a single page of data from the Snipe-IT API with retry logic.
    Args:
        base_url: The base URL of the Snipe-IT instance.
        api_token: The API token for authentication.
        endpoint: The API endpoint to fetch data from.
        offset: The pagination offset.
        limit: The number of records per page.
        sort_field: The field to sort by.
        order: The sort order (asc or desc).
    Returns:
        A list of records from the API response.
    Raises:
        RuntimeError: if the API request fails after retries.
    """
    url = f"{base_url}{__API_BASE_PATH}/{endpoint}"
    params = {"limit": limit, "offset": offset, "sort": sort_field, "order": order}
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_token}"}

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                return data.get("rows", [])

            should_retry = handle_http_error(response, attempt)
            if should_retry:
                continue

        except requests.Timeout as e:
            should_retry = handle_network_error(e, "Request timeout", attempt)
            if should_retry:
                continue

        except requests.ConnectionError as e:
            should_retry = handle_network_error(e, "Connection error", attempt)
            if should_retry:
                continue

    return []


def flatten_record(record, parent_key="", separator="_"):
    """
    Flatten a nested dictionary into a single-level dictionary.
    Nested dictionaries are flattened with keys joined by separator.
    Arrays are skipped as they should be handled in separate breakout tables.
    Args:
        record: The record dictionary to flatten.
        parent_key: The parent key for nested fields.
        separator: The separator to use between nested keys.
    Returns:
        A flattened dictionary.
    """
    flattened = {}

    for key, value in record.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key

        if value is None:
            flattened[new_key] = None
        elif isinstance(value, dict):
            # Recursively flatten nested dictionaries
            flattened.update(flatten_record(value, new_key, separator))
        elif isinstance(value, list):
            # Skip arrays - they should be handled in separate breakout tables
            # For now, convert to JSON string representation
            flattened[new_key] = None if not value else str(value)
        else:
            # Convert value to string if it's not a basic type
            flattened[new_key] = value

    return flattened


def extract_timestamp(record, field_name):
    """
    Extract and parse timestamp from a record field.
    Snipe-IT timestamps are nested in objects with 'datetime' key.
    Args:
        record: The record dictionary.
        field_name: The name of the timestamp field.
    Returns:
        ISO format timestamp string or None if not found.
    """
    timestamp_obj = record.get(field_name)

    if not timestamp_obj:
        return None

    if isinstance(timestamp_obj, dict):
        datetime_str = timestamp_obj.get("datetime")
        if datetime_str:
            return datetime_str

    return None


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
