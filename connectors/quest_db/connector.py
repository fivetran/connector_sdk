"""QuestDB connector for Fivetran - syncs high-performance time-series data from QuestDB.
This connector demonstrates how to fetch IoT sensor data, financial market data, and industrial telemetry from QuestDB and sync it to Fivetran using the Fivetran Connector SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json
from typing import Any

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to QuestDB REST API
import requests

# For URL encoding SQL queries
from urllib.parse import quote

# For handling time operations and timestamps
from datetime import datetime, timezone

# For adding delays between retry attempts
import time

# For encoding authentication credentials
import base64

# For validating SQL identifiers
import re

# Batch size for pagination
__BATCH_SIZE = 1000

# Checkpoint after processing every 5000 records
__CHECKPOINT_INTERVAL = 5000

# Maximum number of retry attempts for API requests
__MAX_RETRIES = 3

# Base delay in seconds for API request retries
__BASE_DELAY = 1

# Request timeout in seconds
__REQUEST_TIMEOUT_SEC = 60


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters with valid values.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = ["host", "port", "tables"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate port is a valid integer
    try:
        port = int(configuration["port"])
        if port < 1 or port > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {port}")
    except (ValueError, TypeError):
        raise ValueError(f"Port must be a valid integer, got {configuration['port']}")

    # Validate batch_size if provided
    if "batch_size" in configuration:
        try:
            batch_size = int(configuration["batch_size"])
            if batch_size < 1:
                raise ValueError(f"batch_size must be positive, got {batch_size}")
        except (ValueError, TypeError):
            raise ValueError(
                f"batch_size must be a valid integer, got {configuration['batch_size']}"
            )

    # Validate username/password together
    username = configuration.get("username")
    password = configuration.get("password")
    if (username and not password) or (password and not username):
        raise ValueError("Both username and password must be provided for authentication")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    tables = configuration.get("tables", "").split(",")
    schemas = []

    for table in tables:
        table_name = table.strip()
        if table_name:
            schemas.append({"table": table_name, "primary_key": ["_fivetran_synced_key"]})

    return schemas


def validate_identifier(identifier: str) -> bool:
    """
    Validate SQL identifier to prevent SQL injection.
    Args:
        identifier: SQL identifier (table name or column name) to validate.
    Returns:
        True if identifier is valid, False otherwise.
    """
    # Allow only alphanumeric characters and underscores, must start with letter or underscore
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier))


def build_questdb_url(configuration: dict, query: str) -> str:
    """
    Build QuestDB REST API URL with encoded query.
    Args:
        configuration: Configuration dictionary.
        query: SQL query to execute.
    Returns:
        Complete URL for QuestDB REST API request.
    """
    host = configuration.get("host", "localhost")
    port = configuration.get("port", "9000")
    encoded_query = quote(query)
    return f"http://{host}:{port}/exec?query={encoded_query}"


def build_auth_header(configuration: dict) -> dict:
    """
    Build authentication header if credentials are provided.
    Args:
        configuration: Configuration dictionary.
    Returns:
        Dictionary with authentication headers.
    """
    username = configuration.get("username")
    password = configuration.get("password")

    if username and password:
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded_credentials}"}

    return {}


def handle_retry_logic(attempt: int, error_message: str):
    """
    Handle retry logic with exponential backoff.
    Args:
        attempt: Current attempt number.
        error_message: Error message to log.
    Raises:
        RuntimeError: If max retries reached.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY * (2**attempt)
        log.warning(
            f"{error_message}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{error_message} after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{error_message} after {__MAX_RETRIES} attempts")


def handle_response_status(response: requests.Response, attempt: int) -> Any | None:
    """
    Handle HTTP response status and return JSON if successful.
    Args:
        response: HTTP response object.
        attempt: Current attempt number.
    Returns:
        JSON response if successful, None if should retry.
    Raises:
        RuntimeError: If response indicates permanent error or max retries reached.
    """
    if response.status_code == 200:
        return response.json()

    # Check if status code is retryable (rate limits and server errors)
    if response.status_code in [429, 500, 502, 503, 504]:
        handle_retry_logic(attempt, f"Request failed with status {response.status_code}")
        return None

    # Non-retryable error
    log.error(f"Query execution failed with status {response.status_code}: {response.text}")
    raise RuntimeError(f"Query execution failed: {response.status_code} - {response.text}")


