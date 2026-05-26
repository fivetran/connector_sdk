"""This connector demonstrates how to fetch data from Customer Thermometer API and upsert it into destination using the Fivetran Connector SDK.
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
import requests  # For making HTTP requests to the Customer Thermometer API
import json  # For JSON data handling and serialization
import xml.etree.ElementTree as et  # For parsing XML responses
from datetime import datetime, timezone  # For handling date and time
from typing import Optional  # For type hinting
import time  # For sleep delays in retry logic

# Base URL for the Customer Thermometer API
__BASE_URL = "https://app.customerthermometer.com/api.php"
__API_TIMEOUT_SECONDS = 30  # API request timeout in seconds
__MIN_API_KEY_LENGTH = 10  # Minimum length for a valid API key

# Retry configuration
__MAX_RETRIES = 3  # Maximum number of retry attempts
__RETRY_DELAY_IN_SECONDS = 1  # Initial delay in seconds between retries
__RETRY_BACKOFF = 2  # Backoff multiplier for exponential backoff
__DEFAULT_START_DATE = "1970-01-01"  # Default start date for initial sync


# Constants for metric endpoints
__METRIC_ENDPOINTS = [
    "getNumResponsesValue",
    "getResponseRateValue",
    "getTempRatingValue",
    "getNPSValue",
    "getHappinessValue",
    "getSendQuota",
]

__TABLE_CONFIGS = [
    {
        "table_name": "comment",
        "endpoint": "getComments",
        "root_element": "comments",
        "child_element": "comment",
        "supports_incremental": True,
    },
    {
        "table_name": "blast_result",
        "endpoint": "getBlastResults",
        "root_element": "thermometer_blast_responses",
        "child_element": "thermometer_blast_response",
        "supports_incremental": True,
    },
    {
        "table_name": "recipient_list",
        "endpoint": "getRecipientLists",
        "root_element": "recipient_lists",
        "child_element": "recipient_list",
        "supports_incremental": False,
    },
    {
        "table_name": "thermometer",
        "endpoint": "getThermometers",
        "root_element": "thermometers",
        "child_element": "thermometer",
        "supports_incremental": False,
    },
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
    # Check for required configuration parameters
    if "api_key" not in configuration:
        raise ValueError("Missing required configuration value: api_key")

    # Validate API key format (basic check)
    api_key = configuration.get("api_key")
    if not api_key or len(api_key) < __MIN_API_KEY_LENGTH:
        raise ValueError("Invalid API key format")


def make_api_request(
    endpoint: str, api_key: str, from_date: Optional[str] = None, to_date: Optional[str] = None
) -> requests.Response:
    """
    Make an authenticated request to the Customer Thermometer API with retry logic.
    Args:
        endpoint (str): The API method to call (e.g., 'getComments', 'getThermometers')
        api_key (str): The API key for authentication
        from_date (str, optional): Optional start date filter (YYYY-MM-DD format)
        to_date (str, optional): Optional end date filter (YYYY-MM-DD format)
    Returns:
        requests.Response: The API response object
    Raises:
        requests.RequestException: If the API request fails after all retries
    """
    params = {"apiKey": api_key, "getMethod": endpoint}

    # Add date filters if provided
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["endDate"] = to_date

    for attempt in range(__MAX_RETRIES + 1):
        try:
            response = requests.get(__BASE_URL, params=params, timeout=__API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if attempt == __MAX_RETRIES:
                log.error(
                    f"API request failed for endpoint {endpoint} after {__MAX_RETRIES} retries", e
                )
                raise

            # Calculate delay with exponential backoff
            delay = __RETRY_DELAY_IN_SECONDS * (__RETRY_BACKOFF**attempt)
            log.warning(
                f"API request failed for endpoint {endpoint} (attempt {attempt + 1}/{__MAX_RETRIES + 1}): {str(e)}. Retrying in {delay} seconds..."
            )
            time.sleep(delay)

    raise requests.RequestException(
        f"Unexpected error: failed to complete API request for endpoint {endpoint}"
    )


def parse_xml_response_and_upsert(
    xml_content: str, root_element: str, child_element: str, table_name: str
) -> int:
    """
    Parse XML response from Customer Thermometer API and directly upsert records to avoid memory buffering.
    This approach is more memory efficient as it processes and upserts records one at a time instead of
    loading all records into memory first.
    Args:
        xml_content (str): The XML response content as string
        root_element (str): The root XML element name to search within
        child_element (str): The child XML element name to extract data from
        table_name (str): The name of the table to upsert data into
    Returns:
        int: Number of records processed
    Raises:
        et.ParseError: If the XML content cannot be parsed
    """
    try:
        # Handle empty responses
        xml_content = xml_content.strip()
        if not xml_content:
            log.info("Empty API response - no new data to process")
            return 0

        root = et.fromstring(xml_content)
        records_processed = 0

        for item in root.findall(child_element):
            record = {}
            for child in item:
                # Convert XML element to dictionary, handling empty values
                value = child.text if child.text is not None else ""
                record[child.tag] = value

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=record)
            records_processed += 1

        return records_processed
    except et.ParseError as e:
        log.error("Failed to parse XML response", e)
        raise


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "comment",
            "primary_key": ["response_id", "date_submitted"],
        },
        {
            "table": "blast_result",
            "primary_key": ["blast_id", "response_id", "thermometer_id", "date_submitted"],
        },
        {
            "table": "recipient_list",
            "primary_key": ["id"],
        },
        {
            "table": "thermometer",
            "primary_key": ["id"],
        },
        {
            "table": "metric",
            "primary_key": ["metric_name", "recorded_at"],
        },
    ]


def get_incremental_date_range(
    state: dict, table_name: str, config_from_date: Optional[str] = None
) -> tuple[str, str]:
    """
    Determine the date range for incremental sync.
    Args:
        state (dict): The state dictionary from previous runs
        table_name (str): Name of the table
        config_from_date (str, optional): Optional from_date from configuration
    Returns:
        tuple[str, str]: (from_date, to_date) in YYYY-MM-DD format
    """
    # to_date is always current time for incremental sync
    current_time = datetime.now(timezone.utc)
    to_date = current_time.strftime("%Y-%m-%d")

    # Determine from_date based on priority:
    # 1. If config has from_date, use it (for backfill/override scenarios)
    # 2. If state has last sync, use it (normal incremental)
    # 3. Otherwise, use EPOCH (initial sync)

    if config_from_date:
        from_date = config_from_date
        log.info(f"Using configured from_date for {table_name}: {from_date}")
    else:
        last_sync_key = f"{table_name}_last_sync"
        last_sync_timestamp = state.get(last_sync_key)

        if last_sync_timestamp:
            # Convert ISO timestamp to YYYY-MM-DD format for API
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_timestamp.replace("Z", "+00:00"))
                from_date = last_sync_dt.strftime("%Y-%m-%d")
                log.info(f"Using incremental sync for {table_name} from {from_date}")
            except (ValueError, AttributeError):
                log.warning(
                    f"Invalid last sync timestamp for {table_name}: {last_sync_timestamp}, using EPOCH"
                )
                from_date = __DEFAULT_START_DATE
        else:
            from_date = __DEFAULT_START_DATE
            log.info(f"Performing initial sync for {table_name} from EPOCH")

    return from_date, to_date


def process_table_data(
    table_name: str,
    endpoint: str,
    api_key: str,
    root_element: str,
    child_element: str,
    state: dict,
    config_from_date: Optional[str] = None,
    supports_incremental: bool = True,
) -> None:
    """
    Generic function to process data from any Customer Thermometer API endpoint with incremental sync support.
    Args:
        table_name (str): Name of the destination table
        endpoint (str): API endpoint to call
        api_key (str): API key for authentication
        root_element (str): Root XML element name
        child_element (str): Child XML element name
        state (dict): State dictionary from previous runs, updated in-place
        config_from_date (str, optional): Optional from_date from configuration
        supports_incremental (bool): Whether this table supports incremental sync
    """
    log.info(f"Fetching {table_name} data...")

    # Determine date range for the API call
    if supports_incremental:
        from_date, to_date = get_incremental_date_range(state, table_name, config_from_date)
    else:
        # For non-incremental tables, always do full sync (no date filters)
        from_date, to_date = None, None
        log.info(f"Performing full sync for {table_name} (no incremental support)")

    response = make_api_request(endpoint, api_key, from_date, to_date)
    records_count = parse_xml_response_and_upsert(
        response.text, root_element, child_element, table_name
    )

    # Checkpoint the state after processing this table
    current_time = datetime.now(timezone.utc).isoformat()
    state[f"{table_name}_last_sync"] = current_time

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=state)

    log.info(f"Processed and checkpointed {records_count} {table_name} records")


def process_metrics(api_key: str, state: dict, config_from_date: Optional[str] = None) -> None:
    """
    Process metrics data from Customer Thermometer API with incremental sync support.
    Args:
        api_key (str): API key for authentication
        state (dict): State dictionary from previous runs, updated in-place
        config_from_date (str, optional): Optional from_date from configuration
    """
    log.info("Fetching metrics data...")
    metrics_processed = 0
    current_time = datetime.now(timezone.utc).isoformat()

    # Determine date range for metrics
    from_date, to_date = get_incremental_date_range(state, "metric", config_from_date)

    for endpoint in __METRIC_ENDPOINTS:
        try:
            response = make_api_request(endpoint, api_key, from_date, to_date)

            # Create a record with the metric value and current timestamp
            metric_name = endpoint.replace("get", "").replace("Value", "").lower()
            metric_data = {
                "metric_name": metric_name,
                "metric_value": response.text.strip(),
                "recorded_at": current_time,
                "from_date": from_date,
                "to_date": to_date,
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table="metric", data=metric_data)
            metrics_processed += 1
            log.info(f"Processed metric: {endpoint}")
        except Exception as e:
            log.warning(f"Failed to fetch metric {endpoint}: {str(e)}")
            continue

    # Checkpoint the state after processing all metrics
    state["metric_last_sync"] = current_time

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=state)

    log.info(f"Processed and checkpointed {metrics_processed} metric records")


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
    log.warning("Example: Source Examples : Customer Thermometer")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Extract configuration parameters (validated above, so safe to assume they exist)
    api_key: str = configuration["api_key"]
    config_from_date = configuration.get("from_date")  # Optional from_date from config

    try:
        # Process each endpoint and checkpoint state after each
        for config in __TABLE_CONFIGS:
            process_table_data(
                config["table_name"],
                config["endpoint"],
                api_key,
                config["root_element"],
                config["child_element"],
                state,
                config_from_date,
                config["supports_incremental"],
            )

        process_metrics(api_key, state, config_from_date)

        log.info("Sync completed successfully. Processed all endpoints.")

    except requests.RequestException as e:
        # Handle API request failures
        log.error("API request failed", e)
        raise
    except et.ParseError as e:
        # Handle XML parsing errors
        log.error("XML parsing failed", e)
        raise
    except ValueError as e:
        # Handle validation and data errors
        log.error("Validation error", e)
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        log.error("Sync failed with unexpected error", e)
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
