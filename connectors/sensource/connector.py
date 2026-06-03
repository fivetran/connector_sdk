"""
Sensource API Connector for Fivetran
This connector fetches traffic and occupancy data from Sensource API with OAuth2 authentication.
Sensource API documentation: https://vea.sensourceinc.com/api-docs/
"""

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For date and time operations
from datetime import datetime, timedelta

# For type hints
from typing import Dict, List, Any

# For making HTTP requests
import requests

# For reading configuration from a JSON file
import json

# For handling time delays
import time

"""
Configuration constants for the Sensource connector.

API Configuration:
- AUTH_URL: OAuth2 authentication endpoint
- BASE_URL: Base URL for Sensource API requests

Retry Configuration:
Users can adjust these values based on their needs:
- __MAX_RETRY_ATTEMPTS: Maximum number of retry attempts for failed requests
- __RETRY_BASE_DELAY: Base delay in seconds for exponential backoff

Date Processing Configuration:
Users can modify the chunk size for different data volumes:
- DAYS_PER_CHUNK: Number of days per chunk (creates 30-day ranges with 29 + 1 day overlap)
"""
__AUTH_URL = "https://auth.sensourceinc.com/oauth/token"
__BASE_URL = "https://vea.sensourceinc.com"

__MAX_RETRY_ATTEMPTS = 3
__RETRY_BASE_DELAY = 2

__DAYS_PER_CHUNK = 29


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    # Validate required configuration parameters
    required_configs = ["client_id", "client_secret"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def get_access_token(client_id: str, client_secret: str) -> str:
    """
    Obtain OAuth2 access token from Sensource auth endpoint.
    This function handles the OAuth2 client credentials flow to authenticate with the Sensource API.
    Uses retry logic for improved reliability with network issues and temporary server errors.

    Args:
        client_id: OAuth2 client ID from Sensource
        client_secret: OAuth2 client secret from Sensource

    Returns:
        Access token string for API requests

    Raises:
        ValueError: If no access token is received from the API
        ConnectionError: If authentication request fails due to network issues
    """

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        # Use make_request_with_retry for consistent retry behavior
        response = make_request_with_retry("post", __AUTH_URL, data=payload, headers=headers)

        token_data = response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            log.error("No access token received from authentication endpoint")
            raise ValueError("No access token received from authentication endpoint")

        log.debug("Successfully obtained access token")
        return access_token

    except requests.exceptions.RequestException as e:
        log.error("Authentication request failed", e)
        raise ConnectionError(f"Failed to authenticate with Sensource API: {str(e)}")


def fetch_static_data(endpoint: str, access_token: str) -> List[Dict[str, Any]]:
    """
    Fetch static reference data from Sensource API endpoint.
    This function retrieves reference data that doesn't change frequently (locations, sites, zones, spaces, sensors).
    Static data is fetched without state tracking since it's reference information.

    Args:
        endpoint: API endpoint name (location, site, zone, space, sensor)
        access_token: OAuth2 access token for API authentication

    Returns:
        List of data records from the API endpoint

    Raises:
        ConnectionError: If the API request fails
    """
    url = f"{__BASE_URL}/api/{endpoint}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = make_request_with_retry("get", url, headers=headers)
    data = response.json()
    results = data.get("results", []) if isinstance(data, dict) else data
    log.info(f"Successfully fetched {len(results)} records from {endpoint} endpoint")
    return results


def fetch_data(
    endpoint: str,
    access_token: str,
    start_date: str,
    end_date: str,
    metrics: str,
    entity_type: str = "zone",
) -> List[Dict[str, Any]]:
    """
    Fetch time-series data from Sensource API endpoint.
    This function retrieves traffic or occupancy data for a specific date range with hourly granularity.
    The data is processed in chunks to avoid memory overflow with large datasets.

    Args:
        endpoint: API endpoint name (traffic or occupancy)
        access_token: OAuth2 access token for API authentication
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        metrics: Comma-separated list of metrics to fetch
        entity_type: Entity type for data aggregation (zone for traffic, space for occupancy)

    Returns:
        List of data records from the API endpoint

    Raises:
        ConnectionError: If the API request fails
    """
    url = f"{__BASE_URL}/api/data/{endpoint}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    params = {
        "startDate": start_date,
        "endDate": end_date,
        "dateGroupings": "hour",
        "entityType": entity_type,
        "metrics": metrics,
        "relativeDate": "custom",
    }

    response = make_request_with_retry("get", url, headers=headers, params=params)
    data = response.json()
    results = data.get("results", []) if isinstance(data, dict) else data

    # Calculate the actual data end date (end_date - 1 day since API end_date is non-inclusive)
    actual_end_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    log.info(
        f"Successfully fetched {len(results)} records from {endpoint} endpoint for {start_date} to {actual_end_date}"
    )
    return results