def execute_questdb_query(configuration: dict, query: str) -> Any:
    """
    Execute a SQL query against QuestDB REST API with retry logic.
    Args:
        configuration: Configuration dictionary.
        query: SQL query to execute.
    Returns:
        JSON response from QuestDB.
    Raises:
        RuntimeError: If the API request fails after all retry attempts.
    """
    url = build_questdb_url(configuration, query)
    headers = build_auth_header(configuration)

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=__REQUEST_TIMEOUT_SEC)
            result = handle_response_status(response, attempt)
            if result is not None:
                return result

        except requests.Timeout:
            handle_retry_logic(attempt, "Request timeout")

        except requests.RequestException as e:
            handle_retry_logic(attempt, f"Request exception: {str(e)}")

    # If we've exhausted all retries, raise an exception
    log.error(f"Failed to execute query after {__MAX_RETRIES} attempts")
    raise RuntimeError(f"Failed to execute query after {__MAX_RETRIES} attempts")


def build_sync_query(
    table_name: str, timestamp_col: str, last_timestamp: str | None, offset: int, batch_size: int
) -> str:
    """
    Build SQL query for table sync with optional incremental filtering.
    Args:
        table_name: Name of the table to sync.
        timestamp_col: Name of the timestamp column.
        last_timestamp: Last synced timestamp for incremental sync, None for full sync.
        offset: Offset for pagination.
        batch_size: Number of records per batch.
    Returns:
        SQL query string.
    Raises:
        ValueError: If table_name or timestamp_col contain invalid characters.
    """
    if not validate_identifier(table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    if not validate_identifier(timestamp_col):
        raise ValueError(f"Invalid column name: {timestamp_col}")

    if last_timestamp:
        return f"SELECT * FROM {table_name} WHERE {timestamp_col} >= '{last_timestamp}' ORDER BY {timestamp_col} LIMIT {offset},{batch_size}"
    return f"SELECT * FROM {table_name} ORDER BY {timestamp_col} LIMIT {offset},{batch_size}"


def find_timestamp_index(column_names: list, timestamp_col: str) -> int | None:
    """
    Find the index of timestamp column in column names list.
    Args:
        column_names: List of column names.
        timestamp_col: Name of the timestamp column to find.
    Returns:
        Index of timestamp column or None if not found.
    """
    for idx, col_name in enumerate(column_names):
        if col_name == timestamp_col:
            return idx
    return None


def transform_row_to_record(
    row: list,
    column_names: list,
    timestamp_idx: int | None,
    table_name: str,
    row_idx: int,
    offset: int,
) -> tuple[dict, str | None]:
    """
    Transform a row from QuestDB response into a record dictionary.
    Args:
        row: Row data from QuestDB.
        column_names: List of column names.
        timestamp_idx: Index of timestamp column.
        table_name: Name of the table.
        row_idx: Row index within the current batch.
        offset: Global offset for this batch to ensure unique keys across all batches.
    Returns:
        Tuple of (record dictionary, row timestamp value).
    """
    record = {}
    row_timestamp = None

    for idx, value in enumerate(row):
        if idx < len(column_names):
            record[column_names[idx]] = value
            if idx == timestamp_idx:
                row_timestamp = value

    record["_fivetran_synced_key"] = f"{table_name}_{row_timestamp}_{offset + row_idx}"
    return record, row_timestamp


def checkpoint_if_needed(
    records_since_checkpoint: int, state: dict, table_name: str, max_timestamp: str | None
) -> int:
    """
    Checkpoint state if threshold reached and return reset counter.
    Args:
        records_since_checkpoint: Number of records processed since last checkpoint.
        state: Current state dictionary.
        table_name: Name of the table being synced.
        max_timestamp: Maximum timestamp seen so far.
    Returns:
        Reset counter (0 if checkpointed, unchanged otherwise).
    """
    if records_since_checkpoint >= __CHECKPOINT_INTERVAL:
        if max_timestamp:
            state[f"{table_name}_last_timestamp"] = max_timestamp
        state["last_sync_time"] = datetime.now(timezone.utc).isoformat()
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
        log.info(f"Checkpointed at timestamp {max_timestamp} for {table_name}")
        return 0
    return records_since_checkpoint


def process_batch(
    dataset: list,
    columns: list,
    timestamp_col: str,
    table_name: str,
    max_timestamp: str | None,
    offset: int,
) -> tuple[int, str | None]:
    """
    Process a batch of records and upsert to destination.
    Args:
        dataset: List of rows from QuestDB response.
        columns: Column metadata from QuestDB response.
        timestamp_col: Name of timestamp column.
        table_name: Name of the table.
        max_timestamp: Current maximum timestamp.
        offset: Global offset for this batch to ensure unique keys across all batches.
    Returns:
        Tuple of (number of records processed, new maximum timestamp).
    """
    column_names = [col["name"] for col in columns]
    timestamp_idx = find_timestamp_index(column_names, timestamp_col)
    records_processed = 0
    new_max_timestamp = max_timestamp

    for row_idx, row in enumerate(dataset):
        record, row_timestamp = transform_row_to_record(
            row, column_names, timestamp_idx, table_name, row_idx, offset
        )

        if row_timestamp and (new_max_timestamp is None or row_timestamp > new_max_timestamp):
            new_max_timestamp = row_timestamp

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table_name, data=record)
        records_processed += 1

    return records_processed, new_max_timestamp


