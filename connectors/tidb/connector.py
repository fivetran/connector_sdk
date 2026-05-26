"""
This example connector enables incremental data synchronization from TiDB databases,
including support for vector embeddings stored as JSON columns.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For type hints
from typing import Dict, List, Any, Optional

# For reading configuration from a JSON file
import json

# CA bundle used for TLS connections (used by TiDB DSN)
import certifi

# TiDB client used to connect/query the TiDB cluster
from pytidb import TiDBClient

# For timestamp parsing/normalization
from datetime import datetime, timezone

# For time delays during retries
import time

# Module-level constants
__TIDB_CONNECTION_KEYS = ["TIDB_HOST", "TIDB_USER", "TIDB_PASS", "TIDB_PORT", "TIDB_DATABASE"]
__REQUIRED_CONFIG_KEYS = __TIDB_CONNECTION_KEYS + ["TABLES_PRIMARY_KEY_COLUMNS"]
__FALLBACK_TIMESTAMP = datetime(1990, 1, 1, tzinfo=timezone.utc)
__BATCH_SIZE = 50
__MAX_RETRIES = 3


def validate_configuration(configuration: Dict[str, Any]):
    """
    Validate that required configuration keys are present.

    Args:
        configuration: Dictionary containing connector configuration

    Raises:
        ValueError: If any required configuration key is missing
    """
    missing = [k for k in __REQUIRED_CONFIG_KEYS if not configuration.get(k)]
    if missing:
        raise ValueError(f"Missing required configuration keys: {', '.join(missing)}")


def parse_json_config(configuration: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    Parse a JSON string from configuration.

    Args:
        configuration: Dictionary containing connector configuration
        key: Configuration key to parse

    Returns:
        Parsed dictionary from JSON string

    Raises:
        ValueError: If JSON parsing fails
    """
    if key not in configuration:
        raise ValueError(f"Could not find '{key}' in configuration")

    try:
        return json.loads(configuration[key])
    except Exception as e:
        raise ValueError(f"Failed to parse {key} JSON") from e


def build_schema_entry(table_name: str, primary_key_column: str) -> Dict[str, Any]:
    """
    Build a schema entry for a regular table.

    Args:
        table_name: Name of the table
        primary_key_column: Primary key column name

    Returns:
        Schema dictionary with table name and primary key
    """
    return {"table": table_name, "primary_key": [primary_key_column]}


