"""n8n Connector for Fivetran Connector SDK.
This connector demonstrates how to sync workflow automation data from
n8n including workflows, executions, and credentials using the
n8n REST API.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for details
"""

# For reading configuration from a JSON file
import json

# For making HTTP requests to the n8n API
import requests

# For handling API request delays during rate limiting
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert, Update, Delete, checkpoint
from fivetran_connector_sdk import Operations as op

# Constants for API configuration
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 2
__CHECKPOINT_INTERVAL = 100
__PAGE_LIMIT = 100


def validate_configuration(configuration: dict):
    """
    Validate configuration dictionary for required parameters.
    This function is called at the start of the update method to ensure
    that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds configuration settings.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["base_url", "api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    base_url = configuration.get("base_url", "").strip()
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema
    your connector delivers.
    See the technical reference documentation for more details on the
    schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds configuration settings.
    """
    return [
        {"table": "workflows", "primary_key": ["id"]},
        {"table": "executions", "primary_key": ["id"]},
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your
    connector fetches data.
    See the technical reference documentation for more details on the
    update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds configuration settings.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: Source Connector : n8n")

    validate_configuration(configuration=configuration)

    base_url = configuration.get("base_url").rstrip("/")
    api_key = configuration.get("api_key")

    last_workflow_update = state.get("last_workflow_update")
    last_execution_id = state.get("last_execution_id")

    new_state = {
        "last_workflow_update": last_workflow_update,
        "last_execution_id": last_execution_id,
    }

    try:
        new_workflow_update = sync_workflows(
            base_url, api_key, last_workflow_update, last_execution_id
        )
        if new_workflow_update:
            new_state["last_workflow_update"] = new_workflow_update

        new_execution_id = sync_executions(
            base_url, api_key, last_execution_id, new_state["last_workflow_update"]
        )
        if new_execution_id:
            new_state["last_execution_id"] = new_execution_id

        # Note: Credentials endpoint is not available via n8n public API
        # for security reasons. Skipping credentials sync.
        log.info("Skipping credentials sync (not available via public API)")

        # Save the progress by checkpointing the state. This is important
        # for ensuring that the sync process can resume from the correct
        # position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best
        # practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(new_state)

    except Exception as e:
        raise RuntimeError(f"Failed to sync n8n data: {str(e)}")


def sync_workflows(base_url: str, api_key: str, last_update: str, last_execution_id: str):
    """
    Sync workflow data from n8n API with pagination support.
    Args:
        base_url: The base URL of the n8n instance.
        api_key: The API key for authentication.
        last_update: The timestamp of the last workflow update from previous sync.
        last_execution_id: The ID of the last execution (preserved in checkpoints).
    Returns:
        The latest workflow update timestamp encountered during this sync.
    """
    log.info("Starting workflows sync")

    cursor = 0
    latest_update = last_update
    records_synced = 0

    while True:
        workflows_data = fetch_workflows_page(base_url, api_key, cursor)

        if not workflows_data or len(workflows_data) == 0:
            break

        for workflow in workflows_data:
            flattened_workflow = flatten_workflow(workflow)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="workflows", data=flattened_workflow)

            records_synced += 1

            workflow_update = flattened_workflow.get("updated_at")
            if workflow_update and (not latest_update or workflow_update > latest_update):
                latest_update = workflow_update

        if records_synced >= __CHECKPOINT_INTERVAL:
            temp_state = {
                "last_workflow_update": latest_update,
                "last_execution_id": last_execution_id,
            }
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(temp_state)
            records_synced = 0

        if len(workflows_data) < __PAGE_LIMIT:
            break

        cursor += __PAGE_LIMIT

    log.info(f"Completed workflows sync with latest update: {latest_update}")
    return latest_update


def sync_executions(
    base_url: str, api_key: str, last_execution_id: str, last_workflow_update: str
):
    """
    Sync execution data from n8n API with cursor-based pagination.
    Executions are returned newest-first, so we stop when we reach
    the last synced ID.
    Args:
        base_url: The base URL of the n8n instance.
        api_key: The API key for authentication.
        last_execution_id: The ID of the last execution from previous sync.
        last_workflow_update: The timestamp of the last workflow update (preserved in checkpoints).
    Returns:
        The latest execution ID encountered during this sync.
    """
    log.info("Starting executions sync")

    next_cursor = None
    latest_execution_id = last_execution_id
    records_synced = 0
    new_records_count = 0

    while True:
        response = fetch_executions_page_with_cursor(base_url, api_key, next_cursor)

        executions_data = response.get("data", [])
        next_cursor = response.get("nextCursor")

        if not executions_data:
            break

        should_stop, latest_id = process_executions_batch(
            executions_data,
            last_execution_id,
            latest_execution_id,
        )

        if should_stop:
            log.info(
                f"Completed executions sync: {new_records_count} new records, latest ID: {latest_id or last_execution_id}"
            )
            return latest_id or last_execution_id

        # Update tracking variables
        batch_size = len(executions_data)
        records_synced += batch_size
        new_records_count += batch_size
        latest_execution_id = latest_id

        if records_synced >= __CHECKPOINT_INTERVAL:
            checkpoint_execution_state(latest_execution_id, last_workflow_update)
            records_synced = 0

        if not next_cursor:
            break

    log.info(
        f"Completed executions sync: {new_records_count} new records, latest ID: {latest_execution_id}"
    )
    return latest_execution_id


