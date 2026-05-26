# This is a simple example for how to work with the fivetran_connector_sdk module.
# The code will retrieve managed Devices from Microsoft InTune and create one table called managed_devices
# You will need to provide your own Microsoft credentials for this to work --> "tenant_id", "client_id", and "client_secret" in configuration.json
# Relevant Microsoft API documentation: https://learn.microsoft.com/en-us/graph/api/intune-devices-manageddevice-list?view=graph-rest-1.0
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log
import requests
import time
import json

# Define base URL for Microsoft graph API
BASE_URL = "https://graph.microsoft.com/v1.0/"
# Max Retries to call on the API
MAX_RETRIES = 3


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [{"table": "managed_devices", "primary_key": ["id"]}]


# The get_access_token function is to retrieve an access token from Culture Amp using client credentials flow
# The function takes in two parameters:
# - client_id: Culture Amp client ID
# - client_secret: Culture Amp client Secret
# And returns
# - access_token: Access Token to use in API calls to Culture Amp
def get_access_token(tenant_id, client_id, client_secret):
    auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}&scope=https%3A%2F%2Fgraph.microsoft.com%2F.default"
    response = requests.post(auth_url, headers=headers, data=payload)

    # Check the response
    if response.status_code == 200:
        access_token = response.json().get("access_token")
        return access_token
    else:
        log.error(f"Error: {response.status_code} - {response.text}")
        raise RuntimeError("Unable to fetch access_token")


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):

    # Retrieve secrets from configuration.json and call Auth endpoint to get access token
    tenant_id = configuration.get("tenant_id")
    client_id = configuration.get("client_id")
    client_secret = configuration.get("client_secret")

    access_token = get_access_token(tenant_id, client_id, client_secret)

    # Define API headers
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Define Managed Devices endpoint
    devices_url = f"{BASE_URL}deviceManagement/managedDevices"

    # Set Boolean to handle pagination and loop through pages
    more_devices = True
    while more_devices:

        # Initialize retry counter
        retry_count = 0
        while retry_count <= MAX_RETRIES:
            try:
                # Call API and retrieve JSON response
                log.info(f"Calling API: {devices_url} (Attempt {retry_count + 1})")
                response = requests.get(devices_url, headers=headers)
                response.raise_for_status()
                break  # successful call, exit retry loop
            except requests.RequestException as e:
                log.warning(f"Request failed: {e}")
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    log.error("Max retries reached. Exiting.")
                    raise
                sleep_time = MAX_RETRIES**retry_count
                log.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)

        # Parse API response
        response_page = response.json()

        # Define Next Page Link and Count of records from API response
        next_page = response_page.get("@odata.nextLink")
        count = response_page.get("@odata.count")
        log.info(f"{count} records retrieved")

        # Loop through records in response and upsert
        for record in response_page.get("value"):
            op.upsert("managed_devices", list_to_json(record))

        # If there was a nextLink in API response, call that API next
        # If no nextLink in API response, end pagination
        if next_page:
            devices_url = next_page
        else:
            more_devices = False


# Converts any list values in the input dictionary to JSON strings.
# The function takes one parameter
# - data: Dictionary to process
#
# Returns
# - New dictionary with lists converted to JSON strings
def list_to_json(data: dict):
    return {
        key: json.dumps(value) if isinstance(value, list) else value for key, value in data.items()
    }


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.

if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)
