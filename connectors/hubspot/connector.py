# This is a simple example for how to work with the fivetran_connector_sdk module.
# The code will retrieve data for specific event type(s) from Hubspot and create one table per event type
# You can modify this so that all event types write to one table if desired
# You will need to provide your own Hubspot credentials for this to work --> "api_token" in configuration.json
# You can also define how far back in history to go on initial sync using the "initial_sync_start_date" in configuration.json
# Relevant Hubspot API documentation: https://developers.hubspot.com/docs/reference/api/analytics-and-events/event-analytics
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log  # For enabling Logs in your connector code
import requests
import json
from datetime import datetime, timezone

# Define Event Types to retrieve data for -
# The event types in this list should match the "table" values in the schema() method if you want each event type to be in its own table
EVENT_TYPE_NAMES = ["e_visited_page"]

# Define page_size - number of records to retrieve per API call
PAGE_SIZE = 1000


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [{"table": "e_visited_page", "primary_key": ["id"]}]


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):

    # Define base URL for events endpoint, api_token
    events_url = "https://api.hubapi.com/events/v3/events/"
    api_token = configuration.get("api_token")

    # Define current date in UTC. This will be the occurredBefore query parameter for the current sync AND the occurredAfter query parameter for the NEXT sync
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # If there is a start_date in state, retrieve it to use as occurredAfter query parameter
    # If no start_date in state, full sync, utilizing initial_sync_start_date in configuration as occurredAfter query parameter
    start_date = (
        state.get("start_date")
        if "start_date" in state
        else configuration.get("initial_sync_start_date")
    )
    end_date = current_date

    # Define API headers
    headers = {"Authorization": f"Bearer {api_token}"}

    # Loop through event type names and query events API for records in given time frame
    for event_type_name in EVENT_TYPE_NAMES:
        params = {
            "eventType": event_type_name,
            "occurredAfter": start_date,
            "occurredBefore": end_date,
            "limit": PAGE_SIZE,
            "after": None,
        }

        sync_items(event_type_name, events_url, params, headers)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint({"start_date": end_date})


# The sync_items function handles the retrieval and processing of paginated API data.
# It performs the following tasks:
# 1. Sends an API request to the specified URL with the provided parameters.
# 2. Processes the items returned in the API response by performing upsert operations to send to Fivetran.
# 3. Continues fetching and processing data from the API until all pages are processed.
#
# The function takes four parameters:
# - endpoint: Doubles as the endpoint and the name of the table to write to in the destination
# - api_url: The URL to the API endpoint.
# - params: A dictionary of query parameters to be sent with the API request.
# - headers: API headers including API key
def sync_items(endpoint, api_url, params, headers):
    more_data = True

    while more_data:
        # Get response from API call.
        response_page = get_api_response(api_url, params, headers)

        # Process the items.
        items = response_page.get("results", [])
        if not items:
            break  # End pagination if there are no records in response.

        # Iterate over each user in the 'items' list and performs an upsert operation.
        for item in items:

            # Convert any column values that are Lists to json and upsert record
            item_mod = flatten_json(item)
            op.upsert(table=endpoint, data=item_mod)

        # Determine if we should continue pagination based on the total items and the current offset.
        more_data, params = should_continue_pagination(response_page, params)


# The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
# It performs the following tasks:
# 1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
# 2. Makes the API request using the 'requests' library, passing the URL and parameters.
# 3. Parses the JSON response from the API and returns it as a dictionary.
#
# The function takes three parameters:
# - url: The URL to which the API request is made.
# - params: A dictionary of query parameters to be included in the API request.
# - headers: API headers (api key included)
#
# Returns:
# - response_page: A dictionary containing the parsed JSON response from the API.
def get_api_response(url, params, headers):
    log.info(f"Making API call to url: {url} with params: {params}")
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    return response_page


# Function to check if there are more pages of data
# Takes in two parameters
# - response_page: most recent response page from the API
# - params: most recent params sent to the API
# And returns two objects
# - has_more: Boolean to indicate whether there are more pages or not
# - params: new params for next API call if needed
def should_continue_pagination(response_page, params):
    next_page_after = response_page.get("paging", {}).get("next", {}).get("after")
    if next_page_after:
        has_more = True
    else:
        has_more = False
    params["after"] = next_page_after
    return has_more, params


# Converts any list values in the input dictionary to JSON strings.
# The function takes one parameter
# - data: Dictionary to process
#
# Returns
# - New dictionary with lists converted to JSON strings
def list_to_json(data: dict):
    return {
        key: json.dumps(value) if isinstance(value, list) else value for key, value in data.items()
    }


# Function that takes in a dictionary and flattens it if it has nested json
def flatten_json(data):
    new_items = {}
    for key, value in data.items():
        if isinstance(value, dict):
            new_items.update(value)

    # Add new flattened items
    data.update(new_items)
    return data


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":

    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)

# Fivetran debug results:
#
# Mar 25, 2025 03:06:55 PM: INFO Fivetran-Tester-Process: Checkpoint: {"start_date": "2025-03-25T21:52:14Z"}
# Mar 25, 2025 03:06:55 PM: INFO Fivetran-Tester-Process: SYNC PROGRESS:
# Operation       | Calls
# ----------------+------------
# Upserts         | 6335
# Updates         | 0
# Deletes         | 0
# Truncates       | 0
# SchemaChanges   | 1
# Checkpoints     | 1

# Mar 25, 2025 03:06:55 PM: INFO Fivetran-Tester-Process: Sync SUCCEEDED
