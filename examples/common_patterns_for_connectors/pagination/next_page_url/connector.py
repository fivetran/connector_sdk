# This is a simple example for how to work with next-page-url pagination for a REST API.
# It defines a simple `update` method, which upserts retrieved data to a table named "item".
# THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
# (https://pypi.org/project/fivetran-api-playground/) TO RUN.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import requests to make HTTP calls to API
import requests as rq

# Import required classes from fivetran_connector_sdk
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

    log.warning("Example: Common Patterns For Connectors - Pagination - Next Page URL")

    print(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )
    base_url = "http://127.0.0.1:5001/pagination/next_page_url"

    # Retrieve the cursor from the state to determine the current position in the data sync.
    # If the cursor is not present in the state, start from the beginning of time ('0001-01-01T00:00:00Z').
    cursor = state["last_updated_at"] if "last_updated_at" in state else "0001-01-01T00:00:00Z"

    params = {
        "order_by": "updatedAt",
        "order_type": "asc",
        "updated_since": cursor,
        "per_page": 50,
    }

    current_url = base_url  # Start with the base URL and initial params

    sync_items(current_url, params, state)


def sync_items(current_url, params, state):
    """
    The sync_items function handles the retrieval and processing of paginated API data.
    It performs the following tasks:
        1. Sends an API request to the specified URL with the provided parameters.
        2. Processes the items returned in the API response by using upsert operations to send to Fivetran.
        3. Updates the state with the 'updatedAt' timestamp of the last processed item.
        4. Saves the state periodically to ensure the sync can resume from the correct point.
        5. Continues fetching and processing data from the API until all pages are processed.
    Args:
        current_url: The URL to the API endpoint, which may be updated with the next page's URL during pagination.
        params: A dictionary of query parameters to be sent with the API request.
        state: A dictionary representing the current state of the sync, including the last 'updatedAt' timestamp.
    """
    more_data = True

    while more_data:
        # Get response from API call.
        response_page = get_api_response(current_url, params)

        # Process the items
        items = response_page.get("data", [])
        if not items:
            more_data = False  # End pagination if there are no records in response

        # Iterate over each user in the 'items' list and perform an upsert operation.
        # The 'upsert' operation inserts the data into the destination.
        # Update the state with the 'updatedAt' timestamp of the current item.
        summary_first_item = {"id": items[0]["id"], "name": items[0]["name"]}
        log.info(
            f"processing page of items. First item starts: {summary_first_item}, Total items: {len(items)}"
        )
        for user in items:
            op.upsert(table="item", data=user)
            state["last_updated_at"] = user["updatedAt"]

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

        current_url, more_data, params = should_continue_pagination(
            current_url, params, response_page
        )


def should_continue_pagination(current_url, params, response_page):
    """
    The should_continue_pagination function checks whether pagination should continue based on the presence of a
    next page URL in the API response.
    It performs the following tasks:
        1. Retrieves the URL for the next page of data using the get_next_page_url_from_response function.
        2. If a next page URL is found, updates the current URL to this new URL and clears the existing query parameters,
        as they are included in the next URL.
        3. If no next page URL is found, sets the flag to end the pagination process.

    Api response looks like:
        {
          "data": [
            {"id": "c8fda876-6869-4aae-b989-b514a8e45dc6", "name": "Mark Taylor", ... },
            {"id": "3910cbb0-27d4-47f5-9003-a401338eff6e", "name": "Alan Taylor", ... }
            ...
          ],
          "total_items": 200,
          "page": 1,
          "per_page": 10,
          "next_page_url": "http://127.0.0.1:5001/pagination/next_page_url?page=2&per_page=10&order_by=updatedAt&order_type=asc"
          }
        }
    For real API example you can refer Drift's Account Listing API: https://devdocs.drift.com/docs/listing-accounts
    Args:
        current_url: The current URL being used to fetch data from the API. It will be updated if a next page URL is found.
        params: A dictionary of query parameters used in the API request. It will be cleared if a next page URL is found.
        response_page: A dictionary representing the parsed JSON response from the API.
    Returns:
        current_url: The updated URL for the next page, or the same URL if no next page URL is found.
        has_more_pages: A boolean indicating whether there are more pages to retrieve.
        params: The updated or cleared query parameters for the next API request.
    """
    has_more_pages = True

    # Check if there is a next page URL in the response to continue the pagination
    next_page_url = get_next_page_url_from_response(response_page)

    if next_page_url:
        current_url = next_page_url
        params = {}  # Clear params since the next URL contains the query params
    else:
        has_more_pages = False  # End pagination if there is no 'next' URL in the response.

    return current_url, has_more_pages, params


def get_api_response(current_url, params):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        current_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    """
    log.info(f"Making API call to url: {current_url} with params: {params}")
    response = rq.get(current_url, params=params)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    return response_page


def get_next_page_url_from_response(response_page):
    """
    The get_next_page_url_from_response function extracts the URL for the next page of data from the API response.
    Args:
        response_page: A dictionary representing the parsed JSON response from the API.
    Returns:
         The URL for the next page if it exists, otherwise None.
    """
    return response_page.get("next_page_url")


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
