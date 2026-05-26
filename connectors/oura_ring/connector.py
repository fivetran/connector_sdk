"""
Oura Ring Connector Example - Syncs daily activity, sleep, readiness, stress, and heart rate
data from the Oura Ring API v2 to your Fivetran destination.

This connector implements incremental syncing using date-based cursors and handles
cursor-based pagination via next_token. Nested contributor objects are flattened
and time-series arrays are serialized to JSON strings for warehouse compatibility.

See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For date calculations and incremental sync ranges
from datetime import datetime, timedelta

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# API Configuration Constants
__BASE_URL = "https://api.ouraring.com"
__API_TIMEOUT_SECONDS = 30

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

# Sync Configuration Constants
__DEFAULT_LOOKBACK_DAYS = 90
__HEART_RATE_MAX_RANGE_DAYS = 30

# Table Configuration - maps table names to their API endpoint details
__TABLE_CONFIG = {
    "daily_activity": {
        "endpoint": "/v2/usercollection/daily_activity",
        "primary_key": ["id"],
        "start_param": "start_date",
        "end_param": "end_date",
    },
    "daily_sleep": {
        "endpoint": "/v2/usercollection/daily_sleep",
        "primary_key": ["id"],
        "start_param": "start_date",
        "end_param": "end_date",
    },
    "daily_readiness": {
        "endpoint": "/v2/usercollection/daily_readiness",
        "primary_key": ["id"],
        "start_param": "start_date",
        "end_param": "end_date",
    },
    "daily_stress": {
        "endpoint": "/v2/usercollection/daily_stress",
        "primary_key": ["id"],
        "start_param": "start_date",
        "end_param": "end_date",
    },
    "heart_rate": {
        "endpoint": "/v2/usercollection/heartrate",
        "primary_key": ["timestamp"],
        "start_param": "start_datetime",
        "end_param": "end_datetime",
        "max_range_days": __HEART_RATE_MAX_RANGE_DAYS,
    },
}


def flatten_dict(d, parent_key="", sep="_"):
    """
    Flatten nested dictionaries and serialize lists to JSON strings.
    REQUIRED for Fivetran compatibility.

    Args:
        d: Dictionary to flatten
        parent_key: Prefix for nested keys (used in recursion)
        sep: Separator between nested key levels

    Returns:
        Flattened dictionary with all nested structures resolved
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, (list, tuple)):
            items.append((new_key, json.dumps(v) if v else None))
        else:
            items.append((new_key, v))
    return dict(items)


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = ["personal_access_token"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")

    lookback_days = configuration.get("lookback_days")
    if lookback_days is not None:
        try:
            lookback_value = int(lookback_days)
        except (TypeError, ValueError):
            raise ValueError("lookback_days must be a valid positive integer")
        if lookback_value < 1:
            raise ValueError("lookback_days must be a positive integer")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": table_name, "primary_key": config["primary_key"]}
        for table_name, config in __TABLE_CONFIG.items()
    ]


def create_session(configuration: dict):
    """
    Create an authenticated requests session for the Oura API.

    Args:
        configuration: Configuration dictionary with personal_access_token

    Returns:
        requests.Session configured with Bearer token authentication
    """
    session = requests.Session()
    personal_access_token = configuration.get("personal_access_token")
    session.headers.update(
        {
            "Authorization": f"Bearer {personal_access_token}",
            "User-Agent": "Fivetran-Oura-Ring-Connector/1.0",
        }
    )
    return session