def build_vector_schema_entry(
    table_name: str, table_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Build a schema entry for a vector table with JSON typed column.

    Args:
        table_name: Name of the vector table
        table_data: Dictionary containing primary_key_column and vector_column

    Returns:
        Schema dictionary with table, primary key, and typed columns, or None if invalid
    """
    pk = table_data.get("primary_key_column")
    vector_col = table_data.get("vector_column")

    if not pk or not vector_col:
        log.info("Skipping vector table '%s' due to missing keys", table_name)
        return None

    return {"table": table_name, "primary_key": [pk], "columns": {vector_col: "JSON"}}


def schema(configuration: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    tables_and_primary_key_columns = parse_json_config(configuration, "TABLES_PRIMARY_KEY_COLUMNS")

    schema_list = []
    for table_name, primary_key_column in tables_and_primary_key_columns.items():
        schema_list.append(build_schema_entry(table_name, primary_key_column))

    # Add vector tables if configured
    if configuration.get("VECTOR_TABLES_DATA"):
        try:
            vector_tables_data = json.loads(configuration["VECTOR_TABLES_DATA"])
            for table_name, table_data in vector_tables_data.items():
                entry = build_vector_schema_entry(table_name, table_data)
                if entry:
                    schema_list.append(entry)
        except Exception:
            log.info("Failed to parse VECTOR_TABLES_DATA; ignoring vector table configuration.")

    return schema_list


def parse_embedding_string_to_list(s: Optional[str]) -> Optional[List[float]]:
    """
    Parse an embedding string into a list of floats.

    Args:
        s: Embedding string in JSON or bracketed CSV format

    Returns:
        List of float values, or None if parsing fails
    """
    if s is None:
        return None

    # Try JSON parsing first
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [float(x) for x in parsed]
    except Exception as e:
        log.info("Failed to parse embedding string as JSON: '%s' (error: %s)", s, e)

    # Fallback parse for bracketed CSV format
    try:
        ss = s.strip()
        if ss.startswith("[") and ss.endswith("]"):
            inner = ss[1:-1].strip()
        else:
            inner = ss

        if inner == "":
            return []

        parts = [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip() != ""]
        out = []
        for p in parts:
            try:
                out.append(float(p))
            except Exception:
                log.info("Failed to parse embedding element '%s' in '%s'", p, s)
                return None
        return out
    except Exception:
        return None


def parse_state_timestamp(timestamp_str: Optional[str]) -> datetime:
    """
    Parse a timestamp string from state.

    Args:
        timestamp_str: ISO-format timestamp string

    Returns:
        Timezone-aware datetime object, or fallback datetime if parsing fails
    """
    if not timestamp_str:
        return __FALLBACK_TIMESTAMP

    try:
        parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        log.info("Failed to parse state timestamp '%s', using fallback.", timestamp_str)
        return __FALLBACK_TIMESTAMP


def normalize_timestamp_field(row_data: Dict[str, Any], field_name: str, table_name: str):
    """
    Normalize a timestamp field to timezone-aware datetime.

    Args:
        row_data: Dictionary containing row data
        field_name: Name of the timestamp field
        table_name: Name of the table (for logging)
    """
    if field_name in row_data and row_data[field_name] is not None:
        val = row_data[field_name]

        # Handle datetime objects
        if hasattr(val, "tzinfo"):
            if val.tzinfo is None:
                row_data[field_name] = val.replace(tzinfo=timezone.utc)
        else:
            # Handle string timestamps
            try:
                parsed = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                row_data[field_name] = parsed
            except Exception:
                log.debug("Could not parse %s value for table %s: %s", field_name, table_name, val)


def parse_vector_column(row_data: Dict[str, Any], table_name: str, configuration: Dict[str, Any]):
    """
    Parse vector embedding column to list format.

    Args:
        row_data: Dictionary containing row data
        table_name: Name of the table
        configuration: Dictionary containing connector configuration
    """
    if not configuration.get("VECTOR_TABLES_DATA"):
        return

    try:
        vector_tables = json.loads(configuration["VECTOR_TABLES_DATA"])
        if table_name in vector_tables:
            embedding_column = vector_tables[table_name]["vector_column"]
            raw_embeddings = row_data.get(embedding_column)
            emb_list = parse_embedding_string_to_list(raw_embeddings)
            if emb_list is not None:
                row_data[embedding_column] = emb_list
    except Exception:
        log.debug(
            "Skipping vector parse for table %s due to malformed VECTOR_TABLES_DATA", table_name
        )


def process_row(
    row_data: Dict[str, Any], table_name: str, configuration: Dict[str, Any], is_vector_table: bool
) -> Dict[str, Any]:
    """
    Normalize row values before upsert.

    Args:
        row_data: Dictionary containing row data
        table_name: Name of the table
        configuration: Dictionary containing connector configuration
        is_vector_table: Whether this is a vector table

    Returns:
        Processed row data dictionary
    """
    # Normalize timestamp fields
    normalize_timestamp_field(row_data, "created_at", table_name)
    normalize_timestamp_field(row_data, "updated_at", table_name)

    # Parse vector columns if applicable
    if is_vector_table:
        parse_vector_column(row_data, table_name, configuration)

    return row_data


def escape_table_name(table_name: str) -> str:
    """
    Escape table name for SQL query to prevent injection.

    Args:
        table_name: Raw table name

    Returns:
        Escaped table name wrapped in backticks
    """
    # Remove any existing backticks and wrap in backticks
    clean_name = table_name.replace("`", "")
    return f"`{clean_name}`"


def build_incremental_query(table_name: str, last_created: str) -> str:
    """
    Build SQL query for incremental data fetch.

    Args:
        table_name: Name of the table to query
        last_created: Last processed timestamp in ISO format

    Returns:
        Tuple of (SQL query string, parameters dictionary)

    Raises:
        ValueError: If query building fails
    """
    try:
        # Convert ISO timestamp to TiDB format
        tidb_timestamp = last_created.replace("T", " ").replace("Z", "")
        escaped_table = escape_table_name(table_name)
        query = f"SELECT * FROM {escaped_table} WHERE created_at > :last_created ORDER BY created_at LIMIT :limit OFFSET :offset"
        params = {"last_created": tidb_timestamp}
        return query, params
    except Exception as e:
        raise ValueError(f"Failed to build query for table {table_name}") from e


def execute_query_with_retry(cursor, query, params=None):
    """
    Execute a query and return results as list of dictionaries.

    Args:
        cursor: TiDB client connection
        query: SQL query to execute
        params: Optional dict of params to bind to the query

    Returns:
        List of row dictionaries

    Raises:
        Exception: If query execution fails
    """
    for attempt in range(__MAX_RETRIES):
        try:
            query_result = cursor.query(query, params)
            return query_result
        except Exception as e:
            if attempt == __MAX_RETRIES - 1:
                raise
            sleep_time = min(60, 2**attempt)
            log.warning(
                f"Query failed, retry {attempt + 1}/{__MAX_RETRIES} after {sleep_time}s: %s",
                str(e),
            )
            time.sleep(sleep_time)

    # Handle different result types
    if hasattr(query_result, "to_list"):
        return query_result.to_list()
    else:
        return list(query_result)


def extract_row_timestamp(created_val: datetime) -> Optional[datetime]:
    """
    Extract and parse created_at timestamp.

    Args:
        created_val: datetime field containing created_at value

    Returns:
        Parsed datetime object or None if extraction fails
    """

    if not created_val:
        return None

    # Handle datetime objects
    if hasattr(created_val, "tzinfo"):
        if created_val.tzinfo is None:
            return created_val.replace(tzinfo=timezone.utc)
        return created_val

    # Handle string timestamps
    try:
        return parse_state_timestamp(str(created_val))
    except Exception:
        return None


def process_and_upsert_rows(
    rows: List[Dict[str, Any]],
    table_name: str,
    state: Dict[str, Any],
    configuration: Dict[str, Any],
    is_vector_table: bool,
    last_created_timestamp: datetime,
) -> datetime:
    """
    Process and upsert rows, tracking the maximum timestamp.

    Args:
        rows: List of row dictionaries to process
        table_name: Name of the table
        state: State dictionary for checkpointing
        configuration: Dictionary containing connector configuration
        is_vector_table: Whether this is a vector table
        last_created_timestamp: Current last processed timestamp

    Returns:
        Maximum timestamp seen across all rows
    """
    max_seen_timestamp = last_created_timestamp

    for row in rows:
        try:
            row_data = process_row(row, table_name, configuration, is_vector_table)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=table_name, data=row_data)

            # Update max timestamp once upsert succeeded
            max_seen_timestamp = row_data.get("created_at")

        except Exception as row_err:
            # Log row-level errors and continue processing other rows
            log.error(f"Error processing row for table {table_name}: {row_err}")

            # Store sample of problematic row for debugging
            try:
                sample_key = f"{table_name}_last_row_error_sample"
                # Store only non-sensitive metadata about the error for debugging
                error_metadata = {
                    "row_id": row.get("id", "<no-id>"),
                    "table_name": table_name,
                    "error_message": str(row_err),
                }
                # Optionally include timestamp if present
                if "created_at" in row:
                    error_metadata["created_at"] = str(row.get("created_at"))
                state[sample_key] = json.dumps(error_metadata)
            except Exception as sample_row_err:
                # If storing the error metadata fails (e.g., due to serialization issues), ignore the error.
                # This is non-critical and should not interrupt processing of other rows.
                log.debug(
                    "Ignoring error while storing sample row for table %s: %s",
                    table_name,
                    sample_row_err,
                )

    return extract_row_timestamp(max_seen_timestamp)


def update_state_timestamp(state: Dict[str, Any], table_name: str, timestamp: datetime):
    """
    Update state with the last processed timestamp.

    Args:
        state: State dictionary
        table_name: Name of the table
        timestamp: Datetime to store in state
    """
    try:
        state[f"{table_name}_last_created"] = timestamp.isoformat()
    except Exception:
        # Fallback to string representation if isoformat fails
        state[f"{table_name}_last_created"] = str(timestamp)


def fetch_and_upsert_data(
    cursor: TiDBClient,
    table_name: str,
    state: Dict[str, Any],
    configuration: Dict[str, Any],
    is_vector_table: bool = False,
):
    """
    Fetch incremental data and upsert to destination.

    Args:
        cursor: TiDB client connection
        table_name: Name of the table to sync
        state: State dictionary for checkpointing
        configuration: Dictionary containing connector configuration
        is_vector_table: Whether this is a vector table
    """
    # Retrieve last processed timestamp from state
    last_created = state.get(f"{table_name}_last_created", "1990-01-01T00:00:00Z")
    last_created_timestamp = parse_state_timestamp(last_created)

    # Build and execute query
    try:
        page = 0
        query, params = build_incremental_query(table_name, last_created)
    except Exception as e:
        log.error(f"Failed to build query for table {table_name}: {e}")
        return
    try:
        while True:
            params["limit"] = __BATCH_SIZE
            params["offset"] = __BATCH_SIZE * page
            rows = execute_query_with_retry(cursor, query, params)
            if not rows:
                break
            # Process rows and track maximum timestamp
            max_seen_timestamp = process_and_upsert_rows(
                rows, table_name, state, configuration, is_vector_table, last_created_timestamp
            )
            # Persist updated timestamp to state
            update_state_timestamp(state, table_name, max_seen_timestamp)
            op.checkpoint(state)
            page += 1
    except Exception as e:
        # Query execution failed, likely due to missing column
        log.error(f"Failed to execute query for table {table_name}. {e}")
        state[f"{table_name}_last_error"] = str(e)
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
        return


def create_tidb_connection(configuration: Dict[str, Any]) -> TiDBClient:
    """
    Create TiDB database connection.

    Args:
        configuration: Dictionary containing connector configuration

    Returns:
        Connected TiDB client instance

    Raises:
        ValueError: If required connection parameters are missing
        Exception: If connection fails
    """
    missing = [k for k in __TIDB_CONNECTION_KEYS if not configuration.get(k)]
    if missing:
        raise ValueError(f"Missing required TiDB configuration keys: {', '.join(missing)}")

    user = configuration["TIDB_USER"]
    password = configuration["TIDB_PASS"]
    host = configuration["TIDB_HOST"]
    port = configuration["TIDB_PORT"]
    database = configuration["TIDB_DATABASE"]

    try:
        tidb_database_url = (
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?ssl_ca={certifi.where()}"
        )
        connection = TiDBClient.connect(tidb_database_url)
        return connection
    except Exception as e:
        log.error(f"Failed to create TiDB connection: {e}")
        raise


def get_tables_to_sync(configuration: Dict[str, Any]) -> List[str]:
    """
    Extract list of table names from configuration.

    Args:
        configuration: Dictionary containing connector configuration

    Returns:
        List of table names to sync
    """
    try:
        tables_config = json.loads(configuration.get("TABLES_PRIMARY_KEY_COLUMNS", "{}"))
        return list(tables_config.keys())
    except Exception:
        log.error("Failed to parse TABLES_PRIMARY_KEY_COLUMNS; nothing to do.")
        return []


def get_vector_tables_to_sync(configuration: Dict[str, Any]) -> List[str]:
    """
    Extract list of vector table names from configuration.

    Args:
        configuration: Dictionary containing connector configuration

    Returns:
        List of vector table names to sync
    """
    if not configuration.get("VECTOR_TABLES_DATA"):
        return []

    try:
        vector_tables_config = json.loads(configuration["VECTOR_TABLES_DATA"])
        return list(vector_tables_config.keys())
    except Exception:
        log.info("Failed to parse VECTOR_TABLES_DATA; skipping vector table processing.")
        return []


def sync_regular_tables(
    connection: TiDBClient, tables: List[str], state: Dict[str, Any], configuration: Dict[str, Any]
):
    """
    Synchronize all regular tables.

    Args:
        connection: TiDB client connection
        tables: List of table names to sync
        state: State dictionary for checkpointing
        configuration: Dictionary containing connector configuration
    """
    for table_name in tables:
        try:
            fetch_and_upsert_data(
                cursor=connection, table_name=table_name, state=state, configuration=configuration
            )
        except Exception as t_err:
            # Log table-level errors but continue with other tables
            log.error(f"Unhandled error processing table: {table_name}. {t_err}")
            state[f"{table_name}_last_error"] = str(t_err)
            try:
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)
            except Exception:
                log.error(f"Failed to checkpoint state after table-level error for {table_name}")


def sync_vector_tables(
    connection: TiDBClient,
    vector_tables: List[str],
    state: Dict[str, Any],
    configuration: Dict[str, Any],
):
    """
    Synchronize all vector tables.

    Args:
        connection: TiDB client connection
        vector_tables: List of vector table names to sync
        state: State dictionary for checkpointing
        configuration: Dictionary containing connector configuration
    """
    for table_name in vector_tables:
        try:
            fetch_and_upsert_data(
                cursor=connection,
                table_name=table_name,
                state=state,
                configuration=configuration,
                is_vector_table=True,
            )
        except Exception as t_err:
            # Log vector table errors but continue with other tables
            log.error(f"Unhandled error processing vector table {table_name}: {t_err}")
            state[f"{table_name}_last_error"] = str(t_err)
            try:
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)
            except Exception:
                log.error(f"Failed to checkpoint state after vector-table error for {table_name}")


def close_connection(connection: TiDBClient):
    """
    Close TiDB connection if close method exists.

    Args:
        connection: TiDB client connection
    """
    try:
        if hasattr(connection, "close"):
            connection.close()
    except Exception:
        log.debug("Error while closing TiDB connection (non-fatal).")


def update(configuration: Dict[str, Any], state: Dict[str, Any]):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: DATABASE : TIDB")

    # Validate configuration early
    validate_configuration(configuration)

    # Establish database connection
    try:
        connection = create_tidb_connection(configuration=configuration)
    except Exception as conn_err:
        log.error(f"Could not connect to TiDB: {conn_err}")
        state["last_connection_error"] = str(conn_err)
        try:
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)
        except Exception:
            log.error("Failed to checkpoint state after connection error.")
        raise

    # Get tables to sync
    tables = get_tables_to_sync(configuration)
    vector_tables = get_vector_tables_to_sync(configuration)

    # Synchronize regular tables
    sync_regular_tables(connection, tables, state, configuration)

    # Synchronize vector tables
    sync_vector_tables(connection, vector_tables, state, configuration)

    # Clean up connection
    close_connection(connection)


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
