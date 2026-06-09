# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to sync data from InfluxDB.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
from datetime import datetime, timezone
import json
from influxdb_client_3 import InfluxDBClient3  # InfluxDB client library for Python

# Define the table name where the data will be upserted
TABLE_NAME = "census_table"


def validate_configuration(configuration: dict):
    # check if required configuration values are present in configuration
    for key in ["hostname", "token", "org", "database", "measurement"]:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value : {key}")


def create_influx_client(configuration: dict):
    """
    This function creates an InfluxDB client using the influxdb_client library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        client: an influxdb client object
    """
    try:
        # Validate the configuration to ensure all required fields are present
        validate_configuration(configuration)
        log.info("Configuration validated successfully")

        # Create an InfluxDB client using the provided configuration
        token = configuration.get("token")
        org = configuration.get("org")
        host = configuration.get("hostname")
        client = InfluxDBClient3(host=host, token=token, org=org)
        log.info(f"Successfully connected to InfluxDB at {host} with organization {org}")
        return client

    except Exception as e:
        raise RuntimeError(f"Failed to connect to InfluxDB: {e}")


def handle_timestamp(value):
    """
    This function handles the conversion of timestamp values to UTC datetime object.
    If the value is not a datetime object, it returns the value as is.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # If the datetime is naive, assume it is UTC and add tzinfo explicitly.
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
    return value


def upsert_record_batch(num_rows, record_batch, column_names, table_name, last_upserted_timestamp):
    """
    This function processes a record batch and performs upsert operations for each row.
    Args:
        num_rows: number of rows in the record batch
        record_batch: an Apache Arrow RecordBatch object containing the data
        column_names: list of column names in the record batch
        table_name: the name of the table to upsert data into
        last_upserted_timestamp: the timestamp of the last upserted record, used for incremental syncs
    """
    latest_upserted_timestamp = last_upserted_timestamp

    # Iterate over each row index in the batch.
    for row_idx in range(num_rows):
        row_dict = {}

        # Iterate through each column in the schema.
        for col_idx, col in enumerate(column_names):
            # Extract the value at row `row_idx`, column `col_idx` and convert it to a native Python type.
            value = record_batch.column(col_idx)[row_idx].as_py()
            value = handle_timestamp(value)
            # Store the processed value in the row dictionary.
            row_dict[col] = value

        # The 'upsert' operation is used to insert or update the data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted.
        op.upsert(table=table_name, data=row_dict)

        # Update the latest upserted timestamp if the current row's timestamp is greater.
        if "time" in row_dict:
            fetched_time = row_dict.get("time")
            if fetched_time > latest_upserted_timestamp:
                latest_upserted_timestamp = fetched_time

    # Update the latest upserted timestamp in the state.
    new_state = {"last_upserted_timestamp": latest_upserted_timestamp.isoformat()}
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(new_state)


def parse_state_timestamp(timestamp_str):
    """
    Parse the last_timestamp from the state dictionary.
    If the timestamp is not present or invalid, return a default datetime.
    Args:
        timestamp_str: a string representing the last processed timestamp
    Returns:
        A datetime object representing the last processed timestamp.
    """
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


def execute_query_and_upsert(client, database, query, table_name, last_upserted_timestamp):
    """
    This function executes a query and upserts the results into destination.
    The data is fetched in a streaming manner to handle large datasets efficiently.
    The influxdb_client_3 library supports streaming query results using Apache Arrow Flight.
    This allows to fetch data in a memory-efficient manner without loading the entire dataset at once.
    Args:
        client: an InfluxDB client object
        database: the name of the database to query
        query: the SQL query to execute
        table_name: the name of the table to upsert data into
        last_upserted_timestamp: the timestamp of the last upserted record, used for incremental syncs
    """
    try:
        last_upserted_timestamp = parse_state_timestamp(timestamp_str=last_upserted_timestamp)
        # Execute the query in chunk mode to handle large datasets efficiently.
        # This prevents memory overflow issues.
        record_iterator = client.query(
            query=query, database=database, language="sql", mode="chunk"
        )
        log.info(f"Executed query on database: {database}")

        # Process each chunk to upsert data into the destination
        for chunk in record_iterator:
            # Get the record batch from the chunk. This is an Apache Arrow RecordBatch object.
            record_batch = chunk.data
            # Get the list of column names (schema) in the batch.
            column_names = record_batch.schema.names
            # Get the number of rows in this record batch.
            num_rows = record_batch.num_rows
            log.info(f"Fetched record batch with {num_rows} rows")

            # Upsert the record batch into the destination.
            upsert_record_batch(
                num_rows, record_batch, column_names, table_name, last_upserted_timestamp
            )

    except Exception as e:
        # In case of exception, raise a RuntimeError
        raise RuntimeError(f"Failed to fetch and upsert data : {e}")


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
            "table": TABLE_NAME,  # Name of the table in the destination, required.
            "primary_key": [],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "ants": "INT",  # Contains a dictionary of column names and data types
                "bees": "INT",
                "location": "STRING",
                "time": "STRING",
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
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
    log.warning("Example: Source Examples: InfluxDB Connector")

    # Create InfluxDB client
    client = create_influx_client(configuration)
    database = configuration.get("database")
    measurement = configuration.get("measurement")

    # Get the last upserted timestamp from the state
    # This is required for incremental syncs to ensure that we only fetch new or updated records.
    last_upserted_timestamp = state.get("last_upserted_timestamp", "1990-01-01T00:00:00Z")

    # SQL query to fetch data from the collection
    # You can modify this query to fetch data as per your requirements.
    # The query fetches the records from the specified measurement that are newer than the last upserted timestamp in ascending order.
    # The order is important for incremental syncs to ensure that we only fetch new or updated records.
    sql_query = (
        f"SELECT * FROM '{measurement}' WHERE time > '{last_upserted_timestamp}' ORDER BY time ASC"
    )

    # execute the query and upsert the data into destination
    execute_query_and_upsert(client, database, sql_query, TABLE_NAME, last_upserted_timestamp)


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
