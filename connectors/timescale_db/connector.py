# This is a simple example for how to work with the fivetran_connector_sdk module.
# The example demonstrates how to fetch data from TimescaleDb database using psycopg2 and upsert it into a destination table.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# Import required libraries.
import json
from timescaleclient import TimescaleClient

# Name of the destination tables to upsert data into.
SENSOR_TABLE = "sensor_data"
VECTOR_TABLE = "sensor_embeddings"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters for connecting to the TimescaleDb database.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Check if the credentials for connecting to database is present in the configuration.
    cred = ["HOST", "DATABASE", "USERNAME", "PASSWORD", "PORT"]
    for key in cred:
        if key not in configuration:
            raise ValueError(f"Missing required configuration: {key}")


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
            "table": SENSOR_TABLE,  # Name of the table in the destination.
            "primary_key": ["sensor_id"],  # Primary key column(s) for the table.
            "columns": {
                "sensor_id": "INT",
                "time": "UTC_DATETIME",
            },
            # columns not defined will be inferred.
        },
        {
            "table": VECTOR_TABLE,
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
                "embedding_type": "STRING",
                "vector_data": "JSON",
                "created_at": "UTC_DATETIME",
            },
        },
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
    log.warning("Example: Source Examples: TimescaleDb Database")

    # Validate the configuration to ensure all required parameters are present.
    validate_configuration(configuration)

    # Get the last timestamps from the state dictionary.
    last_timestamp = state.get("last_timestamp", "1990-01-01T00:00:00Z")
    last_vector_timestamp = state.get("last_vector_timestamp", "1990-01-01T00:00:00Z")

    # create a TimescaleClient object to handle database operations.
    timescaledb_client = TimescaleClient(configuration)
    log.info("Connected to TimescaleDb database.")

    # IMPORTANT: This connector requires the following prerequisites in your TimescaleDb database:
    # 1. A table named 'sensor_data' with following schema:
    #    - sensor_id: INT
    #    - temperature: FLOAT
    #    - humidity: FLOAT
    #    - time: UTC_DATETIME
    # 2. A table named 'sensor_embeddings' with following schema:
    #    - id: INT
    #    - sensor_id: INT
    #    - embedding_type: STRING
    #    - vector_data: JSON
    #    - created_at: UTC_DATETIME
    #
    # Sample data must be present in your source TimescaleDb instance before running this connector.
    # If these prerequisites are not met, the connector will not function correctly.

    # SQL query to fetch data from the TimescaleDb database.
    # you can modify this query to fetch data from any table in your TimescaleDb database as per your need.
    # You can include additional features like vectorized queries, chunking, aggregation queries, or any other features supported by TimescaleDb.
    # The query used here is for demonstration purposes.
    query = f"SELECT * FROM {SENSOR_TABLE} WHERE time > '{last_timestamp}' ORDER BY time"

    # This query fetches vector data from the TimescaleDb database.
    # You can modify this query to fetch vector data as per your need.
    # The query used here is for demonstration purposes.
    vector_query = f"SELECT * FROM {VECTOR_TABLE} WHERE created_at > '{last_vector_timestamp}' ORDER BY created_at"

    try:
        # Call the upsert_data method to fetch data from the TimescaleDb database and upsert it into the destination table.
        timescaledb_client.upsert_data(query, SENSOR_TABLE, state)

        # Call the upsert_vector_data method to fetch vector data from the TimescaleDb database and upsert it into the destination table.
        timescaledb_client.upsert_vector_data(vector_query, VECTOR_TABLE, state)

    except Exception as e:
        raise RuntimeError(f"Error during update: {e}")

    finally:
        # Close the connection to the TimescaleDb database.
        timescaledb_client.disconnect()


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