def generate_date_ranges(start_date: str = None) -> List[tuple]:
    """
    Generate date ranges for processing large historical datasets.
    This function creates 30-day chunks to process data efficiently and avoid memory issues.
    Users can modify the DAYS_PER_CHUNK constant to adjust the chunk size based on their data volume.

    Note: Since the API treats end dates as non-inclusive, we adjust the end date
    to be one day later to ensure we get the complete intended range.

    Args:
        start_date: Starting date in YYYY-MM-DD format

    Returns:
        List of (start_date, end_date) tuples where end_date is adjusted for API inclusivity
    """
    ranges = []
    today = datetime.now().strftime("%Y-%m-%d")

    if start_date:
        # If start date is today or in the future, return empty list
        if start_date >= today:
            log.debug(
                f"Start date {start_date} is today or in the future, no date ranges to process"
            )
            return ranges

        # Resume from the last sync date
        current_start = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        # Default to current year if no start_date provided
        current_start = datetime(datetime.now().year, 1, 1)

    end_date = datetime.now()

    while current_start < end_date:
        """
        Create chunks of DAYS_PER_CHUNK days to process data efficiently.
        Add one day to make it inclusive for the API (since API treats end_date as non-inclusive).
        """
        range_end = min(current_start + timedelta(days=__DAYS_PER_CHUNK), end_date)
        api_end_date = range_end + timedelta(days=1)

        ranges.append((current_start.strftime("%Y-%m-%d"), api_end_date.strftime("%Y-%m-%d")))

        current_start = range_end + timedelta(days=1)

    return ranges


def schema(configuration: Dict[str, Any]):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    This function defines the table structure and primary keys for all tables created by the connector.
    Users can modify the primary keys or add additional columns as needed for their specific use case.

    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "traffic", "primary_key": ["zone_id", "record_date_hour_1"]},
        {"table": "occupancy", "primary_key": ["space_id", "record_date_hour_1"]},
        {"table": "location", "primary_key": ["location_id"]},
        {"table": "site", "primary_key": ["site_id"]},
        {"table": "zone", "primary_key": ["zone_id"]},
        {"table": "space", "primary_key": ["space_id"]},
        {"table": "sensor", "primary_key": ["sensor_id"]},
    ]


