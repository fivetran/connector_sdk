"""
This connector demonstrates how to fetch data from Microsoft SQL Server (such as Caboodle)
and sync it to your Fivetran destination using the Fivetran Connector SDK.
This example is a simple implementation meant to provide basic understanding of how to use the Fivetran Connector SDK for MSSQL server
It detects the tables in the database, their columns, and primary keys, and performs incremental syncs based on a modified date column.
This example also includes batch fetching and checkpointing to ensure reliable delivery of large datasets.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For JSON data serialization and configuration parsing
import json

# Microsoft SQL Server database driver for TDS protocol connections
import pytds

# For timestamp handling and timezone-aware operations
from datetime import datetime, timezone

# For handling DECIMAL values returned by pytds
from decimal import Decimal

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Number of rows fetched from the database cursor per round-trip
__BATCH_SIZE = 1000

# Number of records processed before saving progress with a checkpoint
__CHECKPOINT_INTERVAL = 5000

# Maximum number of tables to discover and sync in this example
__MAX_TABLES = 10

# The name of the column used for incremental syncs if it exists in a table
# You can modify this to use a different column based on your database schema
__MODIFIED_COLUMN_NAME = "modified_date"

# Sentinel cursor used on the very first sync for tables that have the __MODIFIED_COLUMN_NAME column.
# SQL Server DATETIME does not support timezone offsets, so use a plain datetime string.
__INITIAL_SYNC_DATE = "1970-01-01 00:00:00"


def validate_configuration(configuration: dict) -> None:
    """
    Validate that all required connection parameters are present in the configuration.
    Args:
        configuration: A dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: If any required configuration parameter is missing.
    """
    required_configs = [
        "mssql_server",
        "mssql_database",
        "mssql_user",
        "mssql_password",
        "mssql_port",
    ]

    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def _connect_to_mssql(configuration: dict):
    """
    Connect to Microsoft SQL Server using pytds.
    Args:
        configuration: Dictionary containing server, database, user, password, and port.
    Returns:
        An active pytds connection object.
    """
    server = configuration["mssql_server"]
    database = configuration["mssql_database"]
    user = configuration["mssql_user"]
    password = configuration["mssql_password"]
    port = int(configuration["mssql_port"])

    try:
        connection = pytds.connect(
            server=server,
            database=database,
            user=user,
            password=password,
            port=port,
            validate_host=False,
        )
        log.info(f"Successfully connected to MSSQL database: {database}")
        return connection
    except Exception as e:
        log.error(f"Failed to connect to MSSQL: {e}")
        raise


def _get_table_list(connection) -> list[tuple[str, str]]:
    """
    Retrieve up to __MAX_TABLES user tables from the database as (schema, table) tuples.
    Both TABLE_SCHEMA and TABLE_NAME are returned so that all downstream queries can use
    fully qualified names, preventing collisions when the same table name exists in multiple schemas.
    System tables (prefixed with 'sys' or 'INFORMATION_SCHEMA') are excluded.
    You can modify the query to include specific tables or schemas as needed for your use case.
    Args:
        connection: Active database connection object.
    Returns:
        List of (schema_name, table_name) tuples.
    """
    # Discovers all user-defined base tables, limited to __MAX_TABLES for this example.
    query = f"""
    SELECT TOP {__MAX_TABLES} TABLE_SCHEMA, TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
    AND TABLE_NAME NOT LIKE 'sys%'
    AND TABLE_NAME NOT LIKE 'INFORMATION_SCHEMA%'
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            tables = [(row[0], row[1]) for row in cursor.fetchall()]
            log.info(f"Found {len(tables)} tables: {tables}")
            return tables
    except Exception as e:
        log.error(f"Failed to get table list: {e}")
        raise


