# This is a simple example of how to work with offset-based pagination for a REST API.
# It defines a simple `update` method, which upserts retrieved data to a table named "item".
# THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
# (https://pypi.org/project/fivetran-api-playground/) TO RUN.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import requests to make HTTP calls to API.
import requests as rq

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


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
            "table": "user",
            "primary_key": ["id"],
            "columns": {
                "id": "STRING",
                "name": "STRING",
                "email": "STRING",
                "address": "STRING",
                "company": "STRING",
                "job": "STRING",
                "updatedAt": "UTC_DATETIME",
                "createdAt": "UTC_DATETIME",
            },
        }
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
    log.warning("Example: Common Patterns For Connectors - Pagination - Offset Based")

    print(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )
    base_url = "http://127.0.0.1:5001/pagination/offset"

    # Retrieve the cursor from the state to determine the current position in the data sync.
    # If the cursor is not present in the state (initial sync or full resync case), start from the beginning of time
    # ('0001-01-01T00:00:00Z'). Make sure the format is time is valid for parsing.
    cursor = state["last_updated_at"] if "last_updated_at" in state else "0001-01-01T00:00:00Z"

    params = {
        "order_by": "updatedAt",
        "order_type": "asc",
        "updated_since": cursor,
        "limit": 50,
    }

    sync_items(base_url, params, state)


def sync_items(base_url, params, state):
    """
    The sync_items function handles the retrieval and processing of paginated API data.
    It performs the following tasks:
        1. Sends an API request to the specified URL with the provided parameters.
        2. Processes the items returned in the API response by using upsert operations to send to Fivetran.
        3. Updates the state with the 'updatedAt' timestamp of the last processed item.
        4. Saves the state periodically to ensure the sync can resume from the correct point.
        5. Continues fetching and processing data from the API until all pages are processed.
    Args:
        base_url: The URL to the API endpoint.
        params: A dictionary of query parameters to be sent with the API request.
        state: A dictionary that holds the state of the sync process, including the last updated timestamp.
    """
    more_data = True

    while more_data:
        # Get response from API call.
        response_page = get_api_response(base_url, params)

        # Process the items.
        items = response_page.get("data", [])
        if not items:
            break  # End pagination if there are no records in response.

        # Iterate over each user in the 'items' list and perform an upsert operation.
        # The 'upsert' operation inserts the data into the destination.
        # Update the state with the 'updatedAt' timestamp of the current item.
        summary_first_item = {"id": items[0]["id"], "name": items[0]["name"]}
        log.info(
            f"processing page of items. First item starts: {summary_first_item}, Total items: {len(items)}"
        )
        for user in items:
            op.upsert(table="user", data=user)
            state["last_updated_at"] = user["updatedAt"]

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

        # Determine if we should continue pagination based on the total items and the current offset.
        more_data, params = should_continue_pagination(params, response_page, len(items))


def should_continue_pagination(params, response_page, current_page_size):
    """
    The should_continue_pagination function determines whether pagination should continue based on the
    'total' and 'offset' in the API response.
    It performs the following tasks:
        1. Checks if the sum of the current offset and current page's record count is less than the total number of items.
        2. If the current offset + current_page_size is less than the total, updates the parameters with the new offset
        for the next API request.
        3. If the current offset + current_page_size is greater than or equal to the total,
        sets the flag to end the pagination process.

    API response will look like the following structure:
        {
          "data": [
            {"id": "c8fda876-6869-4aae-b989-b514a8e45dc6", "name": "Mark Taylor", ... },
            {"id": "3910cbb0-27d4-47f5-9003-a401338eff6e", "name": "Alan Taylor", ... }
          ],
          "offset": 20, // Current offset
          "limit": 100,  // Number of items per page
          "total": 100  // Total number of items available
        }
    For real API example you can refer vwo's Campaign's API:
        https://developers.vwo.com/reference/get-the-campaigns-of-an-account
    Args:
        params: A dictionary of query parameters used in the API request. It will be updated with the new offset.
        response_page: A dictionary representing the parsed JSON response from the API.
        current_page_size: The number of items in the current page of the response.
    Returns:
        has_more_pages: A boolean indicating whether there are more pages to retrieve.
        params: The updated query parameters for the next API request.
    """
    offset = response_page.get("offset", 0)
    total = response_page.get("total", 0)

    has_more_pages = (offset + current_page_size) < total
    if has_more_pages:
        params["offset"] = offset + current_page_size
    return has_more_pages, params


def get_api_response(base_url, params):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        base_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    """
    log.info(f"Making API call to url: {base_url} with params: {params}")
    response = rq.get(base_url, params=params)
    response.raise_for_status()  # Ensure
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    return response_page


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from
    # your IDE.
    connector.debug()

# Resulting table:
# ┌───────────────────────────────────────┬───────────────┬────────────────────────┬──────────────────────────┬───────────────────────────┐
# │                 id                    │      name     │         job            │        updatedAt         │        createdAt          │
# │               string                  │     string    │       string           │      timestamp with UTC  │      timestamp with UTC   │
# ├───────────────────────────────────────┼───────────────┼────────────────────────┼──────────────────────────┼───────────────────────────┤
# │ c8fda876-6869-4aae-b989-b514a8e45dc6  │ Mark Taylor   │   Pilot, airline       │ 2024-09-22T19:35:41Z     │ 2024-09-22T18:50:06Z      │
# │ 3910cbb0-27d4-47f5-9003-a401338eff6e  │ Alan Taylor   │   Dispensing optician  │ 2024-09-22T20:28:11Z     │ 2024-09-22T19:58:38Z      │
# ├───────────────────────────────────────┴───────────────┴────────────────────────┴──────────────────────────┴───────────────────────────┤
# │  2 rows                                                                                                                     5 columns │
# └───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
