"""
This example shows how you can update the configuration of the connector during a sync using the Fivetran REST API.
THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
(https://pypi.org/project/fivetran-api-playground/) TO RUN.
See the Technical Reference documentation
(https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
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
import json
import os  # For getting environment variables
from datetime import datetime, timezone, timedelta  # For handling date and time operations

__TOKEN_EXPIRY_TIME = 3600  # Token expiry time in seconds (60 minutes)
__BASE_URL = "http://127.0.0.1:5001/auth/session_token"  # URL for getting session token
__UPDATE_BASE_URL = "https://api.fivetran.com/v1/connections"


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
    required_configs = ["username", "password", "fivetran_api_key"]
    missing = [key for key in required_configs if key not in configuration]
    if missing:
        raise ValueError(f"Missing required configuration value(s): {', '.join(missing)}")


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
    log.warning("Example: Common Patterns For Connectors - Update configuration during sync")

    # validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    log.warning(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )

    sync_items(__BASE_URL, {}, state, configuration)


def update_configuration(config, new_token):
    """
    Update the connector configuration with the new token for future use using the Fivetran API.
    For documentation on the Fivetran API, see https://fivetran.com/docs/rest-api/api-reference.
    Args:
        config: dictionary contains any secrets or payloads you configure when deploying the connector.
        new_token: The new session token to be updated in the configuration.
    """
    config["token"] = new_token
    fivetran_api_key = config.get("fivetran_api_key")
    # You can get the connection id during the runtime from environment variable
    connection_id = os.environ.get("FIVETRAN_CONNECTION_ID")
    update_url = f"{__UPDATE_BASE_URL}/{connection_id}"

    # updating the configuration values as per the required format of Fivetran API
    # Ensure that the entire configuration needs to be passed as payload while calling the Fivetran REST API endpoint,
    # and it will override all the keys present.
    # For reference check the Fivetran REST API documentation
    # https://fivetran.com/docs/rest-api/api-reference/connections/modify-connection?service=connector_sdk
    payload = {
        "config": {
            "secrets_list": [
                {"value": str(value), "key": str(key)} for key, value in config.items()
            ]
        }
    }

    headers = {
        "Accept": "application/json;version=2",
        "Authorization": f"Basic {fivetran_api_key}",
        "content-type": "application/json",
    }

    # Making a PATCH request to the Fivetran API to update the configuration
    response = rq.patch(update_url, json=payload, headers=headers)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    log.info(f"Configuration updated successfully with new token: {response.json()}")


def refresh_session_token(base_url, config):
    """
    This function can be used to refresh the session token.
    This function also updates the connector configuration with the new token for future use using the Fivetran API.
    Args:
        base_url: the API endpoint base url
        config: dictionary contains any secrets or payloads you configure when deploying the connector.
    Returns:
        session_token: A string representing the refreshed session token for making API calls.
    """
    username = config.get("username")
    password = config.get("password")

    token_url = base_url + "/login"
    body = {"username": username, "password": password}

    log.info(f"Making API call to url: {token_url} with body: {body}")

    response = rq.post(token_url, json=body)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    token = response_page.get("token")

    # Update the connector configuration with the new token for future use using the Fivetran API
    update_configuration(config=config, new_token=token)

    return token


def get_session_token(base_url, config, state):
    """
    Define the session function, which is your custom function to generate session token for making API calls.
    This method ensures that a new token is fetched only if the existing token has expired.
    Args:
        base_url: the API endpoint base url
        config: dictionary contains any secrets or payloads you configure when deploying the connector.
        state: A dictionary containing state information from previous runs.
    Returns:
        session_token: A string representing the session token for making API calls.
    """
    last_token_refresh = state.get("last_token_refresh_time", "1990-01-01T00:00:00Z")
    # Convert the last_token_refresh string to a datetime object for comparison
    last_token_refresh_time = datetime.fromisoformat(last_token_refresh.replace("Z", "+00:00"))
    current_time = datetime.now(timezone.utc)
    # Calculate the time difference between the current time and the last token refresh time
    time_difference = current_time - last_token_refresh_time

    # If the token is expired, refresh it
    if time_difference >= timedelta(seconds=__TOKEN_EXPIRY_TIME):
        token = refresh_session_token(base_url, config)
        # Update the state with the current time as the last token refresh time
        state["last_token_refresh_time"] = current_time.isoformat()
        return token

    # If the token is still valid, return the existing token from the configuration
    token = config.get("token")
    return token


def get_auth_headers(session_token):
    """
    Define the get_auth_headers function, which is your custom function to generate auth headers for making API calls.
    Args:
        session_token: A string representing the session token for making API calls.
    Returns:
        headers: A dictionary containing the Authorization header with Basic Auth credentials.
    """
    # Create the auth string
    headers = {
        "Authorization": f"Token {session_token}",
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
    session_token = get_session_token(base_url, configuration, state)
    items_url = base_url + "/data"
    response_page = get_api_response(items_url, params, get_auth_headers(session_token))

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
