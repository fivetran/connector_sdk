# This is a simple example for how to work with the fivetran_connector_sdk module.
# It shows how to use the Schema() method to define columns for all supported data types.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

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
            "table": "specified",  # Name of the table in the destination.
            "primary_key": ["_bool"],  # Primary key column(s) for the table.
            "columns": {
                "_bool": "BOOLEAN",  # Boolean data type.
                "_short": "SHORT",  # Short integer data type.
                "_long": "LONG",  # Long integer data type.
                "_dec": {  # Decimal data type with precision and scale.
                    "type": "DECIMAL",
                    "precision": 15,
                    "scale": 2,
                },
                "_float": "FLOAT",  # Floating-point data type.
                "_double": "DOUBLE",  # Double precision floating-point data type.
                "_ndate": "NAIVE_DATE",  # Naive date data type.
                "_ndatetime": "NAIVE_DATETIME",  # Naive date-time data type.
                "_utc": "UTC_DATETIME",  # UTC date-time data type.
                "_binary": "BINARY",  # Binary data type.
                "_xml": "XML",  # XML data type.
                "_str": "STRING",  # String data type.
                "_json": "JSON",  # JSON data type.
                "_null": "STRING",  # String data type, can handle null values.
            },
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

    log.warning("Example: Common Patterns For Connectors - Specified Types")

    # Upsert operation to insert/update the row in the "specified" table.
    log.debug("upserting to table 'specified'")
    op.upsert(
        table="specified",
        data={
            "_bool": True,  # Boolean value.
            "_short": 15,  # Short integer value.
            "_long": 132353453453635,  # Long integer value.
            "_dec": "105.34",  # Decimal value as a string.
            "_float": 10.4,  # Floating-point value.
            "_double": 1e-4,  # Double precision floating-point value.
            "_ndate": "2007-12-03",  # Naive date value.
            "_ndatetime": "2007-12-03T10:15:30",  # Naive date-time value.
            "_utc": "2007-12-03T10:15:30.123Z",  # UTC date-time value.
            "_binary": b"\x00\x01\x02\x03",  # Binary data.
            "_xml": "<tag>This is XML</tag>",  # XML data.
            "_str": "This is a string",  # String data.
            "_json": {"a": 10},  # JSON data.
            "_null": None,  # Null value.
        },
    )

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
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    result = connector.debug()

# Resulting table:
# ┌─────────┬────────┬─────────────────┬───────────────┬────────┬─────────┬────────────┬─────────────────────┬───────────────────────────────┬──────────────────┬────────────────────────┬──────────────────┬───────────┬─────────┐
# │  _bool  │ _short │      _long      │     _dec      │ _float │ _double │   _ndate   │     _ndatetime      │             _utc              │     _binary      │          _xml          │       _str       │   _json   │  _null  │
# │ boolean │ int16  │      int64      │ decimal(15,2) │ float  │ double  │    date    │      timestamp      │   timestamp with time zone    │       blob       │        varchar         │     varchar      │  varchar  │ varchar │
# ├─────────┼────────┼─────────────────┼───────────────┼────────┼─────────┼────────────┼─────────────────────┼───────────────────────────────┼──────────────────┼────────────────────────┼──────────────────┼───────────┼─────────┤
# │ true    │     15 │ 132353453453635 │        105.34 │   10.4 │  0.0001 │ 2007-12-03 │ 2007-12-03 10:15:30 │ 2007-12-03 15:45:30.123+05:30 │ \x00\x01\x02\x03 │ <tag>This is XML</tag> │ This is a string │ {"a": 10} │         │
# └─────────┴────────┴─────────────────┴───────────────┴────────┴─────────┴────────────┴─────────────────────┴───────────────────────────────┴──────────────────┴────────────────────────┴──────────────────┴───────────┴─────────┘
