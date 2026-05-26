"""
NOTE: NEEDS TO BE VALIDATED WITH VEEVA USERNAME/PASSWORD, only the basic_auth example has been fully validated
IF INTENDING TO USE - PLEASE CREATE A SAVE ME TIME TICKET HERE: https://fivetran.com/docs/connector-sdk#connectorsdk

This is a simple example for how to work with the fivetran_connector_sdk module.
This code is currently configured to Retrieve Details from All Object Types in Veeva Vault and then utilize VQL to retrieve all Object records, creating one table per object
You will need to provide your own Veeva Vault credentials for this to work --> subdomain, username, and password variables in configuration.json
Retrieve Details from All Object Types endpoint: https://developer.veevavault.com/api/24.2/#retrieve-details-from-all-object-types
VQL endpoint: https://developer.veevavault.com/api/24.2/#vault-query-language-vql
You can also add code to extract from other endpoints as needed.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
from collections import defaultdict
import requests
import json
import time
import datetime

# Define the content type for the API requests
__APPLICATION_JSON = "application/json"
# Batch size to query, this can be updated and will be placed in every query's PAGESIZE VQL clause
__PAGE_SIZE = 1000
# Burst Limit threshold and sleep time (5 min)
__BURST_LIMIT_THRESHOLD = 1000
__BURST_LIMIT_SLEEP_TIME_IN_SECONDS = 300
# Global session ID to prevent multiple authentications
__SESSION_ID = None


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
    required_configs = ["username", "password", "subdomain"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def start_veeva_session(configuration: dict):
    """
    Function to start a Veeva Session, inputs needed are: username, password, and subdomain -- all from the configuration.json file
    Auth endpoint: https://developer.veevavault.com/api/24.2/#user-name-and-password
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    username = configuration.get("username")
    password = configuration.get("password")
    auth_url = f"https://{configuration.get('subdomain')}/api/v24.2/auth"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": __APPLICATION_JSON}
    data = {"username": username, "password": password}
    response = requests.post(auth_url, headers=headers, data=data)
    if response.status_code == 200:
        response_json = response.json()
        if response_json.get("responseStatus") == "SUCCESS":
            session_id = response_json.get("sessionId")
        else:
            log.error(f"Failed to create session for user with username: {username}")
            session_id = None
    else:
        log.error(
            f"Authentication failed: {auth_url} returned {response.status_code}. Expected 200."
        )
        session_id = None
    log.info(f"Started session for user: {username}")
    return session_id


def end_veeva_session(configuration: dict, session_id):
    """
    Function that ends a Veeva session, inputs needed are: active session_id and subdomain from configuration.json file
    End session endpoint: https://developer.veevavault.com/api/24.2/#end-session
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        session_id: a Veeva Vault session ID generated from the start_veeva_session function
    """
    deactivate_session_url = f"https://{configuration.get('subdomain')}/api/v24.2/session"
    headers = {"Authorization": session_id}
    response_deact = requests.delete(deactivate_session_url, headers=headers)
    log.info(
        f"Deactivation of session for user: {configuration.get('username')} responded with code: {response_deact.status_code}: {response_deact.reason}"
    )


def get_vault_objects(configuration: dict, session_id):
    """
    Function to get list of available Veeva Vault objects
    Endpoint documentation: https://developer.veevavault.com/api/24.2/#retrieve-details-from-all-object-types
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        session_id: a Veeva Vault session_id generated by start_veeva_session() function

    Returns:

    """
    base_url = f"https://{configuration.get('subdomain')}/v24.2/"

    headers = {"Authorization": session_id, "Accept": __APPLICATION_JSON}
    get_objects_url = base_url + "configuration/Objecttype"
    obj_response = requests.get(get_objects_url, headers=headers).json()
    objects = obj_response.get("data")

    # Merge if duplicate object names
    merged_objects = unique_objects_and_fields(objects)
    return merged_objects


def unique_objects_and_fields(objects_response):
    """
    Function to merge Veeva Vault objects if an object shows up multiple times in response from:
    https://developer.veevavault.com/api/24.2/#retrieve-details-from-all-object-types
    Args:
        objects_response: the data node of the response from:
        https://developer.veevavault.com/api/24.2/#retrieve-details-from-all-object-types
    Returns:
        merged_objects: a de-duplicated list of object types and field names
    """
    # Merge items in API response with same "object" value
    grouped = defaultdict(list)
    merged_objects = []

    for item in objects_response:
        grouped[item["object"]].append(item)

    for object_name, items in grouped.items():
        merged_object = {"object": object_name, "type_fields": []}

        # Collect unique "type_fields" for every unique "object"
        unique_fields = {}
        for item in items:
            for field in item["type_fields"]:
                # Use a tuple (name, source) to ensure uniqueness
                field_name = field.get("name")
                if field_name not in unique_fields:
                    unique_fields[field_name] = {
                        "name": field_name,
                        "required": field["required"],
                        "source": field["source"],  # Store sources in a set
                    }

        # Convert dictionary values back to a list, ensuring source is a list of unique values
        merged_object["type_fields"] = [
            {"name": field["name"], "required": field["required"], "source": field["source"]}
            for field in unique_fields.values()
        ]

        merged_objects.append(merged_object)
    return merged_objects


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    global __SESSION_ID

    if not __SESSION_ID:
        __SESSION_ID = start_veeva_session(configuration)

    # Dynamically define schema based on getVaultObjects response
    # Note: Defining all tables to have a PK of "id" right now - need to verify that this will hold true for all objects
    objects = get_vault_objects(configuration, __SESSION_ID)
    schema_def = []
    seen = set()

    for obj in objects:
        object_name = obj.get("object").lower()
        table_dict = {"table": object_name, "primary_key": ["id"]}
        if object_name not in seen:
            seen.add(object_name)
            schema_def.append(table_dict)
    return schema_def


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
    global __SESSION_ID

    log.warning("Example: Source Examples - Veeva Vault Session ID Authentication Example")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Define base_url
    sub_domain = configuration.get("subdomain")
    base_url = f"https://{sub_domain}/v24.2/"

    if not __SESSION_ID:
        __SESSION_ID = start_veeva_session(configuration)

    objects = get_vault_objects(configuration, __SESSION_ID)

    sync_objects(base_url, objects, __SESSION_ID, state)

    # end Veeva Session
    end_veeva_session(configuration, __SESSION_ID)


