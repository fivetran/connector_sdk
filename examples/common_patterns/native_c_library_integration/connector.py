# This example shows how to call a native C library from a Connector SDK connector using ctypes.
# The bundled library (native/custom.c) is compiled into native/libcustom.so by drivers/installation.sh
# at deploy time, which runs before connector.py and guarantees the library is built for the
# hosted production platform (Linux amd64/x86_64).
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import json for reading configuration file
import json

# Import the ctypes wrapper around the bundled native library.
import native_wrapper


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
            "table": "calculations",  # Name of the table in the destination.
            "primary_key": ["id"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "id": "INT",
                "operand_a": "INT",
                "operand_b": "INT",
                "result": "INT",  # Computed by the native C library's `add` function.
            },
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: a dictionary contains any secrets or payloads you configure when deploying the connector.
        state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync.
    """
    # Sample source rows. In a real connector, these would come from your API or database.
    sample_rows = [
        {"id": 1, "operand_a": 2, "operand_b": 3},
        {"id": 2, "operand_a": 10, "operand_b": 20},
        {"id": 3, "operand_a": -5, "operand_b": 5},
    ]

    log.info("Computing results using the native C library (native/libcustom.so).")
    for row in sample_rows:
        result = native_wrapper.add(row["operand_a"], row["operand_b"])
        op.upsert(
            "calculations",
            {
                "id": row["id"],
                "operand_a": row["operand_a"],
                "operand_b": row["operand_b"],
                "result": result,
            },
        )

    # Checkpoint after each sync. This example has no incremental cursor, so state stays empty.
    op.checkpoint(state)


# Create the connector object using the schema and update functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# required inputs docs https://fivetran.com/docs/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