def _map_sql_type(sql_type: str) -> str:
    """
    Map a SQL Server data type to the Fivetran SDK column type.
    All other types return a plain string.
    Args:
        sql_type: SQL Server column type.
    Returns:
        Fivetran SDK column type.
    """
    t = sql_type.lower()
    if t == "bit":
        return "BOOLEAN"
    if t in ("tinyint", "smallint"):
        return "SHORT"
    if t in ("int", "integer"):
        return "INT"
    if t == "bigint":
        return "LONG"
    if t in ("float", "real", "decimal", "numeric", "money", "smallmoney"):
        return "FLOAT"
    if t == "date":
        return "NAIVE_DATE"
    if t in ("datetime", "datetime2", "smalldatetime"):
        return "NAIVE_DATETIME"
    if t == "datetimeoffset":
        return "UTC_DATETIME"
    if t in ("binary", "varbinary", "image"):
        return "BINARY"
    if t == "xml":
        return "XML"
    return "STRING"


def _build_schema(
    table_name: str,
    primary_keys: list[str] | None,
    columns: dict[str, str] | None,
    failure=False,
) -> dict:
    """
    Build a schema dictionary for a given table.
    Args:
        table_name: Name of the table.
        primary_keys: List of primary key column names.
        columns: Dict mapping column names to {"data_type": <Fivetran type>}.
        failure: If True, returns a minimal schema with only the table name.
    Returns:
        Dictionary containing table schema information.
    """
    if failure:
        log.warning(
            f"Building schema for {table_name} with failure mode: only table name included"
        )
        return {"table": table_name}

    log.info(f"Schema for {table_name}: {len(columns)} columns, {len(primary_keys)} primary keys")
    return {
        "table": table_name,
        "primary_key": primary_keys if primary_keys else None,
        "columns": columns if columns else None,
    }


def _get_table_schema(connection, schema_name: str, table_name: str) -> dict:
    """
    Retrieve column names and primary keys for a single table.
    Args:
        connection: Active database connection object.
        schema_name: SQL Server schema name (e.g. 'dbo').
        table_name: Name of the table to inspect.
    Returns:
        Dictionary with keys 'table', 'primary_key', and 'columns'.
    Note:
        The primary key query relies on constraints named with the 'PK_' prefix, which is the
        default SQL Server convention. Adjust the LIKE filter if your schema uses a different
        naming convention.
    """
    destination_table_name = f"{schema_name}_{table_name}"

    primary_key_query = """
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = %s
    AND TABLE_NAME = %s
    AND CONSTRAINT_NAME LIKE 'PK_%%'
    ORDER BY ORDINAL_POSITION
    """

    column_query = """
    SELECT COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = %s
    AND TABLE_NAME = %s
    ORDER BY ORDINAL_POSITION
    """

    try:
        with connection.cursor() as cursor:
            # Fetch primary key columns for the table.
            # This query looks for constraints that start with 'PK_' which is a common naming convention for primary keys.
            # Note: Depending on your database schema, you may need to adjust the constraint filter to accurately capture primary keys.
            cursor.execute(primary_key_query, (schema_name, table_name))
            primary_keys = [row[0] for row in cursor.fetchall()]

            # Fetch all column names and data types for the table.
            cursor.execute(column_query, (schema_name, table_name))
            columns = {row[0]: _map_sql_type(row[1]) for row in cursor.fetchall()}

            return _build_schema(
                table_name=destination_table_name, primary_keys=primary_keys, columns=columns
            )

    except Exception as e:
        log.warning(f"Failed to get schema for table {schema_name}.{table_name}: {e}")
        return _build_schema(
            table_name=destination_table_name, primary_keys=None, columns=None, failure=True
        )


