"""
This is a simple example for how to work with the fivetran_connector_sdk module.
The code will retrieve data for specific endpoints from Talon.one and create one table per endpoint
Tables and endpoints defined at the top of the script in table_endpoint_list
You will need to provide your own Talon.one credentials for this to work --> "base_url" and "api_key" in configuration.json
You can also define how far back in history to go on initial sync using the "initial_sync_start_date" in configuration.json
Relevant Talon.one API documentation: https://docs.talon.one/management-api#tag/Customer-data/operation/getApplicationEventsWithoutTotalCount
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

import requests  # For making API requests
from datetime import datetime, timezone  # For handling date and time
import time  # For adding delays to avoid rate limits

# Define the constants for the connector
__APPLICATION_ID = "<REPLACE_WITH_YOUR_APPLICATION_ID>"
__TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
__DEFAULT_PAGE_SIZE = 100
__INITIAL_SYNC_START_TIME = "2020-01-01T00:00:00.00Z"


def get_table_endpoint_list(application_id):
    """
    Function to get the list of table and endpoint mappings
    You can add more endpoints and tables as per your requirement
    Args:
        application_id: Talon.one Application ID
    Returns:
        List of dictionaries containing table names, primary keys, and endpoints
    """
    return [
        {
            "table": "event",
            "primary_key": ["id"],
            "endpoint": f"applications/{application_id}/events/no_total",
        }
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

    # Validate required configuration parameters
    required_configs = ["base_url", "api_key", "application_id"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    application_id = configuration.get("application_id")
    table_endpoint_list = get_table_endpoint_list(application_id=application_id)

    return [
        {"table": d.get("table"), "primary_key": d.get("primary_key")} for d in table_endpoint_list
    ]


def get_api_response(url, params, headers):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Parses the JSON response from the API, sleeps to avoid 3 calls per second rate limit, and returns it as a dictionary.
    Args:
        url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
        headers: API headers (api key included)
    """

    log.info(f"Making API call to url: {url} with params: {params}")
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    time.sleep(0.3)
    return response_page


def should_continue_pagination(response_page, params):
    """
    Function to check if there are more pages of data
    Args:
        response_page: most recent response page from the API
        params: most recent params sent to the API
    Returns:
        has_more: Boolean indicating if there are more pages of data
        params: Updated params for the next API call if needed
    """
    has_more = response_page.get("hasMore", False)
    if has_more:
        params["skip"] += params.get("pageSize")
    return has_more, params


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
    log.warning("Example: Source Examples - Talon.one Example")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract constants from configuration.json and compose headers
    base_url = configuration.get("base_url")
    api_key = configuration.get("api_key")
    application_id = configuration.get("application_id")
    table_endpoint_list = get_table_endpoint_list(application_id=application_id)

    headers = {"Authorization": f"ManagementKey-v1 {api_key}", "Accept": "application/json"}

    # Retrieve and sync data
    for table in table_endpoint_list:
        # Extract table name and endpoint from the table definition
        table_name = table.get("table")
        endpoint = table.get("endpoint")
        # Set the cursor for the table
        table_cursor = table_name + "_cursor"
        table_cursor_value = state.get(table_cursor, __INITIAL_SYNC_START_TIME)
        table_start_time = datetime.now(timezone.utc).strftime(__TIMESTAMP_FORMAT)

        table_url = f"{base_url}{endpoint}"
        skip = 0

        params = {
            "pageSize": __DEFAULT_PAGE_SIZE,
            "skip": skip,
            "sort": "created",
            "createdAfter": table_cursor_value,
        }

        # Call the method to sync items from the API
        sync_items(table_name, table_url, params, headers)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        state[table_cursor] = table_start_time
        op.checkpoint(state=state)


def sync_items(table_name, api_url, params, headers):
    """
    The sync_items function handles the retrieval and processing of paginated API data.
    It performs the following tasks:
        1. Sends an API request to the specified URL with the provided parameters.
        2. Processes the items returned in the API response by yielding upsert operations to Fivetran.
        3. Continues fetching and processing data from the API until all pages are processed.
    Args:
        table_name: Doubles as the endpoint and the name of the table to write to in the destination
        api_url: The URL to the API endpoint.
        params: A dictionary of query parameters to be sent with the API request.
        headers: API headers including API key
    """
    more_data = True

    while more_data:
        # Get response from API call.
        response_page = get_api_response(api_url, params, headers)

        # Process the items.
        items = response_page.get("data", [])
        if not items:
            break  # End pagination if there are no records in response.

        # Iterate over each user in the 'items' list and yield an upsert operation.
        for item in items:
            # Convert any column values that are Lists to json and upsert record
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table_name, data=list_to_json(item))

        # Determine if we should continue pagination based on the total items and the current offset.
        more_data, params = should_continue_pagination(response_page, params)


def list_to_json(data: dict):
    """
    Converts any list values in the input dictionary to JSON strings.
    Args:
        data: Dictionary to process
    Returns:
        New dictionary with lists converted to JSON strings
    """
    return {
        key: json.dumps(value) if isinstance(value, list) else value for key, value in data.items()
    }


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
