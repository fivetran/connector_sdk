"""
This is a simple example for how to work with the fivetran_connector_sdk module.
This code is currently configured to Retrieve Details from All Object Types in Veeva Vault and then utilize VQL to retrieve all Object records, creating one table per object
You will need to provide your own Veeva Vault credentials for this to work --> subdomain, username, and password variables in configuration.json
Retrieve Details from All Object Types endpoint: https://developer.veevavault.com/api/19.3/#retrieve-details-from-all-object-types
VQL endpoint: https://developer.veevavault.com/api/19.3/#vault-query-language-vql
You can also add code to extract from other endpoints as needed.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
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
import base64
import datetime


def get_vault_objects(configuration: dict, credentials):
    """
    Function to get list of available Veeva Vault objects
    Endpoint documentation: https://developer.veevavault.com/api/19.3/#retrieve-details-from-all-object-types
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        credentials: a Veeva Vault base64 encoded username:password
    """
    base_url = f"https://{configuration.get('subdomain')}/v19.3/"

    headers = {"Authorization": f"Basic {credentials}", "Accept": "application/json"}
    get_objects_url = base_url + "configuration/Objecttype"
    obj_response = requests.get(get_objects_url, headers=headers).json()
    objects = obj_response.get("data")

    # Merge if duplicate object names
    merged_objects = unique_objects_and_fields(objects)
    return merged_objects


def unique_objects_and_fields(objects_response):
    """
    Function to merge Veeva Vault objects if an object shows up multiple times in response from:
    https://developer.veevavault.com/api/19.3/#retrieve-details-from-all-object-types
    Args:
        objects_response: the data node of the response from:
        https://developer.veevavault.com/api/19.3/#retrieve-details-from-all-object-types
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
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    encoded_credentials = encode_credentials(configuration)
    # Dynamically define schema based on getVaultObjects response
    # Note: Defining all tables to have a PK of "id" right now - need to verify that this will hold true for all objects
    objects = get_vault_objects(configuration, encoded_credentials)
    schema_def = []
    seen = set()
    for obj in objects:
        object_name = obj.get("object").lower()
        table_dict = {"table": object_name, "primary_key": ["id"]}
        identifier = tuple(
            (k, tuple(v) if isinstance(v, list) else v) for k, v in table_dict.items()
        )
        if identifier not in seen:
            seen.add(identifier)
            schema_def.append(table_dict)
    return schema_def


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
# This function is designed to loop through and retrieve vault Object data using VQL endpoint: https://developer.veevavault.com/api/24.2/#submitting-a-query
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
    log.warning("Example: Source Examples - Veeva Vault Basic Auth Connector")
    # Initialize the sync process

    # Define base_url
    sub_domain = configuration.get("subdomain")
    base_url = f"https://{sub_domain}/v19.3/"

    encoded_credentials = encode_credentials(configuration)

    # Batch size to query, this can be updated and will be placed in every query's PAGESIZE VQL clause
    page_size = 1000

    objects = get_vault_objects(configuration, encoded_credentials)

    # Loop through all objects to define fields and compose query
    table_cursor = {}
    for obj in objects:
        more_data = True
        object_type = obj.get("object")
        fields_list = obj.get("type_fields")

        obj_start_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        object_cursor = object_type + "_cursor"
        cursor = state.get(object_cursor)

        # May want to wrap some fields in TOLABEL() here depending on desired output
        fields = ", ".join(d.get("name") for d in fields_list)

        # Query with date filter if incremental sync, without if initial sync
        if cursor:
            query = f"select {fields} from {object_type} WHERE modified_date__v > '{cursor}' LIMIT {page_size}"
        else:
            query = f"select {fields} from {object_type} LIMIT {page_size}"
        log.info(f"Next query is: {query}")

        # Define headers and %20 spaces for query payload
        vql_headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Accept": "application/json",
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
                more_data = False

            for record in data:
                row = {k: json.dumps(v) if isinstance(v, list) else v for k, v in record.items()}
                op.upsert(object_type, row)

            # Until there is no next_page, keep calling next_page_url from API response to paginate through object
            vql_url, more_data, payload = should_continue_pagination(
                base_url, vql_url, response_page, payload
            )
        table_cursor[object_cursor] = obj_start_time
        op.checkpoint(table_cursor)


def call_vql(url, headers, payload):
    """
    Function to make a call to the VQL endpoint: https://developer.veevavault.com/api/19.3/#vault-query-language-vql
    Args:
        url: URL of the API endpoint to call
        headers: headers for the API call
        payload: payload to send in the API call
    Returns:
        response_page: the response page from the API
    """
    # Burst Limit threshold and sleep time (5 min)
    burst_limit_threshold = 1000
    burst_limit_sleep_time = 300

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
    if int(resp_headers.get("x-vaultapi-burstlimitremaining")) < burst_limit_threshold:
        time.sleep(burst_limit_sleep_time)
        log.warning(
            f"Burst Limit: {resp_headers.get('x-vaultapi-burstlimit')} -- Burst Limit Remaining:  {resp_headers.get('x-vaultapi-burstlimitremaining')}"
        )

    return response_page


def should_continue_pagination(base_url, current_url, response_page, payload):
    """
    Function to check if there are more pages of data
    Args:
        base_url: API base url
        current_url: most recent full API url that was retrieved
        response_page: most recent response page from the API
        payload: most recent payload sent to the API
    Returns:
        current_url: new API url to call next, retrieved from the "next_page" key of the response_page
        has_more_pages: Boolean to indicate whether there are more pages or not
        payload: new payload for next API call if needed
    """

    has_more_pages = True

    # Check if there is a next page URL in the response to continue the pagination
    response_details = response_page.get("responseDetails", {})
    next_page = response_details.get("next_page")

    if next_page:
        next_page_url = base_url + next_page.replace("/api/v19.3/", "")
    else:
        next_page_url = None

    if next_page_url:
        current_url = next_page_url
        payload = {}
    else:
        has_more_pages = False  # End pagination if there is no 'next' URL in the response.

    return current_url, has_more_pages, payload


def encode_credentials(configuration: dict):
    """
    Function to base64 encode username and password for Basic Auth
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        encoded_credentials: base64 encoded string of username:password
    """
    username = configuration.get("username")
    password = configuration.get("password")
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return encoded_credentials


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
