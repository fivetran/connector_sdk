# This example demonstrates how to fetch data from postgres database using different cursor strategies to minimize memory usage.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import json library for handling JSON data
import json

# Import typing for type hints
from typing import List

# Import datetime for handling date and time
from datetime import datetime

# Import the psycopg2 library for PostgreSQL database connections
import psycopg2
from psycopg2 import sql

__CURSOR_NAME = "ft_server_side_cursor"  # Name of the server-side cursor
__DEFAULT_BATCH_SIZE = 5000  # Default number of rows to fetch per batch
__DEFAULT_CURSOR_MODE = "NAMED"  # Default cursor mode


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = [
        "hostname",
        "port",
        "database",
        "username",
        "password",
        "table_name",
    ]

    for config in required_configs:
        if config not in configuration or not configuration[config]:
            raise ValueError(f"Missing required configuration parameter: {config}")

    if configuration["sslmode"] not in (None, "disable", "require", ""):
        raise ValueError(f"Invalid sslmode value: {configuration['sslmode']}")


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
    port = int(configuration.get("port", 5432))
    database = configuration["database"]
    username = configuration["username"]
    password = configuration["password"]
    sslmode = configuration.get("sslmode", "disable")

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


def _regular_client_cursor_stream(
    connection,
    table_name: str,
    batch_size: int,
    last_updated: str,
    state: dict,
    last_updated_timestamp: datetime,
):
    """
    Stream rows using a regular client-side cursor with explicit fetchmany() batching.
    Args:
        connection: A connection object to the PostgreSQL database.
        table_name: The source table name.
        batch_size: Maximum rows per batch to keep memory bounded.
        last_updated: The last updated timestamp to filter rows.
        state: A dictionary containing state information from previous runs.
        last_updated_timestamp: The latest last_updated timestamp to update.
    Yields:
        An iterator over lists of row dictionaries (batches).

    HOW IT WORKS
    - Executes `SELECT * FROM {table}`.
    - Uses a default (unnamed) cursor and repeatedly calls `fetchmany(batch_size)`.
    - This approach does not necessarily limit client memory use as the query is executed completely
    - Under some circumstances, the driver may buffer the entire result set client-side causing high memory use.
    PROS
    - Simple to implement and reason about.
    - Works everywhere without additional server-side state.
    CONS
    - The server may still prepare large result sets; network and memory use may be less optimal
      than a server-side (named) cursor for very large scans.
    - The client controls batching, but the portal is still client-side.
    BEST USE
    - Small-to-medium tables where simplicity is preferred.
    - Scenarios where server-side cursors are restricted, or you want minimal complexity.
    AVOID WHEN
    - Scanning very large tables where memory/round-trips are critical.
    - You need the server to strictly limit what's shipped per round-trip (prefer named cursor).
    """
    # Use SQL identifier composition to prevent SQL injection
    base_query = (
        "SELECT * FROM {table} WHERE last_updated > {last_updated_timestamp} ORDER BY last_updated"
    )
    sql_query = sql.SQL(base_query).format(
        table=sql.Identifier(table_name), last_updated_timestamp=sql.Literal(last_updated)
    )

    # Create a regular client-side cursor to execute the query
    cursor = connection.cursor()
    try:
        # Execute the query
        # The size of the result set buffered client-side may still be large depending on driver behavior
        cursor.execute(sql_query)
        columns = [col[0].lower() for col in cursor.description]
        # upsert batches from cursor
        _fetch_batches_from_cursor(
            cursor=cursor,
            columns=columns,
            batch_size=batch_size,
            table_name=table_name,
            state=state,
            last_updated_timestamp=last_updated_timestamp,
        )

    finally:
        # Ensure cursor is closed when generator completes or is interrupted
        cursor.close()


def _setup_named_cursor(connection, table_name: str, batch_size: int, last_updated: str):
    """
    Helper to set up a named server-side cursor and return query metadata.
    Args:
        connection: A connection object to the PostgreSQL database.
        table_name: The source table name.
        batch_size: Maximum rows per batch to keep memory bounded.
        last_updated: The last updated timestamp to filter rows.
    Returns:
        cursor: The named server-side cursor object.
        columns: List of column names in the result set.
    """
    base_query = (
        "SELECT * FROM {table} WHERE last_updated > {last_updated_timestamp} ORDER BY last_updated"
    )
    sql_query = sql.SQL(base_query).format(
        table=sql.Identifier(table_name), last_updated_timestamp=sql.Literal(last_updated)
    )
    cursor = connection.cursor(name=__CURSOR_NAME)
    cursor.itersize = batch_size
    # Execute the query to establish the server-side cursor (portal)
    # This does not fetch any row from source yet
    cursor.execute(sql_query)

    # This initial fetch is just to get column metadata; no rows are retrieved
    cursor.fetchmany(0)
    columns = [col[0].lower() for col in cursor.description]
    return cursor, columns


