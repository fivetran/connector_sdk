"""
This is a simple example for how to work with the fivetran_connector_sdk module.
The example demonstrates how to fetch data from Harness.io API and load it into a destination using Fivetran's Connector SDK.
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

from harness_api import (
    HarnessAPI,
)  # Import the HarnessAPI class for interacting with the Harness.io API


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
    required_configs = ["api_token", "account_id"]
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
            "table": "user_projects",  # Name of the table in the destination, required.
            "primary_key": ["identifier"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "identifier": "STRING",  # Contains a dictionary of column names and data types
                "modules": "JSON",
                "tags": "JSON",
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        },
        {
            "table": "connectors",
            "primary_key": ["category"],
            "columns": {
                "category": "STRING",
                "connectors": "JSON",
            },
        },
        {
            "table": "budgets",
            "primary_key": ["uuid"],
            "columns": {
                "uuid": "STRING",
                "scope": "JSON",
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        },
        {
            "table": "mean_time_to_resolution",
            "columns": {
                "unit": "STRING",
            },
        },
    ]


def upsert_all_projects_for_user(api_handler, state):
    """
    Example function to fetch all projects for a user and upsert them into the destination.
    Args:
        api_handler: An instance of the HarnessAPI class for making API requests.
        state: A dictionary containing state information from previous runs.
    """

    # Initial query parameters for the API request
    query_params = {
        "accountIdentifier": api_handler.account_id,
        "pageSize": 100,  # Adjust page size as needed
    }

    while True:
        # Make the API request to fetch projects for the user
        response = api_handler.get("/ng/api/projects", query_params)
        data = response.get("data", {})
        projects = data.get("content", [])

        for project in projects:
            # Combine project data into a single dictionary for upsert
            # Here we are flattening the project dictionary to ensure all relevant fields are included in the row_data dictionary.
            # You can modify this as per your data structure and requirements.
            row_data = {
                **project["project"],
                **{k: v for k, v in project.items() if k != "project"},
            }
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table="user_projects", data=row_data)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        # Check if there is a next page
        # If there is no next page, break the loop and end the function
        if not data.get("pageToken"):
            break

        # Update query parameters for the next page
        query_params["pageToken"] = data["pageToken"]


def upsert_all_connectors(api_handler, state):
    """
    Example function to fetch all connectors and upsert them into the destination.
    Args:
        api_handler: An instance of the HarnessAPI class for making API requests.
        state: A dictionary containing state information from previous runs.
    """

    # Initial query parameters for the API request
    query_params = {
        "accountIdentifier": api_handler.account_id,
    }

    # Make the API request to fetch connectors
    response = api_handler.get("/ng/api/connectors/catalogue", query_params)
    data = response.get("data", {})
    connectors = data.get("catalogue", [])

    for conn in connectors:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted
        op.upsert(table="connectors", data=conn)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


def upsert_all_budgets(api_handler, state):
    """
    Example function to fetch all budgets and upsert them into the destination.
    Args:
        api_handler: An instance of the HarnessAPI class for making API requests.
        state: A dictionary containing state information from previous runs.
    """

    # Initial query parameters for the API request
    query_params = {
        "accountIdentifier": api_handler.account_id,
    }

    # Make the API request to fetch budgets
    response = api_handler.get("/ccm/api/budgets", query_params)
    budgets = response.get("data", [])

    for budget in budgets:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted
        op.upsert(table="budgets", data=budget)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


def upsert_mean_time_to_resolution(api_handler, state):
    """
    Example function to fetch mean time to resolution data and upsert them into the destination.
    Args:
        api_handler: An instance of the HarnessAPI class for making API requests.
        state: A dictionary containing state information from previous runs.
    """

    # Initial query parameters for the API request
    body = {
        "filter": {
            "ratings": ["good", "slow", "needs_attention"],
            "calculation": "ticket_velocity",
            "work_items_type": "jira",
            "limit_to_only_applicable_data": "true",
            "integration_ids": ["<INTEGRATION_ID>"],
        },
        "ou_ids": ["<OU_ID>"],
        "across": "velocity",
        "widget_id": "<WIDGET_ID>",
    }

    # Make the API request to fetch mean time to resolution data
    response = api_handler.post(endpoint="/v1/dora/mean-time", data=body)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The op.upsert method is called with two arguments:
    # - The first argument is the name of the table to upsert the data into.
    # - The second argument is a dictionary containing the data to be upserted
    op.upsert(table="mean_time_to_resolution", data=response)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


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

    log.warning("Example: Source Examples - Harness.io API Example")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Create an instance of the HarnessAPI class to interact with the Harness.io API
    api_handler = HarnessAPI(
        api_key=configuration["api_token"], account_id=configuration["account_id"]
    )

    try:
        # Fetch and upsert all projects for the user
        upsert_all_projects_for_user(api_handler=api_handler, state=state)
    except Exception as e:
        log.error("Error fetching user projects data", e)

    try:
        # Fetch and upsert all connectors
        upsert_all_connectors(api_handler=api_handler, state=state)
    except Exception as e:
        log.error("Error fetching connectors data", e)

    try:
        # Fetch and upsert all budgets
        upsert_all_budgets(api_handler=api_handler, state=state)
    except Exception as e:
        log.error("Error fetching budgets data", e)

    try:
        # Fetch and upsert mean time to resolution data
        upsert_mean_time_to_resolution(api_handler=api_handler, state=state)
    except Exception as e:
        log.error("Error fetching mean time to resolution data", e)


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
