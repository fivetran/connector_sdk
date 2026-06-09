# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with a Cassandra database containing a large dataset and using pagination
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
import json
from datetime import timezone
from dateutil import parser

# Import the Cassandra drivers
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider


def create_cassandra_session(configuration: dict):
    """
    Create a connection to Cassandra
    This function creates a cassandra session using the cassandra_driver library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        session: a Cassandra session object
    """
    host = configuration.get("hostname")
    port = int(configuration.get("port"))
    username = configuration.get("username")
    password = configuration.get("password")
    auth_provider = PlainTextAuthProvider(username=username, password=password)

    try:
        # Create a Cassandra session with the provided configuration
        cluster = Cluster([host], port=port, auth_provider=auth_provider)
        session = cluster.connect()
        log.info("Connection to Cassandra successful")
        return session
    except Exception:
        raise RuntimeError("Failed to connect to Cassandra")


def fetch_new_rows(
    session, keyspace: str, table_name: str, last_created_at: str, fetch_size: int = 100
):
    """
    Fetches new rows from Cassandra using a paginated query.
    Args:
        session: Cassandra session
        keyspace: Keyspace name
        table_name: Table name
        last_created_at: ISO timestamp string
        fetch_size: Page size for Cassandra query
    Returns:
        Generator of fetched rows
    """
    # Set the keyspace for the session
    session.set_keyspace(keyspace)

    # Prepare the query to fetch new rows
    # You can modify the query to suit your needs
    query = f"SELECT * FROM {table_name} WHERE created_at > ? ALLOW FILTERING"
    stmt = session.prepare(query)

    # Convert timestamp string to datetime object for cassandra
    timestamp_obj = parser.parse(last_created_at)
    if timestamp_obj.tzinfo is None:
        # Add UTC timezone if missing
        timestamp_obj = timestamp_obj.replace(tzinfo=timezone.utc)

    try:
        # Set the fetch size using bound and execute the query
        # The bound enables you to bind parameters to the query
        # fetch_size is used to limit the number of rows fetched in one go
        bound = stmt.bind([timestamp_obj])
        bound.fetch_size = fetch_size
        rows = session.execute(bound)
        # Iterate through the rows and yield each row for efficient processing
        # This does not load all rows into memory at once and is ideal for large datasets
        for row in rows:
            yield row
    except Exception as e:
        raise RuntimeError(f"Error fetching rows from Cassandra: {e}")


def upsert_fetched_rows(session, keyspace: str, table_name: str, state: dict):
    """
    Fetches records from Cassandra, upserts them, and updates state.
    Args:
        session: Cassandra session
        keyspace: Keyspace name
        table_name: Table name
        state: A dictionary containing state information from previous runs
    """
    # Get the last sync time from the state
    last_sync = state.get("last_created_at", "1990-01-01T00:00:00")
    max_created_at = parser.parse(last_sync)
    if max_created_at.tzinfo is None:
        max_created_at = max_created_at.replace(tzinfo=timezone.utc)
    record_count = 0

    # Fetch new rows from Cassandra, prepare them and upsert them
    # This is done in a paginated manner to avoid loading all rows into memory at once
    for row in fetch_new_rows(session, keyspace, table_name, last_sync):
        # Ensure created_at has timezone info before comparison
        row_created_at = row.created_at
        if row_created_at and row_created_at.tzinfo is None:
            row_created_at = row_created_at.replace(tzinfo=timezone.utc)

        # Prepare the record for upsert
        # You can handle the record transformation here if needed
        record = {
            "id": str(row.id),
            "name": row.name,
            "created_at": row_created_at if row.created_at else None,
        }

        # Upsert the record into destination and increment the record count
        op.upsert(table=table_name, data=record)
        record_count += 1

        # Update the max_created_at if the current row's created_at is greater
        if row_created_at and row_created_at > max_created_at:
            max_created_at = row_created_at

        # Checkpoint every 1000 records
        # This is useful for large datasets to avoid losing progress in case of failure
        # You can modify this number based on your requirements
        if record_count % 1000 == 0:
            state["last_created_at"] = max_created_at.isoformat()
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)
            log.info(f"{record_count} records processed")

    log.info(f"Total records processed: {record_count}")

    # checkpoint the last created_at timestamp
    state["last_created_at"] = max_created_at.isoformat()
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
    for key in ["hostname", "username", "password", "keyspace", "port"]:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value : {key}")

    return [
        {
            "table": "sample_table",
            "primary_key": ["id"],
            "columns": {
                "id": "STRING",
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
    # Create a Cassandra session
    session = create_cassandra_session(configuration)
    keyspace = configuration.get("keyspace")
    table_name = "sample_table"

    # IMPORTANT: This connector requires that the following prerequisites exist in your Cassandra instance:
    # 1. A keyspace named as specified in your configuration
    # 2. A table named 'sample_table' with the following schema:
    #    - id (UUID): Primary key
    #    - name (text): User name
    #    - created_at (timestamp): Record creation timestamp
    #
    # The table should be created with a statement similar to:
    # CREATE TABLE IF NOT EXISTS sample_table (
    #   id UUID PRIMARY KEY,
    #   name text,
    #   created_at timestamp
    # );
    #
    # Additionally, for efficient querying, an index on created_at is recommended:
    # CREATE INDEX IF NOT EXISTS idx_created_at ON sample_table(created_at);
    # If these prerequisites are not met, the connector will not function correctly.

    # Fetch new rows from Cassandra and upsert them
    upsert_fetched_rows(session=session, keyspace=keyspace, table_name=table_name, state=state)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