def update(configuration: Dict[str, Any], state: Dict[str, Any]):
    """
     Define the update function, which is a required function, and is called by Fivetran during each sync.
    This function orchestrates the entire data sync process, including authentication, static data fetching,
    and incremental time-series data processing with proper state management.

    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

    Args:
        configuration: A dictionary containing connection details and sync parameters
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Source Examples : Sensource API Connector")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    client_id = configuration.get("client_id")
    client_secret = configuration.get("client_secret")
    traffic_metrics = configuration.get("traffic_metrics", "ins,outs")
    occupancy_metrics = configuration.get(
        "occupancy_metrics", "occupancy(max),occupancy(min),occupancy(avg)"
    )
    static_endpoints_str = configuration.get("static_endpoints", "location,site,zone,space")
    static_endpoints = [endpoint.strip() for endpoint in static_endpoints_str.split(",")]
    start_date = configuration.get("start_date", "2022-01-01")
    last_sync_date = state.get("last_sync_date")

    try:
        log.debug("Starting Sensource data sync")

        """
        Get access token and fetch static reference data.
        Static data is reference information that doesn't change frequently (no state tracking needed).
        """
        access_token = get_access_token(client_id, client_secret)

        for endpoint in static_endpoints:
            static_records = fetch_static_data(endpoint, access_token)
            for record in static_records:
                op.upsert(table=endpoint, data=record)

        today = datetime.now().strftime("%Y-%m-%d")

        """
        Check sync status and generate date ranges for incremental processing.
        This ensures we process data in manageable chunks to avoid memory issues.
        """
        if last_sync_date == today:
            log.info(f"Already synced to today ({today}), skipping data fetch")
            return

        if last_sync_date:
            log.debug(f"Resuming sync from {last_sync_date}")
            date_ranges = generate_date_ranges(start_date=last_sync_date)
        else:
            log.debug(f"Starting initial sync from {start_date}")
            date_ranges = generate_date_ranges(start_date=start_date)

        log.debug(f"Generated {len(date_ranges)} date ranges to process")

        """
        Process each date range to handle large datasets efficiently.
        Skip ranges that are before last sync date to avoid duplicate processing.
        """
        for start_date, end_date in date_ranges:
            if last_sync_date and end_date < last_sync_date:
                log.debug(f"Skipping already processed range: {start_date} to {end_date}")
                continue

            log.debug(f"Processing date range: {start_date} to {end_date}")

            """
            Fetch and process traffic and occupancy data.

            Traffic data (entity_type = zone): Entry and exit counts by zone
            Occupancy data (entity_type = space): Maximum, minimum, and average occupancy by space
            Upsert operations ensure we have the latest metrics.
            """
            traffic_records = fetch_data(
                "traffic", access_token, start_date, end_date, traffic_metrics, "zone"
            )

            for record in traffic_records:
                op.upsert(table="traffic", data=record)

            occupancy_records = fetch_data(
                "occupancy",
                access_token,
                start_date,
                end_date,
                occupancy_metrics,
                "space",
            )

            for record in occupancy_records:
                op.upsert(table="occupancy", data=record)

            """
            Update state with the current sync time for the next run.
            Save the actual last date that was synced (end_date - 1 day since API end_date is non-inclusive).
            """
            new_state = state.copy()
            actual_end_date = (
                datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y-%m-%d")
            new_state["last_sync_date"] = actual_end_date
            op.checkpoint(state=new_state)

            log.debug(f"Completed processing for {start_date} to {end_date}")

        # Final checkpoint to ensure the complete state is saved
        op.checkpoint(state=new_state)
        log.debug("Sensource data sync completed")

    except Exception as e:
        """
        Handle exceptions by raising a runtime error with descriptive message.
        """
        log.error("Sync failed with error", e)
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def make_request_with_retry(method, url, **kwargs):
    """
    Make HTTP request with retry logic for improved reliability.
    This function implements exponential backoff for 5xx errors and network failures.
    Users can modify __MAX_RETRY_ATTEMPTS and __RETRY_BASE_DELAY constants to adjust retry behavior.

    Args:
        method: HTTP method (get, post, etc.)
        url: Request URL
        **kwargs: Additional arguments for requests library

    Returns:
        Response object from successful request

    Raises:
        ConnectionError: If request fails after all retry attempts
    """
    for attempt in range(__MAX_RETRY_ATTEMPTS):
        try:
            response = requests.request(method, url, **kwargs)

            if response.status_code == 200:
                return response
            elif 500 <= response.status_code < 600 and attempt < __MAX_RETRY_ATTEMPTS - 1:
                # 5xx error, retry with exponential backoff
                delay = __RETRY_BASE_DELAY**attempt
                log.warning(
                    f"5xx error (status {response.status_code}) on attempt {attempt + 1}/{__MAX_RETRY_ATTEMPTS}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
                continue
            else:
                log.error(f"Request failed with status {response.status_code}: {response.text}")
                raise ConnectionError(f"Request failed with status {response.status_code}")

        except requests.exceptions.RequestException as e:
            if attempt < __MAX_RETRY_ATTEMPTS - 1:
                delay = __RETRY_BASE_DELAY**attempt
                log.warning(
                    f"Request failed on attempt {attempt + 1}/{__MAX_RETRY_ATTEMPTS}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
                continue
            else:
                log.error("Request failed", e)
                raise ConnectionError(f"Request failed: {str(e)}")

    # This should never be reached, but ensures all code paths return or raise
    raise ConnectionError(f"Request failed after {__MAX_RETRY_ATTEMPTS} attempts")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

"""
Main execution block for local testing and debugging.

This is Python's standard entry method allowing the script to be run directly from the command line or IDE 'run' button.
This is useful for debugging while writing code. Note this method is not called by Fivetran when executing the connector in production.
Please test using the Fivetran debug command prior to finalizing and deploying your connector.
"""
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    connector.debug(configuration=configuration)
