# This example demonstrates how you can write a complex connector comprising multiple .py files.
# This includes the __init__.py which is needed to ensure the timestamp_serializer module is correctly recognized.
# The timestamp_serializer module shown in this example is used to handle scenarios where the source sends timestamps in two different formats.
# It assumes that the source will send timestamps in UTC timezone.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import self written modules
from utils.timestamp_serializer import TimestampSerializer


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
            "table": "event",  # Name of the table in the destination.
            "primary_key": ["name"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "name": "STRING",  # String column for the name.
                "timestamp": "UTC_DATETIME",  # UTC date-time column for the timestamp
            },
        }
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
    log.warning("Example: QuickStart Examples - Simple Three Step Cursor")

    timestamp_serializer = TimestampSerializer()

    row_1 = {"name": "Event1", "timestamp": "2024/09/24 14:30:45"}
    row_1["timestamp"] = timestamp_serializer.serialize(row_1["timestamp"])
    op.upsert(table="event", data=row_1)

    row_2 = {"name": "Event2", "timestamp": "2024-09-24 10:30:45"}
    row_2["timestamp"] = timestamp_serializer.serialize(row_2["timestamp"])
    op.upsert(table="event", data=row_2)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug()

# Resulting table:
# ┌───────────────────┬──────────────────────────────────┐
# │      name         │             timestamp            │
# │     varchar       │      timestamp with time zone    │
# ├───────────────────┼──────────────────────────────────│
# │      Event1       │  2024-09-24 14:30:45.000 +0000   │
# │      Event2       │  2024-09-24 10:30:45.000 +0000   │
# └───────────────────┴──────────────────────────────────┘
