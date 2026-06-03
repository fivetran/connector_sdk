"""This connector fetches uptime test data, history, periods, and alerts from StatusCake API and upsert it into destination using the Fivetran Connector SDK.
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

import json  # For reading configuration from a JSON file
import requests  # For making HTTP requests to StatusCake API
import time  # For implementing retry delays and handling rate limiting

__BASE_URL = "https://api.statuscake.com/v1"  # Base URL for StatusCake API
__MAX_RETRIES = 3  # Maximum number of retries for API requests
__RETRY_DELAY = 1  # Retry delay in seconds
__RATE_LIMIT_DELAY = 2  # Rate limit delay in seconds


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
    required_configs = ["api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration parameter: {key}")


def make_api_request(url, headers, max_retries=__MAX_RETRIES):
    """
    Make an API request with retry logic for handling rate limiting and transient errors.
    Args:
        url: The API endpoint URL
        headers: Request headers including authentication
        max_retries: Maximum number of retry attempts
    Returns:
        Response data as JSON or None if all retries failed
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers)

            # Handle rate limiting (429 status code)
            if response.status_code == 429:
                log.warning(
                    f"Rate limit exceeded, waiting {__RATE_LIMIT_DELAY} seconds before retry"
                )
                time.sleep(__RATE_LIMIT_DELAY)
                continue

            # Handle other HTTP errors
            if response.status_code != 200:
                log.warning(
                    f"API request failed with status {response.status_code}: {response.text}"
                )
                if attempt < max_retries - 1:
                    time.sleep(__RETRY_DELAY * (2**attempt))  # Exponential backoff
                    continue
                else:
                    raise requests.exceptions.HTTPError(
                        f"StatusCake API request to {url} failed after {max_retries} attempts with HTTP {response.status_code}: {response.text}"
                    )

            return response.json()

        except requests.exceptions.RequestException as e:
            log.warning(f"Request exception on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(__RETRY_DELAY * (2**attempt))  # Exponential backoff
            else:
                raise requests.exceptions.ConnectionError(
                    f"StatusCake API connection to {url} failed after {max_retries} attempts: {str(e)}"
                )

    return None


def flatten_dictionary(data, parent_key="", separator="_"):
    """
    Flatten nested dictionary structures to create flat key-value pairs for table columns.
    Args:
        data: Dictionary to flatten
        parent_key: Parent key prefix
        separator: Key separator character
    Returns:
        Flattened dictionary
    """
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{separator}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_dictionary(v, new_key, separator=separator).items())
            elif isinstance(v, list):
                # Serialize lists as JSON strings for safer handling
                items.append((new_key, json.dumps(v) if v else "[]"))
            else:
                items.append((new_key, v))
    return dict(items)


def fetch_api_data(endpoint: str, headers: dict, description: str = "") -> list:
    """
    Generic function to fetch data from StatusCake API endpoints.
    Args:
        endpoint: API endpoint path
        headers: HTTP headers including authentication
        description: Description for logging purposes
    Returns:
        List of data records from API response
    """
    url = f"{__BASE_URL}/{endpoint}"
    response_data = make_api_request(url, headers)

    if response_data and "data" in response_data:
        count = len(response_data["data"])
        log.info(f"Fetched {count} {description} records from {endpoint}")
        return response_data["data"]

    log.warning(f"No {description} data found from {endpoint}")
    return []


def upsert_records_with_test_id(table_name: str, records: list, test_id: str, state: dict):
    """
    Common function to process and upsert records with test_id reference.
    Args:
        table_name: Name of the destination table
        records: List of records to process
        test_id: Test ID to add as foreign key reference
        state: A dictionary containing state information from previous runs
    """
    for record in records:
        record["test_id"] = test_id  # Add test_id reference
        flattened_record = flatten_dictionary(record)

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
            "table": "uptime_test",  # Table for main uptime test data
            "primary_key": ["id"],  # Primary key column(s) for the table
        },
        {
            "table": "uptime_test_history",  # Table for uptime test history records
            "primary_key": ["test_id", "created_at"],  # Composite primary key
        },
        {
            "table": "uptime_test_period",  # Table for uptime test periods data
            "primary_key": ["test_id", "created_at"],  # Composite primary key
        },
        {
            "table": "uptime_test_alert",  # Table for uptime test alerts data
            "primary_key": ["test_id", "id"],  # Composite primary key
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

    log.warning("Example: Source Examples : StatusCake")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    api_key = configuration.get("api_key")

    # Set up API headers for authentication
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        # Fetch all uptime tests first - this is the primary data source
        uptime_tests = fetch_api_data("uptime", headers, "uptime tests")

        # Process each uptime test and its related data
        for test in uptime_tests:
            test_id = test.get("id")

            # Flatten the test data for upsert
            flattened_test = flatten_dictionary(test)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # 1. The table name where data should be inserted/updated
            # 2. The data record as a dictionary with column names as keys
            op.upsert(table="uptime_test", data=flattened_test)

            # Process history data for this uptime test
            history_data = fetch_api_data(
                f"uptime/{test_id}/history", headers, f"history records for test {test_id}"
            )
            upsert_records_with_test_id("uptime_test_history", history_data, test_id, state)

            # Process periods data for this uptime test
            periods_data = fetch_api_data(
                f"uptime/{test_id}/periods", headers, f"period records for test {test_id}"
            )
            upsert_records_with_test_id("uptime_test_period", periods_data, test_id, state)

            # Process alerts data for this uptime test
            alerts_data = fetch_api_data(
                f"uptime/{test_id}/alerts", headers, f"alert records for test {test_id}"
            )
            upsert_records_with_test_id("uptime_test_alert", alerts_data, test_id, state)

    except Exception as e:
        log.error("Error during sync", e)
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