def sync_objects(base_url, objects, session_id, state):
    """
    Function to sync objects from Veeva Vault using VQL.
    This function retrieves all objects and their fields, then queries each object type using VQL to retrieve records.
    It calls upsert operations for each record retrieved, and checkpoints the state after processing each object type.
    Args:
        base_url: the base URL for the Veeva Vault API
        objects: a list of objects retrieved from Veeva Vault, each containing an "object" type and "type_fields"
        session_id: a Veeva Vault session ID generated by start_veeva_session() function
        state: a dictionary containing state information from previous runs, used for incremental syncs
    """
    # Loop through all objects to define fields and compose query
    for obj in objects:
        more_data = True
        object_type = obj.get("object")
        fields_list = obj.get("type_fields")

        obj_start_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        object_cursor = object_type + "_cursor"
        cursor = state.get(object_cursor)

        # May want to wrap some fields in TOLABEL() here depending on desired output
        fields = ", ".join(d.get("name") for d in fields_list)

        query = generate_query(cursor, fields, object_type)
        log.info(f"Next query is: {query}")

        # Define headers and %20 spaces for query payload
        vql_headers = {
            "Authorization": session_id,
            "Accept": __APPLICATION_JSON,
            "X-VaultAPI-DescribeQuery": "true",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = f"q={query.replace(' ', '%20')}"

        # Generate API url and send VQL endpoint
        # VQL endpoint: https://developer.veevavault.com/api/24.2/#submitting-a-query
        vql_url = base_url + "query"
        while more_data:

            response_page = call_vql(vql_url, vql_headers, payload)

            data = response_page.get("data", [])

            if not data:
                break

            for record in data:
                row = {k: json.dumps(v) if isinstance(v, list) else v for k, v in record.items()}
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted,
                op.upsert(object_type, row)

            # Until there is no next_page, keep calling next_page_url from API response to paginate through object
            vql_url, more_data, payload = should_continue_pagination(
                base_url, vql_url, response_page, payload
            )
        state[object_cursor] = obj_start_time
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)


def generate_query(cursor, fields, object_type):
    """
    Function to generate a VQL query based on the cursor, fields, and object type.
    Args:
        cursor: the cursor for incremental sync, None for initial sync
        fields: a string of fields to select in the query
        object_type: the type of object to query, e.g., "Document", "User", etc.

    Returns:

    """
    if cursor:
        query = f"select {fields} from {object_type} WHERE modified_date__v > '{cursor}' LIMIT {__PAGE_SIZE}"
    else:
        query = f"select {fields} from {object_type} LIMIT {__PAGE_SIZE}"
    return query


def call_vql(url, headers, payload):
    """
    Function to make a call to the VQL endpoint: https://developer.veevavault.com/api/24.2/#vault-query-language-vql
    Args:
        url: URL of the API endpoint to call
        headers: headers for the API call
        payload: payload to send in the API call
    Returns:
        response_page: the response page from the API
    """
    # Call API and print status_code
    response = requests.post(url, headers=headers, data=payload)
    log.info(f"API call: {url}")
    log.info(f"Response status code: {response.status_code}")
    response.raise_for_status()

    # Convert response to json, analyze responseStatus and Burst Limit Remaining
    response_page = response.json()
    if response_page.get("responseStatus") != "SUCCESS":
        log.warning(
            f"Unsuccessful API call -- Response Status: {response_page.get('responseStatus')}, Errors: {response_page.get('errors')}"
        )
    resp_headers = response.headers

    # If approaching Burst Limit, sleep for 5 min
    if int(resp_headers.get("x-vaultapi-burstlimitremaining")) < __BURST_LIMIT_THRESHOLD:
        time.sleep(__BURST_LIMIT_SLEEP_TIME_IN_SECONDS)
        log.warning(
            f"Burst Limit: {resp_headers.get('x-vaultapi-burstlimit')} -- Burst Limit Remaining:  {resp_headers.get('x-vaultapi-burstlimitremaining')}"
        )

    return response_page


def should_continue_pagination(base_url, current_url, response_page, payload):
    """
    Function to check if there are more pages of data to retrieve from the API.
    Args:
        base_url: API base url, used to construct the next page URL
        current_url: the current URL being processed, used to determine the next page URL
        response_page: the most recent response page from the API, which contains pagination details
        payload: the most recent payload sent to the API, which may be needed for the next call
    Returns:
        current_url: the new API URL to call next, retrieved from the "next_page" key of the response_page
        has_more_pages: a Boolean indicating whether there are more pages of data to retrieve
        payload: the new payload for the next API call if needed
    """

    has_more_pages = True

    # Check if there is a next page URL in the response to continue the pagination
    response_details = response_page.get("responseDetails", {})
    next_page = response_details.get("next_page")

    if next_page:
        next_page_url = base_url + next_page.replace("/api/v24.2/", "")
    else:
        next_page_url = None

    if next_page_url:
        current_url = next_page_url
        payload = {}
    else:
        has_more_pages = False  # End pagination if there is no 'next' URL in the response.

    return current_url, has_more_pages, payload


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