def process_executions_batch(
    executions_data: list, last_execution_id: str, latest_execution_id: str
):
    """
    Process a batch of executions and upsert them to the destination.
    Args:
        executions_data: List of execution records from the API.
        last_execution_id: The ID of the last execution from previous sync.
        latest_execution_id: The highest execution ID seen so far in current sync.
    Returns:
        Tuple of (should_stop: bool, latest_id: str) where should_stop indicates
        whether we've reached previously synced data.
    """
    current_latest_id = latest_execution_id

    for execution in executions_data:
        execution_id = execution.get("id")

        if should_stop_at_execution(execution_id, last_execution_id):
            return True, current_latest_id

        flattened_execution = flatten_execution(execution)

        # The 'upsert' operation is used to insert or update data
        # in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record
        # to be upserted.
        op.upsert(table="executions", data=flattened_execution)

        current_latest_id = update_latest_execution_id(execution_id, current_latest_id)

    return False, current_latest_id


def should_stop_at_execution(execution_id: str, last_execution_id: str):
    """
    Check if we should stop syncing at this execution.
    Executions are returned newest-first, so we stop when we reach
    previously synced data.
    Args:
        execution_id: Current execution ID being processed.
        last_execution_id: The ID of the last execution from previous sync.
    Returns:
        True if we should stop syncing, False otherwise.
    """
    if not last_execution_id:
        return False

    if execution_id == last_execution_id:
        log.info(f"Reached last synced execution ID {last_execution_id}, stopping")
        return True

    if int(execution_id) <= int(last_execution_id):
        log.info(f"Execution ID {execution_id} <= last synced {last_execution_id}, stopping")
        return True

    return False


def update_latest_execution_id(execution_id: str, current_latest_id: str):
    """
    Update the latest execution ID if the current one is higher.
    Args:
        execution_id: Current execution ID being processed.
        current_latest_id: The highest execution ID seen so far.
    Returns:
        The updated latest execution ID.
    """
    if not current_latest_id or int(execution_id) > int(current_latest_id):
        return execution_id
    return current_latest_id


def checkpoint_execution_state(latest_execution_id: str, last_workflow_update: str):
    """
    Save execution sync progress by checkpointing the state.
    Args:
        latest_execution_id: The latest execution ID to checkpoint.
        last_workflow_update: The timestamp of the last workflow update (preserved).
    """
    temp_state = {
        "last_workflow_update": last_workflow_update,
        "last_execution_id": latest_execution_id,
    }
    # Save the progress by checkpointing the state. This is
    # important for ensuring that the sync process can resume
    # from the correct position in case of next sync or
    # interruptions.
    # Learn more about how and where to checkpoint by reading
    # our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(temp_state)


def fetch_workflows_page(base_url: str, api_key: str, cursor: int):
    """
    Fetch a single page of workflows from the n8n API with retry logic.
    Args:
        base_url: The base URL of the n8n instance.
        api_key: The API key for authentication.
        cursor: The pagination cursor offset.
    Returns:
        A list of workflow objects from the API response.
    """
    url = f"{base_url}/api/v1/workflows"
    headers = {"X-N8N-API-KEY": api_key}
    params = {"limit": __PAGE_LIMIT}
    # Only add cursor if it's not the first page
    if cursor > 0:
        params["cursor"] = cursor

    response_data = make_api_request(url, headers, params)
    return response_data.get("data", [])


def fetch_executions_page_with_cursor(base_url: str, api_key: str, cursor: str):
    """
    Fetch executions page using n8n's cursor-based pagination.
    Args:
        base_url: The base URL of the n8n instance.
        api_key: The API key for authentication.
        cursor: The nextCursor value from previous response (None for first page).
    Returns:
        Full API response with 'data' and 'nextCursor' fields.
    """
    url = f"{base_url}/api/v1/executions"
    headers = {"X-N8N-API-KEY": api_key}
    params = {"limit": __PAGE_LIMIT}
    # Add cursor parameter if provided
    if cursor:
        params["cursor"] = cursor

    response_data = make_api_request(url, headers, params)
    return response_data


