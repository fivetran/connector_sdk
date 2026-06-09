# This is an example for how to work with the fivetran_connector_sdk module.
# It demonstrates how to fetch data from Apache Hive using the PyHive library and upsert it into a destination table in batches.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
import json
from datetime import datetime, timezone

# Import the Apache hive modules
from pyhive import hive

# Define the table name
TABLE_NAME = "people"


def create_hive_connection(configuration: dict):
    """
    Create a connection to Apache Hive
    This function creates an Apache Hive connection using the PyHive library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        connection: an Apache Hive connection object
    """
    host = configuration.get("hostname")
    port = int(configuration.get("port"))
    username = configuration.get("username")
    password = configuration.get("password")

    try:
        # You can modify the connection parameters based on your Apache Hive setup here.
        connection = hive.Connection(
            host=host, port=port, username=username, password=password, auth="CUSTOM"
        )
        log.info(f"Connected to Apache Hive at {host}:{port} as user {username}")
        return connection
    except Exception:
        raise RuntimeError("Failed to connect to Apache Hive")


def process_row(columns, row):
    """
    Process a single row of data.
    This function processes a single row and converts it into a dictionary format which is suitable for upserting into the destination table.
    You can modify this function to suit your needs, such as converting data types or formatting row data.
    Args:
        columns: a list of column names corresponding to the row data
        row: a tuple representing a single row of data fetched from Apache Hive
    Returns:
        row_data: a dictionary representing the processed row data
    """
    row_data = {}
    for col_name, value in zip(columns, row):
        # Convert the datetime objects to timezone-aware datetime objects in UTC timezone
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        row_data[col_name] = value
    return row_data


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


def fetch_and_upsert_data(cursor, table_name: str, state: dict, batch_size: int = 1000):
    """
    Fetches records from Apache Hive, upserts them, and updates state.
    Args:
        cursor: an Apache Hive cursor object
        table_name: name of the table to fetch data from
        state: a dictionary that holds the state of the connector
        batch_size: number of records to fetch in each batch
    """
    # Get the last created timestamp from the state for incremental sync.
    last_created = state.get("last_created", "1990-01-01T00:00:00Z")
    last_created_timestamp = parse_state_timestamp(timestamp_str=last_created)

    # Convert ISO format to Hive-compatible timestamp format
    # Remove 'Z' and 'T' to make it compatible with Hive timestamp format
    hive_timestamp = last_created.replace("T", " ").replace("Z", "")

    # Execute the query to fetch data.
    # You can modify the query to suit your needs.
    hive_query = f"SELECT * FROM {table_name} WHERE created_at > %s ORDER BY created_at"
    # You can also modify the query to use DISTRIBUTE BY with SORT BY to use Hive's distributed processing capabilities.
    cursor.execute(hive_query, (hive_timestamp,))

    # Get column names from the cursor description
    columns = [desc[0].split(".")[-1] for desc in cursor.description]

    # upsert the data into the destination table in batches
    # The batch size can be adjusted based on your requirements
    # The batch sizes ensures that the entire data is not loaded into the memory
    # This is important for large datasets as it prevents memory overflow errors.
    while True:
        # Fetch a batch of rows
        rows = cursor.fetchmany(batch_size)
        if not rows:
            # No more rows to fetch, exit the loop
            break
        for row in rows:
            # Process each row and convert it into a dictionary format
            row_data = process_row(columns=columns, row=row)
            # Upsert the row data into the destination table
            op.upsert(table=table_name, data=row_data)

            # Update the last_created state with the maximum created_at value.
            # This is used to track the last created record for incremental sync.
            if row_data.get("created_at") and row_data["created_at"] > last_created_timestamp:
                last_created_timestamp = row_data["created_at"]

        # Update the state with the last created timestamp
        # The checkpoint method will be called after processing each batch of rows.
        # This checkpointing logic requires records to be iterated in ascending order, hence the ORDER BY clause in the SQL query
        new_state = {"last_created": last_created_timestamp.isoformat()}
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(new_state)


def validate_configuration(configuration: dict):
    """
    Validate the configuration to ensure all required fields are present.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration value is missing
    """
    required_keys = ["hostname", "username", "password", "port", "database"]
    for key in required_keys:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


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
            "table": TABLE_NAME,
            "primary_key": ["id"],
            "columns": {"id": "INT", "created_at": "UTC_DATETIME"},
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
    log.warning("Example: Source Examples: Apache Hive using PyHive")

    # Validate the configuration to ensure all required fields are present
    validate_configuration(configuration)

    # Create an Apache Hive session
    connection = create_hive_connection(configuration)
    cursor = connection.cursor()

    database = configuration.get("database")
    select_database = f"USE {database}"
    cursor.execute(select_database)
    log.info(f"Using database: {database}")

    # Get the batch size from the configuration, defaulting to 1000 if not specified
    batch_size = int(configuration.get("batch_size", 1000))

    # The example assumes that the database as mentioned in the configuration file already exists in Apache Hive.
    # The example also assumes that the table 'people' already exists in Apache Hive.
    # The table should have the following schema:
    # TABLE people (
    #     id INT,
    #     name STRING,
    #     age INT,
    #     created_at TIMESTAMP
    # )
    # The table should be created before running the example connector.

    # Fetch new rows from Apache Hive and upsert them
    fetch_and_upsert_data(cursor=cursor, table_name=TABLE_NAME, state=state, batch_size=batch_size)

    # Close the cursor and connection
    cursor.close()
    connection.close()


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
