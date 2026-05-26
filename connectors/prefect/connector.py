"""
Prefect Cloud Connector for Fivetran Connector SDK.
This connector fetches workflow orchestration data from Prefect Cloud
API and syncs it to your data warehouse.
Supports incremental syncing of flow, deployment, work_pool,
work_queue, flow_run, task_run, artifact, and variable.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for details.
"""

# For reading configuration from a JSON file
import json
from typing import Any

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert and checkpoint
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to Prefect API
import requests

# For handling delays in retry logic
import time

# Define constants for the connector
__BASE_URL_TEMPLATE = (
    "https://api.prefect.cloud/api/accounts/{account_id}/workspaces/{workspace_id}"
)
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__BATCH_SIZE = 100
__CHECKPOINT_INTERVAL = 500


def validate_configuration(configuration: dict):
    """
    Validate configuration dictionary for required parameters.
    This function is called at the start of the update method to
    ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration
        settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_key", "account_id", "workspace_id"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


# Configuration mapping for different resource types
# Each entry maps: table_name -> (endpoint, state_key)
__SYNC_CONFIGS = {
    "flow": ("/flows/filter", "flow_last_updated"),
    "deployment": ("/deployments/filter", "deployment_last_updated"),
    "flow_run": ("/flow_runs/filter", "flow_run_last_updated"),
    "task_run": ("/task_runs/filter", "task_run_last_updated"),
    "artifact": ("/artifacts/filter", "artifact_last_updated"),
    "work_pool": ("/work_pools/filter", "work_pool_last_updated"),
    "work_queue": ("/work_queues/filter", "work_queue_last_updated"),
    "variable": ("/variables/filter", "variable_last_updated"),
}


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema
    your connector delivers.
    See the technical reference documentation for more details on
    the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration
        settings for the connector.
    """
    return [{"table": table_name, "primary_key": ["id"]} for table_name in __SYNC_CONFIGS]


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your
    connector fetches data.
    See the technical reference documentation for more details on
    the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration
        settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: Prefect Cloud API Connector")

    validate_configuration(configuration=configuration)

    api_key = configuration.get("api_key")
    account_id = configuration.get("account_id")
    workspace_id = configuration.get("workspace_id")

    base_url = __BASE_URL_TEMPLATE.format(account_id=account_id, workspace_id=workspace_id)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for table_name in __SYNC_CONFIGS:
        sync_resource(base_url, headers, state, table_name)


