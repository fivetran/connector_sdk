# This is a simple example for how to work with the fivetran_connector_sdk module.
# It shows you the inference that is applied if you send data without defining its type in the Schema() method.
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
            "table": "unspecified",  # Name of the table in the destination.
            "primary_key": ["id"],  # Primary key column(s) for the table.
            # No columns are defined, meaning the types will be inferred.
            # Column names will be taken directly from the keys sent in the data
        },
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
    log.warning("Example: Common Patterns For Connectors - Unspecified Types")

    # Upsert operation to insert/update the row in the "unspecified" table.
    # The data dictionary contains various data types.
    # Since the schema does not specify column types, they will be inferred from the data.
    log.debug("upserting to table 'unspecified'")
    op.upsert(
        table="unspecified",
        data={  # The keys sent here, e.g. id, _bool, _short, _ndatetime etc,. will be used as column names
            "id": 1,  # Primary key.
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
# ┌───────┬────────────────────────┬───────┬─────────┬─────────────────┬────────┬─────────────────────┬───────────┬────────────┬──────────────────────────┬──────────────────┬──────────────────┬─────────┬────────┐
# │  id   │          _xml          │ _bool │  _dec   │      _long      │ _short │     _ndatetime      │   _json   │   _ndate   │           _utc           │       _str       │     _binary      │ _double │ _float │
# │ int32 │        varchar         │ int32 │ varchar │      int64      │ int32  │       varchar       │  varchar  │  varchar   │         varchar          │     varchar      │       blob       │  float  │ float  │
# ├───────┼────────────────────────┼───────┼─────────┼─────────────────┼────────┼─────────────────────┼───────────┼────────────┼──────────────────────────┼──────────────────┼──────────────────┼─────────┼────────┤
# │     1 │ <tag>This is XML</tag> │     1 │ 105.34  │ 132353453453635 │     15 │ 2007-12-03T10:15:30 │ {"a": 10} │ 2007-12-03 │ 2007-12-03T10:15:30.123Z │ This is a string │ \x00\x01\x02\x03 │  0.0001 │   10.4 │
# └───────┴────────────────────────┴───────┴─────────┴─────────────────┴────────┴─────────────────────┴───────────┴────────────┴──────────────────────────┴──────────────────┴──────────────────┴─────────┴────────┘
