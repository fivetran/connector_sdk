"""
This module provides Redshift client utilities for the UNLOAD connector.
It handles Redshift connections, UNLOAD command execution, metadata fetching,
and table plan building for efficient data extraction via S3.
"""

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

from dataclasses import dataclass  # For creating data classes
from typing import List, Dict, Optional, Any  # For type hinting
from datetime import date, datetime  # For handling date and datetime types
import redshift_connector  # Redshift database connector
from queue import Queue  # For managing connection pool
import uuid  # For generating unique IDs
import time  # For timestamp generation

# Import table specifications and constants
from table_specs import (
    TABLE_SPECS,
    PREFERRED_TS_COLUMN_NAMES,
    TIMESTAMP_TYPE_NAMES,
    CHECKPOINT_EVERY_ROWS,
    REDSHIFT_TO_FIVETRAN_TYPE_MAP,
)

# Import S3 client utilities
from s3_client import S3Client

# Global variable to hold the list of table plans used during the sync
__TABLE_PLAN_LIST = None

# Variables for UNLOAD command
__MAX_FILE_SIZE = 128  # Maximum file size for each parquet file in MB
__PARALLEL_UNLOAD = True  # Ensure files are created even for small datasets
__CLEAN_EXISTING_PATH = False  # Clean existing files at the S3 path before UNLOAD

# Variables for logging and diagnostics
__QUERY_ROW_COUNT = False  # Query STL_UNLOAD_LOG for row count after UNLOAD (adds latency, disable for faster syncs)

# Variables for S3 bucket
__DEFAULT_BUCKET_PREFIX = "fivetran-unload"


@dataclass
class TablePlan:
    """
    Dataclass to hold the plan for syncing a single table via UNLOAD.
    Attributes:
        stream: Full stream name (schema.table)
        schema: Schema name
        table: Table name
        primary_keys: List of primary key columns
        selected_columns: List of columns to select
        explicit_columns: Mapping of column names to explicit Fivetran semantic types
        strategy: Replication strategy ('FULL' or 'INCREMENTAL')
        replication_key: Name of the replication key column, or None
    """

    stream: str
    schema: str
    table: str
    primary_keys: List[str]
    selected_columns: List[str]
    explicit_columns: Dict[str, str]
    strategy: str
    replication_key: Optional[str]


class _ConnectionPool:
    """
    A simple connection pool for managing Redshift connections.
    This class maintains a pool of Redshift connections that can be reused across multiple threads.
    """

    def __init__(self, size: int, configuration: dict):
        """
        Initialize the connection pool with a specified number of connections.
        Args:
            size: Number of connections in the pool
            configuration: Redshift connection configuration
        """
        log.info("Initializing Redshift connection pool for parallel sync")
        self._queue = Queue(maxsize=size)
        self._all = []
        for _ in range(size):
            conn = connect_redshift(configuration=configuration)
            self._all.append(conn)
            self._queue.put(conn)

    def acquire(self, timeout: Optional[float] = None):
        """
        Acquire a connection from the pool, waiting up to 'timeout' seconds if necessary.
        Args:
            timeout: Maximum time to wait for a connection, or None to wait indefinitely.
        Returns:
            A Redshift connection object.
        """
        return self._queue.get(timeout=timeout)

    def release(self, conn):
        """
        Release a connection back to the pool.
        Args:
            conn: Redshift connection object to be returned to the pool.
        """
        self._queue.put(conn)

    def close_all(self):
        """
        Close all connections in the pool.
        """
        for connection in self._all:
            try:
                connection.close()
            except Exception as e:
                log.error(f"Error closing connection: {e}")


def _get_config_bool(configuration: dict, key: str, default: bool = False) -> bool:
    """
    Parse a boolean configuration value from string.
    Args:
        configuration: Configuration dictionary
        key: Configuration key
        default: Default value if key is missing
    Returns:
        Boolean value
    """
    value = configuration.get(key, str(default)).lower()
    return value == "true"