def upsert_batch(batch, table_name, state, last_updated_timestamp):
    """
    Upsert a batch of data to the destination table.
    Args:
        batch: A list of dictionaries representing the data to be upserted.
        table_name: The destination table name.
        state: A dictionary containing state information from previous runs.
        last_updated_timestamp: The latest last_updated timestamp to update.
    """
    # Upsert the current batch to destination table "employees" (example mapping).
    for data in batch:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table=table_name, data=data)

        # Update last_updated_timestamp if current row's last_updated is greater
        row_last_updated = data.get("last_updated")
        if row_last_updated and row_last_updated > last_updated_timestamp:
            last_updated_timestamp = row_last_updated

    # Save checkpoint after each batch
    save_checkpoint(state=state, last_updated_timestamp=last_updated_timestamp)


def _fetch_batches_from_cursor(
    cursor,
    columns: List[str],
    batch_size: int,
    table_name: str,
    state: dict,
    last_updated_timestamp: datetime,
):
    """
    Helper to fetch batches from cursor and convert to dictionaries.
    Args:
        cursor: The named server-side cursor object.
        columns: List of column names in the result set.
        batch_size: Maximum rows per batch to keep memory bounded.
        table_name: The destination table name.
        state: A dictionary containing state information from previous runs.
        last_updated_timestamp: The latest last_updated timestamp to update.
    Yields:
        An iterator over lists of row dictionaries (batches).
    """
    count = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        data = [dict(zip(columns, row)) for row in rows]
        # upsert the current batch and checkpoint
        upsert_batch(
            batch=data,
            table_name=table_name,
            state=state,
            last_updated_timestamp=last_updated_timestamp,
        )
        count += len(data)

    log.info(f"Total rows upserted from {table_name}: {count}")


def _named_server_side_cursor_stream(
    connection,
    table_name: str,
    batch_size: int,
    last_updated: str,
    state: dict,
    last_updated_timestamp: datetime,
):
    """
    Stream rows using a server-side (named) cursor.
    Args:
        connection: A connection object to the PostgreSQL database.
        table_name: The source table name.
        batch_size: Maximum rows per batch to keep memory bounded.
        last_updated: The last updated timestamp to filter rows.
        state: A dictionary containing state information from previous runs.
        last_updated_timestamp: The latest last_updated timestamp to update in timestamp format.
    Yields:
        An iterator over lists of row dictionaries (batches).

    HOW IT WORKS
    - Creates a named cursor (portal) on the server: rows remain on the server.
    - Sets `cursor.itersize = batch_size` to hint how many rows to fetch per network round-trip.
    - Repeatedly calls `fetchmany(batch_size)`; the server sends rows in small chunks.
    - Uses explicit transaction management to ensure the cursor remains valid throughout iteration.
    PROS
    - Much lower client memory footprint for huge result sets.
    - Better network efficiency via streaming from server.
    - Reduces risk of client OOM for large scans.
    CONS
    - Requires a persistent portal on the server during the transaction.
    - Some PaaS environments may impose limits on long-lived cursors.
    - Transaction remains open during the entire iteration.
    BEST USE
    - Large, sequential table scans.
    - Long-running reads where you want stable, predictable memory on the client.
    AVOID WHEN
    - The environment is hostile to long-lived transactions or portals.
    - You constantly need to interleave writes/commits mid-stream (sometimes `WITH HOLD` variants are needed).
    """
    cursor = None
    try:
        cursor, columns = _setup_named_cursor(
            connection=connection,
            table_name=table_name,
            batch_size=batch_size,
            last_updated=last_updated,
        )
        # upsert batches from cursor
        _fetch_batches_from_cursor(
            cursor=cursor,
            columns=columns,
            batch_size=batch_size,
            table_name=table_name,
            state=state,
            last_updated_timestamp=last_updated_timestamp,
        )

    except Exception as e:
        raise RuntimeError(f"Failed during named cursor streaming: {str(e)}") from e
    finally:
        # Clean up cursor
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                raise RuntimeError(f"Failed to close named cursor: {str(e)}") from e


