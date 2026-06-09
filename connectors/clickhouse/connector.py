# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with a Clickhouse database containing a large dataset and using clickhouse_connect.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
import json
import clickhouse_connect  # This is used to connect to ClickHouse


def create_clickhouse_client(configuration: dict):
    """
    Create and test a connection to ClickHouse
    This function creates a ClickHouse client using the clickhouse_connect library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        client: a ClickHouse client object
    """
    client = clickhouse_connect.get_client(
        host=configuration.get("hostname"),
        username=configuration.get("username"),
        password=configuration.get("password"),
        secure=True,
    )

    try:
        test_connection = client.query("SELECT 1").result_rows[0][0]
        log.info(f"Connection to ClickHouse successful: {test_connection}")
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to connect to ClickHouse: {e}")


def execute_query_and_upsert(client, query, table_name, state):
    """
    This function executes a query and upserts the results into the destination.
    The data is fetched in a streaming manner to handle large datasets efficiently.
    Args:
        client: a ClickHouse client object
        query: the SQL query to execute
        table_name: the name of the table to upsert data into
        state: a dictionary containing state information from previous runs
    """
    # This query fetches the column names from the ClickHouse table
    # The column_names is not supported in ClickHouse streaming queries
    # So we need to run a separate query to get the column names
    # This is needed to map the data to the correct columns in the upsert operation
    column_names = client.query(query + " LIMIT 0").column_names

    with client.query_rows_stream(query) as stream:
        for row in stream:
            # Convert the row tuple to a dictionary using the column names
            row = dict(zip(column_names, row))
            # Upsert the data into the destination table
            op.upsert(table=table_name, data=row)

            # Update the state with the last created_at timestamp
            if row["created_at"]:
                last_created = row.get("created_at").isoformat()
                if last_created > state.get("last_created", "01-01-1800T00:00:00"):
                    state["last_created"] = last_created

    log.info(f"Upserted data into {table_name} successfully.")
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # check if required configuration values are present in configuration
    for key in ["hostname", "username", "password", "database"]:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value : {key}")

    return [
        {
            "table": "test_table",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
                "created_at": "UTC_DATETIME",
            },
        }
    ]


def update(configuration, state):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    # Create a ClickHouse client
    client = create_clickhouse_client(configuration)
    database_name = configuration.get("database")
    table_name = "sample_table"

    # IMPORTANT: This connector requires the following prerequisites in your ClickHouse instance:
    # 1. A database named as specified in your configuration
    # 2. A table named 'sample_table' with the following schema:
    #    - id (UInt32): Primary key
    #    - name (String): Item name
    #    - value (Float64): Numeric value
    #    - created_at (DateTime): Record creation timestamp
    #
    # The table should be created with a statement similar to:
    # CREATE TABLE IF NOT EXISTS database_name.sample_table (
    #     id UInt32,
    #     name String,
    #     value Float64,
    #     created_at DateTime
    # ) ENGINE = MergeTree() ORDER BY id
    #
    # Make sure you have proper permissions to access this table
    # If these prerequisites are not met, the connector will not function correctly.

    last_created = state.get("last_created", "1990-01-01T00:00:00")

    # Execute the query to fetch data from the ClickHouse table and upsert it
    clickhouse_query = (
        f"SELECT * FROM {database_name}.{table_name} WHERE created_at > '{last_created}'"
    )
    # The name of the table to upsert data into
    destination_table = "destination_table"
    execute_query_and_upsert(
        client=client, query=clickhouse_query, table_name=destination_table, state=state
    )


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
