"""This connector demonstrates scroll token pagination for syncing data from a REST API.
The server returns an opaque token in each response; the connector passes it back on the next
request to fetch the next page, stopping when the token is absent.
THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
(https://pypi.org/project/fivetran-api-playground/) TO RUN.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# Import requests to make HTTP calls to API.
import requests

# Import time for retry backoff delays.
import time

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like update() and schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__BASE_URL = "http://127.0.0.1:5001/pagination/keyset"
__STATE_KEY_SCROLL_TOKEN = "scroll_token"
__SCROLL_PARAM_KEY = "scroll_param"
__RESPONSE_KEY_DATA = "data"
__REQUEST_TIMEOUT_SECONDS = 30
__MAX_RETRIES = 3
__BASE_RETRY_DELAY_SECONDS = 1
__CHECKPOINT_INTERVAL = 25
__RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
    log.warning("Example: Common Patterns For Connectors - Pagination - Scroll Token")

    log.warning(
        "RECOMMENDATION: This example requires the fivetran-api-playground mock server running locally. "
        "Install and start it with: pip install fivetran-api-playground && fivetran_api_playground start. "
        "See https://pypi.org/project/fivetran-api-playground/ for details."
    )

    # Retrieve the scroll token from state. An empty string means this is the first page of a new sync.
    scroll_token = state.get(__STATE_KEY_SCROLL_TOKEN, "")

    sync_items(__BASE_URL, scroll_token, state)


def sync_items(base_url, scroll_token, state):
    """
    The sync_items function handles the retrieval and processing of scroll-token-paginated API data.
    It performs the following tasks:
        1. Sends an API request, passing the scroll token when one is available.
        2. Processes items from the response using upsert operations to send to Fivetran.
        3. Persists the scroll token in state after each page so the sync can resume if interrupted.
        4. Continues until the API returns no scroll token, signaling the end of the dataset.

    API response will look like the following structure:
        {
          "data": [
            {"id": "c8fda876-6869-4aae-b989-b514a8e45dc6", "name": "Mark Taylor", ... },
            {"id": "3910cbb0-27d4-47f5-9003-a401338eff6e", "name": "Alan Taylor", ... }
          ],
          "scroll_param": "n3h3nbj23n-213f-wef2-344s-9n3idn34if"
        }
    Args:
        base_url: The URL to the API endpoint.
        scroll_token: The token representing the current scroll position. Empty string for the first page.
        state: A dictionary representing the current state of the sync.
    """
    while True:
        # Build request params. The scroll token is absent on the first request and present on all subsequent ones.
        # Note: different APIs use different field names for the token (e.g. 'cursor', 'next_cursor', 'scroll_id').
        # Check your API documentation for the correct parameter name to pass.
        params = {}
        if scroll_token:
            params[__SCROLL_PARAM_KEY] = scroll_token

        response_page = get_api_response(base_url, params)

        items = response_page.get(__RESPONSE_KEY_DATA, [])

        summary_first_item = {"id": items[0]["id"], "name": items[0]["name"]}
        log.info(
            f"processing page of items. First item starts: {summary_first_item}, Total items: {len(items)}"
        )

        for index, user in enumerate(items):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table="user", data=user)

            # Checkpoint every __CHECKPOINT_INTERVAL records to commit upserts to the destination.
            if (index + 1) % __CHECKPOINT_INTERVAL == 0:
                op.checkpoint(state)

        # Check whether there are more pages. The API returns a scroll token for the next page,
        # or null/absent when the end of the dataset has been reached.
        scroll_token = response_page.get(__SCROLL_PARAM_KEY) or ""

        if not scroll_token:
            # Sync complete. Clear the token from state so the next sync starts from the beginning.
            state.pop(__STATE_KEY_SCROLL_TOKEN, None)
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can
            # resume from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)
            break

        # Persist the token in state after each page.
        # If the sync is interrupted, the next run resumes from the last checkpointed token.
        state[__STATE_KEY_SCROLL_TOKEN] = scroll_token
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can
        # resume from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)


def get_api_response(base_url, params):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Retries on transient errors (429, 5xx, connection errors) with exponential backoff.
        4. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        base_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            log.info(f"Making API call to url: {base_url} with params: {params}")
            response = requests.get(base_url, params=params, timeout=__REQUEST_TIMEOUT_SECONDS)

            if response.status_code in __RETRYABLE_STATUS_CODES:
                if attempt < __MAX_RETRIES - 1:
                    delay = __BASE_RETRY_DELAY_SECONDS * (2**attempt)
                    log.warning(
                        f"Request failed with status {response.status_code}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue

            response.raise_for_status()  # Raise immediately for non-retryable errors.
            return response.json()

        except requests.exceptions.ConnectionError as e:
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_RETRY_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Connection error, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}"
                )
                time.sleep(delay)
            else:
                raise


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)
# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # This example does not require a configuration.json file.
    # Test the connector locally
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
