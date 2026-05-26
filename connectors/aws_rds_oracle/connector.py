"""Example connector demonstrating how to sync data from AWS RDS Oracle using the Fivetran Connector SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# For datetime parsing and formatting of timestamp values
from datetime import datetime

# for implementing retry logic with delays
import time

# For type hints to improve code clarity and enable static type checking
from typing import Any, Dict, Iterable, List, Optional, Tuple

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Add your source-specific imports here.
# oracledb provides the Oracle database driver used for connectivity in this example.
import oracledb

__TABLES: List[Dict[str, Any]] = [
    {
        "schema": "ADMIN",
        "table": "FIVETRAN_LOGMINER_TEST",
        "pk": ["ID"],
        "columns": ["ID", "NAME", "LAST_UPDATED"],
    },
]

__DEFAULT_PORT = 1521
__FETCH_BATCH_SIZE = 500
__CHECKPOINT_INTERVAL = 1000
__DEFAULT_SYNC_DATETIME = datetime(1970, 1, 1, 0, 0, 0)
__MAX_RETRIES = 5


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    required_configs = ["host", "port", "service_name", "user", "password"]
    missing = [key for key in required_configs if not configuration.get(key)]
    if missing:
        raise ValueError(f"Missing required configuration value(s): {', '.join(missing)}")


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            try:
                return datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    return None


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def connect_oracle(configuration: dict) -> "oracledb.Connection":
    """
    Establish a connection to Oracle using configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Active Oracle database connection.
    Raises:
        ValueError: if the provided port value is not an integer.
        oracledb.Error: if the database connection cannot be established.
    """

    try:
        port_value = int(configuration.get("port", __DEFAULT_PORT))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid port value in configuration: {configuration.get('port')}"
        ) from exc

    dsn = oracledb.makedsn(
        host=configuration.get("host"),
        port=port_value,
        service_name=configuration.get("service_name"),
    )
    return oracledb.connect(
        user=configuration.get("user"),
        password=configuration.get("password"),
        dsn=dsn,
    )


def _build_incremental_query(columns: List[str], full_table_name: str) -> str:
    """
    Build the incremental query for pulling Oracle records.
    Args:
        columns: Ordered list of columns to select from the source table.
        full_table_name: Fully qualified table name including schema.
    Returns:
        SQL query string that fetches records newer than the stored watermark.
    """

    select_clause = ", ".join(columns)
    return (
        f"SELECT {select_clause} FROM {full_table_name} "
        "WHERE LAST_UPDATED >= TO_TIMESTAMP(:last_sync_time, 'YYYY-MM-DD HH24:MI:SS') "
        "ORDER BY LAST_UPDATED"
    )


def _iterate_records(cursor: "oracledb.Cursor", columns: List[str]) -> Iterable[Dict[str, Any]]:
    """
    Yield records from the Oracle cursor in batches to avoid loading all rows in memory.
    Args:
        cursor: Active Oracle cursor with an executed query.
        columns: Ordered list of column names to map onto row values.
    Yields:
        Dictionary representation of each record returned by the cursor.
    """

    # Explicitly set the fetch size for batch retrieval
    cursor.arraysize = __FETCH_BATCH_SIZE
    while True:
        rows = cursor.fetchmany(__FETCH_BATCH_SIZE)
        if not rows:
            break
        for row in rows:
            yield dict(zip(columns, row))


def _apply_row_operations(table_name: str, record: Dict[str, Any]) -> Optional[datetime]:
    """
    Upsert the record into the destination and extract the updated watermark.
    Args:
        table_name: Destination table name.
        record: Record fetched from the source.
    Returns:
        Parsed datetime for LAST_UPDATED if available.
    """

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table_name, data=record)
    return _parse_timestamp(record.get("LAST_UPDATED"))


def _checkpoint_if_needed(
    processed_rows: int,
    latest_sync_dt: Optional[datetime],
    fallback_sync_dt: datetime,
    full_table_name: str,
) -> None:
    """
    Checkpoint connector state periodically to guard against data re-processing.
    Args:
        processed_rows: Number of rows processed so far.
        latest_sync_dt: Latest LAST_UPDATED timestamp encountered in this batch.
        fallback_sync_dt: Watermark to use when no new rows are present.
        full_table_name: Fully qualified table name used for logging.
    """

    if processed_rows % __CHECKPOINT_INTERVAL != 0:
        return

    checkpoint_dt = latest_sync_dt or fallback_sync_dt or __DEFAULT_SYNC_DATETIME

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint({"last_sync_time": _format_timestamp(checkpoint_dt)})

    log.info(f"Checkpointed state after {processed_rows} rows for table {full_table_name}")


def _sync_table(
    connection: "oracledb.Connection",
    table_def: Dict[str, Any],
    last_sync_time_str: str,
    fallback_sync_dt: datetime,
) -> Tuple[Optional[datetime], int]:
    """
    Synchronize a single table using the provided connection.
    Args:
        connection: Active Oracle connection used for querying data.
        table_def: Table definition dictionary with schema, table, pk, and columns.
        last_sync_time_str: Serialized watermark in Oracle compatible format.
        fallback_sync_dt: Watermark used when no newer records exist.
    Returns:
        Tuple containing the latest LAST_UPDATED datetime encountered and the total processed rows.
    """

    schema_name = table_def["schema"]
    table_name = table_def["table"]
    columns = table_def["columns"]
    full_table_name = f"{schema_name}.{table_name}"

    log.info(f"Syncing table {full_table_name}")
    latest_sync_dt: Optional[datetime] = None
    processed_rows = 0

    query = _build_incremental_query(columns=columns, full_table_name=full_table_name)

    with connection.cursor() as cursor:
        cursor.arraysize = __FETCH_BATCH_SIZE
        cursor.execute(query, {"last_sync_time": last_sync_time_str})

        for record in _iterate_records(cursor=cursor, columns=columns):
            processed_rows += 1
            record_sync_dt = _apply_row_operations(table_name=table_name, record=record)

            if record_sync_dt and (latest_sync_dt is None or record_sync_dt > latest_sync_dt):
                latest_sync_dt = record_sync_dt

            _checkpoint_if_needed(
                processed_rows=processed_rows,
                latest_sync_dt=latest_sync_dt,
                fallback_sync_dt=fallback_sync_dt,
                full_table_name=full_table_name,
            )

    log.info(f"Finished syncing table {full_table_name}, processed {processed_rows} rows")
    return latest_sync_dt, processed_rows


def schema(configuration: dict) -> List[Dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        List of table schemas for Fivetran.
    """

    return [
        {
            "table": table_def["table"],
            "primary_key": table_def["pk"],
        }
        for table_def in __TABLES
    ]


