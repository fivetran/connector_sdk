"""
This example demonstrates environment-driven connectivity using the Star Wars API (SWAPI).
It selects between a production mirror and the direct API endpoint based on the FIVETRAN_DEPLOYMENT_MODEL environment variable.
See the Working with Connector SDK documentation (https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#referencingenvironmentvariablesinyourcode)
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For accessing environment variables
import os

# For making HTTP requests
import requests

# For implementing retries and backoff
import time

# For type hinting
from typing import Iterable, Tuple

__PRODUCTION_BASE_URL = "https://swapi.py4e.com/api"  # Endpoint to use in production environment
__DEBUG_BASE_URL = "https://swapi.dev/api"  # Endpoint to use in local debug environment


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
            "table": "people",
            "primary_key": ["url"],
            "columns": {
                "created": "UTC_DATETIME",
                "edited": "UTC_DATETIME",
                "films": "JSON",
                "species": "JSON",
                "starships": "JSON",
                "vehicles": "JSON",
            },
        },
        {
            "table": "planets",
            "primary_key": ["url"],
            "columns": {
                "created": "UTC_DATETIME",
                "edited": "UTC_DATETIME",
                "residents": "JSON",
                "films": "JSON",
            },
        },
        {
            "table": "films",
            "primary_key": ["url"],
            "columns": {
                "created": "UTC_DATETIME",
                "edited": "UTC_DATETIME",
                "release_date": "NAIVE_DATE",
                "characters": "JSON",
                "planets": "JSON",
                "starships": "JSON",
                "vehicles": "JSON",
                "species": "JSON",
            },
        },
        {
            "table": "species",
            "primary_key": ["url"],
            "columns": {
                "created": "UTC_DATETIME",
                "edited": "UTC_DATETIME",
                "people": "JSON",
                "films": "JSON",
            },
        },
        {
            "table": "starships",
            "primary_key": ["url"],
            "columns": {
                "created": "UTC_DATETIME",
                "edited": "UTC_DATETIME",
                "pilots": "JSON",
                "films": "JSON",
            },
        },
        {
            "table": "vehicles",
            "primary_key": ["url"],
            "columns": {
                "created": "UTC_DATETIME",
                "edited": "UTC_DATETIME",
                "pilots": "JSON",
                "films": "JSON",
            },
        },
    ]


def get_request_session() -> requests.Session:
    """
    Create and return a requests.Session with default headers.
    You can extend this function to add authentication or other headers as needed.
    Returns:
        A configured requests.Session object.
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


def get_all_collection_names(base_url: str, session: requests.Session):
    """
    Fetch all collection names from the SWAPI root endpoint.
    Args:
        base_url: The base URL of the SWAPI endpoint.
        session: The requests.Session to use for making requests.
    Returns:
        A list of collection names.
    """
    root = make_api_request(base_url, session=session)
    if not root:
        raise ValueError("No collections found at SWAPI root endpoint")

    return list(root.keys())


def select_base_url() -> str:
    """
    Choose Private Link vs direct endpoint using FIVETRAN_DEPLOYMENT_MODEL.
    - production environment : use Private Link mirror (swapi.py4e.com)
    - local debug environment : direct endpoint (swapi.dev)
    """
    env = os.getenv("FIVETRAN_DEPLOYMENT_MODEL").lower()
    is_local_debug = env == "local_debug"
    if is_local_debug:
        log.info("Detected non-production environment via FIVETRAN_DEPLOYMENT_MODEL")
        return __DEBUG_BASE_URL
    else:
        log.info("Detected production environment via FIVETRAN_DEPLOYMENT_MODEL")
        return __PRODUCTION_BASE_URL


def make_api_request(
    url: str, session: requests.Session, max_retries: int = 3, timeout: int = 20
) -> dict:
    """
    Make a GET request to the specified URL with retries and exponential backoff.
    Returns the JSON response as a dictionary.
    429 responses are handled with respect to the Retry-After header if present.
    Raises the last exception if all retries are exhausted.
    Args:
        url: The URL to request.
        session: The requests.Session to use for making the request.
        max_retries: Maximum number of retries for transient errors.
        timeout: Timeout in seconds for the request.
    Returns:
        The JSON response as a dictionary.
    """
    backoff = 1.0
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            result = session.get(url, timeout=timeout)
            if result.status_code == 429:
                # Respect rate limiting if ever applied; sleep and retry.
                retry_after = float(result.headers.get("Retry-After", backoff))
                log.warning(f"HTTP 429; sleeping for {retry_after}s; attempt={attempt}")
                time.sleep(retry_after)
                continue

            result.raise_for_status()
            return result.json()
        except requests.RequestException as exception:
            last_exception = exception
            log.warning(f"Transient error on {url}: {exception}; attempt={attempt}")
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 16.0)
    # Escalate after retries exhausted
    log.error(f"Failed to fetch {url}", last_exception)
    raise last_exception


def _paginate(
    base_url: str, resource: str, session: requests.Session
) -> Iterable[Tuple[str, Iterable[dict]]]:
    """
    Paginate through a SWAPI resource, yielding each page of results.
    Args:
        base_url: The base URL of the SWAPI endpoint.
        resource: The resource to paginate (e.g., "people", "planets").
        session: The requests.Session to use for making requests.
    Yields:
        A tuple of (page_url, list_of_results) for each page.
    """
    url = f"{base_url.rstrip('/')}/{resource}/"
    while url:
        page = make_api_request(url, session=session)
        results = page.get("results", [])
        yield url, results  # Stream this page to the caller
        url = page.get("next")


def sync_resource(base_url: str, resource: str, session: requests.Session, state: dict):
    """
    Sync a single SWAPI resource, handling pagination and upserting data.
    Args:
        base_url: The base URL of the SWAPI endpoint.
        resource: The resource to sync (e.g., "people", "planets").
        session: The requests.Session to use for making requests.
        state: The state dictionary for checkpointing.
    """
    for page_url, rows in _paginate(base_url=base_url, resource=resource, session=session):
        for row in rows:
            if "url" not in row:
                # Log and skip rows without a 'url' field
                log.warning(f"Skipping row without 'url' in {resource} from {page_url}")
                continue
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table=resource, data=row)
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state=state)


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
    # Select the appropriate base URL based on deployment environment
    base_url = select_base_url()
    # Create a requests session for making API requests
    session = get_request_session()
    # Get all the collections to fetch data from SWAPI
    collection = get_all_collection_names(base_url=base_url, session=session)

    for table in collection:
        # Sync each resource individually from SWAPI
        sync_resource(base_url=base_url, resource=table, session=session, state=state)
        log.info(f"Completed sync for table : '{table}'")

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=state)


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
