"""
This is an example to show how to handle complex configuration options in your connector code.
It demonstrates combining configuration values from configuration.json with native Python types defined in a separate config.py file.
It also shows how to define additional constant values directly in the connector code as well.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.
"""

# Import the json module to handle JSON data.
import json

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import static non-sensitive configuration from a separate file.
from config import API_CONFIGURATIONS

# You can define constants which can be used across your connector code
# These are useful for defining static values that do not change across syncs and are not sensitive in nature.
# Do not store secrets here. Always use configuration.json for sensitive values such as API keys or credentials.
# Important: Values defined this way cannot be viewed or modified from the Fivetran dashboard
# If you need to edit the values from the Fivetran dashboard, define them in configuration.json instead.
__API_CONSTANTS = {"api_quota": 12345, "use_bulk_api": True}


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
            "table": "crypto",  # Name of the table in the destination.
            "primary_key": ["msg"],  # Primary key column(s) for the table.
            # No columns are defined, meaning the types will be inferred.
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
    required_configs = ["api_key", "client_id", "client_secret"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def parse_and_get_values(configuration):
    """
    This function is responsible for fetching and parsing the configuration and constant values.
    This function fetches the sensitive values from configuration.json and the static values from config.py.
    This function parses them as needed for use in the connector code.
    You can modify the logic in this function to suit your needs.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        A tuple containing the values: api_key, client_id, client_secret, regions, currencies
    """

    # Fetch the configuration values defined in configuration.json
    # These values are configurable from the Fivetran dashboard
    # These configuration values are always strings, so you may need to cast them to the appropriate type based on your needs
    # You should always store sensitive values such as API keys and credentials in the configuration.json
    # You can parse these values as needed by your connector code as well
    api_key = configuration.get("api_key")
    client_id = configuration.get("client_id")
    client_secret = configuration.get("client_secret")

    # Fetch the complex configuration values from config.py
    # These values are static in nature and cannot be changed from the Fivetran dashboard
    # To change them, you must update the file and redeploy the connector
    # You must not store sensitive values in config.py. Always use configuration.json for any sensitive values
    regions = API_CONFIGURATIONS.get("regions")
    currencies = API_CONFIGURATIONS.get("currencies")

    return api_key, client_id, client_secret, regions, currencies


def validate_fetched_values(api_key, client_id, client_secret, regions, currencies):
    """
    This is a test function to ensure that the values fetched from parse_and_get_values() function are of the expected types and formats.
    You will not typically need to define a function like this in your connector code
    But it is included here for demonstration purposes to validate and test the values you fetch.
    Args:
        api_key: api_key value, expected to be a string
        client_id: client_id value, expected to be a string
        client_secret: client_secret value, expected to be a string
        regions: regions value, expected to be a list of strings
        currencies: currencies value, expected to be a list of dictionaries with 'From' and 'To' keys
    """
    # configuration fetched from configuration.json
    assert isinstance(api_key, str)
    assert isinstance(client_id, str)
    assert isinstance(client_secret, str)
    # static configuration fetched from config.py
    assert isinstance(regions, list) and len(regions) == 3
    assert isinstance(currencies, list) and len(currencies) == 2

    # You can also use the constant values defined in the connector code
    api_quota = __API_CONSTANTS.get("api_quota")
    use_bulk_api = __API_CONSTANTS.get("use_bulk_api")
    assert isinstance(api_quota, int) and api_quota == 12345
    assert isinstance(use_bulk_api, bool) and use_bulk_api


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
    log.warning("Example: Common patterns for connectors - Complex Configuration Options")

    # validate the configuration to ensure all required configuration values are present
    validate_configuration(configuration)

    # Get the values
    api_key, client_id, client_secret, regions, currencies = parse_and_get_values(configuration)

    # Validate the fetched values to ensure they are of the expected types and formats.
    validate_fetched_values(api_key, client_id, client_secret, regions, currencies)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="crypto", data={"msg": "hello world"})

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


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
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)

# Resulting table:
# ┌────────────────────────────────────────────────┐
# │                      msg                       │
# │                    varchar                     │
# ├────────────────────────────────────────────────┤
# │                   hello world                  │
# └────────────────────────────────────────────────┘
