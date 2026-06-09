# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with Apache Hbase using happybase and thrift
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
import json
import happybase  # This is used to connect to Hbase


def create_hbase_connection(configuration: dict):
    """
    This function creates a hbase connection using the happybase library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        connection: a hbase connection object
    """
    # Get the configuration values from the configuration dictionary
    host = configuration.get("hostname")
    port = int(configuration.get("port"))

    # Create a connection to apache hbase and return the connection object
    # In case of failure, raise a RuntimeError with the error message
    try:
        connection = happybase.Connection(host=host, port=port)
        connection.open()
        log.info(f"Connected to Hbase at {host}:{port}")
        return connection
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Hbase: {e}")


def execute_query_and_upsert(table_connection, column_family, table_name, state, batch_size=1000):
    """
    This function fetches data from hbase and upserts the results into the destination.
    The data is fetched in a streaming manner to handle large datasets efficiently.
    Args:
        table_connection: a hbase table client object
        column_family: the column family to use for the query
        table_name: the name of the table to upsert data into
        state: a dictionary containing state information from previous runs
        batch_size: specifies how big the transferred chunks should be
    """
    # Get the last created timestamp from the state for incremental sync
    last_created = state.get("last_created", "1990-01-01T00:00:00")

    # Create a filter string to fetch only the rows with created_at greater than last_created
    filter_str = f"SingleColumnValueFilter('{column_family}', 'created_at', >, 'binary:{last_created}', true, true)"

    # Fetching the data from apache hbase using the scan method of happybase table connection
    # This method is optimized for handling large datasets and does not load the entire data in the memory
    # The filter parameter is used to filter the rows based on the created_at column
    # The batch_size parameter is used to specify how big the transferred chunks should be
    for key, data in table_connection.scan(batch_size=batch_size, filter=filter_str.encode()):
        try:
            # Decode the key and data to get the row data
            # You can add data preprocessing here if needed
            row_data = {
                "id": key.decode("utf-8"),
                "name": data[f"{column_family}:name".encode()].decode("utf-8"),
                "age": int(data[f"{column_family}:age".encode()].decode("utf-8")),
                "city": data[f"{column_family}:city".encode()].decode("utf-8"),
                "created_at": data[f"{column_family}:created_at".encode()].decode("utf-8"),
            }
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=row_data)

            # Update the last_created timestamp if the current row's created_at is greater
            last_created = max(last_created, row_data["created_at"])
        except KeyError as e:
            # Handle the case where a column is missing in the row data
            log.warning(f"Skipping row {key.decode()} due to missing column: {e}")
            continue

    # update the last_created timestamp in the state for checkpointing
    new_state = {
        "last_created": last_created,
    }
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(new_state)


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # check if required configuration values are present in configuration
    for key in ["hostname", "port", "table_name", "column_family"]:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value : {key}")

    return [
        {
            "table": "profile_table",
            "primary_key": ["id"],
            "columns": {
                "id": "STRING",
                "created_at": "UTC_DATETIME",
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
    # Create a hbase connection
    connection = create_hbase_connection(configuration)
    # Get the table name and column family from the configuration
    hbase_table = configuration.get("table_name")
    column_family = configuration.get("column_family")
    # name of the table to upsert data into
    table_name = "profile_table"

    # Get the connection object to interact with the table
    table_connection = connection.table(hbase_table)

    # Fetch the data and upsert it into the destination
    execute_query_and_upsert(
        table_connection=table_connection,
        column_family=column_family,
        table_name=table_name,
        state=state,
        batch_size=1000,
    )


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
