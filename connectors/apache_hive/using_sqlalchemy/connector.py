# This is an example for how to work with the fivetran_connector_sdk module.
# It shows how to fetch data from Apache Hive using the SQLAlchemy library and upsert it into a destination table.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
import json
from datetime import datetime, timezone

# Import the Apache hive modules
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Define table name and checkpoint interval
CHECKPOINT_INTERVAL = 1000
TABLE_NAME = "people"


def create_hive_connection(configuration: dict):
    """
    Create a connection to Apache Hive
    This function creates an Apache Hive session using the PyHive library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        session: an Apache Hive session object
    """
    host = configuration.get("hostname")
    port = int(configuration.get("port"))
    username = configuration.get("username")
    database = configuration.get("database")

    try:
        engine = create_engine(f"hive://{username}@{host}:{port}/{database}")
        session_maker = sessionmaker(bind=engine)
        session = session_maker()
        log.info(
            f"Connected to Apache Hive at {host}:{port} as user {username} and database {database}"
        )
        return session
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


def fetch_and_upsert_data(session, table_name: str, state: dict):
    """
    Fetches records from Apache Hive, upserts them, and updates state.
    Args:
        session: an Apache Hive session object
        table_name: name of the table to fetch data from
        state: a dictionary that holds the state of the connector
    """
    # Get the last created timestamp from the state for incremental sync.
    last_created = state.get("last_created", "1990-01-01T00:00:00Z")
    last_created_timestamp = parse_state_timestamp(timestamp_str=last_created)

    # Convert ISO format to Hive-compatible timestamp format
    # Remove 'Z' and 'T' to make it compatible with Hive timestamp format
    hive_timestamp = last_created.replace("T", " ").replace("Z", "")

    # Use a parameterized query to avoid SQL injection and formatting issues
    query = text(f"SELECT * FROM {table_name} WHERE created_at > :created_at ORDER BY created_at")

    # Execute with parameter binding
    result = session.execute(
        query, {"created_at": hive_timestamp}, execution_options={"stream_results": True}
    )
    # Get column names
    columns = result.keys()

    # Number of rows processed
    count = 0
    for row in result:
        # Process each row and convert it into a dictionary format
        row_data = process_row(columns=columns, row=row)
        # Upsert the row data into the destination table
        op.upsert(table=table_name, data=row_data)
        count += 1

        # Update the last_created state with the maximum created_at value.
        # This is used to track the last created record for incremental sync.
        if row_data.get("created_at") and row_data["created_at"] > last_created_timestamp:
            last_created_timestamp = row_data["created_at"]

        # Checkpointing the state every CHECKPOINT_INTERVAL rows
        # This checkpointing logic requires records to be iterated in ascending order, hence the ORDER BY clause in the SQL query
        if count % CHECKPOINT_INTERVAL == 0:
            new_state = {"last_created": last_created_timestamp.isoformat()}
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(new_state)

    # Checkpoint the final state after processing all rows
    new_state = {"last_created": last_created_timestamp.isoformat()}
    op.checkpoint(new_state)


def validate_configuration(configuration: dict):
    """
    Validate the configuration to ensure all required fields are present.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration value is missing
    """
    required_keys = ["hostname", "username", "database", "port"]
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
    log.warning("Example: Source Examples: Apache Hive using SQLAlchemy and PyHive dialect")

    # Validate the configuration to ensure all required fields are present
    validate_configuration(configuration)

    # Create an Apache Hive session
    session = create_hive_connection(configuration)

    # The example assumes that the table 'people' already exists in Apache Hive.
    # The table should have the following schema:
    # TABLE people (
    #     id INT,
    #     name STRING,
    #     age INT,
    #     created_at TIMESTAMP
    # )
    # The table should be created before running the example connector.

    # Fetch new rows from Apache Hive and upsert them
    fetch_and_upsert_data(session=session, table_name=TABLE_NAME, state=state)

    # Close the session
    session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