def handle_retryable_error(attempt: int, error_message: str):
    """
    Handle retryable errors with logging and delay using exponential backoff.
    Args:
        attempt: Current attempt number (0-indexed).
        error_message: Error description for logging.
    Raises:
        RuntimeError: If max retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{error_message}, retrying in {delay} seconds "
            f"(attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{error_message} after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{error_message} after {__MAX_RETRIES} attempts")


def make_api_request(url: str, headers: dict, payload: dict) -> dict:
    """
    Make an API request with retry logic for transient failures.
    Implements exponential backoff for retries.
    Args:
        url: The API endpoint URL.
        headers: HTTP headers for the request.
        payload: Request body payload.
    Returns:
        Response JSON as a dictionary.
    Raises:
        RuntimeError: If the API request fails after all retry
        attempts.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                return response.json()

            if response.status_code in [429, 500, 502, 503, 504]:
                error_msg = f"Request failed with status {response.status_code}"
                handle_retryable_error(attempt, error_msg)
                continue

            log.error(f"API request failed with status {response.status_code}: {response.text}")
            raise RuntimeError(f"API request failed: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            handle_retryable_error(attempt, "Request timeout")
            continue

        except requests.exceptions.ConnectionError:
            handle_retryable_error(attempt, "Connection error")
            continue

    # This should never be reached due to handle_retryable_error raising
    # RuntimeError on the last attempt, but adding for safety
    raise RuntimeError(f"API request failed after {__MAX_RETRIES} attempts")


def filter_records(
    response_data: dict, cursor_field: str, cursor_value: str, endpoint: str
) -> list[Any] | dict:
    """
    Filter records based on cursor value for incremental sync.
    Args:
        response_data: Dictionary or list of records from API response.
        cursor_field: Field name to use for filtering.
        cursor_value: Cursor value from last sync.
        endpoint: API endpoint path for logging.
    Returns:
        Filtered list of records.
    """
    if cursor_value:
        filtered_records = [
            record for record in response_data if record.get(cursor_field, "") > cursor_value
        ]
        log.info(
            f"Fetched {len(response_data)} records from {endpoint}, "
            f"filtered to {len(filtered_records)} new records"
        )
        return filtered_records

    log.info(f"Fetched {len(response_data)} records from {endpoint}")
    return response_data


def process_record(record: dict, table_name: str, max_updated: str) -> str:
    """
    Process a single record by flattening and upserting it.
    Args:
        record: The record to process.
        table_name: Name of the destination table.
        max_updated: Current maximum updated timestamp.
    Returns:
        Updated maximum timestamp.
    """
    flattened_record = flatten_record(record)
    op.upsert(table=table_name, data=flattened_record)

    record_updated = record.get("updated")
    if record_updated and (max_updated is None or record_updated > max_updated):
        return record_updated

    return max_updated


def checkpoint_if_needed(
    record_count: int, state: dict, state_key: str, max_updated: str, table_name: str
):
    """
    Create a checkpoint if the record count reaches the interval.
    Args:
        record_count: Current count of processed records.
        state: State dictionary to track sync progress.
        state_key: Key in state dict to store cursor value.
        max_updated: Current maximum updated timestamp.
        table_name: Name of the destination table.
    """
    if record_count % __CHECKPOINT_INTERVAL == 0:
        state[state_key] = max_updated
        op.checkpoint(state)
        log.info(f"Checkpointed {table_name} at {record_count} records")


def fetch_and_process_paginated_data(
    base_url: str,
    endpoint: str,
    headers: dict,
    cursor_field: str,
    cursor_value: str,
    table_name: str,
    state: dict,
    state_key: str,
):
    """
    Fetch paginated data from Prefect API and process it page by page.
    This avoids loading all records into memory at once.
    Performs client-side incremental filtering based on cursor value.
    Args:
        base_url: Base URL for the Prefect API.
        endpoint: API endpoint path.
        headers: HTTP headers for authentication.
        cursor_field: Field name to use for incremental filtering.
        cursor_value: Cursor value from last sync for client-side
        filtering.
        table_name: Name of the destination table.
        state: State dictionary to track sync progress.
        state_key: Key in state dict to store cursor value.
    """
    offset = 0
    total_processed = 0
    record_count = 0
    max_updated = cursor_value

    while True:
        payload = {"limit": __BATCH_SIZE, "offset": offset}
        url = f"{base_url}{endpoint}"
        response_data = make_api_request(url, headers, payload)

        if not response_data:
            break

        filtered_records = filter_records(response_data, cursor_field, cursor_value, endpoint)

        for record in filtered_records:
            max_updated = process_record(record, table_name, max_updated)
            record_count += 1
            checkpoint_if_needed(record_count, state, state_key, max_updated, table_name)

        total_processed += len(filtered_records)

        if len(response_data) < __BATCH_SIZE:
            break

        offset += __BATCH_SIZE

    # Final checkpoint if there were any updates
    if max_updated != state.get(state_key):
        state[state_key] = max_updated
        op.checkpoint(state)

    log.info(f"Completed syncing {total_processed} {table_name}")


def flatten_record(record: dict, prefix: str = "") -> dict:
    """
    Flatten nested dictionary into a single-level dictionary.
    Args:
        record: The dictionary to flatten.
        prefix: Prefix for flattened keys.
    Returns:
        Flattened dictionary.
    """
    flattened = {}

    for key, value in record.items():
        new_key = f"{prefix}{key}" if prefix else key

        if isinstance(value, dict):
            flattened.update(flatten_record(value, f"{new_key}_"))
        elif isinstance(value, list):
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


def sync_resource(base_url: str, headers: dict, state: dict, table_name: str):
    """
    Generic function to sync any resource type from Prefect API with
    incremental cursor based on updated timestamp.
    Args:
        base_url: Base URL for the Prefect API.
        headers: HTTP headers for authentication.
        state: State dictionary to track sync progress.
        table_name: Name of the resource/table to sync.
    """
    endpoint, state_key = __SYNC_CONFIGS[table_name]
    last_updated = state.get(state_key)
    fetch_and_process_paginated_data(
        base_url, endpoint, headers, "updated", last_updated, table_name, state, state_key
    )


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