def get_table_plans(configuration):
    """
    Get or build the list of table plans for the sync.
    Args:
        configuration: dict with connector configuration
    Returns:
        List of TablePlan dataclass instances for each table to be synced
    """
    global __TABLE_PLAN_LIST

    if __TABLE_PLAN_LIST is not None:
        # Return the cached list of table plans if already built
        return __TABLE_PLAN_LIST

    connection = connect_redshift(configuration=configuration)
    try:
        # Build the table plans only once per connector run
        __TABLE_PLAN_LIST = build_table_plans(connection=connection, configuration=configuration)
        # Return the list of table plans
        return __TABLE_PLAN_LIST
    finally:
        # Ensure the connection is closed after use
        connection.close()


def connect_redshift(configuration: dict):
    """
    Connect to Redshift using configuration parameters.
    Args:
        configuration: Dictionary containing Redshift connection details
    Returns:
        A Redshift connection object.
    """
    connection = redshift_connector.connect(
        host=configuration.get("redshift_host"),
        port=int(configuration.get("redshift_port", "5439")),
        database=configuration.get("redshift_database"),
        user=configuration.get("redshift_user"),
        password=configuration.get("redshift_password"),
        ssl=True,
    )

    log.info("Connected to Amazon Redshift Database successfully")
    return connection


def _split_table(name: str, default_schema: str) -> tuple:
    """
    Split a table name into schema and table components.
    Args:
        name: full table name, possibly schema-qualified
        default_schema: default schema to use if not specified in name
    Returns:
        A tuple of (schema_name, table_name)
    """
    if "." in name:
        schema_name, table_name = name.split(".", 1)
        return schema_name, table_name
    return (default_schema or "public"), name


def apply_projection(cols_with_types: List[tuple], spec: dict) -> List[tuple]:
    """
    Apply the include/exclude projections to a list of available columns.
    Args:
        cols_with_types: list of (column_name, data_type) tuples
        spec: dict with optional 'include' and 'exclude' lists
    Returns:
        List of selected columns after applying projections
    """
    include = spec.get("include") or None
    exclude = spec.get("exclude") or None

    include_set = {column.lower() for column in include} if include else None
    exclude_set = {column.lower() for column in exclude} if exclude else None

    selected_columns = []
    for col, col_type in cols_with_types:
        lower_column = col.lower()
        if include_set and lower_column not in include_set:
            continue
        if exclude_set and lower_column in exclude_set:
            continue
        selected_columns.append((col, col_type))
    return selected_columns


def infer_replication_key(cols_with_types: List[tuple]) -> Optional[str]:
    """
    Infer a replication key column from available columns based on preferred names and types.
    The function looks for columns with timestamp or date types, prioritizing those with preferred names.
    If no preferred names are found, it falls back to the first timestamp/date column found.
    If no timestamp/date columns are found, it returns None.
    Args:
        cols_with_types: list of (column_name, data_type) tuples
    Returns:
        The name of the inferred replication key column, or None if none found.
    """
    timestamp_cols = [
        column
        for column, column_type in cols_with_types
        if (column_type or "").lower() in TIMESTAMP_TYPE_NAMES
    ]

    if not timestamp_cols:
        # No timestamp or date columns found; cannot infer replication key
        # In this case, the table will fall back to FULL resync strategy
        return None

    lower_columns = {col.lower(): col for col in timestamp_cols}
    for preferred in PREFERRED_TS_COLUMN_NAMES:
        # Check for preferred names in a case-insensitive manner
        if preferred in lower_columns:
            # If the preferred name is found, return the original column name
            return lower_columns[preferred]
    # If no preferred names matched, return the first timestamp column found
    return timestamp_cols[0]


def detect_typed_columns(selected_cols_with_types: List[tuple]) -> Dict[str, str]:
    """
    Detect columns that require explicit typing based on their data types.
    Args:
        selected_cols_with_types: list of (column_name, data_type) tuples
    Returns:
        A dictionary mapping column names to their explicit Fivetran semantic types.
    """
    explicit = {}
    for column, datatype in selected_cols_with_types:
        data_type = (datatype or "").lower()
        if data_type in REDSHIFT_TO_FIVETRAN_TYPE_MAP:
            explicit[column] = REDSHIFT_TO_FIVETRAN_TYPE_MAP[data_type]
    return explicit


