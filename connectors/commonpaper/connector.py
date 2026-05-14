# This connector demonstrates how to fetch and sync data from the Common Paper API.
# This connector fetches agreement data from the Common Paper API and syncs it to the destination.
# It handles pagination and maintains sync state using checkpoints.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
import requests  # For making HTTP requests to the Common Paper API
import json  # For JSON data handling and serialization
import datetime  # For timestamp handling and UTC time operations
import time  # For implementing exponential backoff delays

# Base URL for the Common Paper API
__API_URL = "https://api.commonpaper.com/v1/agreements"
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__BASE_DELAY = 1  # Base delay in seconds for API request retries


def get_headers(api_key):
    """
    Generate the headers required for Common Paper API authentication.
    Args:
        api_key (str): The API key for authentication
    Returns:
        dict: Headers dictionary containing Authorization and Accept headers
    """
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def fetch_agreements(api_key, updated_at):
    """
    Fetch agreements from the Common Paper API with updated_at filter.
    Implements retry logic with exponential backoff for up to 3 attempts.
    Args:
        api_key (str): The API key for authentication
        updated_at (str): ISO format timestamp to filter agreements updated after this time
    Returns:
        dict: JSON response containing agreement data
    Raises:
        Exception: If the API request fails after 3 retry attempts
    """
    # Format the URL with the filter parameter
    url = f"{__API_URL}?filter[updated_at_gt]={updated_at}"
    log.debug(f"Fetching agreements from URL: {url}")

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=get_headers(api_key))

            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 500, 502, 503, 504]:  # Retryable status codes
                if attempt < __MAX_RETRIES - 1:  # Don't sleep on the last attempt
                    delay = __BASE_DELAY * (2**attempt)  # Exponential backoff: 1s, 2s, 4s
                    log.warning(
                        f"Request failed with status {response.status_code}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    log.error(
                        f"Failed to fetch agreements after {__MAX_RETRIES} attempts. Last status: {response.status_code} - {response.text}"
                    )
                    raise RuntimeError(
                        f"API returned {response.status_code} after {__MAX_RETRIES} attempts: {response.text}"
                    )
            else:
                # Non-retryable status codes (4xx errors except 429)
                log.error(f"Failed to fetch agreements: {response.status_code} - {response.text}")
                raise RuntimeError(f"API returned {response.status_code}: {response.text}")

        except requests.exceptions.RequestException as e:
            if attempt < __MAX_RETRIES - 1:  # Don't sleep on the last attempt
                delay = __BASE_DELAY * (2**attempt)  # Exponential backoff: 1s, 2s, 4s
                log.warning(
                    f"Network error occurred, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}"
                )
                time.sleep(delay)
                continue
            else:
                log.error(
                    f"Failed to fetch agreements after {__MAX_RETRIES} attempts due to network error",
                    e,
                )
                raise RuntimeError(f"Network error after {__MAX_RETRIES} attempts: {str(e)}")
    return None


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
    required_configs = ["api_key", "initial_sync_timestamp"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


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
            "table": "agreements",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
        }
    ]


def update(configuration, state):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Source Examples - Commonpaper")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    api_key = configuration["api_key"]
    # Use state to track the last updated_at value. Default to initial_sync_timestamp from config if not present.
    cursor = state.get("sync_cursor", configuration.get("initial_sync_timestamp"))
    log.info(f"Starting sync from updated_at: {cursor}")
    now = datetime.datetime.now(datetime.timezone.utc)
    next_cursor = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    data = fetch_agreements(api_key, cursor)
    agreements = data.get("data", [])

    for record in agreements:
        attributes = record.get("attributes", {})

        # Convert lists to strings for storage
        for field_name, field_value in attributes.items():
            if isinstance(field_value, list):
                attributes[field_name] = json.dumps(field_value)

        # The 'upsert' operation is used to insert or update records in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted
        op.upsert(table="agreements", data=attributes)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint({"sync_cursor": next_cursor})


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
