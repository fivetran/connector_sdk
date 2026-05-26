"""This connector syncs economic data series and observations from FRED API to Fivetran destination.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For date manipulation and formatting
from datetime import datetime

# For making HTTP requests to FRED API
import requests

# For handling request delays during retries
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Maximum number of retry attempts for API requests
__MAX_RETRIES = 3

# Base delay in seconds for exponential backoff retries
__BASE_DELAY_SECONDS = 2

# Base URL for FRED API
__FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Timeout in seconds for HTTP requests
__REQUEST_TIMEOUT_SECONDS = 60

# Default sync start date for observations if not configured
__DEFAULT_SYNC_START_DATE = "2020-01-01"

# Page size for API pagination
__PAGE_SIZE = 1000

# Checkpoint interval for observations processing
__CHECKPOINT_INTERVAL = 1000


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has
    all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_key", "series_ids"]
    for key in required_configs:
        if key not in configuration:
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
        {"table": "series", "primary_key": ["id"]},
        {"table": "series_observations", "primary_key": ["series_id", "date"]},
        {"table": "categories", "primary_key": ["id"]},
        {"table": "releases", "primary_key": ["id"]},
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
    log.warning("Example: SOURCE_EXAMPLES : FRED_API_CONNECTOR")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    api_key = configuration.get("api_key")
    series_ids_str = configuration.get("series_ids", "")
    sync_start_date = configuration.get("sync_start_date", __DEFAULT_SYNC_START_DATE)

    series_ids = parse_series_ids(series_ids_str)

    if not series_ids:
        log.error("No series IDs provided in configuration")
        raise RuntimeError("No series IDs configured for sync")

    sync_categories(api_key, state)
    sync_releases(api_key, state)
    sync_series_and_observations(api_key, series_ids, sync_start_date, state)


def parse_series_ids(series_ids_str):
    """
    Parse comma-separated series IDs from configuration string.
    Args:
        series_ids_str: Comma-separated string of series IDs.
    Returns:
        list: List of series ID strings.
    """
    if not series_ids_str:
        return []
    return [series_id.strip() for series_id in series_ids_str.split(",") if series_id.strip()]


def make_api_request(endpoint, params, api_key):
    """
    Make an API request to FRED with retry logic and exponential backoff.
    Args:
        endpoint: API endpoint path (e.g., 'series', 'series/observations').
        params: Query parameters dictionary.
        api_key: FRED API key for authentication.
    Returns:
        dict: JSON response from the API.
    Raises:
        RuntimeError: If request fails after retries.
    """
    url = f"{__FRED_BASE_URL}/{endpoint}"
    params["api_key"] = api_key
    params["file_type"] = "json"

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=__REQUEST_TIMEOUT_SECONDS)
            # Validate response object before processing
            response.raise_for_status()
            result = handle_api_response(response, url, attempt)
            if result is not None:
                return result

        except requests.exceptions.HTTPError as error:
            # Handle HTTP errors (4xx, 5xx) through the response status code
            if error.response is not None:
                result = handle_api_response(error.response, url, attempt)
                if result is not None:
                    return result
            else:
                handle_request_exception(attempt, f"Request to {endpoint}", error)

        except requests.exceptions.Timeout:
            handle_timeout_error(attempt, f"Request to {endpoint}")
        except requests.exceptions.RequestException as error:
            handle_request_exception(attempt, f"Request to {endpoint}", error)
    raise RuntimeError(f"Request to {endpoint} failed after {__MAX_RETRIES} attempts.")


def handle_api_response(response, url, attempt):
    """
    Handle API response status codes and return appropriate result.
    Args:
        response: HTTP response object.
        url: API endpoint URL.
        attempt: Current retry attempt number.
    Returns:
        dict or None: JSON response if successful, None to continue retry.
    Raises:
        RuntimeError: If request fails permanently.
    """
    if response.status_code == 200:
        return response.json()

    if response.status_code == 400:
        log.error(f"Bad request: {response.text}")
        raise RuntimeError(f"Bad request to {url}: {response.text}")

    if response.status_code == 404:
        log.warning(f"Resource not found: {url}")
        return {}

    if response.status_code in [429, 500, 502, 503, 504]:
        handle_retryable_error(attempt, response.status_code, f"API request to {url}")
        return None

    log.error(f"Unexpected API error: {response.status_code} - {response.text}")
    raise RuntimeError(f"API error: {response.status_code} - {response.text}")


def handle_retryable_error(attempt, status_code, operation_name):
    """
    Handle retryable HTTP errors with exponential backoff.
    Args:
        attempt: Current retry attempt number.
        status_code: HTTP status code received.
        operation_name: Name of the operation being retried.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{operation_name} failed with status {status_code}, "
            f"retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{operation_name} failed after {__MAX_RETRIES} attempts. Status: {status_code}")
        raise RuntimeError(f"{operation_name} failed after {__MAX_RETRIES} attempts")


def handle_timeout_error(attempt, operation_name):
    """
    Handle timeout errors with exponential backoff.
    Args:
        attempt: Current retry attempt number.
        operation_name: Name of the operation being retried.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{operation_name} timed out, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{operation_name} timed out after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{operation_name} timed out after {__MAX_RETRIES} attempts")


def handle_request_exception(attempt, operation_name, error):
    """
    Handle generic request exceptions with exponential backoff.
    Args:
        attempt: Current retry attempt number.
        operation_name: Name of the operation being retried.
        error: The exception that occurred.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{operation_name} failed, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{operation_name} failed after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{operation_name} failed: {str(error)}")