def build_unload_query(
    redshift_schema: str,
    table: str,
    columns: List[str],
    replication_key: Optional[str],
    bookmark: Any,
) -> str:
    """
    Build a SELECT query for use in UNLOAD command.
    Args:
        redshift_schema: schema name
        table: table name
        columns: list of column names to select
        replication_key: name of the replication key column, or None
        bookmark: last synced value of the replication key, or None
    Returns:
        SQL SELECT query string for UNLOAD
    """
    table_columns = list(columns)
    if replication_key and replication_key not in table_columns:
        table_columns.append(replication_key)

    cols_sql = ", ".join(f'"{column}"' for column in table_columns)
    sql = f'SELECT {cols_sql} FROM "{redshift_schema}"."{table}"'

    if replication_key and bookmark is not None:
        # Format bookmark value for SQL
        if isinstance(bookmark, (datetime, date)):
            bookmark_str = bookmark.isoformat()
        else:
            bookmark_str = str(bookmark)
        sql += f" WHERE \"{replication_key}\" > '{bookmark_str}'"

    if replication_key:
        sql += f' ORDER BY "{replication_key}"'

    return sql


def build_unload_command(
    query: str,
    s3_path: str,
    iam_role: str,
) -> str:
    """
    Build a Redshift UNLOAD command to export data to S3.
    Uses optimal hardcoded settings for reliability.
    The command exports data in Parquet format.
    Args:
        query: SELECT query to unload
        s3_path: S3 destination path (s3://bucket/prefix/)
        iam_role: IAM role ARN for S3 access
    Returns:
        Complete UNLOAD command string
    """
    # Escape single quotes in the query for embedding in UNLOAD
    escaped_query = query.replace("'", "''")

    unload_cmd = f"""
    UNLOAD ('{escaped_query}')
    TO '{s3_path}'
    IAM_ROLE '{iam_role}'
    FORMAT AS PARQUET
    PARALLEL {'ON' if __PARALLEL_UNLOAD else 'OFF'}
    MAXFILESIZE {__MAX_FILE_SIZE} MB
    {' CLEANPATH' if __CLEAN_EXISTING_PATH else ''}
    """

    return unload_cmd


