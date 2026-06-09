"""
Apache Druid Connector for Fivetran Connector SDK.
This connector demonstrates how to fetch data from Apache Druid and sync it to destination.
Supports SQL queries, incremental sync, and proper error handling.

See the Technical Reference documentation
(https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Used for encoding credentials for basic authentication
import base64

# Used for parsing JSON configuration
import json

# Used for making HTTP requests to the Druid SQL API
import requests

# Used for replacing invalid characters in table names
import re

# Used for sleep delays between retries and batch requests
import time

# Used for parsing timestamps for safe comparison
from datetime import datetime, timezone

# Constants for API configuration
__REQUEST_TIMEOUT = 30  # Timeout for API requests in seconds
__RATE_LIMIT_DELAY = 2  # Base for exponential backoff calculation (2^attempt)
__MAX_RETRIES = 3  # Maximum number of retries for failed requests
__BATCH_SIZE = 10000  # Number of records to fetch per request
__EPOCH_START = "1970-01-01T00:00:00+00:00"  # Default start timestamp for full sync (ISO 8601)
__CHECKPOINT_INTERVAL = 1000  # Number of records between mid-sync checkpoints
__PAGINATION_DELAY_SECONDS = 1  # Delay in seconds between paginated batch requests
__DEFAULT_PROTOCOL = "https"  # Default protocol for Druid connections
__DEFAULT_HEADERS = {"Content-Type": "application/json"}  # Default HTTP headers for API requests


def to_iso_timestamp(ts: str | datetime) -> str:
    """
    Normalize a timestamp to ISO 8601 format for use with Druid's TIME_PARSE() function.

    Accepts a datetime object or a string in either ISO 8601 format (e.g.
    '2015-09-12T23:59:59.200Z') or the legacy Druid SQL format ('yyyy-MM-dd HH:mm:ss')
    that may be present in older state values.
    Always returns a full ISO 8601 string with UTC offset (e.g. '2015-09-12T23:59:59.200000+00:00').
    """
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    # Handle legacy 'yyyy-MM-dd HH:mm:ss' values that may exist in state from older syncs
    if "T" not in ts:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
    # Already ISO 8601 — normalise Z suffix for Python < 3.11 then round-trip to ensure consistency
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).isoformat()


def sanitize_table_name(name: str) -> str:
    """
    Sanitize a Druid datasource name for use as a destination table name.

    Replaces any character that is not a letter, digit, or underscore with an underscore,
    ensuring the result is a valid identifier in all destination systems.

    Args:
        name: The raw datasource name from Druid

    Returns:
        A sanitized table name safe for use as a destination table identifier
    """
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.

    Args:
        configuration: Dictionary containing connection details

    Raises:
        ValueError: If required configuration is missing or invalid
    """
    required_configs = ["host", "port", "datasources"]

    # Check for required fields
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration: {key}")

    # Validate host
    host = configuration.get("host")
    if not host or not isinstance(host, str) or not host.strip():
        raise ValueError("host must be a non-empty string")

    # Validate port is a valid port number
    port = configuration.get("port")
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        raise ValueError("port must be a valid port number between 1 and 65535") from None
    if port_int < 1 or port_int > 65535:
        raise ValueError("port must be between 1 and 65535")

    # Validate datasources
    datasources = configuration.get("datasources")
    if not datasources or not isinstance(datasources, str) or not datasources.strip():
        raise ValueError("datasources must be a non-empty string (comma-separated list)")

    # Validate optional auth fields if provided
    if "username" in configuration:
        username = configuration.get("username")
        if username and (not isinstance(username, str) or not username.strip()):
            raise ValueError("username must be a non-empty string if provided")

    if "password" in configuration:
        password = configuration.get("password")
        if password and (not isinstance(password, str) or not password.strip()):
            raise ValueError("password must be a non-empty string if provided")

    log.info("Configuration validated successfully")


