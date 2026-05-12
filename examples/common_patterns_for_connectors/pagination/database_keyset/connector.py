"""This connector demonstrates keyset pagination for syncing data from a PostgreSQL database.
It pages through rows using a WHERE (updated_at, id) > (%s, %s) boundary that advances after each page.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# Import json library for handling JSON data
import json

# Import datetime for handling date and time
from datetime import datetime

# Import the psycopg2 library for PostgreSQL database connections
import psycopg2
from psycopg2 import sql

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__ROWS_PER_PAGE = 25
__CHECKPOINT_INTERVAL = 10
__STATE_KEY_UPDATED_AFTER = "updated_after"
__STATE_KEY_LAST_ID = "last_id"
__DEFAULT_CURSOR = "0001-01-01T00:00:00+00:00"
__DEFAULT_LAST_ID = 0


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = ["hostname", "port", "database", "username", "password", "table_name"]

    for config in required_configs:
        if config not in configuration or not configuration[config]:
            raise ValueError(f"Missing required configuration parameter: {config}")

    if configuration.get("sslmode") not in (None, "disable", "require", ""):
        raise ValueError(f"Invalid sslmode value: {configuration['sslmode']}")

    # Validate port is an integer in the valid TCP range (1–65535).
    try:
        port_number = int(configuration["port"])
    except (ValueError, TypeError):
        raise ValueError(
            f"Configuration value for 'port' must be an integer, got: '{configuration['port']}'"
        )
    if not (1 <= port_number <= 65535):
        raise ValueError(
            f"Configuration value for 'port' must be between 1 and 65535, got: {port_number}"
        )


def connect_to_database(configuration: dict):
    """
    Connect to PostgreSQL using credentials provided in configuration.
    Args:
        configuration: A dictionary containing the database connection details.
    Returns:
        connection: A connection object to the PostgreSQL database.
    Raises:
        RuntimeError: If connection fails, with original exception preserved in chain.
    """
    host = configuration["hostname"]
    port = int(configuration["port"])
    database = configuration["database"]
    username = configuration["username"]
    password = configuration["password"]
    sslmode = configuration.get("sslmode") or "disable"

    try:
        connection = psycopg2.connect(
            host=host,
            port=port,
            dbname=database,
            user=username,
            password=password,
            sslmode=sslmode,
        )
        log.info("Successfully connected to database")
        return connection
    except Exception as e:
        raise RuntimeError(f"Failed to connect to database: {str(e)}") from e


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
            "table": "user",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
                "name": "STRING",
                "email": "STRING",
                "updated_at": "UTC_DATETIME",
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
    log.warning("Example: Common Patterns For Connectors - Pagination - Database Keyset")

    validate_configuration(configuration=configuration)

    table_name = configuration["table_name"]

    """
    Ensure that the source table exists and contains the required columns.
    If the table does not exist, create it and insert sample data using the following SQL:

    CREATE TABLE users (
        id         SERIAL PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        email      VARCHAR(255) NOT NULL,
        updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

    INSERT INTO users (name, email, updated_at)
    SELECT
        'User ' || i,
        'user' || i || '@example.com',
        '2026-01-01 00:00:00+00'::TIMESTAMPTZ + (i * INTERVAL '3 minutes')
    FROM generate_series(1, 200) AS i;
    """

    # Retrieve the keyset boundary from state.
    # On the first sync, start before all records by using the earliest possible values.
    last_updated_at = datetime.fromisoformat(
        state.get(__STATE_KEY_UPDATED_AFTER, __DEFAULT_CURSOR)
    )
    last_id = int(state.get(__STATE_KEY_LAST_ID, __DEFAULT_LAST_ID))

    connection = connect_to_database(configuration)

    try:
        sync_items(connection, table_name, last_updated_at, last_id, state)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch or upsert data: {str(e)}") from e
    finally:
        try:
            connection.close()
            log.info("Closed database connection")
        except Exception as close_error:
            # Log and suppress the close error so it does not mask the original sync exception.
            log.warning(f"Failed to close database connection: {str(close_error)}")


def sync_items(connection, table_name, last_updated_at, last_id, state):
    """
    The sync_items function handles the retrieval and processing of paginated database rows using keyset pagination.
    It performs the following tasks:
        1. Queries the database for rows whose (updated_at, id) key is greater than the last seen boundary.
        2. Processes the returned rows using upsert operations to send to Fivetran.
        3. Advances the keyset boundary to the last row of each page.
        4. Saves the boundary in state after each page so the sync can resume if interrupted.
        5. Continues until no more rows are returned.

    Keyset pagination uses a WHERE clause on a monotonic column (updated_at) and a tie-breaker (id)
    to skip already-seen rows.

    Query pattern:
        SELECT id, name, email, updated_at FROM {table}
        WHERE (updated_at, id) > (%s, %s)
        ORDER BY updated_at, id
        LIMIT rows_per_page;
    Args:
        connection: A connection object to the PostgreSQL database.
        table_name: The source table name.
        last_updated_at: The updated_at timestamp of the last processed row (keyset boundary).
        last_id: The id of the last processed row (tie-breaker for rows with identical updated_at).
        state: A dictionary representing the current state of the sync.
    """
    cursor = connection.cursor()

    try:
        while True:
            # Fetch the next page of rows beyond the current keyset boundary.
            # The (updated_at, id) > (%s, %s) row-value comparison is a standard PostgreSQL feature.
            query = sql.SQL("""
                SELECT id, name, email, updated_at
                FROM {table}
                WHERE (updated_at, id) > (%s, %s)
                ORDER BY updated_at, id
                LIMIT %s
                """).format(table=sql.Identifier(table_name))

            cursor.execute(query, (last_updated_at, last_id, __ROWS_PER_PAGE))
            columns = [col[0].lower() for col in cursor.description]
            raw_rows = cursor.fetchall()

            if not raw_rows:
                break  # No more rows — pagination complete.

            rows = [dict(zip(columns, row)) for row in raw_rows]

            log.info(
                f"processing page of rows. First row id: {rows[0]['id']}, Total rows: {len(rows)}"
            )

            for index, row in enumerate(rows):
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="user", data=row)

                # Advance the keyset boundary after every record so a mid-page checkpoint
                # captures the exact position — on resume, only unprocessed rows are re-fetched.
                last_updated_at = row["updated_at"]
                last_id = row["id"]
                state[__STATE_KEY_UPDATED_AFTER] = (
                    last_updated_at.isoformat()
                    if hasattr(last_updated_at, "isoformat")
                    else last_updated_at
                )
                state[__STATE_KEY_LAST_ID] = str(last_id)

                # Checkpoint every __CHECKPOINT_INTERVAL records to commit upserts to the destination.
                if (index + 1) % __CHECKPOINT_INTERVAL == 0:
                    op.checkpoint(state)

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)
    finally:
        cursor.close()


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
