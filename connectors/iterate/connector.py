"""This connector extracts NPS survey data from Iterate's REST API and loads it into Fivetran destination.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

import requests  # For making HTTP requests to the Iterate API
import json  # For reading configuration from a JSON file
import time  # For handling retries and delays
from datetime import datetime, timezone  # For handling date and time operations
from typing import Dict, Optional, Any  # For type hinting

__BASE_URL = "https://iteratehq.com/api/v1"  # Base URL for Iterate API
__API_VERSION = "20230101"  # API version date parameter
__MAX_RETRIES = 3  # Number of retries for API calls
__RETRY_DELAY = 1  # Initial delay between retries in seconds
__EPOCH_START_DATE = "1970-01-01T00:00:00Z"  # Default start date if none provided


def parse_iso_datetime_to_unix(date_string: str) -> int:
    """
    Parse ISO datetime string to unix timestamp.
    Expects format: YYYY-MM-DDTHH:MM:SSZ (UTC timezone only)
    Args:
        date_string: ISO datetime string in UTC format
    Returns:
        Unix timestamp as integer
    Raises:
        ValueError: if date format is invalid
    """
    try:
        # Replace 'Z' with '+00:00' for proper ISO format parsing
        dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        raise ValueError(
            f"Invalid datetime format: {date_string}. Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., '2023-01-01T00:00:00Z')"
        )


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
    required_configs = ["api_token"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate start_date format if provided (must be in UTC format with 'Z' suffix)
    start_date = configuration.get("start_date")
    if start_date:
        if not start_date.endswith("Z"):
            raise ValueError(
                f"Invalid start_date format: {start_date}. Must end with 'Z' to indicate UTC timezone. Expected format: YYYY-MM-DDTHH:MM:SSZ"
            )

        # Test parsing to ensure it's valid
        try:
            parse_iso_datetime_to_unix(start_date)
        except ValueError:
            raise ValueError(
                f"Invalid start_date format: {start_date}. Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., '2023-01-01T00:00:00Z')"
            )


def make_api_request(
    url: str, headers: Dict[str, str], params: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Make API request to Iterate with retry logic and exponential backoff.
    Args:
        url: The API endpoint URL
        headers: Request headers including authentication
        params: Query parameters for the request
    Returns:
        Dictionary containing the API response
    Raises:
        RuntimeError: if API request fails after all retries
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.warning(f"API request failed (attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                # Exponential backoff strategy
                delay = __RETRY_DELAY * (2**attempt)
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Failed to make API request after {__MAX_RETRIES} attempts: {str(e)}"
                )

    raise RuntimeError(f"Failed to make API request after {__MAX_RETRIES} attempts")


def flatten_dict(data: Dict[str, Any], parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
    """
    Flatten nested dictionary structure for table columns.
    Args:
        data: Dictionary to flatten
        parent_key: Parent key for nested structures
        sep: Separator to use between keys
    Returns:
        Flattened dictionary
    """
    items = []
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        elif isinstance(value, list):
            # Convert lists to JSON strings for storage
            items.append((new_key, json.dumps(value)))
        else:
            items.append((new_key, value))
    return dict(items)


def make_iterate_api_call(
    endpoint: str, api_token: str, params: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Make a standardized API call to the Iterate API with common headers and error handling.
    Args:
        endpoint: The API endpoint path (e.g., "/surveys" or "/surveys/123/responses")
        api_token: API token for authentication
        params: Optional query parameters for the request
    Returns:
        Dictionary containing the API response
    Raises:
        RuntimeError: if API request fails after all retries
    """
    headers = {"x-api-key": api_token, "Content-Type": "application/json"}

    # Ensure version parameter is always included
    if not params:
        params = {}
    if "v" not in params:
        params["v"] = __API_VERSION

    url = f"{__BASE_URL}{endpoint}"
    log.info(f"Making API call to: {endpoint}")

    return make_api_request(url, headers, params)


def process_surveys_and_responses(api_token: str, start_date_unix: int) -> int:
    """
    Fetch surveys and process their responses immediately without accumulating survey IDs in memory.
    This approach processes each survey and its responses on-the-fly to minimize memory usage.
    Args:
        api_token: API token for authentication
        start_date_unix: Unix timestamp for filtering responses
    Returns:
        Total number of responses processed across all surveys
    """
    log.info("Fetching surveys from Iterate API")
    response_data = make_iterate_api_call("/surveys", api_token)

    surveys = response_data.get("results", [])
    log.info(f"Retrieved {len(surveys)} surveys")

    total_responses = 0

    # Process each survey immediately without accumulating in memory
    for survey in surveys:
        flattened_survey = flatten_dict(survey)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="survey", data=flattened_survey)

        # Process responses for this survey immediately
        survey_id = survey.get("id")

        if survey_id:
            survey_response_count = process_survey_responses(api_token, survey_id, start_date_unix)
            total_responses += survey_response_count

    log.info(
        f"Successfully processed {len(surveys)} surveys with {total_responses} total responses"
    )
    return total_responses


