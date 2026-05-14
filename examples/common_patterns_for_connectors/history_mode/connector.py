# This example demonstrates how to mimic Fivetran's History Mode using the Connector SDK
# with a Microsoft SQL Server source.
#
# WHAT IS HISTORY MODE?
# Fivetran's History Mode is a sync mode that preserves all historical versions of a record
# in the destination. Instead of overwriting a row when the source record changes, History Mode
# inserts a new row for each observed state, keeping a full audit trail of every change.
#
# WHY THE CONNECTOR SDK DOES NOT NATIVELY SUPPORT HISTORY MODE
# The Connector SDK does not support History Mode. However, you can mimic its behavior by
# including a timestamp column as part of a composite primary key.
#
# HOW THE COMPOSITE PRIMARY KEY APPROACH WORKS
# This connector reads the incremental_column from configuration (e.g. _LastUpdatedInstant).
# For every table that contains that column, the connector:
#   1. Adds the column to the composite primary key alongside the table's natural PKs.
#   2. Uses it as an incremental cursor — only rows changed since the last sync are fetched.
# Because the incremental column is part of the PK, a row whose timestamp changed produces
# a NEW row in the destination rather than overwriting the existing one — History Mode behavior.
#
# ROLE OF THE INCREMENTAL COLUMN WHEN createdAt IS ABSENT
# For sources that do not track record creation time, the incremental column at first observation
# equals the first-seen time — functionally equivalent to createdAt. So it alone is sufficient
# for both the composite primary key and the incremental cursor.
#
# KEY LIMITATION
# Only the state of a record at the time of each sync is captured. If a record is updated
# multiple times between two syncs, only the most recent timestamp value will appear in the
# destination. Intermediate states are lost. For details, see:
# https://fivetran.com/docs/core-concepts/sync-modes/history-mode#changestodatabetweensyncs
#
# See the Technical Reference documentation
# (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# For JSON configuration parsing
import json

# Microsoft SQL Server database driver
import pytds

# For handling DECIMAL values returned by pytds
from decimal import Decimal

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Number of rows fetched from the database per round-trip
__BATCH_SIZE = 1000

# Number of records processed before saving a checkpoint
__CHECKPOINT_INTERVAL = 5000

# Maximum number of tables to discover in this example
__MAX_TABLES = 10

# Sentinel cursor for the very first sync — SQL Server DATETIME does not support timezone
# offsets, so use a plain datetime string
__INITIAL_CURSOR = "1970-01-01 00:00:00"


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_keys = [
        "mssql_server",
        "mssql_database",
        "mssql_user",
        "mssql_password",
        "mssql_port",
        "incremental_column",
    ]
    for config_key in required_keys:
        if config_key not in configuration:
            raise ValueError(f"Missing required configuration value: {config_key}")
        if not str(configuration[config_key]).strip():
            raise ValueError(f"Configuration value for '{config_key}' must not be empty")

    port_raw = configuration["mssql_port"]
    try:
        port_number = int(port_raw)
    except (ValueError, TypeError):
        raise ValueError(f"'mssql_port' must be a valid integer, got: {port_raw!r}")
    if not (1 <= port_number <= 65535):
        raise ValueError(f"'mssql_port' must be between 1 and 65535, got: {port_number}")


def _connect(configuration: dict):
    """Open and return a pytds connection to SQL Server."""
    try:
        connection = pytds.connect(
            server=configuration["mssql_server"],
            database=configuration["mssql_database"],
            user=configuration["mssql_user"],
            password=configuration["mssql_password"],
            port=int(configuration["mssql_port"]),
            validate_host=False,
        )
        log.info(
            f"Connected to {configuration['mssql_database']} on {configuration['mssql_server']}"
        )
        return connection
    except pytds.LoginError as login_error:
        log.error(f"Authentication failed — check mssql_user and mssql_password: {login_error}")
        raise
    except pytds.InterfaceError as interface_error:
        log.error(f"Connection failed — check mssql_server and mssql_port: {interface_error}")
        raise


def _get_tables(connection, schema_name: str) -> list[str]:
    """Return up to __MAX_TABLES user table names from the given schema."""
    query = f"""
        SELECT TOP {__MAX_TABLES} TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_SCHEMA = %s
          AND TABLE_NAME NOT LIKE 'sys%%'
        ORDER BY TABLE_NAME
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (schema_name,))
        table_names = [table_row[0] for table_row in cursor.fetchall()]
    log.info(f"Discovered {len(table_names)} tables in schema '{schema_name}': {table_names}")
    return table_names


def _get_natural_primary_keys(connection, schema_name: str, table_name: str) -> list[str]:
    """Return the natural primary key columns for a table."""
    query = """
        SELECT kcu.COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
          ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
        WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
          AND kcu.TABLE_SCHEMA = %s
          AND kcu.TABLE_NAME = %s
        ORDER BY kcu.ORDINAL_POSITION
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (schema_name, table_name))
        return [pk_row[0] for pk_row in cursor.fetchall()]