def update(configuration: dict, state: dict) -> None:
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: Connector : AWS RDS Oracle")

    validate_configuration(configuration=configuration)

    raw_last_sync_time = state.get("last_sync_time")
    parsed_last_sync_time = _parse_timestamp(raw_last_sync_time)
    if raw_last_sync_time and parsed_last_sync_time is None:
        log.warning(
            f"Unable to parse last_sync_time '{raw_last_sync_time}', defaulting to {_format_timestamp(__DEFAULT_SYNC_DATETIME)}."
        )
    last_sync_time_dt = parsed_last_sync_time or __DEFAULT_SYNC_DATETIME
    last_sync_time_str = _format_timestamp(last_sync_time_dt)
    new_sync_time_dt = last_sync_time_dt

    conn: Optional["oracledb.Connection"] = None
    for attempt in range(__MAX_RETRIES):
        try:
            conn = connect_oracle(configuration=configuration)
            log.info("Connected to Oracle database")
            break
        except (oracledb.OperationalError, oracledb.DatabaseError) as exc:
            if attempt == __MAX_RETRIES - 1:
                log.error(f"Oracle connection failed after {__MAX_RETRIES} attempts: {exc}")
                raise
            sleep_time = min(60, 2**attempt)
            log.warning(
                f"Connection attempt {attempt + 1}/{__MAX_RETRIES} failed, retrying in {sleep_time}s: {exc}"
            )
            time.sleep(sleep_time)

    try:
        for table_def in __TABLES:
            table_latest_sync_dt, _ = _sync_table(
                connection=conn,
                table_def=table_def,
                last_sync_time_str=last_sync_time_str,
                fallback_sync_dt=new_sync_time_dt,
            )

            if table_latest_sync_dt and table_latest_sync_dt > new_sync_time_dt:
                new_sync_time_dt = table_latest_sync_dt
    finally:
        if conn:
            conn.close()

    final_state = {"last_sync_time": _format_timestamp(new_sync_time_dt)}
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(final_state)

    log.info("Update function completed successfully")


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

# Source table:
# ┌─────────────┬─────────────┬─────────────┬─────────────┬──────────┐
# │     ID      │    NAME     │ LAST_UPDATED│   ...other columns...  │
# │   int       │  varchar    │ timestamp   │                        │
# ├─────────────┼─────────────┼─────────────┼─────────────────────── ┤
# │     1       │   Mathew    │ 2023-12-31 23:59:59.000 │ ...        │
# │     2       │   Joe       │ 2024-01-31 23:04:39.000 │ ...        │
# │     3       │   Jake      │ 2023-11-01 23:59:59.000 │ ...        │
# │     4       │   John      │ 2024-02-14 22:59:59.000 │ ...        │
# │     5       │   Ricky     │ 2024-03-16 16:40:29.000 │ ...        │
# ├─────────────┴─────────────┴─────────────┴────────────────────────┤
# │ 5 rows                                              3 columns+   │
# └──────────────────────────────────────────────────────────────────┘

# Resulting table:
# ┌─────────────┬─────────────┬─────────────┬────────────────────────────┐
# │     ID      │    NAME     │ LAST_UPDATED                            │
# │   int       │  varchar    │ timestamp                               │
# ├─────────────┼─────────────┼──────────────────────────────────────────┤
# │     2       │   Joe       │ 2024-01-31T23:04:39Z                    │
# │     4       │   John      │ 2024-02-14T22:59:59Z                    │
# │     5       │   Ricky     │ 2024-03-16T16:40:29Z                    │
# ├─────────────┴─────────────┴──────────────────────────────────────────┤
# │ 3 rows                                                   3 columns   │
# └──────────────────────────────────────────────────────────────────────┘
