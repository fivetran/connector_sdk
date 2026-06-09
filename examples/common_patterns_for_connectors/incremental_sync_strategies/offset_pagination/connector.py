"""This connector demonstrates offset-based pagination for incremental syncs using the Fivetran Connector SDK.
It uses an offset and page size to fetch records in batches, saving the offset as state.
This example is intended for learning purposes and uses the fivetran-api-playground package to mock the API responses locally. It is not meant for production use.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Importing requests for fetching data over api calls
import requests as rq

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Private global configuration variables
__BASE_URL = "http://127.0.0.1:5001/pagination/offset"
__PAGE_SIZE = 50


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings required for the connector.
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
    log.warning(
        "Example: Common Patterns For Connectors - Incremental Sync Strategies - Offset Pagination Example"
    )

    # Get the cursor from state or use default for initial sync
    cursor = state.get("last_updated_at", "0001-01-01T00:00:00Z")

    params = {
        "order_by": "updatedAt",
        "order_type": "asc",
        "updated_since": cursor,
        "limit": __PAGE_SIZE,
        "offset": 0,  # Start from offset 0
    }

    sync_items(__BASE_URL, params, state)


def sync_items(base_url, params, state):
    """
    Handle the retrieval and processing of paginated API data.

    This function manages the pagination loop, processes each batch of data,
    and updates the state with the latest timestamp from processed records.

    Args:
        base_url: The base URL for the API endpoint
        params: Dictionary containing query parameters for the API request
        state: Dictionary containing the current sync state
    """
    more_data = True

    while more_data:
        # Get response from API call
        response_page = get_api_response(base_url, params)

        # Process the items
        items = response_page.get("data", [])
        if not items:
            break  # End pagination if there are no records in response

        # Process each user and update state
        for user in items:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table="user", data=user)
            state["last_updated_at"] = user["updatedAt"]

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

        # Determine if we should continue pagination
        more_data, params = should_continue_pagination(params, response_page, len(items))


def should_continue_pagination(params, response_page, current_page_size):
    """
    Determine whether pagination should continue based on the API response.

    This function checks if there are more pages available by comparing the current
    offset plus page size against the total number of records.

    Args:
        params: Dictionary containing current query parameters
        response_page: Dictionary containing the API response data
        current_page_size: Number of records in the current page

    Returns:
        tuple: (has_more_pages, updated_params) where has_more_pages is a boolean
               indicating if pagination should continue, and updated_params contains
               the parameters for the next page
    """
    offset = response_page.get("offset", 0)
    total = response_page.get("total", 0)

    has_more_pages = (offset + current_page_size) < total
    if has_more_pages:
        params["offset"] = offset + current_page_size
    return has_more_pages, params


def get_api_response(base_url, params):
    """
    Send an HTTP GET request to the provided URL with the specified parameters.

    This function makes the actual API call and handles the HTTP response,
    raising an exception if the request fails.

    Args:
        base_url: The base URL for the API endpoint
        params: Dictionary containing query parameters for the request

    Returns:
        dict: JSON response from the API

    Raises:
        requests.exceptions.HTTPError: If the HTTP request fails
    """
    log.info(f"Making API call to url: {base_url} with params: {params}")
    response = rq.get(base_url, params=params)
    response.raise_for_status()
    response_page = response.json()
    return response_page


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Test the connector locally
    connector.debug()
