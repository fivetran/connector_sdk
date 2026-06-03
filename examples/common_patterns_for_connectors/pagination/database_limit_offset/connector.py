"""This connector demonstrates LIMIT/OFFSET pagination for syncing data from a PostgreSQL database.
It queries rows using ORDER BY updated_at, id LIMIT <N> OFFSET <k>, advancing the offset after each page.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# Import json library for handling JSON data
import json

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
__STATE_KEY_OFFSET = "offset"
__DEFAULT_OFFSET = 0


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
    # Coerce None and empty string to "disable" — libpq treats "" as unset and falls back to "prefer",
    # which causes unexpected TLS negotiation when users intend to disable SSL.
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
    log.warning("Example: Common Patterns For Connectors - Pagination - Database LIMIT/OFFSET")

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
        '2024-01-01 00:00:00+00'::TIMESTAMPTZ + (i * INTERVAL '3 minutes')
    FROM generate_series(1, 200) AS i;
    """

    # Retrieve the current offset from state. On the first sync, start from the beginning.
    offset = int(state.get(__STATE_KEY_OFFSET, __DEFAULT_OFFSET))

    connection = connect_to_database(configuration)

    try:
        sync_items(connection, table_name, offset, state)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch or upsert data: {str(e)}") from e
    finally:
        try:
            connection.close()
            log.info("Closed database connection")
        except Exception as close_error:
            # Log and suppress the close error so it does not mask the original sync exception.
            log.warning(f"Failed to close database connection: {str(close_error)}")


def sync_items(connection, table_name, offset, state):
    """
    The sync_items function handles the retrieval and processing of paginated database rows using LIMIT/OFFSET.
    It performs the following tasks:
        1. Queries the database for a page of rows starting at the current offset.
        2. Processes the returned rows using upsert operations to send to Fivetran.
        3. Advances the offset by the number of rows returned after each page.
        4. Saves the offset in state after each page so the sync can resume if interrupted.
        5. Continues until no more rows are returned.

    LIMIT/OFFSET pagination adds LIMIT <N> OFFSET <k> to every query. It is simple to implement
    but has two important limitations:
        1. Row-shift: if rows are inserted or deleted while paging, later offsets can shift,
           causing gaps or duplicate rows. Mitigate this with a deterministic ORDER BY.
        2. Performance: the database must scan and skip OFFSET rows for every page, so queries
           become slower as the offset grows. For large or frequently updated tables, prefer
           keyset pagination (see the database_keyset example).

    Query pattern:
        SELECT id, name, email, updated_at FROM {table}
        ORDER BY updated_at, id
        LIMIT rows_per_page OFFSET offset;
    Args:
        connection: A connection object to the PostgreSQL database.
        table_name: The source table name.
        offset: The row offset to start the current page from.
        state: A dictionary representing the current state of the sync.
    """
    cursor = connection.cursor()

    try:
        while True:
            # Fetch a page of rows. A deterministic ORDER BY is required so that OFFSET refers to a
            # consistent position across requests.
            query = sql.SQL("""
                SELECT id, name, email, updated_at
                FROM {table}
                ORDER BY updated_at, id
                LIMIT %s OFFSET %s
                """).format(table=sql.Identifier(table_name))

            cursor.execute(query, (__ROWS_PER_PAGE, offset))
            columns = [col[0].lower() for col in cursor.description]
            raw_rows = cursor.fetchall()

            if not raw_rows:
                break  # No more rows — pagination complete.

            rows = [dict(zip(columns, row)) for row in raw_rows]

            log.info(
                f"processing page at offset {offset}. First row id: {rows[0]['id']}, Total rows: {len(rows)}"
            )

            for index, row in enumerate(rows):
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="user", data=row)

                # Checkpoint every __CHECKPOINT_INTERVAL records to commit upserts to the destination.
                # Update state with the cumulative offset so that on resume the sync continues
                # from this exact row rather than re-fetching the full current page.
                if (index + 1) % __CHECKPOINT_INTERVAL == 0:
                    state[__STATE_KEY_OFFSET] = offset + (index + 1)
                    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                    # from the correct position in case of next sync or interruptions.
                    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                    # Learn more about how and where to checkpoint by reading our best practices documentation
                    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                    op.checkpoint(state)

            # Advance offset by the actual number of rows returned on this page.
            # Using len(rows) rather than __ROWS_PER_PAGE ensures the offset is accurate
            # when the last page contains fewer rows than the page size.
            offset += len(rows)
            state[__STATE_KEY_OFFSET] = offset

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)
    finally:
        cursor.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