def _table_has_column(connection, schema_name: str, table_name: str, column_name: str) -> bool:
    """Return True if the table contains the given column."""
    query = """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (schema_name, table_name, column_name))
        return cursor.fetchone()[0] > 0


def _map_sql_type(sql_type: str) -> str:
    """Map a SQL Server data type string to a Fivetran SDK column type."""
    normalized_type = sql_type.lower()
    if normalized_type == "bit":
        return "BOOLEAN"
    if normalized_type in ("tinyint", "smallint"):
        return "SHORT"
    if normalized_type in ("int", "integer"):
        return "INT"
    if normalized_type == "bigint":
        return "LONG"
    if normalized_type in ("float", "real", "decimal", "numeric", "money", "smallmoney"):
        return "FLOAT"
    if normalized_type == "date":
        return "NAIVE_DATE"
    if normalized_type in ("datetime", "datetime2", "smalldatetime"):
        return "NAIVE_DATETIME"
    if normalized_type == "datetimeoffset":
        return "UTC_DATETIME"
    if normalized_type in ("binary", "varbinary", "image"):
        return "BINARY"
    return "STRING"


def _get_columns(connection, schema_name: str, table_name: str) -> dict[str, str]:
    """Return {column_name: fivetran_type} for all columns in the table."""
    query = """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (schema_name, table_name))
        return {
            column_name: _map_sql_type(sql_type) for column_name, sql_type in cursor.fetchall()
        }


def _serialize(column_value):
    """Convert Decimal to float for SDK compatibility."""
    if isinstance(column_value, Decimal):
        return float(column_value)
    return column_value


