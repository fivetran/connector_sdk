"""Vercel Deployments Connector for Fivetran - fetches deployment data from Vercel /v6/deployments API.
This connector demonstrates how to fetch deployment data from Vercel REST API /v6/deployments endpoint and upsert it into destination using the Fivetran Connector SDK.
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

# For making HTTP requests to Vercel API
import requests

# For handling time operations and timestamps
import time

from typing import Optional

__BASE_URL = "https://api.vercel.com"  # Base URL for Vercel API
__DEPLOYMENTS_ENDPOINT = "/v6/deployments"  # Endpoint path for deployments API
__PAGINATION_LIMIT = (
    20  # Pagination limit - higher values reduce API calls but increase memory usage
)
__REQUEST_TIMEOUT_IN_SECONDS = 30

# Retry configuration constants
__MAX_RETRIES = 5  # Maximum number of retry attempts for API requests
__BACKOFF_BASE = 1  # Base delay in seconds for API request retries


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
    required_configs = ["api_token"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def flatten_dict(data: dict, prefix: str = "", separator: str = "_") -> dict:
    """
    Flatten a nested dictionary by concatenating keys with a separator.
    This is used to convert nested JSON responses into flat table structures.

    Args:
        data: The dictionary to flatten
        prefix: Prefix to add to keys (used for recursion)
        separator: Separator to use between nested keys

    Returns:
        A flattened dictionary
    """
    flattened = {}

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            flattened.update(flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            # Convert lists to JSON strings for storage
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


def make_api_request(url: str, headers: dict, params: Optional[dict] = None) -> dict:
    """
    Make an HTTP GET request to the Vercel API with error handling and exponential backoff retry logic.

    Args:
        url: The API endpoint URL
        headers: HTTP headers for the request
        params: Optional query parameters

    Returns:
        The JSON response from the API

    Raises:
        requests.exceptions.RequestException: For HTTP errors
        ValueError: For invalid JSON responses
    """
    params = params or {}

    for attempt in range(__MAX_RETRIES):
        response = None
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_IN_SECONDS
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if attempt < __MAX_RETRIES - 1:
                delay = __BACKOFF_BASE * (2**attempt)
                log.warning(f"Request timeout for URL: {url}. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            log.error(f"Request timeout for URL: {url}")
            raise
        except requests.exceptions.HTTPError as e:
            is_retryable_error = response and (
                response.status_code == 429 or response.status_code >= 500
            )
            should_retry = is_retryable_error and attempt < __MAX_RETRIES - 1
            if should_retry:
                delay = __BACKOFF_BASE * (2**attempt)
                log.warning(
                    f"Rate limit or server error for URL: {url}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
                continue
            log.error(f"HTTP error for URL: {url}", e)
            raise
        except (requests.exceptions.RequestException, ValueError) as e:
            log.error(f"Request failed for URL: {url}", e)
            raise

    raise requests.exceptions.RequestException(
        f"Request failed for URL: {url} after {__MAX_RETRIES} attempts"
    )


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
            "table": "deployment",  # Table for Vercel deployments
            "primary_key": ["uid"],  # Deployment UID as primary key
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

    log.warning("Example: API Connector : Vercel Deployments Connector")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    api_token = configuration.get("api_token")
    team_id = configuration.get("team_id")  # Optional team ID for accessing team resources

    # Set up authentication headers
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

    # Get the state variable for the sync, if needed
    last_sync_timestamp = state.get("last_sync_timestamp")
    current_sync_timestamp = int(time.time() * 1000)  # Current time in milliseconds

    try:
        # Sync deployments data from /v6/deployments endpoint
        sync_deployments(headers, last_sync_timestamp, team_id)

        # Update state with the current sync time for the next run
        new_state = {"last_sync_timestamp": current_sync_timestamp}

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(new_state)

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def sync_deployments(
    headers: dict, last_sync_timestamp: Optional[int] = None, team_id: Optional[str] = None
):
    """
    Fetch and sync deployments data from Vercel API.
    This function handles pagination to process all deployments in batches.

    Args:
        headers: HTTP headers including authorization
        last_sync_timestamp: Timestamp of last sync for incremental updates
        team_id: Optional team ID to access team resources instead of personal account
    """
    log.info("Starting deployments sync")

    # Build the URL and query parameters
    url = f"{__BASE_URL}{__DEPLOYMENTS_ENDPOINT}"
    params: dict = {"limit": __PAGINATION_LIMIT}

    # Add team ID if provided to access team resources
    if team_id:
        params["teamId"] = team_id

    # Use last_sync_timestamp for incremental sync if available
    if last_sync_timestamp:
        params["since"] = last_sync_timestamp

    deployments_synced = 0
    next_timestamp = None

    while True:
        # For pagination, use 'next' parameter with the continuation token
        if next_timestamp:
            params["next"] = next_timestamp

        try:
            response_data = make_api_request(url, headers, params)
            deployments = response_data.get("deployments", [])

            for deployment in deployments:
                # Flatten the deployment data for table storage
                flattened_deployment = flatten_dict(deployment)

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted
                op.upsert(table="deployment", data=flattened_deployment)
                deployments_synced += 1

            # Check pagination - if there's a next timestamp, continue
            pagination = response_data.get("pagination", {})
            next_timestamp = pagination.get("next")

            if not next_timestamp:
                break

        except Exception as e:
            log.error("Error syncing deployments", e)
            raise

    log.info(f"Synced {deployments_synced} deployments")


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
