# This is an example for how to work with the fivetran_connector_sdk module.
# This example shows how to sync data from the Fleetio API using the Fivetran Connector SDK.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
import json  # For working with JSON data
from typing import List, Dict  # For type hinting and annotations
from flatten_json import (
    flatten,
)  # This is needed to transform a nested JSON data structure into a flat, one-level structure
import requests  # This is needed to make HTTP requests to the Fleetio API


def update_list_of_dicts(list_of_dicts: List[Dict], keys: List, remove: bool = False):
    """
    Update a list of dictionaries by including or excluding specified keys.
    Args:
        list_of_dicts: List of dictionaries to be updated.
        keys: List of keys to include or exclude.
        remove: If True, the specified keys will be removed from each dictionary.
    Returns:
        A new list of dictionaries with the specified keys included or excluded.
    """
    if remove:
        updated = [{key: d[key] for key in d if key not in keys} for d in list_of_dicts]
    else:
        updated = [{key: d[key] for key in d if key in keys} for d in list_of_dicts]
    return updated


def base_schema():
    """
    Base schema for Fleetio API data synchronization.
    Returns:
        A list of dictionaries representing the base schema for Fleetio API data.
        Each dictionary contains the table name, primary key, columns, and request information.
    """
    base_schema = [
        {
            "table": "submitted_inspection_forms",
            "primary_key": ["id"],
            "request_info": {"path": "/submitted_inspection_forms", "params": {"per_page": 100}},
        },
        {
            "table": "issues",
            "primary_key": ["id"],
            "columns": {
                "custom_fields": "JSON",
                "attachment_permissions": "JSON",
                "assigned_contacts": "JSON",
                "labels": "JSON",
            },
            "request_info": {"path": "/issues", "params": {"per_page": 100}},
        },
        {
            "table": "service_entries",
            "primary_key": ["id"],
            "columns": {
                "custom_fields": "JSON",
                "attachment_permissions": "JSON",
                "labels": "JSON",
            },
            "request_info": {"path": "/service_entries", "params": {"per_page": 100}},
        },
        {
            "table": "vehicles",
            "primary_key": ["id"],
            "columns": {"custom_fields": "JSON", "labels": "JSON"},
            "request_info": {"path": "/vehicles", "params": {"per_page": 100}},
        },
        {
            "table": "expense_entries",
            "primary_key": ["id"],
            "request_info": {"path": "/expense_entries", "params": {"per_page": 100}},
        },
        {
            "table": "contacts",
            "primary_key": ["id"],
            "request_info": {"path": "/contacts", "params": {"per_page": 100}},
        },
        {
            "table": "fuel_entries",
            "primary_key": ["id"],
            "request_info": {"path": "/fuel_entries", "params": {"per_page": 100}},
        },
        {
            "table": "parts",
            "primary_key": ["id"],
            "request_info": {"path": "/parts", "params": {"per_page": 100}},
        },
        {
            "table": "purchase_orders",
            "primary_key": ["id"],
            "columns": {"custom_fields": "JSON", "labels": "JSON"},
            "request_info": {"path": "/purchase_orders", "params": {"per_page": 100}},
        },
        {
            "table": "vehicle_assignments",
            "primary_key": ["id"],
            "request_info": {"path": "/vehicle_assignments", "params": {"per_page": 100}},
        },
    ]
    return base_schema


def schema(configuration: dict) -> List[Dict[str, List]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    keys_to_include = [
        "table",
        "primary_key",
        "columns",
    ]
    base = base_schema()
    schema = update_list_of_dicts(base, keys_to_include)

    log.info("Loading schema for tables")

    return schema


def continue_pagination(response_json):
    """
    Check if there are more pages to fetch from the API response.
    Args:
        response_json: A JSON object containing the API response data.
    Returns:
        A tuple containing a boolean indicating if there are more pages and a dictionary of parameters for the next request.
        If there are no more pages, the boolean will be False and the dictionary will be empty.
    """
    params = {}
    has_more_pages = True

    next_cursor = response_json.get("next_cursor", None)
    if next_cursor is not None:
        params = {"next_cursor": next_cursor}
    else:
        has_more_pages = False
    return has_more_pages, params


def make_api_request(base_url, path, headers, params=None):
    """
    Make an API request to the Fleetio API and return the JSON response.
    Args:
        base_url: The base URL of the Fleetio API.
        path: The specific API endpoint path to request.
        headers: The headers to include in the API request.
        params: Optional; a dictionary of next cursor to include in the request.
    Returns:
        The JSON response from the API if the request is successful, or None if the request fails.
    """
    log.info("Attempting to retrieve data from API")
    try:
        log.info(f"Making API GET request to {path}")
        url = base_url + path
        response = requests.get(url=url, headers=headers, params=params)
        return response.json()

    except requests.RequestException as e:
        log.error("API call failed", e)
        return None


def validate_configuration(configuration: dict):
    """
    Validate the configuration for the connector.
    Args:
        configuration: A dictionary containing connection details.
    """
    required_keys = ["Account-Token", "Authorization"]
    for key in required_keys:
        if key not in configuration:
            raise ValueError(f"Missing required configuration key: {key}")


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
    log.info("Example: Source Examples: Fleetio Example")

    # Validate the configuration
    validate_configuration(configuration)

    base_url = "https://secure.fleetio.com/api"
    base = base_schema()
    additional_configuration = {
        "Accept": "application/json",
        "X-Api-Version": "2025-05-05",
        "X-Client-Name": "data_connector",
        "X-Client-Platform": "fleetio_fivetran",
    }
    headers = {**configuration, **additional_configuration}

    for schema in base:
        log.info(f"Starting sync for {schema['table']}")
        sync_table(
            base_url=base_url,
            path=schema["request_info"]["path"],
            headers=headers,
            params=schema["request_info"]["params"],
            table=schema["table"],
        )

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)


def sync_table(base_url, path, headers, params, table):
    """
    Sync data from a specific table in the Fleetio API.
    This function retrieves data from the Fleetio API, flattens it, and performs upsert operations for each record.
    Args:
        base_url: The base URL of the Fleetio API.
        path: The specific API endpoint path to request.
        headers: The headers to include in the API request.
        params: a dictionary of next cursor to include in the request.
        table: The name of the table to upsert the data into.
    """
    has_more_pages = True

    while has_more_pages:
        response = make_api_request(base_url, path, headers, params)
        if not response:
            return

        data = response.get("records", [])
        if not data:
            break

        log.info(f"Processing data for {path}")
        for item in data:
            flat_item = flatten(item)
            # The 'upsert' operation is used to insert or update records in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table, data=flat_item)

        has_more_pages, params = continue_pagination(response)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    try:
        # Open the configuration.json file and load its contents
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        log.info("Using empty configuration!")
        configuration = {}

    # Test the connector locally
    connector.debug(configuration=configuration)
