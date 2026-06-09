# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with a DolphinDB database containing a large dataset using pydolphindb.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import the required libraries
import json
import pydolphindb  # This is used to connect to DolphinDB
import pandas as pd  # This is used for data manipulation
from datetime import datetime, timezone  # This is used for handling timestamps

# Define the batch size for fetching data from DolphinDB in batches
BATCH_SIZE = 1000


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains the required keys.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    required_keys = ["HOST", "PORT", "DATABASE", "TABLE_NAME", "USERNAME", "PASSWORD"]
    for key in required_keys:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def serialize_row_data(row: dict):
    """
    Serialize the row data to ensure it is in the correct format for upserting.
    This function converts pandas timestamp objects to python datetime objects.
    You can modify this function to handle other data types as needed.
    Args:
        row: a dictionary representing a single row of data.
    Returns:
        A serialized dictionary with datetime objects.
    """
    for key, value in row.items():
        if isinstance(value, pd.Timestamp):
            row[key] = value.to_pydatetime()  # Convert pandas Timestamp to python datetime object
    return row


def parse_state_timestamp(state):
    """
    Parse the last_timestamp from the state dictionary.
    If the timestamp is not present or invalid, return a default datetime.
    Args:
        state: a dictionary containing state information from previous runs
    Returns:
        A datetime object representing the last processed timestamp.
    """
    timestamp_str = state.get("last_timestamp")
    if not timestamp_str:
        return datetime(1990, 1, 1, tzinfo=timezone.utc)
    try:
        # Handle possible 'Z'
        timestamp_str = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if timestamp_str.tzinfo is None:
            timestamp_str = timestamp_str.replace(tzinfo=timezone.utc)
        return timestamp_str
    except ValueError:
        return datetime(1990, 1, 1, tzinfo=timezone.utc)


def create_dolphin_client(configuration: dict):
    """
    Create a connection to DolphinDB
    This function creates a DolphinDB connection using the pydolphindb library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        connection: a DolphinDB connection object
    """
    host = configuration.get("HOST")
    port = int(configuration.get("PORT"))
    username = configuration.get("USERNAME")
    password = configuration.get("PASSWORD")

    try:
        connection = pydolphindb.connect(
            host=host, port=port, username=username, password=password
        )
        log.info(f"Successfully connected to DolphinDB at {host}:{port}")
        return connection
    except Exception as e:
        raise RuntimeError(f"Failed to connect to DolphinDB: {e}")


def execute_query_and_upsert(cursor, query, table_name, state, batch_size=1000):
    """
    This function executes a query and upserts the results into the destination.
    The data is fetched in a batching manner to handle large datasets efficiently.
    Args:
        cursor: a DolphinDB cursor object
        query: the DolphinDB query to execute
        table_name: the name of the table to upsert data into
        state: a dictionary containing state information from previous runs
        batch_size: the number of rows to fetch in each batch
    """
    # Initialize the last_timestamp from the state or set a default value
    last_timestamp = parse_state_timestamp(state=state)

    # Execute the query to fetch data from the DolphinDB table
    cursor.execute(query)
    # Get column names from cursor metadata
    # This is required to prepare the data in the format required by the upsert operation
    column_names = [desc[0] for desc in cursor.description]

    # fetchmany() is used to retrieve a batch of rows from the cursor
    # The loop continues until there are no more rows to fetch
    # This is done to avoid loading the entire dataset into memory at once, which is crucial for large datasets
    # This prevents memory overflow and allows processing of large datasets in manageable chunks
    while True:
        # Fetch a batch of rows from the cursor
        rows = cursor.fetchmany(batch_size)
        if not rows:
            # If no rows are returned, break the loop
            # This indicates that all data has been processed
            break
        # Iterate over the fetched rows and prepare them for upsert
        # Each row is converted to a dictionary with column names as keys
        # and serialized to ensure the data is in the correct format for upserting
        for row in rows:
            upsert_row = dict(zip(column_names, row))
            upsert_row = serialize_row_data(upsert_row)
            # The 'upsert' operation is used to insert or update the data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=upsert_row)

            if upsert_row["timestamp"] > last_timestamp:
                # Update the last_timestamp if the current row's timestamp is greater
                last_timestamp = upsert_row["timestamp"]

        state["last_timestamp"] = last_timestamp.isoformat()
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

    # After processing all rows, update the state with the last processed timestamp and checkpoint it
    state["last_timestamp"] = last_timestamp.isoformat()
    op.checkpoint(state)


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
            "table": "trade",  # Name of the table in the destination, required.
            "primary_key": [],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "symbol": "STRING",  # Contains a dictionary of column names and data types
                "timestamp": "UTC_DATETIME",
                "price": "FLOAT",
                "volume": "INT",
            },  # For any columns whose names are not provided here, their data types will be inferred
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
    # Validate the configuration to ensure it contains the required keys
    validate_configuration(configuration)

    # Initialize the last_timestamp from the state or set a default value
    # This is used to track the last processed timestamp for incremental updates
    last_timestamp = state.get("last_timestamp", "1990-01-01T00:00:00")

    # Create a DolphinDB connection and cursor
    connection = create_dolphin_client(configuration)
    cursor = connection.cursor()
    # Get the database and table name from the configuration
    database_name = configuration.get("DATABASE")
    table_name = configuration.get("TABLE_NAME")

    # IMPORTANT: This connector requires the following prerequisites in your DolphinDB instance:
    # 1. A database named as specified in your configuration
    # 2. A table named as specified in your configuration with the following schema:
    #    - symbol (STRING): Name of the stock or asset
    #    - timestamp (NANOTIMESTAMP): Timestamp of the trade
    #    - price (FLOAT): price of the trade
    #    - volume (INT): volume of the trade
    # Make sure you have proper permissions to access this table
    # If these prerequisites are not met, the connector will not function correctly.

    # Define the DolphinDB query to fetch data from the specified table
    # The query retrieves all records with a timestamp greater than the last_timestamp.
    # The query is ordered by timestamp to ensure the data is processed in chronological order. This is important for data consistency.
    # You can modify this query to suit your needs
    dolphin_query = f"""
    select symbol, timestamp, price, volume
    from loadTable('dfs://{database_name}', '{table_name}')
    where timestamp > nanotimestamp("{last_timestamp.replace("-", ".")}")
    order by timestamp
    """

    try:
        # Execute the query and upsert the results into the destination table
        execute_query_and_upsert(cursor, dolphin_query, table_name, state, batch_size=BATCH_SIZE)
        log.info(f"Successfully upserted data into {table_name} table.")

    except Exception as e:
        # If an error occurs during the query execution or upsert, raise a RuntimeError
        raise RuntimeError(f"Failed to execute query and upsert data: {e}")

    finally:
        # Close the DolphinDB cursor and connection to release resources
        cursor.close()
        connection.close()
        log.info("DolphinDB connection closed successfully.")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
