# This example demonstrates how to connect to an API over SSH tunnels using `sshtunnel` and `paramiko`.
# This example uses key-based authentication for the SSH tunnel.
# It establishes a secure SSH tunnel from a local port to a remote API server port, allowing secure API access as if it were local.
# The connector uses an API key to authenticate and retrieve data from the API endpoint over the SSH tunnel.
# THIS EXAMPLE USES DUMMY DATA AND REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE (https://pypi.org/project/fivetran-api-playground/).
# For this example, an EC2 instance is running fivetran-api-playground and is only accessible via an SSH tunnel.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import requests to make HTTP calls to API.
import io
import json
from sshtunnel import SSHTunnelForwarder
import paramiko  # For handling SSH keys and connections
from fivetran_connector_sdk import (
    Logging as log,
    Connector,
)  # For enabling Logs in your connector code
from fivetran_connector_sdk import (
    Operations as op,
)  # For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
import requests as rq

DEFAULT_REMOTE_PORT = 5005  # The port on the remote server where the API is running.
DEFAULT_LOCAL_PORT = 8000  # The local port that the SSH tunnel will bind to. This is the port you will use to access the API locally.


def get_auth_headers(config):
    """
    Define the get_auth_headers function, which is your custom function to generate auth headers for making API calls.
    Args:
        config: dictionary contains any secrets or payloads you configure when deploying the connector.
    Returns:
        headers: A dictionary containing the authentication headers for the API request.
    """
    api_key = config.get("api_key")

    if api_key is None:
        raise ValueError("API Key is missing in the configuration.")

    # Create the auth string
    headers = {
        "Authorization": f"apiKey {api_key}",
        "Content-Type": "application/json",  # Optional: specify content type
    }
    return headers


def sync_items(params, state, configuration):
    """
    The sync_items function retrieves data from the remote API over an SSH tunnel.
    Steps:
        1. Calls get_api_response to fetch data from the API using the provided parameters and authentication headers.
        2. Extracts the list of items from the API response.
        3. Upsert operation for each item to insert/update it in the destination.
        4. Checkpoint operation to save the current sync state for resuming future syncs.
    Args:
        params: A dictionary of query parameters to be sent with the API request.
        state: A dictionary representing the current state of the sync, including the last retrieved key.
        configuration: A dictionary contains any secrets or payloads you configure when deploying the connector.
    """
    response_page = get_api_response(params, get_auth_headers(configuration), configuration)

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
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


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
    required_configs = ["ssh_host", "ssh_user", "api_key", "ssh_private_key", "ssh_key_passphrase"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def get_api_response(params, headers, configuration):
    """
    The get_api_response function establishes an SSH tunnel to the remote server and sends an HTTP GET request to the API endpoint over the tunnel.
    It performs the following tasks:
        1. Reads SSH connection details and private key from the configuration.
        2. Opens an SSH tunnel from a local port to the remote API server port using sshtunnel and paramiko.
        3. Logs the tunnel status for diagnostics.
        4. Sends an HTTP GET request to the API endpoint through the tunnel, passing query parameters and authentication headers.
        5. Raises an exception for any HTTP errors.
        6. Parses and returns the JSON response from the API as a dictionary.
    Args:
        params: A dictionary of query parameters to include in the API request.
        headers: A dictionary of HTTP headers for authentication and content type.
        configuration: A dictionary containing SSH and API connection details.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    """
    ssh_host = configuration.get("ssh_host")
    ssh_user = configuration.get("ssh_user")
    private_key_string = configuration.get("ssh_private_key")
    key_stream = io.StringIO(private_key_string)
    key_passphrase = configuration.get(
        "ssh_key_passphrase", None
    )  # Optional: passphrase for the private key if it is encrypted
    try:
        private_key = paramiko.RSAKey.from_private_key(key_stream, password=key_passphrase)
    except Exception as e:
        log.error("Failed to load SSH private key", e)
        raise

    local_port = int(
        configuration.get("local_port", DEFAULT_LOCAL_PORT)
    )  # The local port that the SSH tunnel will bind to. This is the port you will use to access the API locally.
    remote_port = int(
        configuration.get("remote_port", DEFAULT_REMOTE_PORT)
    )  # The port on the remote server where the API is running.
    try:
        with SSHTunnelForwarder(
            (ssh_host, 22),
            ssh_username=ssh_user,
            # Uncomment below param, if your ssh server is configured for both key and password-based authentication
            # ssh_password=configuration.get("ssh_password"),
            ssh_pkey=private_key,
            remote_bind_address=("127.0.0.1", remote_port),
            local_bind_address=("127.0.0.1", local_port),
        ) as _:
            log.error(f"Tunnel open at http://127.0.0.1:{local_port}")

            base_url = f"http://127.0.0.1:{local_port}/auth/api_key"
            try:
                response = rq.get(base_url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                response_page = response.json()
            except rq.exceptions.RequestException as e:
                log.error("HTTP request failed", e)
                raise
            except ValueError as e:
                log.error("Failed to parse JSON response", e)
                raise
            return response_page
    except Exception as e:
        log.error("SSH tunnel or API call failed", e)
        raise


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

    validate_configuration(configuration)
    sync_items({}, state, configuration)


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    try:
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        # Fallback to an empty configuration if the file is not found
        configuration = {}
    # Allows testing the connector directly
    connector.debug(configuration=configuration)