def fetch_metadata(connection, table_tuples: List[tuple]) -> Dict[tuple, dict]:
    """
    Fetch metadata (columns and primary keys) for the given list of (schema, table) tuples from Redshift.
    The function queries the information_schema to retrieve column names, data types, and primary key information
    for the specified tables.
    Args:
        connection: Redshift connection object
        table_tuples: list of (schema_name, table_name) tuples
    Returns:
        A dictionary mapping (schema_name, table_name) to metadata
    """
    if not table_tuples:
        log.warning("No tables specified for metadata fetch.")
        return {}

    conditions = []
    params = []
    for schema_name, table_name in table_tuples:
        conditions.append("(c.table_schema = %s AND c.table_name = %s)")
        params.extend([schema_name, table_name])
    where_clause = " OR ".join(conditions)

    sql = f"""
    WITH pk AS (
        SELECT tc.table_schema, tc.table_name, kcu.column_name, kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
    )
    SELECT
        c.table_schema,
        c.table_name,
        c.column_name,
        c.data_type,
        c.ordinal_position,
        CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END AS is_pk
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON c.table_schema = t.table_schema
     AND c.table_name = t.table_name
     AND t.table_type = 'BASE TABLE'
    LEFT JOIN pk
      ON pk.table_schema = c.table_schema
     AND pk.table_name = c.table_name
     AND pk.column_name = c.column_name
    WHERE {where_clause}
    ORDER BY c.table_schema, c.table_name, c.ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    metadata = {}
    for schema_name, table_name, column, datatype, _, is_primary_key in rows:
        key = (schema_name, table_name)
        if key not in metadata:
            metadata[key] = {"columns": [], "primary_keys": []}
        metadata[key]["columns"].append((column, datatype))
        if is_primary_key:
            metadata[key]["primary_keys"].append(column)
    return metadata


def fetch_schema_auto(connection, redshift_schema: str) -> tuple:
    """
    Discover tables in the given schema and fetch their metadata from Redshift.
    This function queries the information_schema to find all base tables in the specified schema,
    then retrieves their columns and primary key information.
    Args:
        connection: Redshift connection object
        redshift_schema: schema name to discover tables in
    Returns:
        A tuple of (table_tuples, meta) where:
        - table_tuples is a list of (schema_name, table_name) tuples
        - meta is a dictionary mapping (schema_name, table_name) to metadata including columns and primary keys
    """
    sql_tables = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY 1, 2;
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_tables, (redshift_schema,))
        # Build a list of (schema, table) tuples fetched from redshift information_schema
        # This is used when auto schema detection is enabled
        table_tuples = [(data[0], data[1]) for data in cursor.fetchall()]

    # Fetch the metadata for the discovered tables from Redshift
    metadata = fetch_metadata(connection=connection, table_tuples=table_tuples)
    return table_tuples, metadata


def _load_base_specs_and_metadata(
    connection, redshift_schema: str, auto_schema_detection: bool
) -> tuple:
    """
    Load the base table specifications and fetch metadata from Redshift.
    If auto_schema_detection is enabled, discover tables and primary keys from Redshift.
    Otherwise, use predefined TABLE_SPECS and fetch metadata for those tables.
    Args:
        connection: Redshift connection object
        redshift_schema: default schema to use if not specified in table name
        auto_schema_detection: whether to auto-discover tables and primary keys
    Returns:
        A tuple of (base_specs, meta) where:
        - base_specs is a list of table specifications
        - meta is a dictionary mapping (schema, table) to metadata including columns and primary keys
    """
    if auto_schema_detection:
        # Discover tables and primary keys from Redshift when auto_schema_detection is enabled
        table_tuples, metadata = fetch_schema_auto(
            connection=connection, redshift_schema=redshift_schema
        )
        base_table_specs = [
            {
                "name": f"{table_schema}.{table}",
                "primary_keys": metadata.get((table_schema, table), {}).get("primary_keys", []),
            }
            for table_schema, table in table_tuples
        ]
    else:
        # Use predefined TABLE_SPECS and fetch metadata for those tables
        base_table_specs = TABLE_SPECS
        table_tuples = []
        for spec in base_table_specs:
            table_schema, table = _split_table(spec["name"], redshift_schema)
            table_tuples.append((table_schema, table))
        metadata = fetch_metadata(connection, table_tuples)
    return base_table_specs, metadata


def _prepare_table_identity(spec, redshift_schema):
    """
    Prepare the table identity (schema, table, stream) from the specification.
    Args:
        spec: dict with 'name' key
        redshift_schema: default schema to use if not specified in table name
    Returns:
        A tuple of (table_schema, table, stream) where stream is 'schema.table'
    """
    table_schema, table = _split_table(spec["name"], redshift_schema)
    stream = f"{table_schema}.{table}"
    return table_schema, table, stream


def _determine_strategy_and_replication_key(
    spec: dict, cols_with_types: List[tuple], enable_complete_resync: bool
) -> tuple:
    """
    Determine the replication strategy and replication key for a table spec.
    If the strategy is INCREMENTAL but no replication key is specified, attempt to infer one
    from the available columns. If no suitable replication key is found, fall back to FULL.
    Args:
        spec: dict with optional 'strategy' and 'replication_key'
        cols_with_types: list of (column_name, data_type) tuples
        enable_complete_resync: bool, if True, forces FULL resync for all tables
    Returns:
        A tuple of (strategy, replication_key) where strategy is either 'FULL' or 'INCREMENTAL',
        and replication_key is the name of the replication key column or None.
    """
    strategy_raw = spec.get("strategy")
    strategy = strategy_raw.upper() if strategy_raw else None
    provided_replication_key = spec.get("replication_key")
    table_name = spec.get("name")

    if strategy == "FULL" or enable_complete_resync:
        return "FULL", None

    if strategy == "INCREMENTAL":
        replication_key = (
            provided_replication_key
            if provided_replication_key
            else infer_replication_key(cols_with_types)
        )
        if not replication_key:
            log.warning(f"{table_name}: no replication key found; falling back to FULL resync.")
            return "FULL", None
        return "INCREMENTAL", replication_key

    replication_key = (
        provided_replication_key
        if provided_replication_key
        else infer_replication_key(cols_with_types)
    )
    if replication_key:
        return "INCREMENTAL", replication_key
    return "FULL", None


def _build_plan(
    spec: dict,
    table_schema: str,
    table: str,
    stream: str,
    table_metadata: dict,
    selected_cols_with_types: List[tuple],
    enable_complete_resync: bool,
) -> TablePlan:
    """
    Build a TablePlan dataclass instance for a given table specification.
    Args:
        spec: dict with table specification details
        table_schema: str, schema name of the table
        table: str, table name
        stream: str, full stream name (schema.table)
        table_metadata: dict with metadata including primary keys
        selected_cols_with_types: list of (column_name, data_type) tuples for selected columns
        enable_complete_resync: bool, if True, forces FULL resync for all tables
    Returns:
        A TablePlan dataclass instance with all relevant details for syncing the table.
    """
    # Determine primary keys for the table
    primary_keys = spec.get("primary_keys") or table_metadata.get("primary_keys") or []
    # Determine replication strategy and replication key
    strategy, replication_key = _determine_strategy_and_replication_key(
        spec=spec,
        cols_with_types=selected_cols_with_types,
        enable_complete_resync=enable_complete_resync,
    )
    # Detect columns that require explicit typing based on their data types
    explicit_cols = detect_typed_columns(selected_cols_with_types=selected_cols_with_types)
    # List of selected column names required for building the SQL query
    selected_columns = [column for column, _ in selected_cols_with_types]

    # Construct and return the TablePlan dataclass instance with all relevant details
    plan = TablePlan(
        stream=stream,
        schema=table_schema,
        table=table,
        primary_keys=list(primary_keys),
        selected_columns=selected_columns,
        explicit_columns=explicit_cols,
        strategy=strategy,
        replication_key=replication_key,
    )
    return plan


def build_table_plans(connection, configuration: dict) -> List[TablePlan]:
    """
    Build table plans based on configuration and Redshift metadata.
    If auto_schema_detection is enabled, discover tables and primary keys from Redshift.
    Otherwise, use predefined TABLE_SPECS and fetch metadata for those tables.
    Each plan includes details such as selected columns, primary keys, replication strategy, and replication key
    Args:
        connection: Redshift connection object
        configuration: dict with connector configuration
    Returns:
        List of TablePlan dataclass instances for each table to be synced
    """
    # Extract configuration parameters
    redshift_schema = configuration["redshift_schema"]
    auto_schema_detection = _get_config_bool(configuration, "auto_schema_detection")
    log.info(f"Auto schema detection is {'enabled' if auto_schema_detection else 'disabled'}.")

    # If enabled, there will be no incremental sync for any table. All the tables will be fully synced everytime.
    enable_complete_resync = _get_config_bool(configuration, "enable_complete_resync")
    log.info(f"Complete resync is {'enabled' if enable_complete_resync else 'disabled'}.")

    # Load base table specifications and fetch metadata from Redshift
    base_specs, metadata = _load_base_specs_and_metadata(
        connection=connection,
        redshift_schema=redshift_schema,
        auto_schema_detection=auto_schema_detection,
    )

    # Build table plans for each table specified in the base_specs
    plans = []
    for spec in base_specs:
        # Prepare table identity and retrieve metadata
        table_schema, table, stream = _prepare_table_identity(
            spec=spec, redshift_schema=redshift_schema
        )
        table_metadata = metadata.get((table_schema, table))

        if not table_metadata:
            log.warning(f"{stream}: no metadata returned; skipping.")
            continue

        cols_with_types = table_metadata.get("columns") or []
        if not cols_with_types:
            log.warning(f"{stream}: no columns discovered; skipping.")
            continue

        selected_cols_with_types = apply_projection(cols_with_types=cols_with_types, spec=spec)

        if not selected_cols_with_types:
            log.warning(f"{stream}: no columns selected after projection; skipping.")
            continue

        # Build the plan and add to the list of plans
        plan = _build_plan(
            spec=spec,
            table_schema=table_schema,
            table=table,
            stream=stream,
            table_metadata=table_metadata,
            selected_cols_with_types=selected_cols_with_types,
            enable_complete_resync=enable_complete_resync,
        )
        plans.append(plan)

    log.info(f"Built table plans for {len(plans)} tables.")
    return plans


def _checkpoint(state, stream, replication_key, bookmark, last_processed_record):
    """
    Update the state dictionary with the latest bookmark for a given stream and replication key.
    This function is called periodically during the sync process to save progress.
    Args:
        state: current state dictionary
        stream: name of the stream (table) being synced
        replication_key: name of the replication key column
        bookmark: latest value of the replication key
        last_processed_record: the last record processed
    """
    if replication_key:
        replication_key_val = last_processed_record.get(replication_key)
        if replication_key_val is not None:
            bookmark = replication_key_val

    if replication_key and bookmark is not None:
        # Format the bookmark value appropriately for JSON serialization
        bookmark = (
            bookmark.isoformat() if isinstance(bookmark, (datetime, date)) else str(bookmark)
        )

    state[stream] = {"bookmark": bookmark, "replication_key": replication_key}
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=state)


def _generate_s3_prefix(configuration: dict, stream: str) -> str:
    """
    Generate a unique S3 prefix for UNLOAD output.
    Args:
        configuration: Connector configuration
        stream: Stream name (schema.table)
    Returns:
        S3 prefix string
    """
    base_prefix = configuration.get("s3_prefix", __DEFAULT_BUCKET_PREFIX).rstrip("/")
    # Handle empty prefix or just "/"
    if not base_prefix:
        base_prefix = __DEFAULT_BUCKET_PREFIX

    # Generate unique suffix to avoid conflicts
    timestamp = int(time.time() * 1000)
    unique_id = str(uuid.uuid4())[:8]
    safe_stream = stream.replace(".", "_")
    return f"{base_prefix}/{safe_stream}/{timestamp}_{unique_id}/"


def _get_unload_row_count(connection, s3_path: str) -> int:
    """
    Query STL_UNLOAD_LOG to get the number of rows exported by UNLOAD.
    Args:
        connection: Redshift connection object
        s3_path: S3 path used in the UNLOAD command
    Returns:
        Total number of rows unloaded, or 0 if not found
    """
    # Query STL_UNLOAD_LOG for the row count based on the S3 path
    # The path in STL_UNLOAD_LOG includes the full file path, so we use LIKE with the prefix
    query = """
        SELECT COALESCE(SUM(line_count), 0) as total_rows
        FROM stl_unload_log
        WHERE path LIKE %s
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (f"{s3_path}%",))
            result = cursor.fetchone()
            return int(result[0]) if result and result[0] else 0
    except Exception as e:
        log.warning(f"Could not fetch row count from STL_UNLOAD_LOG: {e}")
        return 0


