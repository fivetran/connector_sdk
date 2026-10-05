"""
This connector demonstrates how to implement a simple connector that supports multiple schemas.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


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
            "schema": "schema_1",
            "table": "sample_table",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
            },
        },
        {
            "schema": "schema_2",
            "table": "sample_table",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
            },
        },
    ]


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
    log.warning("Examples: Quickstart - multiple schemas")
    # fetch the data row
    data = get_data_row()
    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the schema where the destination table resides.
    # The second argument is the name of the destination table.
    # The third argument is a dictionary containing the record to be upserted.
    op.upsert(schema="schema_1", table="sample_table", data=data)
    op.upsert(schema="schema_2", table="sample_table", data=data)

    # Using multiple schema with update()
    modified_data = {"id": 1, "sample_column": 100}
    op.update(schema="schema_1", table="sample_table", data=modified_data)

    # Using multiple schema with delete()
    key_to_delete = {"id": 1}
    op.delete(schema="schema_2", table="sample_table", key=key_to_delete)

    # Using multiple schema with truncate()
    op.truncate(schema="schema_1", table="sample_table")

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def get_data_row():
    """
    This function is a placeholder for your data retrieval logic.
    In a real-world scenario, you would implement the logic to fetch data from your source system.
    For demonstration purposes, this function returns a static dictionary representing a data row.
    """
    return {"id": 1, "sample_column": 42}


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
# Schema: schema_1  |  Table: sample_table
# ┌──────────┐─────────────────────┐─────────────────────┐
# │    id    │    sample_column    │  _fivetran_deleted  │
# ├──────────┤─────────────────────┤─────────────────────┤
# │     1    │         100         │       true          │
# └──────────┴─────────────────────┘─────────────────────┘
# Schema: schema_2  |  Table: sample_table
# ┌──────────┐─────────────────────┐─────────────────────┐
# │    id    │    sample_column    │  _fivetran_deleted  │
# ├──────────┤─────────────────────┤─────────────────────┤
# │     1    │         42          │       true          │
# └──────────┴─────────────────────┘─────────────────────┘