def fetch_survey_responses(
    api_token: str,
    survey_id: str,
    start_date: Optional[int] = None,
    next_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch responses for a specific survey with pagination support and optional date filtering.
    Args:
        api_token: API token for authentication
        survey_id: ID of the survey to fetch responses for
        start_date: Optional unix timestamp to filter responses from this date onwards
        next_url: URL for next page if pagination is needed
    Returns:
        Dictionary containing responses data and pagination info
    """
    if next_url:
        # For pagination, use the provided URL directly
        headers = {"x-api-key": api_token, "Content-Type": "application/json"}
        log.info(f"Fetching responses for survey {survey_id} (paginated)")
        return make_api_request(next_url, headers, None)
    else:
        # For initial request, use the standardized API call
        params = {}
        if start_date:
            params["start_date"] = str(start_date)

        endpoint = f"/surveys/{survey_id}/responses"
        log_message = f"Fetching responses for survey {survey_id}"
        if start_date:
            log_message += f" from {start_date}"
        log.info(log_message)

        return make_iterate_api_call(endpoint, api_token, params)


def determine_sync_start_date(state: dict, configuration: dict) -> str:
    """
    Determine the start date for this sync based on priority order.
    Priority: 1) last_survey_sync from state, 2) config start_date, 3) EPOCH time
    Args:
        state: Dictionary containing state information from previous runs
        configuration: Dictionary containing connection details
    Returns:
        ISO datetime string for sync start date
    """
    last_survey_sync = state.get("last_survey_sync")
    config_start_date = configuration.get("start_date")

    if last_survey_sync:
        # Incremental sync: use last successful sync timestamp
        log.info(f"Incremental sync from saved state: {last_survey_sync}")
        return last_survey_sync
    elif config_start_date:
        # First sync with configured start date
        log.info(f"Initial sync from configured start_date: {config_start_date}")
        return config_start_date
    else:
        # First sync with EPOCH time (all data)
        log.info(f"Initial sync from EPOCH time: {__EPOCH_START_DATE}")
        return __EPOCH_START_DATE


def convert_to_unix_timestamp(sync_start_date: str) -> int:
    """
    Convert ISO datetime string to unix timestamp for API filtering.
    Args:
        sync_start_date: ISO datetime string to convert
    Returns:
        Unix timestamp as integer
    """
    try:
        start_date_unix = parse_iso_datetime_to_unix(sync_start_date)
        log.info(f"Using start_date unix timestamp: {start_date_unix}")
        return start_date_unix
    except ValueError as e:
        log.warning(
            f"Invalid sync_start_date format: {sync_start_date}, using EPOCH time. Error: {e}"
        )
        # Fallback to EPOCH time
        return 0


def process_survey_responses(api_token: str, survey_id: str, start_date_unix: int) -> int:
    """
    Process all responses for a specific survey with pagination support.
    Args:
        api_token: API token for authentication
        survey_id: ID of the survey to process responses for
        start_date_unix: Unix timestamp for filtering responses
    Returns:
        Number of responses processed for this survey
    """
    response_count = 0
    next_url = None

    # Fetch all responses for this survey with pagination
    while True:
        response_data = fetch_survey_responses(api_token, survey_id, start_date_unix, next_url)

        if "results" not in response_data:
            break

        results = response_data.get("results", {})
        response_list = results.get("list", [])

        if not response_list:
            break

        # Process and upsert responses
        for response in response_list:
            # Add survey_id to each response for foreign key relationship
            response["survey_id"] = survey_id
            flattened_response = flatten_dict(response)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table="response", data=flattened_response)
            response_count += 1

        log.info(f"Processed {len(response_list)} responses for survey {survey_id}")

        # Check if there are more pages
        links = response_data.get("links", {})
        next_url = links.get("next")

        # If no next URL, we've processed all pages for this survey
        if not next_url:
            break

    return response_count


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    return [
        {
            "table": "survey",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
        },
        {
            "table": "response",  # Name of the table for survey responses, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
        },
    ]


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
    log.warning("Example: Source Examples : Iterate NPS Survey Connector")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration)

    api_token = configuration["api_token"]

    # Determine the start date for this sync
    sync_start_date = determine_sync_start_date(state, configuration)

    # Convert sync_start_date to unix timestamp for API filtering
    start_date_unix = convert_to_unix_timestamp(sync_start_date)

    try:
        # Process surveys and their responses in a streaming fashion (most memory-efficient approach)
        log.info("Starting survey and response data sync")
        total_responses = process_surveys_and_responses(api_token, start_date_unix)

        # Final checkpoint with updated state
        new_state = {"last_survey_sync": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(new_state)

        log.info(f"Successfully completed sync. Total responses processed: {total_responses}")

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")


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