def sync_table_data(configuration: dict, table_name: str, state: dict) -> int:
    """
    Sync data from a QuestDB table with timestamp-based incremental sync.
    Args:
        configuration: Configuration dictionary.
        table_name: Name of the table to sync.
        state: State dictionary for tracking sync progress.
    Returns:
        Number of records synced.
    """
    batch_size = int(configuration.get("batch_size", __BATCH_SIZE))
    timestamp_col = configuration.get("timestamp_column", "timestamp")
    last_timestamp = state.get(f"{table_name}_last_timestamp")
    offset = 0
    total_records = 0
    records_since_checkpoint = 0
    max_timestamp = last_timestamp

    # Log sync type
    sync_type = "incremental" if last_timestamp else "full"
    log_message = f"Starting {sync_type} sync for {table_name}"
    if last_timestamp:
        log_message += f" from {last_timestamp}"
    log.info(log_message)

    # Pagination loop
    while True:
        query = build_sync_query(table_name, timestamp_col, last_timestamp, offset, batch_size)

        try:
            response = execute_questdb_query(configuration, query)
            columns = response.get("columns", [])
            dataset = response.get("dataset", [])

            # Check if pagination complete
            if not dataset:
                log.info(f"No more data to sync for table {table_name}")
                break

            # Process batch of records
            batch_records, max_timestamp = process_batch(
                dataset, columns, timestamp_col, table_name, max_timestamp, offset
            )
            total_records += batch_records
            records_since_checkpoint += batch_records
            offset += len(dataset)

            # Checkpoint if needed
            records_since_checkpoint = checkpoint_if_needed(
                records_since_checkpoint, state, table_name, max_timestamp
            )

            # Check if last page
            if len(dataset) < batch_size:
                log.info(f"Reached end of table {table_name}")
                break

        except (RuntimeError, requests.RequestException, KeyError, ValueError, IndexError) as e:
            log.error(f"Error syncing table {table_name}: {str(e)}")
            raise RuntimeError(f"Failed to sync table {table_name}: {str(e)}")

    # Final checkpoint
    if max_timestamp:
        state[f"{table_name}_last_timestamp"] = max_timestamp
    state["last_sync_time"] = datetime.now(timezone.utc).isoformat()
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info(f"Completed sync for {table_name}, total records: {total_records}")
    return total_records


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: SOURCE_EXAMPLES : QUESTDB_CONNECTOR")

    validate_configuration(configuration=configuration)

    tables = configuration.get("tables", "").split(",")

    for table in tables:
        table_name = table.strip()
        if not table_name:
            continue

        try:
            records_synced = sync_table_data(configuration, table_name, state)
            log.info(f"Successfully synced {records_synced} records from table {table_name}")
        except RuntimeError as e:
            log.error(f"Failed to sync table {table_name}: {str(e)}")
            raise


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
