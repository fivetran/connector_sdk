# This is a simple example for how to work with the fivetran_connector_sdk module.
# It shows the three operations you can use to deliver data to Fivetran.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

import uuid  # Import the uuid module to generate unique identifiers.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


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
            "table": "three",  # Name of the table in the destination.
            "primary_key": ["id"],  # Primary key column(s) for the table.
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
    log.warning("Example: Common Patterns For Connectors - Three Operations")

    # Generate three unique identifiers using the uuid4 method.
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    # Loop through the generated ids and perform an upsert operation for each.
    for ii, id in enumerate(ids):
        log.debug(f"adding {id}")
        # Upsert operation to insert/update the row in the "three" table.
        op.upsert(table="three", data={"id": id, "val1": id, "val2": ii})

    log.debug(f"updating {ids[1]} to 'abc'")
    # Update operation to modify the row with the second id in the "three" table.
    op.update(table="three", modified={"id": ids[1], "val1": "abc"})

    log.debug(f"deleting {ids[2]}")
    # Delete operation to remove the row with the third id from the "three" table.
    op.delete(table="three", keys={"id": ids[2]})

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


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
# ┌──────────────────────────────────────┬──────────────────────────────────────┬───────┐
# │                  id                  │                 val1                 │ val2  │
# │               varchar                │               varchar                │ int32 │
# ├──────────────────────────────────────┼──────────────────────────────────────┼───────┤
# │ c188327d-32fb-461b-90b2-4a08daf6c2db │ c188327d-32fb-461b-90b2-4a08daf6c2db │     0 │
# │ efcbeddb-44d5-4edf-900e-d50cf9146859 │ abc                                  │     1 │
# └──────────────────────────────────────┴──────────────────────────────────────┴───────┘
