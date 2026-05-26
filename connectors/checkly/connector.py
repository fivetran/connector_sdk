"""This connector demonstrates how to fetch data from Checkly API and upsert it into destination using the Fivetran Connector SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
import json  # For JSON data handling and serialization
import requests  # For making HTTP requests to the Checkly API
import time  # For handling time-related functions like sleep for rate limiting

__BASE_URL = "https://api.checklyhq.com/v1"
__PAGE_SIZE = 100
__MAX_RETRIES = 3
__RETRY_DELAY_SECONDS = 60

# Analytics metrics constants
NON_AGGREGATED_METRICS = [
    # Performance metrics
    "responseTime",
    "TTFB",
    # Core Web Vitals
    "FCP",
    "LCP",
    "CLS",
    "TBT",
    # Error metrics
    "consoleErrors",
    "networkErrors",
    "userScriptErrors",
    "documentErrors",
]

AGGREGATED_METRICS = [
    # General availability metrics
    "availability",
    "retries",
    # Response Time metrics
    "responseTime_avg",
    "responseTime_max",
    "responseTime_median",
    "responseTime_min",
    "responseTime_p50",
    "responseTime_p90",
    "responseTime_p95",
    "responseTime_p99",
    "responseTime_stddev",
    "responseTime_sum",
    # Time To First Byte (TTFB) metrics
    "TTFB_avg",
    "TTFB_max",
    "TTFB_median",
    "TTFB_min",
    "TTFB_p50",
    "TTFB_p90",
    "TTFB_p95",
    "TTFB_p99",
    "TTFB_stddev",
    "TTFB_sum",
    # First Contentful Paint (FCP) metrics
    "FCP_avg",
    "FCP_max",
    "FCP_median",
    "FCP_min",
    "FCP_p50",
    "FCP_p90",
    "FCP_p95",
    "FCP_p99",
    "FCP_stddev",
    "FCP_sum",
    # Largest Contentful Paint (LCP) metrics
    "LCP_avg",
    "LCP_max",
    "LCP_median",
    "LCP_min",
    "LCP_p50",
    "LCP_p90",
    "LCP_p95",
    "LCP_p99",
    "LCP_stddev",
    "LCP_sum",
    # Cumulative Layout Shift (CLS) metrics
    "CLS_avg",
    "CLS_max",
    "CLS_median",
    "CLS_min",
    "CLS_p50",
    "CLS_p90",
    "CLS_p95",
    "CLS_p99",
    "CLS_stddev",
    "CLS_sum",
    # Total Blocking Time (TBT) metrics
    "TBT_avg",
    "TBT_max",
    "TBT_median",
    "TBT_min",
    "TBT_p50",
    "TBT_p90",
    "TBT_p95",
    "TBT_p99",
    "TBT_stddev",
    "TBT_sum",
    # Console Errors metrics
    "consoleErrors_avg",
    "consoleErrors_max",
    "consoleErrors_median",
    "consoleErrors_min",
    "consoleErrors_p50",
    "consoleErrors_p90",
    "consoleErrors_p95",
    "consoleErrors_p99",
    "consoleErrors_stddev",
    "consoleErrors_sum",
    # Network Errors metrics
    "networkErrors_avg",
    "networkErrors_max",
    "networkErrors_median",
    "networkErrors_min",
    "networkErrors_p50",
    "networkErrors_p90",
    "networkErrors_p95",
    "networkErrors_p99",
    "networkErrors_stddev",
    "networkErrors_sum",
    # User Script Errors metrics
    "userScriptErrors_avg",
    "userScriptErrors_max",
    "userScriptErrors_median",
    "userScriptErrors_min",
    "userScriptErrors_p50",
    "userScriptErrors_p90",
    "userScriptErrors_p95",
    "userScriptErrors_p99",
    "userScriptErrors_stddev",
    "userScriptErrors_sum",
    # Document Errors metrics
    "documentErrors_avg",
    "documentErrors_max",
    "documentErrors_median",
    "documentErrors_min",
    "documentErrors_p50",
    "documentErrors_p90",
    "documentErrors_p95",
    "documentErrors_p99",
    "documentErrors_stddev",
    "documentErrors_sum",
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

    required_configs = ["api_key", "account_id"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    validate_quick_range(configuration)

    validate_aggregation_interval(configuration)


def validate_aggregation_interval(configuration: dict):
    """
    Validates the 'aggregation_interval' value in the configuration dictionary.
    Checks if the 'aggregation_interval' key in the provided configuration is set to a valid integer
    between 1 and 43200. If not present, defaults to '60'. Raises a ValueError if the value is invalid.
    Args:
        configuration (dict): The configuration dictionary containing the 'aggregation_interval' key.
    Raises:
        ValueError: If 'aggregation_interval' is not a valid integer between 1 and 43200.
    """
    aggregation_interval = configuration.get("aggregation_interval", "60")
    try:
        interval = int(aggregation_interval)
        if interval < 1 or interval > 43200:
            raise ValueError("aggregation_interval must be a positive integer between 1 and 43200")
    except ValueError:
        raise ValueError("aggregation_interval must be a valid integer between 1 and 43200")


def validate_quick_range(configuration: dict):
    """
    Checks if the 'quick_range' key in the provided configuration is set to a valid value.
    If not present, defaults to 'last24Hours'. Raises a ValueError if the value is not one of the allowed options.
    Args:
        configuration (dict): The configuration dictionary containing the 'quick_range' key.
    Raises:
        ValueError: If 'quick_range' is not one of the valid options.
    """

    quick_range = configuration.get("quick_range", "last24Hours")
    valid_quick_ranges = [
        "last24Hours",
        "last7Days",
        "last30Days",
        "thisWeek",
        "thisMonth",
        "lastWeek",
        "lastMonth",
    ]
    if quick_range not in valid_quick_ranges:
        raise ValueError(f"quick_range must be one of: {', '.join(valid_quick_ranges)}")


def flatten_nested_objects(data: dict, parent_key: str = "", separator: str = "_") -> dict:
    """
    Flatten nested dictionary objects into a single level dictionary.
    Args:
        data: Dictionary to flatten
        parent_key: Parent key for nested objects
        separator: Separator to use between parent and child keys
    Returns:
        Flattened dictionary
    """

    items = []

    for key, value in data.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key

        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            items.extend(flatten_nested_objects(value, new_key, separator).items())
        elif isinstance(value, list):
            # Convert arrays to comma-separated strings as mentioned in notes
            if value and all(isinstance(item, str) for item in value):
                items.append((new_key, ",".join(value)))
            else:
                # For complex arrays, convert to JSON string
                items.append((new_key, json.dumps(value)))
        else:
            items.append((new_key, value))

    return dict(items)


def make_api_request(url: str, headers: dict):
    """
    Make an API request to Checkly with proper error handling and retry logic.
    Args:
        url: Complete API endpoint URL with parameters
        headers: Request headers including authentication
    Returns:
        JSON response data (dict or list)
    Raises:
        RuntimeError: If API request fails after all retries
    """

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            if attempt == __MAX_RETRIES - 1:  # Last attempt
                log.error(f"API request failed after {__MAX_RETRIES} attempts", e)
                raise RuntimeError(f"API request failed: {str(e)}")

            # Wait before retry with exponential backoff
            wait_time = __RETRY_DELAY_SECONDS * (2**attempt)
            log.warning(
                f"Request failed (attempt {attempt + 1}/{__MAX_RETRIES}), retrying in {wait_time}s: {str(e)}"
            )
            time.sleep(wait_time)
    return None


def get_analytics_data(configuration: dict, check_id: str, check_type: str, state: dict):
    """
    Fetch analytics data for browser checks from Checkly API.
    Args:
        configuration: Configuration dictionary with API credentials
        check_id: The check ID to fetch analytics for
        check_type: The type of check (only process if it's BROWSER)
    Process analytics records and upsert them to destination tables.
    """
    # Only fetch analytics for browser checks
    if check_type != "BROWSER":
        return

    # Get configuration parameters with defaults
    aggregation_interval = int(configuration.get("aggregation_interval", "60"))
    quick_range = configuration.get("quick_range", "last24Hours")

    headers = build_api_headers(configuration)

    # Process both aggregated and non-aggregated metrics
    for metrics_type, metrics_list in [
        ("non_aggregated", NON_AGGREGATED_METRICS),
        ("aggregated", AGGREGATED_METRICS),
    ]:
        try:
            # Build metrics query parameters
            metrics_params = "&".join([f"metrics={metric}" for metric in metrics_list])

            # Construct URL with quickRange - single API call, no pagination
            url = f"{__BASE_URL}/analytics/browser-checks/{check_id}?quickRange={quick_range}&aggregationInterval={aggregation_interval}&{metrics_params}"

            response_data = make_api_request(url, headers)

            if not response_data or not isinstance(response_data, dict):
                continue

            # Process each series item in the response
            series = response_data.get("series", [])
            for series_item in series:
                data_points = series_item.get("data", [])

                # For each data point, create a record
                for data_point in data_points:
                    analytics_record = {
                        "check_id": check_id,
                        "quick_range": quick_range,
                        "aggregation_interval": aggregation_interval,
                    }
                    analytics_record.update(data_point)

                    # Flatten the nested objects as required
                    flattened_record = flatten_nested_objects(analytics_record)

                    # Determine the target table based on metrics type
                    table_name = f"browser_checks_analytics_{metrics_type}"

                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The op.upsert method is called with two arguments:
                    # - The first argument is the name of the table to upsert the data into.
                    # - The second argument is a dictionary containing the data to be upserted,
                    op.upsert(table=table_name, data=flattened_record)

                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)

        except Exception as e:
            log.warning(f"Error fetching {metrics_type} analytics for check {check_id}: {str(e)}")
            # Continue with next metrics type instead of failing completely
            continue


def build_api_headers(configuration: dict) -> dict:
    """
    Build API headers for Checkly requests.
    Args:
        configuration: Configuration dictionary with API credentials
    Returns:
        Headers dictionary for API requests
    """
    api_key = configuration.get("api_key")
    account_id = configuration.get("account_id")

    return {
        "accept": "application/json",
        "x-checkly-account": account_id,
        "Authorization": f"Bearer {api_key}",
    }


def process_single_check(check_record: dict, configuration: dict, state: dict) -> None:
    """
    Process a single check record and handle analytics data if it's a browser check.
    Args:
        check_record: Individual check record from API response
        configuration: Configuration dictionary with API credentials
    """
    # Flatten the nested objects as required for destination table
    flattened_record = flatten_nested_objects(check_record)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The op.upsert method is called with two arguments:
    # - The first argument is the name of the table to upsert the data into.
    # - The second argument is a dictionary containing the data to be upserted,
    op.upsert(table="checks", data=flattened_record)

    # If this is a browser check, fetch analytics data
    check_type = check_record.get("checkType")
    check_id = check_record.get("id")

    if check_type == "BROWSER" and check_id:
        try:
            get_analytics_data(configuration, check_id, check_type, state)
        except Exception as e:
            log.error(f"Failed to process analytics for check {check_id}", e)
            # Continue with other checks for non-critical errors


def fetch_checks_page(page: int, headers: dict) -> list:
    """
    Fetch a single page of checks data from Checkly API.
    Args:
        page: Page number to fetch
        headers: API request headers
    Returns:
        List of check records from the API response
    """
    # Construct URL with query parameters for pagination
    url = f"{__BASE_URL}/checks?limit={__PAGE_SIZE}&page={page}&applyGroupSettings=false"

    response_data = make_api_request(url, headers)

    # Return empty list if no data or invalid response
    if not response_data or not isinstance(response_data, list):
        return []

    return response_data


def get_checks_data(configuration: dict, state: dict):
    """
    Fetch checks data from Checkly API with pagination support.
    Args:
        configuration: Configuration dictionary with API credentials
    Process check records and upsert them to destination table.
    """
    headers = build_api_headers(configuration)

    page = 1
    total_records = 0

    # Pagination loop to fetch all checks data from Checkly API
    # Each page returns up to __PAGE_SIZE records until all data is retrieved
    while True:
        try:
            response_data = fetch_checks_page(page, headers)

            # Break if no more data
            if not response_data:
                break

            # Process each check record in the current page
            for check_record in response_data:
                process_single_check(check_record, configuration, state)
                total_records += 1

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

            # Check if we have more data to fetch
            if len(response_data) < __PAGE_SIZE:
                break

            page += 1

        except Exception as e:
            log.error(f"Error fetching checks data on page {page}", e)
            raise

    log.info(f"Successfully processed {total_records} check records")


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
            "table": "checks",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
        },
        {
            "table": "browser_checks_analytics_aggregated",
            # Name of the aggregated analytics table in the destination, required.
        },
        {
            "table": "browser_checks_analytics_non_aggregated",
            # Name of the non-aggregated analytics table in the destination, required.
        },
    ]


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
    log.warning("Example: Source Connector : Checkly")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    try:
        # Fetch and process checks data with pagination
        get_checks_data(configuration, state)

        log.info("Checkly sync completed successfully")

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