def make_api_request(url: str, headers: dict, params: dict):
    """
    Make an API request with exponential backoff retry logic for transient errors.
    Args:
        url: The API endpoint URL.
        headers: The request headers including authentication.
        params: The query parameters for the request.
    Returns:
        The JSON response data from the API.
    Raises:
        RuntimeError: if the API request fails after all retry attempts.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                return response.json()

            handle_failed_response(response, attempt)

        except requests.exceptions.Timeout as e:
            handle_timeout_error(attempt, e)

        except requests.exceptions.ConnectionError as e:
            handle_connection_error(attempt, e)

    raise RuntimeError("API request failed after all retry attempts")


def handle_failed_response(response, attempt: int):
    """
    Handle failed API response with appropriate retry or error logic.
    Args:
        response: The HTTP response object.
        attempt: Current retry attempt number (0-indexed).
    Raises:
        RuntimeError: if the response indicates a non-retryable error
                     or max retries reached.
    """
    is_retryable_error = response.status_code in [429, 500, 502, 503, 504]

    if is_retryable_error and attempt < __MAX_RETRIES - 1:
        retry_with_backoff(
            f"Request failed with status {response.status_code}",
            attempt,
        )
        return

    if is_retryable_error:
        error_message = f"Failed after {__MAX_RETRIES} attempts. Last status: {response.status_code} - {response.text}"
        log.error(error_message)
        raise RuntimeError(
            f"API returned {response.status_code} after {__MAX_RETRIES} attempts: {response.text}"
        )

    log.error(f"API request failed with status {response.status_code}: {response.text}")
    raise RuntimeError(f"API returned {response.status_code}: {response.text}")


def handle_timeout_error(attempt: int, error: Exception):
    """
    Handle request timeout error with retry logic.
    Args:
        attempt: Current retry attempt number (0-indexed).
        error: The timeout exception that occurred.
    Raises:
        RuntimeError: if max retries reached.
    """
    if attempt < __MAX_RETRIES - 1:
        retry_with_backoff("Request timeout", attempt)
        return

    log.error(f"Request timeout after {__MAX_RETRIES} attempts")
    raise RuntimeError(f"Request timeout after {__MAX_RETRIES} attempts: {str(error)}")


def handle_connection_error(attempt: int, error: Exception):
    """
    Handle connection error with retry logic.
    Args:
        attempt: Current retry attempt number (0-indexed).
        error: The connection exception that occurred.
    Raises:
        RuntimeError: if max retries reached.
    """
    if attempt < __MAX_RETRIES - 1:
        retry_with_backoff("Connection error", attempt)
        return

    log.error(f"Connection error after {__MAX_RETRIES} attempts")
    raise RuntimeError(f"Connection error after {__MAX_RETRIES} attempts: {str(error)}")


def retry_with_backoff(error_message: str, attempt: int):
    """
    Execute retry logic with exponential backoff delay.
    Args:
        error_message: Description of the error that triggered the retry.
        attempt: Current retry attempt number (0-indexed).
    """
    delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
    log.warning(
        f"{error_message}, retrying in {delay_seconds} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
    )
    time.sleep(delay_seconds)


def flatten_workflow(workflow: dict):
    """
    Flatten a workflow object from the n8n API into a flat dictionary for database storage.
    Args:
        workflow: The workflow object from the API response.
    Returns:
        A flattened dictionary with all nested objects converted to dot notation.
    """
    flattened = {
        "id": workflow.get("id"),
        "name": workflow.get("name"),
        "active": workflow.get("active"),
        "created_at": workflow.get("createdAt"),
        "updated_at": workflow.get("updatedAt"),
        "tags": (json.dumps(workflow.get("tags", [])) if workflow.get("tags") else None),
        "nodes": (json.dumps(workflow.get("nodes", [])) if workflow.get("nodes") else None),
        "connections": (
            json.dumps(workflow.get("connections", {})) if workflow.get("connections") else None
        ),
        "settings": (
            json.dumps(workflow.get("settings", {})) if workflow.get("settings") else None
        ),
        "static_data": (
            json.dumps(workflow.get("staticData", {})) if workflow.get("staticData") else None
        ),
        "version_id": workflow.get("versionId"),
    }
    return flattened


def flatten_execution(execution: dict):
    """
    Flatten an execution object from the n8n API into a flat dictionary for database storage.
    Args:
        execution: The execution object from the API response.
    Returns:
        A flattened dictionary with all nested objects converted to dot notation.
    """
    flattened = {
        "id": execution.get("id"),
        "workflow_id": execution.get("workflowId"),
        "mode": execution.get("mode"),
        "status": execution.get("status"),
        "started_at": execution.get("startedAt"),
        "stopped_at": execution.get("stoppedAt"),
        "finished": execution.get("finished"),
        "data": (json.dumps(execution.get("data", {})) if execution.get("data") else None),
        "waiting_execution": (
            json.dumps(execution.get("waitingExecution", {}))
            if execution.get("waitingExecution")
            else None
        ),
        "retry_of": execution.get("retryOf"),
        "retry_success_id": execution.get("retrySuccessId"),
    }
    return flattened


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