def execute_unload(
    connection,
    plan: TablePlan,
    configuration: dict,
    state: dict,
) -> str:
    """
    Execute UNLOAD command to export table data to S3.
    Args:
        connection: Redshift connection object
        plan: TablePlan instance
        configuration: Connector configuration
        state: Current sync state
    Returns:
        S3 prefix where data was exported
    """
    replication_key = plan.replication_key
    prev_state = state.get(plan.stream) or {}
    bookmark = prev_state.get("bookmark") if replication_key else None

    # Build SELECT query for UNLOAD
    query = build_unload_query(
        redshift_schema=plan.schema,
        table=plan.table,
        columns=plan.selected_columns,
        replication_key=replication_key,
        bookmark=bookmark,
    )

    # Generate S3 path
    s3_bucket = configuration["s3_bucket"]
    s3_prefix = _generate_s3_prefix(configuration, plan.stream)
    s3_path = f"s3://{s3_bucket}/{s3_prefix}"

    # Get IAM role for S3 access
    iam_role = configuration["iam_role"]

    # Build and execute UNLOAD command
    unload_cmd = build_unload_command(
        query=query,
        s3_path=s3_path,
        iam_role=iam_role,
    )

    log.info(f"{plan.stream}: Executing UNLOAD to {s3_path}")

    with connection.cursor() as cursor:
        cursor.execute(unload_cmd)
        # UNLOAD does not return a result set, so we don't call fetchone()

    # Optionally query STL_UNLOAD_LOG to get the actual row count
    # This adds latency, so it's disabled by default for faster syncs
    if __QUERY_ROW_COUNT:
        row_count = _get_unload_row_count(connection, s3_path)
        if row_count > 0:
            log.info(f"{plan.stream}: UNLOAD completed - {row_count} rows exported")
        else:
            log.info(f"{plan.stream}: UNLOAD completed - no rows exported or count unavailable")
    else:
        log.info(f"{plan.stream}: UNLOAD completed successfully")

    return s3_prefix


