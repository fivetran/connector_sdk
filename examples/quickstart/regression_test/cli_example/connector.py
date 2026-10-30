# This is an example for how to record and replay a connector run with the fivetran_connector_sdk module.
# It reads customers from the Fivetran API Playground and is meant to be run with the `fivetran debug` command:
#   fivetran debug --record basic     (records the @action calls and the output)
#   fivetran debug --replay basic     (replays them and compares the output with the recording)
# See the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import the json module to load the configuration file.
import json

# Import the time module to wait between retries.
import time

# Import the requests module for making HTTP requests.
import requests

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For marking the functions that read from the source so they can be recorded and replayed
from fivetran_connector_sdk import action

__BASE_URL = "http://127.0.0.1:5001"
__PER_PAGE = 10
__MAX_RETRIES = 3
__RETRY_BASE_DELAY_SECONDS = 2
__TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def get_with_retry(url: str, params: dict):
    """
    Send a GET request and retry transient failures with exponential backoff.
    Timeouts, connection errors, HTTP 429, and HTTP 5xx responses are retried up to __MAX_RETRIES times.
    Other HTTP errors, such as 400 or 404, are permanent and are raised immediately.
    The @action functions call this helper, so a replay returns the recorded result and never runs it.
    Args:
        url: The URL to request.
        params: The query parameters.
    Returns:
        The successful response.
    """
    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code not in __TRANSIENT_STATUS_CODES:
                # Raises immediately for a permanent client error.
                response.raise_for_status()
                return response
            error = requests.HTTPError(f"HTTP {response.status_code}", response=response)
        except (requests.Timeout, requests.ConnectionError) as e:
            error = e

        if attempt == __MAX_RETRIES:
            raise error
        delay = __RETRY_BASE_DELAY_SECONDS * 2 ** (attempt - 1)
        log.warning(
            f"request failed ({error}); retrying in {delay}s (attempt {attempt} of {__MAX_RETRIES})"
        )
        time.sleep(delay)


# match= lists the arguments that identify the call during a replay. It receives the same arguments as the function.
# You can omit match, and then every argument is saved in the fixture and identifies the call.
# We recommend setting it so that secrets and other unwanted arguments aren't stored in the fixture.
@action(
    "customers_page",
    match=lambda page, updated_since: {"page": page, "updated_since": updated_since},
)
def fetch_customers_page(page: int, updated_since: str = None):
    """
    Fetch one page of customers from the API Playground.
    The @action decorator records the result during `--record` and returns it during `--replay`.
    It has no effect when you run the connector without these options.
    Args:
        page: The page number to fetch. It identifies the call during a replay.
        updated_since: Only customers updated at or after this UTC timestamp are returned. None returns all customers.
    Returns:
        The parsed JSON response, which must be JSON-serializable.
    """
    params = {"page": page, "per_page": __PER_PAGE, "order_by": "updatedAt", "order_type": "asc"}
    if updated_since:
        params["updated_since"] = updated_since
    response = get_with_retry(f"{__BASE_URL}/pagination/page_number", params)
    return response.json()


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [{"table": "customer", "primary_key": ["id"]}]


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
    log.warning("Example: Quickstart Examples - Regression Test (CLI)")

    # "last_updated_at" is the newest customer updatedAt that was synced. It is None on the first sync.
    # "updated_since" stays fixed for the whole sync, so every page comes from the same filtered query.
    updated_since = state.get("last_updated_at")
    # We request customers sorted by updatedAt, oldest first, and updated_since is inclusive.
    # Each sync reads from page 1 of the same filtered query, so the pages never shift past unread changes.
    page = 1

    while True:
        payload = fetch_customers_page(page, updated_since)
        if not payload["data"]:
            break

        for item in payload["data"]:
            # The 'upsert' operation inserts the data into the destination.
            op.upsert(table="customer", data=item)

        log.info(f"synced page {page} of {payload['total_pages']}")
        state["last_updated_at"] = payload["data"][-1]["updatedAt"]

        # Checkpoint after each fully processed page, so a failed sync resumes from the newest updatedAt it saved.
        op.checkpoint(state)
        if page >= payload["total_pages"]:
            break
        page += 1

    # Final checkpoint, which also covers a sync that found no data.
    op.checkpoint(state)


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