def _get_tables_with_modified_date(connection, tables: list[tuple[str, str]]) -> set[str]:
    """
    Return destination table names (schema_table) for tables that contain a __MODIFIED_COLUMN_NAME column.
    Args:
        connection: Active database connection object.
        tables: List of (schema_name, table_name) tuples to check.
    Returns:
        Set of destination table names (schema_table format) that have the __MODIFIED_COLUMN_NAME column.
    """
    if not tables:
        return set()
    conditions = " OR ".join(["(TABLE_SCHEMA = %s AND TABLE_NAME = %s)"] * len(tables))
    params = [__MODIFIED_COLUMN_NAME]
    for schema_name, table_name in tables:
        params += [schema_name, table_name]
    query = f"""
    SELECT TABLE_SCHEMA, TABLE_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE COLUMN_NAME = %s
    AND ({conditions})
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return {f"{row[0]}_{row[1]}" for row in cursor.fetchall()}
    except Exception as e:
        log.warning(f"Failed to detect modified-date columns: {e}")
        return set()


def _serialize_value(value):
    """
    Convert pytds-returned decimal type to Float
    Args:
        value: Value to serialize.
    Returns:
        Serialized value.
    """
    if isinstance(value, Decimal):
        return float(value)
    return value


def _get_table_data(
    connection,
    schema_name: str,
    table_name: str,
    last_sync_time: str = None,
    has_modified_date: bool = False,
):
    """
    Fetch rows from a table one batch at a time, yielding each row as a dictionary.
    When has_modified_date is True, last_sync_time is always a concrete ISO timestamp
    (either from state or the __INITIAL_SYNC_DATE sentinel), so the query always filters
    with WHERE __MODIFIED_COLUMN_NAME > last_sync_time ORDER BY __MODIFIED_COLUMN_NAME.
    When has_modified_date is False, last_sync_time is ignored and a full sync is performed.
    Args:
        connection: Active database connection object.
        schema_name: SQL Server schema name (e.g. 'dbo').
        table_name: Name of the table to fetch data from.
        last_sync_time: ISO timestamp cursor; only used when has_modified_date is True.
        has_modified_date: Whether the table contains a __MODIFIED_COLUMN_NAME column.
    Yields:
        Dictionary mapping column names to row values.
    """
    qualified_table = f"[{schema_name}].[{table_name}]"
    try:
        with connection.cursor() as cursor:
            if has_modified_date:
                # This query fetches only rows that have been modified since the last sync time,
                # ordered by the modified date to ensure proper incremental sync behavior.
                cursor.execute(
                    f"SELECT * FROM {qualified_table} WHERE {__MODIFIED_COLUMN_NAME} > %s ORDER BY {__MODIFIED_COLUMN_NAME}",
                    (last_sync_time,),
                )
                log.info(f"Incremental sync for {schema_name}.{table_name} from {last_sync_time}")
            else:
                cursor.execute(f"SELECT * FROM {qualified_table} ORDER BY (SELECT NULL)")
                log.info(f"Full sync for {schema_name}.{table_name}")

            # Extract column names from the cursor description to map row values to column names
            columns = [desc[0] for desc in cursor.description]

            # Fetch rows in batches
            while True:
                rows = cursor.fetchmany(__BATCH_SIZE)
                if not rows:
                    # No more rows to fetch
                    break
                for row in rows:
                    # This yields each row as a dictionary where keys are column names and values are the corresponding row values.
                    # _serialize_value converts Decimal to float
                    yield {column: _serialize_value(value) for column, value in zip(columns, row)}

    except Exception as e:
        log.error(f"Failed to get data from table {schema_name}.{table_name}: {e}")
        raise


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # validate the configuration parameters before attempting to connect to the database
    validate_configuration(configuration)
    # connect to the database using the provided configuration parameters
    connection = _connect_to_mssql(configuration)

    try:
        # get the list of tables to sync from the database
        tables = _get_table_list(connection)

        schema_list = []
        for schema_name, table_name in tables:
            # for each table, get the schema information (columns and primary keys) and add it to the schemas list
            schema_list.append(_get_table_schema(connection, schema_name, table_name))

        # Declare the sync_history table so Fivetran knows its primary key.
        # This table is used to store a summary record after each sync, which can be useful for monitoring and debugging.
        schema_list.append(
            {
                "table": "sync_history",
                "primary_key": ["sync_timestamp"],
                "columns": {
                    "sync_timestamp": "STRING",
                    "total_tables": "INT",
                    "total_records": "INT",
                    "tables_processed": "STRING",
                },
            }
        )

        log.info(f"Schema discovery complete: {len(schema_list)} tables found")
        return schema_list

    finally:
        # Ensure the database connection is closed after schema discovery
        connection.close()


def upsert_to_sync_history(state: dict, sync_start: str, tables: list[str], total_records: int):
    """
    Helper function to upsert a summary record into the sync_history table after each sync.
    This can be used to track sync history over time.
    Args:
        state: The state dictionary to checkpoint after the upsert.
        sync_start: The ISO timestamp when the sync started.
        tables: List of table names that were processed in the sync.
        total_records: Total number of records processed across all tables.
    """
    try:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(
            table="sync_history",
            data={
                "sync_timestamp": sync_start,
                "total_tables": len(tables),
                "total_records": total_records,
                "tables_processed": ", ".join(tables),
            },
        )

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)
        log.info(
            f"Upserted sync summary to validation table: {total_records} records from {len(tables)} tables"
        )
    except Exception as e:
        log.warning(f"Failed to upsert to validation table: {e}")


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
    log.warning("Examples: Connectors - Simple EHI Example")

    # validate the configuration parameters before attempting to connect to the database
    validate_configuration(configuration)
    # connect to the database using the provided configuration parameters
    connection = _connect_to_mssql(configuration)

    try:
        # get the list of tables to sync from the database
        tables = _get_table_list(connection)
        # capture start time of the sync for sync_history table and logging purposes
        sync_start = datetime.now(timezone.utc).isoformat()

        # Determine which tables have a __MODIFIED_COLUMN_NAME column
        tables_with_modified_date = _get_tables_with_modified_date(connection, tables)

        total_records = 0
        destination_table_names = []

        for schema_name, table_name in tables:
            destination_table_name = f"{schema_name}_{table_name}"
            destination_table_names.append(destination_table_name)
            log.info(f"Processing table: {schema_name}.{table_name} → {destination_table_name}")
            records_processed = 0

            # Determine once whether the table has a __MODIFIED_COLUMN_NAME column.
            has_modified_date = destination_table_name in tables_with_modified_date
            if has_modified_date:
                # Use the stored cursor, or the sentinel date on historical sync
                last_sync_time = state.get(destination_table_name, __INITIAL_SYNC_DATE)
            else:
                # Tables without __MODIFIED_COLUMN_NAME always perform full sync
                last_sync_time = None

            for record in _get_table_data(
                connection, schema_name, table_name, last_sync_time, has_modified_date
            ):
                try:
                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The first argument is the name of the destination table.
                    # The second argument is a dictionary containing the record to be upserted.
                    op.upsert(table=destination_table_name, data=record)
                    records_processed += 1

                    if has_modified_date:
                        last_modified = record.get(__MODIFIED_COLUMN_NAME)
                        if last_modified is not None:
                            state[destination_table_name] = (
                                last_modified.isoformat()
                                if isinstance(last_modified, datetime)
                                else str(last_modified)
                            )

                    if records_processed % __CHECKPOINT_INTERVAL == 0:
                        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                        # from the correct position in case of next sync or interruptions.
                        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                        # Learn more about how and where to checkpoint by reading our best practices documentation
                        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                        op.checkpoint(state)

                except Exception as e:
                    log.warning(f"Failed to process record in {destination_table_name}: {e}")
                    raise

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)

            total_records += records_processed
            log.info(
                f"Completed table {destination_table_name}: {records_processed} records processed"
            )

        # Write a summary record after all tables have been processed.
        upsert_to_sync_history(state, sync_start, destination_table_names, total_records)

    except Exception as e:
        log.error(f"Failed to sync data: {e}")
        raise
    finally:
        # Ensure the database connection is closed after the sync process completes
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
