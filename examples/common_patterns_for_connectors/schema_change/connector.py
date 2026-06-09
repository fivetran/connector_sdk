# This is an example for how to work with the fivetran_connector_sdk module.
"""This connector demonstrates how Fivetran handles data type changes without defining them in Connector SDK."""

# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# This connector demonstrates schema changes by returning data with different types
# First sync: int_to_string field is an integer (42)
# Second sync: int_to_string field is a float (42.42)
# Third sync: int_to_string field is a non-numeric string ("forty-two point forty-two")
# Fourth+ syncs: int_to_string field is a float again (42.43)

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
import json


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update

    In this example the update function demonstrates schema evolution across syncs.

    Args:
        configuration (dict): Configuration parameters (unused in this example)
        state (dict): State dictionary to track sync count and maintain sync history
    """

    log.warning("Example: Fivetran Platform Features - Schema Change")

    # Get the current sync count from state, defaulting to 0 if not present
    sync_count = state.get("sync_count", 0)

    # Define the sequence of values that will demonstrate type evolution
    # Each value represents a different data type that will be used in subsequent syncs
    values = [42, 42.42, "forty-two point forty-two", 42.43]

    # Log information about the schema change demonstration
    log.warning("Schema change demo: field type evolves across syncs")
    log.info(
        f"Sync #{sync_count + 1}: inserting value '{values[min(sync_count, 3)]}' ({type(values[min(sync_count, 3)]).__name__})"
    )

    # Define descriptive text for each sync to explain the type change
    descriptions = [
        "First sync with integer",
        "Second sync with float",
        "Third sync with non-numeric string",
        "Fourth sync with float again",
    ]

    # Upsert operation with the current value and its description
    # The min(sync_count, 3) ensures we don't go beyond our defined values
    op.upsert(
        table="change_int_to_string",
        data={
            "id": 1,
            "int_to_string": values[min(sync_count, 3)],
            "description": descriptions[min(sync_count, 3)],
        },
    )

    # Checkpoint operation to save the updated sync count
    op.checkpoint({"sync_count": sync_count + 1})


# Create the connector object using the update function
connector = Connector(update=update)

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
