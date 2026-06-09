# This is a simple example of how to work with HTTP BEARER authentication for a REST API.
# It defines a simple `update` method, which upserts retrieved data to a table named "user".
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
import json


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
    if "bearer_token" not in configuration:
        raise ValueError("Missing required configuration value: 'bearer_token'")


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
    log.warning("Example: Common Patterns For Connectors - Authentication - HTTP BEARER")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    print(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )
    base_url = "http://127.0.0.1:5001/auth/http_bearer"

    sync_items(base_url, {}, state, configuration)


def get_auth_headers(config):
    """
    Define the get_auth_headers function, which is your custom function to generate auth headers for making API calls.
    Args:
        config: A dictionary containing connection details
    Returns:
        headers: A dictionary containing the Authorization header with Basic Auth credentials.
    """
    bearer_token = config.get("bearer_token")

    # Create the auth string
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",  # Optional: specify content type
    }
    return headers


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
    # The 'upsert' operation inserts the data into the destination.
    for user in items:
        op.upsert(table="user", data=user)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def get_api_response(base_url, params, headers):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        base_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
        headers: A dictionary containing headers for the API request, such as authentication tokens.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    """
    log.info(f"Making API call to url: {base_url} with params: {params} and headers: {headers}")
    response = rq.get(base_url, params=params, headers=headers)
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
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
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
