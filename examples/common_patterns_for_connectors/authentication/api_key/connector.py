"""
This is a simple example of how to work with API Key authentication for a REST API.
It defines a simple `update` method, which upserts retrieved data to a table named "user".
THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
(https://pypi.org/project/fivetran-api-playground/) TO RUN.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# Import requests to make HTTP calls to API.
import requests as rq

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For reading configuration from a JSON file
import json

# For implementing retry logic with exponential backoff
import time

# Define global constants
__MAX_RETRIES = 3
__REQUEST_TIMEOUT = 30


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
    if "api_key" not in configuration:
        raise ValueError("Missing required configuration value: 'api_key'")


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
    log.warning("Example: Common Patterns For Connectors - Authentication - API KEY")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    log.info(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )
    base_url = "http://127.0.0.1:5001/auth/api_key"

    # Test API connection before starting sync
    probe_api(base_url, configuration)

    sync_items(base_url, {}, state, configuration)


def get_auth_headers(config):
    """
    Define the get_auth_headers function, which is your custom function to generate auth headers for making API calls.
    Args:
        config: dictionary contains any secrets or payloads you configure when deploying the connector.
    Returns:
        headers: A dictionary containing the Authorization header with the API key.
    """
    api_key = config.get("api_key")

    # Create the auth string
    headers = {
        "Authorization": f"apiKey {api_key}",
        "Content-Type": "application/json",  # Optional: specify content type
    }
    return headers


def probe_api(base_url, configuration):
    """
    Test API connection and authentication before starting the sync.
    This method performs a fail-fast check to ensure the API is accessible and credentials are valid.
    Args:
        base_url: The URL to the API endpoint.
        configuration: A dictionary containing connection details including api_key.
    Raises:
        ConnectionError: if unable to connect to the API or if the API returns a server error.
        ValueError: if authentication fails or API returns a client error.
    """
    headers = get_auth_headers(configuration)

    try:
        log.info("Testing API connection and authentication")
        response = rq.get(base_url, headers=headers, timeout=__REQUEST_TIMEOUT)
        response.raise_for_status()
        log.info("API connection test successful. Starting the sync")

    except rq.exceptions.Timeout:
        raise ConnectionError(
            f"Connection timeout while trying to reach {base_url}. "
            "Please verify the API endpoint is accessible."
        )
    except rq.exceptions.HTTPError as e:
        response_code = e.response.status_code
        if response_code == 401 or response_code == 403:
            raise ValueError(
                f"Authentication failed. Please verify your API key is correct. "
                f"Status code: {response_code}"
            )
        elif response_code >= 500:
            raise ConnectionError(f"API server error (status {response_code}). ")
        raise ValueError(f"API request failed with status {response_code}: {str(e)}")
    except Exception as e:
        raise ConnectionError(f"Unexpected error while testing API connection: {str(e)}")


def sync_items(base_url, params, state, configuration):
    """
    The sync_items function handles the retrieval of API data.
    It performs the following tasks:
        1. Sends an API request to the specified URL with the provided parameters.
        2. Processes the items returned in the API response by using upsert operations to send to Fivetran.
        3. Saves the state periodically to ensure the sync can resume from the correct point.
    Args:
        base_url: The URL to the API endpoint.
        params: A dictionary of query parameters to be sent with the API request.
        state: A dictionary representing the current state of the sync, including the last retrieved key.
        configuration: A dictionary contains any secrets or payloads you configure when deploying the connector.
    """
    response_page = get_api_response(base_url, params, get_auth_headers(configuration))

    # Process the items.
    items = response_page.get("data", [])
    if not items:
        return

    # Iterate over each user in the 'items' list and perform an upsert operation.
    for user in items:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="user", data=user)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


def get_api_response(base_url, params, headers, max_retries=__MAX_RETRIES):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks with retry and exponential backoff:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Retries on transient errors (timeouts, connection errors, 5xx errors, 429 rate limit) with exponential backoff.
        4. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        base_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
        headers: A dictionary containing headers for the API request, such as authentication tokens.
        max_retries: Maximum number of retry attempts (default: 3).
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    Raises:
        requests.exceptions.RequestException: if all retry attempts fail.
    """
    log.info(f"Making API call to url: {base_url}")

    for attempt in range(max_retries + 1):
        try:
            response = rq.get(base_url, params=params, headers=headers, timeout=__REQUEST_TIMEOUT)
            response.raise_for_status()
            response_page = response.json()
            return response_page

        except Exception as e:
            # Determine if this is a retryable error
            is_retryable = False

            # Retryable errors: Timeout, connection errors, 5xx server errors, and 429 rate limit
            if isinstance(e, (rq.exceptions.Timeout, rq.exceptions.ConnectionError)):
                is_retryable = True
            elif isinstance(e, rq.exceptions.HTTPError):
                status_code = e.response.status_code if e.response else None
                if status_code and (status_code >= 500 or status_code == 429):
                    is_retryable = True

            # Retry if error is retryable and attempts remain
            if is_retryable and attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                log.warning(
                    f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}. "
                    f"Retrying in {wait_time} seconds..."
                )
                time.sleep(wait_time)
            else:
                # No retry needed: either non-retryable error or exhausted all retries
                if is_retryable:
                    log.error(f"API call failed after {max_retries + 1} attempts")
                else:
                    log.error(f"API call failed: {str(e)}")
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
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)

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
