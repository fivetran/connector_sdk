# This is an example for how to record and replay a connector run from an IDE with the fivetran_connector_sdk module.
# It reads customers from the Fivetran API Playground. Set MODE in the `__main__` block below and run the file:
#   MODE = "record"   records the @action calls and the output into fixtures/<SCENARIO>/
#   MODE = "replay"   replays them and compares the output with the recording
# See the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import the json module to load the configuration file.
import json

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


# match= limits the call identity to the page argument.
@action("customers_page", match=lambda page: {"page": page})
def fetch_customers_page(page: int):
    """
    Fetch one page of customers from the API Playground.
    The @action decorator records the result during a record run and returns it during a replay.
    It has no effect when you run the connector without these options.
    Args:
        page: The page number to fetch. It identifies the call during a replay.
    Returns:
        The parsed JSON response, which must be JSON-serializable.
    """
    response = requests.get(
        f"{__BASE_URL}/pagination/page_number",
        params={"page": page, "per_page": __PER_PAGE},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# No match= here, so every argument identifies the call during a replay.
# Use this form when all arguments are stable across runs.
@action("customers_total_pages")
def fetch_total_pages(per_page: int):
    """
    Fetch the total number of customer pages from the API Playground.
    Args:
        per_page: The page size. It is part of the call identity because match is not set.
    Returns:
        The total number of pages, which is JSON-serializable.
    """
    response = requests.get(
        f"{__BASE_URL}/pagination/page_number",
        params={"page": 1, "per_page": per_page},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["total_pages"]


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
    log.warning("Example: Quickstart Examples - Regression Test (IDE)")

    log.info(f"customer pages to sync: {fetch_total_pages(__PER_PAGE)}")

    # Resume after the last page that a previous sync completed.
    last_page = state.get("last_page", 0)
    page = last_page + 1

    while True:
        payload = fetch_customers_page(page)
        if not payload["data"]:
            break

        for item in payload["data"]:
            # The 'upsert' operation inserts the data into the destination.
            yield op.upsert(table="customer", data=item)

        log.info(f"synced page {page} of {payload['total_pages']}")
        last_page = page
        if page >= payload["total_pages"]:
            break
        page += 1

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    yield op.checkpoint(state={"last_page": last_page})


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

    # "record" captures a scenario from the live source. "replay" runs against that recording and compares the output.
    MODE = "record"
    SCENARIO = "basic"

    if MODE == "record":
        # Stop recording after 50 write operations to keep the recording small.
        connector.debug(configuration=configuration, record=SCENARIO, max_records=50)
    else:
        connector.debug(configuration=configuration, replay=SCENARIO)