def fetch_data_with_retry(session, url, params=None):
    """
    Fetch data from API with exponential backoff retry logic.

    Args:
        session: requests.Session object for connection pooling
        url: Full URL to fetch
        params: Optional query parameters

    Returns:
        JSON response as dictionary

    Raises:
        RuntimeError: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=__API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.error(f"Connection failed after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}")

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.error(f"Timeout after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}")

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )

            # Handle authentication/authorization errors immediately
            if status_code in (401, 403):
                msg = (
                    f"HTTP {status_code}: Check your personal_access_token "
                    f"and API scopes. URL: {url}"
                )
                log.error(msg)
                raise RuntimeError(msg) from e

            should_retry = status_code in __RETRYABLE_STATUS_CODES

            if should_retry and attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Request failed with status {status_code}, "
                    f"retrying in {delay_seconds}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                attempts = attempt + 1
                log.error(
                    f"Request failed after {attempts} attempt(s). "
                    f"URL: {url}, Status: {status_code or 'N/A'}, "
                    f"Error: {str(e)}"
                )
                raise RuntimeError(f"API request failed after {attempts} attempt(s): {e}") from e


def build_date_params(table_name, table_config, start_date_str, end_date_str):
    """
    Build date query parameters appropriate for the endpoint type.

    Daily endpoints use start_date/end_date (YYYY-MM-DD format).
    Heart rate endpoint uses start_datetime/end_datetime (ISO 8601 format).

    Args:
        table_name: Name of the table being synced
        table_config: Configuration dict for this table
        start_date_str: Start date as YYYY-MM-DD string
        end_date_str: End date as YYYY-MM-DD string

    Returns:
        Dictionary of query parameters for the API request
    """
    start_param = table_config["start_param"]
    end_param = table_config["end_param"]

    if table_name == "heart_rate":
        return {
            start_param: f"{start_date_str}T00:00:00",
            end_param: f"{end_date_str}T23:59:59",
        }

    return {
        start_param: start_date_str,
        end_param: end_date_str,
    }


def generate_date_chunks(start_date, end_date, max_days):
    """
    Split a date range into chunks of a maximum number of days.

    Used for endpoints like heart_rate that have API-enforced date range limits.

    Args:
        start_date: Start date as a date object
        end_date: End date as a date object
        max_days: Maximum number of days per chunk

    Returns:
        List of (start_date_str, end_date_str) tuples in YYYY-MM-DD format
    """
    chunks = []
    current_start = start_date

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=max_days - 1), end_date)
        chunks.append(
            (
                current_start.strftime("%Y-%m-%d"),
                current_end.strftime("%Y-%m-%d"),
            )
        )
        current_start = current_end + timedelta(days=1)

    return chunks


def sync_table(session, table_name, table_config, start_date_str, end_date_str, state):
    """
    Sync a single table with cursor-based pagination and checkpointing.

    Fetches records from the Oura API endpoint, flattens nested structures,
    and upserts records to the Fivetran destination. Checkpoints state after
    each page to support resumable syncs.

    Args:
        session: Authenticated requests session
        table_name: Name of the destination table
        table_config: Configuration dict with endpoint, primary_key, and date params
        start_date_str: Start date as YYYY-MM-DD string
        end_date_str: End date as YYYY-MM-DD string
        state: State dictionary for tracking sync progress

    Raises:
        RuntimeError: If API requests fail after max retries
    """
    pk_field = table_config["primary_key"][0]
    endpoint = table_config["endpoint"]
    next_token_key = f"{table_name}_next_token"
    next_token = state.get(next_token_key)
    record_count = 0
    page_count = 0

    log.info(f"Starting sync for table: {table_name}")

    while True:
        page_count += 1
        params = build_date_params(table_name, table_config, start_date_str, end_date_str)

        if next_token:
            params["next_token"] = next_token

        log.info(f"{table_name}: Fetching page {page_count}")

        url = f"{__BASE_URL}{endpoint}"
        data = fetch_data_with_retry(session, url, params=params)
        records = data.get("data", [])

        if not records:
            # Clear any stale next_token to prevent reuse on subsequent runs
            state[next_token_key] = None
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            break

        batch_size = len(records)
        log.info(f"{table_name}: Processing batch of {batch_size} records")

        for record in records:
            if pk_field not in record:
                log.warning(f"Skipping {table_name} record without primary key '{pk_field}'")
                continue

            flattened = flatten_dict(record)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=table_name, data=flattened)
            record_count += 1

        next_token = data.get("next_token")
        state[next_token_key] = next_token

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        if not next_token:
            break

    log.info(
        f"Completed sync: {record_count} {table_name} records synced across {page_count} pages"
    )


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: connectors : oura_ring")

    validate_configuration(configuration)

    session = create_session(configuration)
    lookback_days = int(configuration.get("lookback_days", str(__DEFAULT_LOOKBACK_DAYS)))

    end_date = datetime.now().date()
    last_sync_date = state.get("last_sync_date")

    if last_sync_date:
        start_date = datetime.strptime(last_sync_date, "%Y-%m-%d").date()
        log.info(f"Incremental sync from {start_date} to {end_date}")
    else:
        start_date = end_date - timedelta(days=lookback_days)
        log.info(
            f"Initial sync: fetching last {lookback_days} days from {start_date} to {end_date}"
        )

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    try:
        for table_name, table_config in __TABLE_CONFIG.items():
            try:
                max_range_days = table_config.get("max_range_days")
                if max_range_days:
                    chunks = generate_date_chunks(start_date, end_date, max_range_days)
                    log.info(
                        f"{table_name}: Splitting into {len(chunks)} date chunks of {max_range_days} days"
                    )
                    for chunk_start, chunk_end in chunks:
                        sync_table(
                            session,
                            table_name,
                            table_config,
                            chunk_start,
                            chunk_end,
                            state,
                        )
                else:
                    sync_table(
                        session,
                        table_name,
                        table_config,
                        start_date_str,
                        end_date_str,
                        state,
                    )
            except RuntimeError as e:
                error_msg = str(e)
                is_access_error = "403" in error_msg or "426" in error_msg
                if table_name == "daily_stress" and is_access_error:
                    log.warning(
                        f"Skipping {table_name}: access restricted "
                        f"(check API token scopes or Oura subscription tier)"
                    )
                else:
                    raise

        state["last_sync_date"] = end_date_str
        for table_name in __TABLE_CONFIG:
            state[f"{table_name}_next_token"] = None

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info("Sync complete for all tables")

    finally:
        session.close()


# Create the connector object using the schema and update functions
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
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug()