def sync_categories(api_key, state):
    """
    Sync category data from FRED API.
    Args:
        api_key: FRED API key.
        state: State dictionary for tracking sync progress.
    """
    log.info("Starting categories sync")

    params = {}
    response_data = make_api_request("category/children", params, api_key)

    if not response_data or "categories" not in response_data:
        log.warning("No category data found")
        return

    categories = response_data.get("categories", [])
    process_categories(categories)

    state["categories_last_sync"] = datetime.now().isoformat()

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info(f"Completed categories sync. Synced {len(categories)} categories")


def process_categories(categories):
    """
    Process and upsert category records.
    Args:
        categories: List of category records.
    """
    for category in categories:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="categories", data=category)


def sync_releases(api_key, state):
    """
    Sync release data from FRED API with pagination.
    Args:
        api_key: FRED API key.
        state: State dictionary for tracking sync progress.
    """
    log.info("Starting releases sync")

    offset = 0
    total_synced = 0

    while True:
        params = {"limit": __PAGE_SIZE, "offset": offset}

        log.info(f"Fetching releases at offset {offset}")
        response_data = make_api_request("releases", params, api_key)

        if not response_data or "releases" not in response_data:
            log.warning(f"No release data found at offset {offset}")
            break

        releases = response_data.get("releases", [])

        if not releases:
            break

        process_releases(releases)
        total_synced += len(releases)

        state["releases_last_sync"] = datetime.now().isoformat()

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if len(releases) < __PAGE_SIZE:
            break

        offset += __PAGE_SIZE

    log.info(f"Completed releases sync. Total synced: {total_synced} releases")


def process_releases(releases):
    """
    Process and upsert release records.
    Args:
        releases: List of release records.
    """
    for release in releases:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="releases", data=release)


def sync_series_and_observations(api_key, series_ids, sync_start_date, state):
    """
    Sync series metadata and observations for each configured series ID.
    Args:
        api_key: FRED API key.
        series_ids: List of series IDs to sync.
        sync_start_date: Initial start date for syncing observations.
        state: State dictionary for tracking sync progress.
    """
    log.info(f"Starting sync for {len(series_ids)} series")

    for series_id in series_ids:
        sync_single_series(api_key, series_id, sync_start_date, state)


def sync_single_series(api_key, series_id, sync_start_date, state):
    """
    Sync metadata and observations for a single series.
    Args:
        api_key: FRED API key.
        series_id: Series ID to sync.
        sync_start_date: Initial start date for syncing observations.
        state: State dictionary for tracking sync progress.
    """
    log.info(f"Syncing series: {series_id}")

    params = {"series_id": series_id}
    response_data = make_api_request("series", params, api_key)

    if not response_data or "seriess" not in response_data:
        log.warning(f"Series metadata not found for {series_id}")
        return

    series_list = response_data.get("seriess", [])
    if series_list:
        series_data = series_list[0]

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="series", data=series_data)

    sync_series_observations(api_key, series_id, sync_start_date, state)


def sync_series_observations(api_key, series_id, sync_start_date, state):
    """
    Sync observations for a series with incremental sync support.
    Args:
        api_key: FRED API key.
        series_id: Series ID to sync observations for.
        sync_start_date: Initial start date for syncing observations.
        state: State dictionary for tracking sync progress.
    """
    state_key = f"series_{series_id}_last_observation_date"
    last_observation_date = state.get(state_key)

    observation_start = last_observation_date if last_observation_date else sync_start_date

    log.info(f"Fetching observations for series {series_id} from {observation_start}")

    offset = 0
    total_observations = 0
    records_since_checkpoint = 0
    latest_date = observation_start

    while True:
        params = {
            "series_id": series_id,
            "observation_start": observation_start,
            "limit": __PAGE_SIZE,
            "offset": offset,
            "sort_order": "asc",
        }

        response_data = make_api_request("series/observations", params, api_key)

        if not response_data or "observations" not in response_data:
            log.warning(f"No observations found for series {series_id} at offset {offset}")
            break

        observations = response_data.get("observations", [])

        if not observations:
            break

        for observation in observations:
            observation["series_id"] = series_id
            observation_date = observation.get("date")

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="series_observations", data=observation)

            if observation_date and observation_date > latest_date:
                latest_date = observation_date

            records_since_checkpoint += 1
            total_observations += 1

            if records_since_checkpoint >= __CHECKPOINT_INTERVAL:
                state[state_key] = latest_date

                # Save the progress by checkpointing the state. This is important for ensuring that
                # the sync process can resume from the correct position in case of next sync or
                # interruptions. Learn more about how and where to checkpoint by reading our best
                # practices documentation (https://fivetran.com/docs/connectors/connector-sdk/
                # best-practices#largedatasetrecommendation).
                op.checkpoint(state)
                records_since_checkpoint = 0

        if len(observations) < __PAGE_SIZE:
            break

        offset += __PAGE_SIZE

    state[state_key] = latest_date

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info(
        f"Completed observations sync for series {series_id}. Total observations: {total_observations}"
    )


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