def sync_from_s3(
    s3_client: S3Client,
    plan: TablePlan,
    s3_prefix: str,
    state: dict,
) -> int:
    """
    Sync data from S3 files exported by UNLOAD.
    Args:
        s3_client: S3Client instance
        plan: TablePlan instance
        s3_prefix: S3 prefix where files are located
        state: Current sync state
    Returns:
        Total number of rows processed
    """
    replication_key = plan.replication_key
    prev_state = state.get(plan.stream) or {}
    last_bookmark = prev_state.get("bookmark")

    # List all Parquet files at the prefix
    files = s3_client.list_files(s3_prefix)

    if not files:
        log.warning(f"{plan.stream}: No Parquet files found at {s3_prefix}")
        return 0

    seen = 0

    for file_key in files:
        log.info(f"{plan.stream}: Processing file {file_key}")
        processed_record = None

        # Read Parquet file in batches
        for record in s3_client.read_parquet_file(file_key):
            # Convert any special types for proper serialization
            processed_record = _process_record(record=record)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=plan.stream, data=processed_record)
            seen += 1

            # Periodically checkpoint the state to save progress
            if seen % CHECKPOINT_EVERY_ROWS == 0:
                _checkpoint(state, plan.stream, replication_key, last_bookmark, processed_record)

        # Final checkpoint after each file
        _checkpoint(state, plan.stream, replication_key, last_bookmark, processed_record)
    return seen


