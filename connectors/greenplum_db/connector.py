# This is a simple example for how to work with the fivetran_connector_sdk module.
# The example demonstrates how to fetch data from GreenPlum database using psycopg2 and upsert it into a destination table.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.

# Import required libraries.
import json
from greenplumclient import GreenplumClient

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# Name of the destination table to upsert data into.
DESTINATION_TABLE = "sample_table"


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
            "table": DESTINATION_TABLE,  # Name of the table in the destination.
            "primary_key": ["datid"],  # Primary key column(s) for the table.
            "columns": {
                "datid": "INT",
                "query_start": "UTC_DATETIME",
            },
            # columns not defined will be inferred.
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: dictionary containing any secrets or payloads you configure when deploying the connector.
        state:  a dictionary containing the state checkpointed during the prior sync.
        The state dictionary is empty for the first sync or for any full re-sync.
    """
    log.warning("Example: Source Examples: Greenplum Database")

    # Get the last query from the state dictionary.
    last_query_timestamp = state.get("last_query_timestamp", "1990-01-01T00:00:00Z")

    # create a GreenplumClient object to handle database operations.
    greenplum_client = GreenplumClient(configuration)
    log.info("Connected to Greenplum database.")

    # SQL query to fetch data from the Greenplum database.
    # you can modify this query to fetch data from any table in your Greenplum database as per your need.
    # The query used here is for demonstration purposes.
    # This query fetches all rows from the pg_stat_activity system view.
    query = f"SELECT * FROM pg_stat_activity WHERE query_start > '{last_query_timestamp}'"

    # Call the upsert_data method to fetch data from the Greenplum database and upsert it into the destination table.
    greenplum_client.upsert_data(query, DESTINATION_TABLE, state)


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