def make_druid_request(url: str, headers: dict, data: dict):
    """
    Make a POST request to Druid API with proper error handling and retry logic.

    Args:
        url: The API endpoint URL
        headers: Request headers
        data: Request body for the POST request

    Returns:
        Response object from requests library

    Raises:
        RuntimeError: If the request fails after all retries
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=__REQUEST_TIMEOUT)

            # Handle HTTP errors
            if response.status_code >= 400:
                if response.status_code >= 500:
                    # Retry on 5xx server errors
                    if attempt == __MAX_RETRIES - 1:
                        raise RuntimeError(
                            f"Druid server error after {__MAX_RETRIES} attempts. "
                            f"Status: {response.status_code} - {response.text}"
                        )
                    delay = __RATE_LIMIT_DELAY ** (attempt + 1)
                    log.warning(
                        f"Server error {response.status_code}, retrying in {delay} seconds"
                    )
                    time.sleep(delay)
                    continue
                else:
                    # 4xx errors - fail fast
                    raise RuntimeError(
                        f"Druid client error {response.status_code}: {response.text}"
                    )

            return response

        except requests.exceptions.Timeout:
            if attempt == __MAX_RETRIES - 1:
                raise RuntimeError(f"Request timeout after {__MAX_RETRIES} attempts to {url}")
            delay = __RATE_LIMIT_DELAY ** (attempt + 1)
            log.warning(
                f"Request timeout, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
            )
            time.sleep(delay)

        except requests.exceptions.RequestException as e:
            if attempt == __MAX_RETRIES - 1:
                raise RuntimeError(
                    f"Failed to make request to url {url} after {__MAX_RETRIES} attempts: {str(e)}"
                )
            delay = __RATE_LIMIT_DELAY ** (attempt + 1)
            log.warning(
                f"Request attempt {attempt + 1} failed, retrying in {delay} seconds: {str(e)}"
            )
            time.sleep(delay)

    raise RuntimeError(f"Failed to make request after {__MAX_RETRIES} attempts")


def execute_sql_query(base_url: str, headers: dict, query: str):
    """
    Execute a SQL query against Druid and return results.

    Args:
        base_url: Base URL for Druid API
        headers: Request headers including authentication
        query: SQL query string to execute

    Returns:
        List of result rows as dictionaries
    """
    url = f"{base_url}/druid/v2/sql"
    data = {"query": query}

    log.info(f"Executing SQL query: {query[:100]}...")
    response = make_druid_request(url, headers, data)

    results = response.json()
    log.info(f"Query returned {len(results)} rows")
    return results


def fetch_datasource_data(
    base_url: str,
    headers: dict,
    datasource: str,
    timestamp_column: str = "__time",
    since: str | None = None,
):
    """
    Fetch data from a Druid datasource with optional incremental sync.

    Args:
        base_url: Base URL for Druid API
        headers: Request headers
        datasource: Name of the datasource to query
        timestamp_column: Name of the timestamp column for incremental sync
        since: ISO timestamp to fetch records after (None triggers a full fetch)

    Yields:
        Dictionary records from the datasource
    """
    # Use time-based pagination for both full and incremental sync.
    # Full sync starts from epoch; incremental sync starts from the last synced timestamp.
    # Records are sorted by __time so results[-1] is always the max timestamp in the batch.
    # This avoids OFFSET which becomes expensive as tables grow large.
    cursor = since or __EPOCH_START
    total_records = 0

    if since:
        log.info(f"Fetching data from {datasource} since {since}")
    else:
        log.info(f"Fetching full data from {datasource} starting from epoch")

    while True:
        query = f"""
        SELECT *
        FROM "{datasource}"
        WHERE "{timestamp_column}" > TIME_PARSE('{cursor}')
        ORDER BY "{timestamp_column}"
        LIMIT {__BATCH_SIZE}
        """
        results = execute_sql_query(base_url, headers, query)

        if not results:
            log.info(f"No more data to fetch from {datasource}")
            break

        yield from results
        total_records += len(results)
        log.info(f"Fetched {total_records} records so far from {datasource}")

        if len(results) < __BATCH_SIZE:
            break

        # Advance cursor to the last record's __time; results are sorted so this is the max
        cursor = results[-1][timestamp_column]
        time.sleep(__PAGINATION_DELAY_SECONDS)

    log.info(f"Completed fetching {total_records} total records from {datasource}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Validate configuration
    validate_configuration(configuration)

    # Get datasources from configuration
    datasources = configuration.get("datasources", "").split(",")

    # Define schema for each datasource as a separate table
    schema_list = []
    for datasource in datasources:
        datasource = datasource.strip()
        if datasource:
            schema_list.append({"table": sanitize_table_name(datasource)})

    return schema_list


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Connectors - Apache Druid")
    log.info("Starting Apache Druid Connector sync")

    # Extract configuration parameters
    host = configuration.get("host")
    port = configuration.get("port")
    datasources = configuration.get("datasources")
    username = configuration.get("username")
    password = configuration.get("password")

    # Build base URL
    protocol = __DEFAULT_PROTOCOL
    base_url = f"{protocol}://{host}:{port}"
    log.info(f"Connecting to Druid at {base_url}")

    # Prepare headers
    headers = __DEFAULT_HEADERS.copy()

    # Add basic auth if credentials provided
    if username and password:
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
        log.info("Using basic authentication")

    try:
        record_count = 0

        # Start with a copy of existing state so all previous datasource keys are preserved
        current_state = dict(state)

        # Process each datasource
        for datasource in datasources.split(","):
            datasource = datasource.strip()
            if not datasource:
                continue

            log.info(f"Processing datasource: {datasource}")
            table_name = sanitize_table_name(datasource)

            # Get datasource-specific last sync time. None triggers a full fetch for new datasources.
            # Normalize to ISO 8601 to handle any legacy 'yyyy-MM-dd HH:mm:ss' values in state.
            raw_last_sync = current_state.get(f"last_sync_{datasource}")
            datasource_last_sync = to_iso_timestamp(raw_last_sync) if raw_last_sync else None

            # Track max __time from actual data processed as datetime for safe comparison
            max_time_processed: datetime | None = None
            datasource_record_count = 0

            # Fetch and upsert data
            for record in fetch_datasource_data(
                base_url, headers, datasource, "__time", datasource_last_sync
            ):
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table=table_name, data=record)
                record_count += 1
                datasource_record_count += 1

                # Track the maximum __time from actual data using datetime for safe comparison.
                # Replace "Z" with "+00:00" for Python 3.10 compatibility (handled natively in 3.11+).
                # If Druid returns a naive datetime (no timezone), assume UTC for consistent comparison.
                record_time = record.get("__time")
                if record_time:
                    try:
                        record_dt = datetime.fromisoformat(record_time.replace("Z", "+00:00"))
                        if record_dt.tzinfo is None:
                            record_dt = record_dt.replace(tzinfo=timezone.utc)
                        if max_time_processed is None or record_dt > max_time_processed:
                            max_time_processed = record_dt
                    except (ValueError, AttributeError):
                        log.warning(
                            f"Could not parse __time value '{record_time}', skipping for cursor tracking"
                        )

                # Checkpoint periodically for large datasets
                if record_count % __CHECKPOINT_INTERVAL == 0:
                    log.info(f"Processed {record_count} records, checkpointing...")
                    # Save the progress by checkpointing the state. This is important for ensuring that
                    # the sync process can resume from the correct position in case of next sync or interruptions.
                    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
                    # it is safe to write to destination.
                    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                    # Learn more about how and where to checkpoint by reading our best practices documentation
                    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                    current_state[f"last_sync_{datasource}"] = (
                        to_iso_timestamp(max_time_processed)
                        if max_time_processed
                        else datasource_last_sync
                    )
                    op.checkpoint(state=current_state)

            log.info(
                f"Completed processing datasource: {datasource}. "
                f"Processed {datasource_record_count} records. "
                f"Max __time: {max_time_processed or 'N/A'}"
            )
            current_state[f"last_sync_{datasource}"] = (
                to_iso_timestamp(max_time_processed)
                if max_time_processed
                else datasource_last_sync
            )

            # Save the progress by checkpointing the state. This is important for ensuring that
            # the sync process can resume from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
            # it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=current_state)

        log.info(f"Sync completed successfully. Total records processed: {record_count}")

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to sync Apache Druid data: {str(e)}")


# Create connector instance
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Load configuration from configuration.json
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