def fetch_and_upsert_data_from_database(
    connection,
    table_name: str,
    cursor_mode: str,
    batch_size: int,
    last_updated: str,
    state: dict,
    last_updated_timestamp: datetime,
):
    """
    Retrieve data from the PostgreSQL database in batches using the chosen cursor strategy.
    Args:
        connection: A connection object to the PostgreSQL database.
        table_name: The source table name.
        cursor_mode: One of: 'CLIENT', 'NAMED', 'COPY'. Defaults to 'NAMED'.
        batch_size: Maximum rows per batch to keep memory bounded.
        last_updated: The last updated timestamp to filter rows.
        state: A dictionary containing state information from previous runs.
        last_updated_timestamp: The latest last_updated timestamp to update in timestamp format.
    Returns:
        An iterator over lists of row dictionaries (batches).

    STRATEGY SUMMARY
    - CLIENT: simplest; reasonable for modest datasets; Result set is buffered in memory depending on driver implementation.
    - NAMED: best general-purpose low-memory streaming for large scans (RECOMMENDED for large datasets).
    """
    mode = cursor_mode.upper()
    log.info(f"Fetching data using {mode} cursor mode and {batch_size} batch size.")

    if mode == "CLIENT":
        _regular_client_cursor_stream(
            connection=connection,
            table_name=table_name,
            batch_size=batch_size,
            last_updated=last_updated,
            state=state,
            last_updated_timestamp=last_updated_timestamp,
        )
    elif mode == "NAMED":
        _named_server_side_cursor_stream(
            connection=connection,
            table_name=table_name,
            batch_size=batch_size,
            last_updated=last_updated,
            state=state,
            last_updated_timestamp=last_updated_timestamp,
        )
    else:
        raise ValueError(
            f"Unsupported cursor_mode: {cursor_mode}. Please use 'CLIENT' or 'NAMED'."
        )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Get the table name from configuration
    table_name = configuration["table_name"]

    return [
        {
            "table": table_name,  # Name of the destination table
            "primary_key": ["id"],  # Primary key(s) of the table
            "columns": {
                "id": "INT",
                "last_updated": "UTC_DATETIME",
            },
            # Columns not defined in schema will be inferred
        }
    ]


def save_checkpoint(state: dict, last_updated_timestamp: datetime):
    """
    Save the checkpoint state with the latest last_updated timestamp.
    Args:
        state: A dictionary containing state information from previous runs.
        last_updated_timestamp: The latest last_updated timestamp to save in state.
    """
    # Update state with the latest last_updated timestamp after processing the batch
    state["last_updated"] = last_updated_timestamp.isoformat()
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


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
    log.warning("Example: Common Patterns For Connectors - Server Side Cursors")

    # Validate required configuration parameters
    validate_configuration(configuration=configuration)

    # Extract configuration parameters
    table_name = configuration["table_name"]
    batch_size = int(configuration.get("batch_size", __DEFAULT_BATCH_SIZE))
    cursor_mode = configuration.get("cursor_mode", __DEFAULT_CURSOR_MODE)

    # Get the last updated timestamp from state or default to a very old date
    last_updated = state.get("last_updated", "1990-01-01T00:00:00+00:00")
    last_updated_timestamp = datetime.fromisoformat(last_updated)

    # Connect to database
    connection = connect_to_database(configuration)

    try:
        # fetch and upsert data from the source
        fetch_and_upsert_data_from_database(
            connection=connection,
            table_name=table_name,
            cursor_mode=cursor_mode,
            batch_size=batch_size,
            last_updated=last_updated,
            state=state,
            last_updated_timestamp=last_updated_timestamp,
        )
    except Exception as e:
        # Preserve the original exception chain for better debugging
        raise RuntimeError(f"Failed to fetch or upsert data: {str(e)}") from e
    finally:
        try:
            # Ensure the database connection is closed
            connection.close()
            log.info("Closed database connection")
        except Exception as close_error:
            raise RuntimeError(
                f"Failed to close database connection: {str(close_error)}"
            ) from close_error


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
