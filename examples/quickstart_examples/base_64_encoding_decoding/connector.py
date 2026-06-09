# This is a simple example of how to work with Base 64 Encoding and Decoding.
# It defines a simple `update` method, which upserts defined data to a table named "user".
# See the Technical Reference documentation
# (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.


# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import base64 for API Auth Param Encoding
import base64


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
            "table": "user",
            "primary_key": ["id"],
            "columns": {"id": "STRING", "name": "STRING", "email": "STRING"},
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
    log.warning("Example: QuickStart Examples - Using Base64 Encoding and Decoding")

    # Original values
    user_info = {"id": "12345", "name": "John Doe", "email": "john.doe@example.com"}

    # Encode each value to Base64
    encoded_info = {
        key: base64.b64encode(value.encode("utf-8")).decode("utf-8")
        for key, value in user_info.items()
    }
    # Upsert the encoded data to the "user" table
    op.upsert(table="user", data=encoded_info)

    # Decode each Base64 value back to original
    decoded_info = {
        key: base64.b64decode(value.encode("utf-8")).decode("utf-8")
        for key, value in encoded_info.items()
    }
    # Upsert the decoded data to the "user" table
    op.upsert(table="user", data=decoded_info)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug()

# Resulting table:
# ┌──────────────┬───────────────┬───────────────────────────────┐
# │     id       │      name     │             email             │
# │   string     │     string    │             string            │
# ├──────────────┼───────────────┼───────────────────────────────┤
# │    12345     │   John Doe    │  john.doe@example.com         │
# │   MTIzNDU=   │ Sm9obiBEb2U=  │ am9obi5kb2VAZXhhbXBsZS5jb20=  │
# ├──────────────┴───────────────┴───────────────────────────────┤
# │  2 rows                                            3 columns │
# └──────────────────────────────────────────────────────────────┘