def _fetch_rows(
    connection,
    schema_name: str,
    table_name: str,
    incremental_col: str,
    cursor_value: str,
    natural_pks: list[str],
    last_pk_value=None,
):
    """
    Yield rows as dicts. When incremental_col is provided, fetches only rows updated after
    cursor_value using a keyset cursor to handle timestamp ties correctly.

    Keyset logic (single natural PK):
        WHERE (incremental_col > cursor_value)
           OR (incremental_col = cursor_value AND tiebreaker_pk_column > last_pk_value)
        ORDER BY incremental_col, tiebreaker_pk_column

    This ensures that if multiple rows share the same timestamp, none are skipped.
    For tables with no natural PK or a composite PK, falls back to a simple > filter.
    """
    fully_qualified_table = f"[{schema_name}].[{table_name}]"
    with connection.cursor() as db_cursor:
        if incremental_col:
            tiebreaker_pk_column = natural_pks[0] if len(natural_pks) == 1 else None

            if tiebreaker_pk_column and last_pk_value is not None:
                # Keyset cursor: resume mid-timestamp-group after a batch boundary.
                db_cursor.execute(
                    f"""SELECT * FROM {fully_qualified_table}
                        WHERE ([{incremental_col}] > %s)
                           OR ([{incremental_col}] = %s AND [{tiebreaker_pk_column}] > %s)
                        ORDER BY [{incremental_col}], [{tiebreaker_pk_column}]""",
                    (cursor_value, cursor_value, last_pk_value),
                )
                log.info(
                    f"Incremental fetch {schema_name}.{table_name}: {incremental_col} > '{cursor_value}' OR (= '{cursor_value}' AND {tiebreaker_pk_column} > {last_pk_value})"
                )
            elif tiebreaker_pk_column:
                # First sync for this table: no last_pk yet, but still sort by (timestamp, pk)
                # so rows within the same timestamp arrive in a stable, deterministic order.
                db_cursor.execute(
                    f"""SELECT * FROM {fully_qualified_table}
                        WHERE [{incremental_col}] > %s
                        ORDER BY [{incremental_col}], [{tiebreaker_pk_column}]""",
                    (cursor_value,),
                )
                log.info(
                    f"Incremental fetch {schema_name}.{table_name}: {incremental_col} > '{cursor_value}' (ordered by {incremental_col}, {tiebreaker_pk_column})"
                )
            else:
                # Composite or missing natural PK — fall back to timestamp-only ordering.
                db_cursor.execute(
                    f"SELECT * FROM {fully_qualified_table} WHERE [{incremental_col}] > %s ORDER BY [{incremental_col}]",
                    (cursor_value,),
                )
                log.info(
                    f"Incremental fetch {schema_name}.{table_name}: {incremental_col} > '{cursor_value}'"
                )
        else:
            db_cursor.execute(f"SELECT * FROM {fully_qualified_table}")
            log.info(f"Full scan of {schema_name}.{table_name}")

        column_names = [column_description[0] for column_description in db_cursor.description]
        while True:
            batch = db_cursor.fetchmany(__BATCH_SIZE)
            if not batch:
                break
            for row in batch:
                yield {
                    column_name: _serialize(column_value)
                    for column_name, column_value in zip(column_names, row)
                }


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    validate_configuration(configuration)
    incremental_col = configuration["incremental_column"]
    schema_name = configuration.get("mssql_schema", "dbo")

    connection = _connect(configuration)
    try:
        table_names = _get_tables(connection, schema_name)
        table_schemas = []

        for table_name in table_names:
            natural_pks = _get_natural_primary_keys(connection, schema_name, table_name)
            log.debug("Natural Primary Keys: {}".format(natural_pks))
            column_definitions = _get_columns(connection, schema_name, table_name)
            table_has_incremental_column = _table_has_column(
                connection, schema_name, table_name, incremental_col
            )

            if table_has_incremental_column and incremental_col not in natural_pks:
                # Append the incremental column to the composite primary key.
                # This is the key change that mimics History Mode: a new value of
                # incremental_col means a new composite PK, so a new row is inserted
                # rather than the existing row being overwritten.
                composite_primary_key = natural_pks + [incremental_col]
            else:
                composite_primary_key = natural_pks

            table_schemas.append(
                {
                    "table": f"{schema_name}_{table_name}",
                    "primary_key": composite_primary_key if composite_primary_key else None,
                    "columns": column_definitions if column_definitions else None,
                }
            )

        return table_schemas
    finally:
        connection.close()


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning(
        "Example: Common Patterns For Connectors - History Mode Mimicry Using Composite Primary Key"
    )

    validate_configuration(configuration)
    incremental_col = configuration["incremental_column"]
    schema_name = configuration.get("mssql_schema", "dbo")

    connection = _connect(configuration)
    try:
        table_names = _get_tables(connection, schema_name)

        for table_name in table_names:
            destination_table = f"{schema_name}_{table_name}"
            natural_pks = _get_natural_primary_keys(connection, schema_name, table_name)
            table_has_incremental_column = _table_has_column(
                connection, schema_name, table_name, incremental_col
            )
            tiebreaker_pk_column = natural_pks[0] if len(natural_pks) == 1 else None

            # State per table is a dict: {"cursor": <timestamp>, "last_pk": <pk_value>}
            # This supports keyset pagination to handle timestamp ties correctly.
            table_state = state.get(destination_table, {})
            cursor_value = (
                table_state.get("cursor", __INITIAL_CURSOR)
                if table_has_incremental_column
                else None
            )
            last_pk_value = (
                table_state.get("last_pk")
                if table_has_incremental_column and tiebreaker_pk_column
                else None
            )

            log.info(
                f"Starting {destination_table}: cursor='{cursor_value}', last_pk={last_pk_value}"
            )

            records_processed = 0
            latest_cursor_value = cursor_value
            latest_pk_value = last_pk_value

            for record in _fetch_rows(
                connection,
                schema_name,
                table_name,
                incremental_col if table_has_incremental_column else None,
                cursor_value,
                natural_pks,
                last_pk_value,
            ):
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table=destination_table, data=record)
                records_processed += 1

                if table_has_incremental_column:
                    incremental_column_value = record.get(incremental_col)
                    if incremental_column_value is not None:
                        # Use str() not isoformat() — pytds datetime objects stringify with a space
                        # separator ("2026-04-24 04:57:58.588") which SQL Server accepts directly.
                        # isoformat() produces a T separator which causes SQL Server conversion errors.
                        latest_cursor_value = str(incremental_column_value)
                    if tiebreaker_pk_column:
                        latest_pk_value = record.get(tiebreaker_pk_column)

                if records_processed % __CHECKPOINT_INTERVAL == 0:
                    if table_has_incremental_column:
                        state[destination_table] = {
                            "cursor": latest_cursor_value,
                            "last_pk": latest_pk_value,
                        }
                    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                    # from the correct position in case of next sync or interruptions.
                    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                    # Learn more about how and where to checkpoint by reading our best practices documentation
                    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                    op.checkpoint(state)

            # Advance the cursor for this table and checkpoint after all rows are processed.
            if table_has_incremental_column and latest_cursor_value:
                state[destination_table] = {
                    "cursor": latest_cursor_value,
                    "last_pk": latest_pk_value,
                }

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)
            log.info(f"Finished {destination_table}: {records_processed} rows processed")

    except pytds.ProgrammingError as sql_error:
        log.error(f"SQL error during sync (permanent — check query or schema): {sql_error}")
        raise
    except pytds.InterfaceError as connection_error:
        log.error(
            f"Connection lost during sync (transient — will retry on next run): {connection_error}"
        )
        raise
    finally:
        connection.close()


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
