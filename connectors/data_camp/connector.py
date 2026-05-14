"""This connector fetches course catalog data from DataCamp's LMS Catalog API including courses, projects, assessments, practices, tracks, and custom tracks. It flattens nested objects and creates breakout tables for array relationships following Fivetran best practices.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
import requests  # For making HTTP requests to the DataCamp API
import json  # For JSON data handling and serialization
import time  # For retry delays
from typing import Dict, Any, List, Optional

# Base URL for the DataCamp LMS Catalog API
__BASE_URL_DEFAULT = "https://lms-catalog-api.datacamp.com"
__REQUEST_TIMEOUT_SECONDS = 30  # Timeout for API requests in seconds
__MAX_RETRIES = 3  # Maximum number of retry attempts
__RETRY_DELAY_SECONDS = 1  # Initial delay between retries in seconds
__RETRY_BACKOFF_MULTIPLIER = 2  # Exponential backoff multiplier

__ENDPOINTS = {
    "custom_tracks": {
        "url": "/v1/catalog/live-custom-tracks",
        "table": "custom_track",
        "primary_key": ["id"],
    },
    "custom_tracks_content": {
        "table": "custom_track_content",
        "primary_key": ["custom_track_id", "position"],
    },
    "courses": {
        "url": "/v1/catalog/live-courses",
        "table": "course",
        "primary_key": ["id"],
    },
    "courses_chapters": {
        "table": "course_chapter",
        "primary_key": ["id", "course_id"],
    },
    "projects": {
        "url": "/v1/catalog/live-projects",
        "table": "project",
        "primary_key": ["id"],
    },
    "projects_topics": {
        "table": "project_topic",
        "primary_key": ["project_id", "name"],
    },
    "assessments": {
        "url": "/v1/catalog/live-assessments",
        "table": "assessment",
        "primary_key": ["id"],
    },
    "practices": {
        "url": "/v1/catalog/live-practices",
        "table": "practice",
        "primary_key": ["id"],
    },
    "tracks": {
        "url": "/v1/catalog/live-tracks",
        "table": "track",
        "primary_key": ["id"],
    },
    "tracks_content": {
        "table": "track_content",
        "primary_key": ["track_id", "position"],
    },
}


def flatten_item(
    item: Dict[str, Any],
    skip_keys: Optional[List[str]] = None,
    flatten_topic: bool = False,
    flatten_licenses: bool = False,
    flatten_instructors: bool = False,
) -> Dict[str, Any]:
    """
    A generic function to flatten nested objects within an item from the DataCamp API.

    Args:
        item: The dictionary object to flatten.
        skip_keys: A list of top-level keys to skip during processing.
        flatten_topic: Whether to flatten the 'topic' object.
        flatten_licenses: Whether to flatten the 'includedInLicenses' list.
        flatten_instructors: Whether to flatten the 'instructors' list.

    Returns:
        A flattened dictionary.
    """
    flattened_data = {}
    skip_keys = skip_keys or []

    for key, value in item.items():
        if key in skip_keys:
            continue

        if key == "topic" and flatten_topic and isinstance(value, dict):
            flattened_data["topic_name"] = value.get("name")
            flattened_data["topic_description"] = value.get("description")
        elif key == "imageUrl" and isinstance(value, dict):
            flattened_data.update({f"imageUrl_{k}": v for k, v in value.items()})
        elif key == "includedInLicenses" and flatten_licenses and isinstance(value, list):
            flattened_data["includedInLicenses"] = ", ".join(str(v) for v in value)
        elif key == "instructors" and flatten_instructors and isinstance(value, list):
            names = [inst.get("fullName", "") for inst in value if isinstance(inst, dict)]
            flattened_data["instructors"] = ", ".join(names)
        else:
            flattened_data[key] = value

    return flattened_data


def extract_data_from_response(data: Any) -> List[Any]:
    """
    Extract list data from API response in various formats.

    Args:
        data: The API response data, which can be a dict, list, or other type.

    Returns:
        List[Any]: The extracted list of data items.
    """
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]

    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value

    if isinstance(data, list):
        return data

    return [data]


def handle_request_error(e: Exception, endpoint: str, attempt: int) -> bool:
    """
    Handle request errors and determine if retry should continue.

    Args:
        e: The exception that occurred during the request.
        endpoint: The API endpoint that was being accessed.
        attempt: The current attempt number.

    Returns:
        bool: True if retry should continue, False otherwise.
    """
    error_type = (
        "Request failed"
        if isinstance(e, requests.exceptions.RequestException)
        else "Unexpected error"
    )

    if attempt < __MAX_RETRIES:
        delay = __RETRY_DELAY_SECONDS * (__RETRY_BACKOFF_MULTIPLIER ** (attempt - 1))
        log.warning(
            f"{error_type} for {endpoint} (attempt {attempt}/{__MAX_RETRIES}): {e}. Retrying in {delay} seconds..."
        )
        time.sleep(delay)
        return True

    log.error(f"Failed to fetch {endpoint} after {__MAX_RETRIES} attempts: {e}")
    return False


def fetch_endpoint(base_url: str, endpoint: str, bearer_token: str) -> List[Any]:
    """
    Fetch data from a DataCamp API endpoint with proper error handling and retry logic.

    Args:
        base_url (str): Base URL for the API
        endpoint (str): Specific endpoint path to fetch
        bearer_token (str): Authentication token for API access

    Returns:
        List[Any]: List of records from the API endpoint

    Raises:
        Exception: Logs errors but returns empty list on failure after all retries
    """
    url = base_url.rstrip("/") + endpoint
    headers = {"Accept": "application/json", "Authorization": f"Bearer {bearer_token}"}

    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            log.info(f"Attempting to fetch {endpoint} (attempt {attempt}/{__MAX_RETRIES})")
            response = requests.get(url, headers=headers, timeout=__REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()

            extracted_data = extract_data_from_response(data)
            log.info(f"Successfully fetched {len(extracted_data)} records from {endpoint}")
            return extracted_data

        except (requests.exceptions.RequestException, Exception) as e:
            should_continue = handle_request_error(e, endpoint, attempt)
            if not should_continue:
                return []

    return []


def process_endpoint(
    endpoint_config: Dict[str, Any],
    bearer_token: str,
    base_url: str,
    flatten_params: Dict[str, Any],
    breakout_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Generic function to process any DataCamp API endpoint.

    Args:
        endpoint_config: Configuration containing endpoint URL, table name, and primary key info.
        bearer_token: Authentication token for API access.
        base_url: Base URL for the API.
        flatten_params: Parameters to pass to flatten_item function.
        breakout_config: Optional configuration for processing breakout tables.
            Format: {
                "source_key": "content",
                "table_name": "custom_track_content",
                "foreign_key": "custom_track_id"
            }
    """
    endpoint_url = endpoint_config["url"]
    main_table = endpoint_config["table"]
    endpoint_name = endpoint_url.split("/")[-1]  # Extract endpoint name from URL

    log.info(f"Fetching endpoint: {endpoint_url}")
    items = fetch_endpoint(base_url, endpoint_url, bearer_token)

    if items is None:
        log.warning(f"No data received from endpoint {endpoint_url}")
        return

    main_upserted = 0
    breakout_upserted = 0

    for item in items:
        # Process main record
        flattened_item_data = flatten_item(item=item, **flatten_params)
        try:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=main_table, data=flattened_item_data)
            main_upserted += 1
        except Exception as e:
            log.error(f"Failed to upsert record in {main_table}", e)

        # Process breakout table if configured
        if breakout_config:
            breakout_items = item.get(breakout_config["source_key"], [])
            for breakout_item in breakout_items:
                breakout_row = dict(breakout_item)
                breakout_row[breakout_config["foreign_key"]] = item.get("id")
                try:
                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The op.upsert method is called with two arguments:
                    # - The first argument is the name of the table to upsert the data into.
                    # - The second argument is a dictionary containing the data to be upserted.
                    op.upsert(table=breakout_config["table_name"], data=breakout_row)
                    breakout_upserted += 1
                except Exception as e:
                    log.error(
                        f"Failed to upsert {breakout_config['source_key']} for {main_table} {item.get('id')}",
                        e,
                    )

    log.info(f"Upserted {main_upserted} records into {main_table}")
    if breakout_config:
        log.info(f"Upserted {breakout_upserted} records into {breakout_config['table_name']}")

    # Checkpoint progress
    checkpoint_key = endpoint_name.replace("live-", "").replace("-", "_")

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state={"last_synced_endpoint": checkpoint_key})


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # Only include tables, not endpoints without a table key
    return [
        {"table": value["table"], "primary_key": value["primary_key"]}
        for key, value in __ENDPOINTS.items()
        if "table" in value
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    if "bearer_token" not in configuration:
        raise ValueError("Missing required configuration value: 'bearer_token'")


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

    log.warning("Example: Source Examples : DataCamp")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration)

    # Extract configuration values
    bearer_token = configuration["bearer_token"]
    base_url = configuration.get("base_url", __BASE_URL_DEFAULT)

    # Process custom tracks
    process_endpoint(
        __ENDPOINTS["custom_tracks"],
        bearer_token,
        base_url,
        {"skip_keys": ["content"], "flatten_topic": True},
        {
            "source_key": "content",
            "table_name": "custom_track_content",
            "foreign_key": "custom_track_id",
        },
    )

    # Process courses
    process_endpoint(
        __ENDPOINTS["courses"],
        bearer_token,
        base_url,
        {
            "skip_keys": ["chapters"],
            "flatten_topic": True,
            "flatten_licenses": True,
            "flatten_instructors": True,
        },
        {"source_key": "chapters", "table_name": "course_chapter", "foreign_key": "course_id"},
    )

    # Process projects
    process_endpoint(
        __ENDPOINTS["projects"],
        bearer_token,
        base_url,
        {"skip_keys": ["topics"], "flatten_instructors": True},
        {"source_key": "topics", "table_name": "project_topic", "foreign_key": "project_id"},
    )

    # Process tracks
    process_endpoint(
        __ENDPOINTS["tracks"],
        bearer_token,
        base_url,
        {"skip_keys": ["content"], "flatten_topic": True, "flatten_licenses": True},
        {"source_key": "content", "table_name": "track_content", "foreign_key": "track_id"},
    )

    # Process practices
    process_endpoint(__ENDPOINTS["practices"], bearer_token, base_url, {})

    # Process assessments
    process_endpoint(__ENDPOINTS["assessments"], bearer_token, base_url, {})


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