def _process_record(record) -> Dict[str, Any]:
    """
    Process a record to ensure proper serialization of special types.
    Args:
        record: record from Parquet file
    Returns:
        Processed record with serializable values
    """
    processed = {}
    for key, value in record.items():
        if isinstance(value, (datetime, date)):
            processed[key] = value.isoformat()
        elif isinstance(value, bytes):
            processed[key] = value.decode("utf-8", errors="replace")
        else:
            processed[key] = value
    return processed


def sync_table_via_unload(
    connection,
    s3_client: S3Client,
    configuration: dict,
    plan: TablePlan,
    state: dict,
):
    """
    Sync a single table using UNLOAD to S3.
    Args:
        connection: Redshift connection object
        s3_client: S3Client instance
        configuration: Connector configuration
        plan: TablePlan instance
        state: Current sync state
    """
    # Execute UNLOAD to export data to S3
    s3_prefix = execute_unload(
        connection=connection,
        plan=plan,
        configuration=configuration,
        state=state,
    )

    # Read data from S3 and sync
    try:
        seen = sync_from_s3(
            s3_client=s3_client,
            plan=plan,
            s3_prefix=s3_prefix,
            state=state,
        )
        log.info(f"{plan.stream}: Sync complete, {seen} row(s) processed.")
    finally:
        # Clean up S3 files
        deleted = s3_client.delete_prefix(s3_prefix)
        log.info(f"{plan.stream}: Cleaned up {deleted} S3 file(s)")


def _run_plan_with_pool(
    plan: TablePlan,
    pool: _ConnectionPool,
    s3_client: S3Client,
    configuration: dict,
    state: dict,
) -> str:
    """
    Run a table plan using a connection from the pool.
    Args:
        plan: TablePlan instance
        pool: Connection pool
        s3_client: S3Client instance
        configuration: Connector configuration
        state: Current sync state
    Returns:
        Stream name that was synced
    """
    connection = pool.acquire()
    try:
        sync_table_via_unload(
            connection=connection,
            s3_client=s3_client,
            configuration=configuration,
            plan=plan,
            state=state,
        )
        return plan.stream
    finally:
        pool.release(connection)


def run_single_worker_sync(
    plans: List[TablePlan],
    s3_client: S3Client,
    configuration: dict,
    state: dict,
):
    """
    Run the sync for all table plans using a single connection.
    Args:
        plans: List of TablePlan instances
        s3_client: S3Client instance
        configuration: Connector configuration
        state: Current sync state
    """
    connection = connect_redshift(configuration=configuration)
    try:
        for plan in plans:
            sync_table_via_unload(
                connection=connection,
                s3_client=s3_client,
                configuration=configuration,
                plan=plan,
                state=state,
            )
            log.info(f"{plan.stream}: Sync finished.")
    finally:
        connection.close()
