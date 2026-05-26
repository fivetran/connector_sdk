# This is a simple example for how to work with the fivetran_connector_sdk module.
# It uses a simple_three_step_cursor SOURCE_DATA object created at the start of the script, and demonstrates the Schema() method use.
# It also shows a way to manage state.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Define the SOURCE_DATA which simulates the source data that will be upserted to Fivetran.
SOURCE_DATA = [
    {"id": 10, "message": "Hello world"},
    {"id": 20, "message": "Hello again"},
    {"id": 30, "message": "Good bye"},
]


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
            "table": "hello_world",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "message": "STRING",  # Contains a dictionary of column names and data types
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        }
    ]


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
    log.warning("Example: QuickStart Examples - Simple Three Step Cursor")

    # Retrieve the cursor from the state object to determine the current position in the SOURCE_DATA.
    # If the cursor is not present in the state, start from the beginning (cursor = 0).
    cursor = state["cursor"] if "cursor" in state else 0
    log.debug(f"current cursor is {repr(cursor)}")

    # Get the row of data from SOURCE_DATA using the cursor position.
    if cursor >= SOURCE_DATA.__len__():
        raise Exception(
            "Expected ‘list index out of range’ on 4th sync due to local data being exhausted in Example Connector"
        )
    row = SOURCE_DATA[cursor]

    # Upsert operation to insert/update the row in the "hello_world" table.
    op.upsert(table="hello_world", data=row)

    # Update the state with the new cursor position, incremented by 1.
    new_state = {"cursor": cursor + 1}
    log.debug(f"state updated, new state: {repr(new_state)}")

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=new_state)


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug()

# Resulting table:
# ┌───────┬─────────────┐
# │  id   │   message   │
# │ int32 │   varchar   │
# ├───────┼─────────────┤
# │   10  │ Hello world │
# │   20  │ Hello again │
# │   30  │  Good bye   │
# └───────┴─────────────┘
