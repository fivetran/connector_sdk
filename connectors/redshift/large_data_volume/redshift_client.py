"""
This python file contains the Redshift client code for connecting to Redshift,
fetching metadata, building table plans, and performing data sync operations.
This includes handling both full and incremental syncs, applying projections,
and managing connection pooling for parallel execution.
"""

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

from dataclasses import dataclass  # For defining data classes
from typing import List, Dict, Optional  # For type hinting
from datetime import date, datetime  # For handling date and time
import redshift_connector  # Redshift database connector
from queue import Queue  # For connection pooling
from table_specs import (
    TABLE_SPECS,
    PREFERRED_TS_COLUMN_NAMES,
    TIMESTAMP_TYPE_NAMES,
    CHECKPOINT_EVERY_ROWS,
    CHUNK_SIZE,
)  # Table specifications and constants

# Global variable to hold the list of table plans used during the sync
__TABLE_PLAN_LIST = None

# Fivetran semantic type constants
__FIVETRAN_TYPE_NAIVE_DATE = "NAIVE_DATE"
__FIVETRAN_TYPE_NAIVE_DATETIME = "NAIVE_DATETIME"
__FIVETRAN_TYPE_UTC_DATETIME = "UTC_DATETIME"
__FIVETRAN_TYPE_JSON = "JSON"

# Mapping from Redshift data types to Fivetran semantic types
__REDSHIFT_TO_FIVETRAN_TYPE = {
    "date": __FIVETRAN_TYPE_NAIVE_DATE,
    "timestamp": __FIVETRAN_TYPE_NAIVE_DATETIME,
    "timestamp without time zone": __FIVETRAN_TYPE_NAIVE_DATETIME,
    "timestamp with time zone": __FIVETRAN_TYPE_UTC_DATETIME,
    "timestamptz": __FIVETRAN_TYPE_UTC_DATETIME,
    "super": __FIVETRAN_TYPE_JSON,
}

# Replication strategy constants
__STRATEGY_FULL = "FULL"
__STRATEGY_INCREMENTAL = "INCREMENTAL"


@dataclass
class TablePlan:
    """
    Dataclass to hold the plan for syncing a single table.
    Attributes:
        stream: str - Full stream name (schema.table)
        schema: str - Schema name
        table: str - Table name
        primary_keys: List[str] - List of primary key columns
        selected_columns: List[str] - List of columns to select
        explicit_columns: Dict[str, str] - Mapping of column names to explicit Fivetran semantic types
        strategy: str - Replication strategy ('FULL' or 'INCREMENTAL')
        replication_key: Optional[str] - Name of the replication key column, or None
        use_chunking: bool - Whether to use chunked cursor processing for this table (true) or not (false)
    """

    stream: str
    schema: str
    table: str
    primary_keys: List[str]
    selected_columns: List[str]
    explicit_columns: Dict[str, str]
    strategy: str
    replication_key: Optional[str]
    use_chunking: bool


class _ConnectionPool:
    """
    A simple connection pool for managing Redshift connections.
    This class maintains a pool of Redshift connections that can be reused across multiple threads.
    Attributes:
        size: int - Maximum number of connections in the pool
        configuration: dict - Configuration dictionary for connecting to Redshift
    """

    def __init__(self, size, configuration):
        log.info("Initializing Redshift connection pool for parallel sync")
        self._queue = Queue(maxsize=size)
        self._all = []
        for _ in range(size):
            # Create a new Redshift connection and add it to the pool
            conn = connect_redshift(configuration=configuration)
            self._all.append(conn)
            self._queue.put(conn)

    def acquire(self, timeout=None):
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
                log.error("Error closing connection", e)


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
        configuration: a dictionary that holds the configuration settings for the connector.
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


def _split_table(name, default_schema):
    """
    Split a table name into schema and table components.
    If no schema is provided, use the default_schema or 'public'.
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


def _get_config_bool(configuration, key):
    """
    Parse a boolean configuration value from the configuration dictionary.
    Configuration values are typically stored as strings, so this function
    handles the conversion to boolean.
    Args:
        configuration: dict with connector configuration
        key: the configuration key to look up
    Returns:
        Boolean value of the configuration setting
    """
    return configuration.get(key, "").lower() == "true"


def apply_projection(cols_with_types, include, exclude):
    """
    Apply the include/exclude projections to a list of available columns.
    If include is specified, only those columns are kept.
    If exclude is specified, those columns are removed.
    If both are specified, include is applied first, then exclude.
    If neither is specified, all available columns are kept.
    Args:
        cols_with_types: list of (column_name, data_type) tuples
        include: list of column names to include
        exclude: list of column names to exclude
    Returns:
        List of selected columns after applying projections
    """
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


def infer_replication_key(cols_with_types):
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
            replication_key = lower_columns[preferred]
            return replication_key
    # If no preferred names matched, return the first timestamp column found
    replication_key = timestamp_cols[0]
    # return the inferred replication key column name
    return replication_key


def detect_typed_columns(selected_cols_with_types):
    """
    Detect columns that require explicit typing based on their data types.
    This function looks for columns with specific data types (date, timestamp, timestamptz, super)
    and assigns them Fivetran semantic types for proper handling.
    Only columns that are in the selected list are considered.
    Uses __REDSHIFT_TO_FIVETRAN_TYPE mapping for type conversion.
    Args:
        selected_cols_with_types: list of (column_name, data_type) tuples for selected columns
    Returns:
        A dictionary mapping column names to their explicit Fivetran semantic types.
    """
    explicit = {}
    for column, datatype in selected_cols_with_types:
        data_type = (datatype or "").lower()
        if data_type in __REDSHIFT_TO_FIVETRAN_TYPE:
            explicit[column] = __REDSHIFT_TO_FIVETRAN_TYPE[data_type]
    return explicit


def build_select(redshift_schema, table, columns, replication_key, bookmark, upper_bound=None):
    """
    Build a parameterized SELECT SQL query for the given table and columns.
    If a replication_key and bookmark are provided, add a WHERE clause to filter rows.
    The query will always order by the replication_key if provided.
    This ensures data integrity and consistency during incremental syncs.
    Args:
        redshift_schema: schema name
        table: table name
        columns: list of column names to select
        replication_key: name of the replication key column, or None
        bookmark: last synced value of the replication key, or None
        upper_bound: optional upper bound for the replication_key (for chunking)
    Returns:
        A tuple of (sql_query, params) where sql_query is the parameterized SQL string
        and params is a list of parameters to bind to the query.
    """
    table_columns = list(columns)
    if replication_key and replication_key not in table_columns:
        table_columns.append(replication_key)

    cols_sql = ", ".join(f'"{column}"' for column in table_columns)
    sql = f'SELECT {cols_sql} FROM "{redshift_schema}"."{table}"'

    params = []
    where_conditions = []
    if replication_key and bookmark is not None:
        # If a bookmark is provided, add a WHERE clause to filter rows greater than the bookmark
        where_conditions.append(f'"{replication_key}" > %s')
        params.append(bookmark)
    if replication_key and upper_bound is not None:
        # If an upper bound is provided, add it to the WHERE clause for chunking
        where_conditions.append(f'"{replication_key}" <= %s')
        params.append(upper_bound)

    if where_conditions:
        sql += " WHERE " + " AND ".join(where_conditions)

    if replication_key:
        # Always order by the replication key to ensure consistent ordering and data integrity
        sql += f' ORDER BY "{replication_key}"'
    return sql, params


def _declare_cursor(cursor, table_cursor, sql_query, params):
    """
    Declare a server-side cursor for the given SQL query.
    This helper centralizes cursor declaration logic and ensures consistent logging.
    Args:
        cursor: database cursor object
        table_cursor: name for the cursor to be declared
        sql_query: SQL query string for the cursor
        params: query parameters to bind
    """
    cursor.execute("BEGIN")
    cursor.execute(f"DECLARE {table_cursor} NO SCROLL CURSOR FOR {sql_query}", params)
    log.info(f"Successfully declared cursor {table_cursor}")


def _find_chunk_upper_bound(connection, plan, replication_key, bookmark, chunk_size):
    """
    Find the replication_key value at approximately row chunk_size from the current bookmark.
    This provides a safe boundary to end the chunk, ensuring all rows with the boundary
    value are included in the same chunk (no data loss at boundaries).

    Args:
        connection: Redshift connection object
        plan: TablePlan dataclass instance with sync details
        replication_key: name of the replication key column
        bookmark: current bookmark value (last synced replication_key value)
        chunk_size: target number of rows per chunk

    Returns:
        The replication_key value at the chunk boundary, or None if no more rows exist.
    """
    # Build WHERE clause conditionally based on bookmark presence
    where_clause = f'WHERE "{replication_key}" > %s' if bookmark is not None else ""
    sql = f"""
        SELECT "{replication_key}"
        FROM "{plan.schema}"."{plan.table}"
        {where_clause}
        ORDER BY "{replication_key}"
        OFFSET %s LIMIT 1
    """
    params = [bookmark, chunk_size - 1] if bookmark is not None else [chunk_size - 1]

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None


def fetch_metadata(connection, table_tuples):
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


def fetch_schema_auto(connection, redshift_schema: str):
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
        ORDER BY 1,2;
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_tables, (redshift_schema,))
        # Build a list of (schema, table) tuples fetched from redshift information_schema
        # This is used when auto schema detection is enabled
        table_tuples = [(data[0], data[1]) for data in cursor.fetchall()]

    # Fetch the metadata for the discovered tables from Redshift
    metadata = fetch_metadata(connection=connection, table_tuples=table_tuples)
    return table_tuples, metadata


def _load_base_specs_and_metadata(connection, redshift_schema, auto_schema_detection):
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


def _determine_strategy_and_replication_key(spec, cols_with_types, enable_complete_resync):
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

    # Explicit FULL: never infer, ignore any provided replication key
    if strategy == __STRATEGY_FULL or enable_complete_resync:
        return __STRATEGY_FULL, None

    # Explicit INCREMENTAL: require a replication key (provided or inferred)
    if strategy == __STRATEGY_INCREMENTAL:
        replication_key = provided_replication_key or infer_replication_key(cols_with_types)
        if not replication_key:
            log.warning(f"{table_name}: no replication key found; falling back to FULL resync.")
            return __STRATEGY_FULL, None
        return __STRATEGY_INCREMENTAL, replication_key

    # Strategy not specified: infer behavior based on key presence/inference
    replication_key = provided_replication_key or infer_replication_key(cols_with_types)
    if replication_key:
        return __STRATEGY_INCREMENTAL, replication_key
    return __STRATEGY_FULL, None


def _build_plan(
    spec,
    table_schema,
    table,
    stream,
    table_metadata,
    selected_cols_with_types,
    enable_complete_resync,
    auto_schema_detection,
):
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
        auto_schema_detection: bool, if True, auto schema detection is enabled
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

    # Determine if chunking should be enabled for this table
    if auto_schema_detection:
        # For auto schema detection, use the global enable_chunking flag
        use_chunking = False
    else:
        # For manual schema, If the table spec has use_chunking defined, use that value
        use_chunking = spec.get("use_chunking", False)

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
        use_chunking=use_chunking,
    )
    return plan


def build_table_plans(connection, configuration):
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

        # Apply include/exclude projections to select columns
        selected_cols_with_types = apply_projection(
            cols_with_types=cols_with_types,
            include=spec.get("include") or None,
            exclude=spec.get("exclude") or None,
        )
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
            auto_schema_detection=auto_schema_detection,
        )
        plans.append(plan)

    log.info(f"Built table plans for {len(plans)} tables.")
    return plans


def _checkpoint(state, stream, replication_key, bookmark):
    """
    Update the state dictionary with the latest bookmark for a given stream and replication key.
    This function is called periodically during the sync process to save progress.
    Args:
        state: current state dictionary
        stream: name of the stream (table) being synced
        replication_key: name of the replication key column
        bookmark: latest value of the replication key
    """
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


def sync_table_chunked_cursors(connection, plan, state, bookmark, batch_size):
    """
    Sync a table using chunked cursors to avoid server side cursor memory limits.
    This function processes data in chunks by creating smaller cursors based on replication_key ranges.
    Each chunk is bounded by finding the replication_key value at approximately CHUNK_SIZE rows,
    ensuring all rows with the boundary value are included in the same chunk (no data loss).

    Args:
        connection: Redshift connection object
        plan: TablePlan dataclass instance with sync details
        state: current state dictionary
        bookmark: last synced value of the replication key
        batch_size: number of rows to fetch per batch
    """
    replication_key = plan.replication_key
    current_bookmark = bookmark
    total_seen = 0
    chunk_number = 0

    log.info(f"{plan.stream}: Using chunked cursors with target chunk size of {CHUNK_SIZE} rows")

    # Process data in chunks until all rows are synced
    while True:
        # Find the upper bound for this chunk (replication_key value at ~CHUNK_SIZE rows)
        upper_bound = _find_chunk_upper_bound(
            connection=connection,
            plan=plan,
            replication_key=replication_key,
            bookmark=current_bookmark,
            chunk_size=CHUNK_SIZE,
        )

        chunk_number += 1

        # Build query for this chunk
        # If upper_bound exists, use it to bound the chunk (inclusive)
        if upper_bound is not None:
            log.info(
                f"{plan.stream}: Processing chunk {chunk_number} "
                f"(bookmark: {current_bookmark}, upper_bound: {upper_bound})"
            )
            chunk_query, chunk_params = build_select(
                redshift_schema=plan.schema,
                table=plan.table,
                columns=plan.selected_columns,
                replication_key=replication_key,
                bookmark=current_bookmark,
                upper_bound=upper_bound,
            )
        else:
            # If upper_bound is None, there are fewer than CHUNK_SIZE rows remaining - process all of them
            log.info(
                f"{plan.stream}: Processing final chunk {chunk_number} "
                f"(bookmark: {current_bookmark}, no upper_bound - fetching all remaining rows)"
            )
            chunk_query, chunk_params = build_select(
                redshift_schema=plan.schema,
                table=plan.table,
                columns=plan.selected_columns,
                replication_key=replication_key,
                bookmark=current_bookmark,
            )

        with connection.cursor() as cursor:
            table_cursor = f"{plan.table}_chunk_{chunk_number}_cursor"
            _declare_cursor(cursor, table_cursor, chunk_query, chunk_params)

            # Upsert records in batches and update state with bookmarks
            # Column names are extracted from cursor.description after first FETCH
            state, chunk_last_bookmark, chunk_seen = upsert_record(
                cursor=cursor,
                plan=plan,
                state=state,
                replication_key=replication_key,
                last_bookmark=current_bookmark,
                batch_size=batch_size,
                seen=0,
                table_cursor=table_cursor,
            )
            cursor.execute("COMMIT")

            total_seen += chunk_seen

            # Update bookmark based on what was processed
            if upper_bound is not None:
                # Use upper_bound as bookmark (safe boundary - all rows with this value processed)
                current_bookmark = upper_bound
            else:
                # Final chunk - use the last bookmark from actual data processed
                current_bookmark = chunk_last_bookmark

            # Checkpoint after each chunk
            _checkpoint(state, plan.stream, replication_key, current_bookmark)

            log.info(
                f"{plan.stream}: Chunk {chunk_number} complete, {chunk_seen} row(s) processed"
            )

            # Exit conditions:
            # 1. This was the final chunk (no upper_bound) - we've processed all remaining rows
            # 2. No rows were processed in this chunk - no more data
            if upper_bound is None or chunk_seen == 0:
                break

    log.info(
        f"{plan.stream}: Chunked cursor sync complete, {total_seen} row(s) processed in {chunk_number} chunk(s)."
    )


def upsert_record(
    cursor,
    plan,
    state,
    replication_key,
    last_bookmark,
    batch_size,
    seen,
    table_cursor,
):
    """
    Upsert records from the cursor into the destination table based on the provided TablePlan.
    This function fetches rows in batches, forms record dictionaries, and performs upsert operations.
    It also updates the state with the latest bookmark for incremental syncs.
    Column names are extracted from cursor.description after the first FETCH, eliminating the need
    for a separate metadata query.
    Args:
        cursor: database cursor with executed query
        plan: TablePlan dataclass instance with sync details
        state: current state dictionary
        replication_key: name of the replication key column, or None
        last_bookmark: last synced value of the replication key, or None
        batch_size: number of rows to fetch per batch
        seen: count of rows processed so far
        table_cursor: name of the declared cursor in the database
    Returns:
        Updated state dictionary, last bookmark value, and total rows seen
    """
    column_names = None

    while True:
        # Fetch rows in batches to handle large datasets efficiently
        cursor.execute(f"FETCH {batch_size} FROM {table_cursor}")
        rows = cursor.fetchall()

        if not rows:
            # No more rows to fetch; exit the loop
            break

        # Extract column names from cursor.description after first FETCH
        if column_names is None:
            column_names = [desc[0] for desc in cursor.description]

        for row in rows:
            # Form a record dictionary mapping column names to their corresponding values
            record = dict(zip(column_names, row))
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=plan.stream, data=record)
            seen += 1

            if replication_key:
                # If replication key is defined, update the last bookmark
                replication_key_val = record.get(replication_key)
                if replication_key_val is not None:
                    last_bookmark = replication_key_val

            if seen % CHECKPOINT_EVERY_ROWS == 0:
                # Periodically checkpoint the state to save progress
                _checkpoint(state, plan.stream, replication_key, last_bookmark)

    cursor.execute(f"CLOSE {table_cursor}")
    return state, last_bookmark, seen


def sync_table_server_side_cursor(connection, replication_key, plan, state, bookmark, batch_size):
    """
    Sync a single table using server-side cursors.
    This function handles both full and incremental syncs, applying the appropriate logic based on the plan.
    It fetches data in batches, upserts records into the destination, and updates the state with bookmarks.
    Args:
        connection: Redshift connection object
        replication_key: name of the replication key column, or None
        plan: TablePlan dataclass instance with sync details
        state: current state dictionary
        bookmark: last synced value of the replication key
        batch_size: number of rows to fetch per batch
    """
    # Build the SQL query and parameters for the SELECT statement
    sql_query, params = build_select(
        redshift_schema=plan.schema,
        table=plan.table,
        columns=plan.selected_columns,
        replication_key=replication_key,
        bookmark=bookmark,
    )

    # Initialize counter to track number of rows processed
    seen = 0
    # Initialize last_bookmark to the current bookmark value
    last_bookmark = bookmark

    with connection.cursor() as cursor:
        # Declare the server-side cursor
        table_cursor = f"{plan.table}_cursor"
        _declare_cursor(cursor, table_cursor, sql_query, params)

        # Upsert records in batches and update state with bookmarks
        state, last_bookmark, seen = upsert_record(
            cursor=cursor,
            plan=plan,
            state=state,
            replication_key=replication_key,
            last_bookmark=last_bookmark,
            batch_size=batch_size,
            seen=seen,
            table_cursor=table_cursor,
        )

        # Commit the transaction
        cursor.execute("COMMIT")

    # Final checkpoint after completing the sync for the table
    _checkpoint(state, plan.stream, replication_key, last_bookmark)
    log.info(f"{plan.stream}: sync complete, {seen} row(s) processed.")


def sync_table(connection, configuration, plan, state):
    """
    Sync a single table based on the provided TablePlan.
    This function handles both full and incremental syncs, applying the appropriate logic based on the plan.
    It fetches data in batches, upserts records into the destination, and updates the state with bookmarks.
    Supports both standard and chunked cursor processing based on the plan configuration.
    Args:
        connection: Redshift connection object
        configuration: dict with connector configuration
        plan: TablePlan dataclass instance with sync details
        state: current state dictionary
    """
    replication_key = plan.replication_key
    prev_state = state.get(plan.stream) or {}
    bookmark = prev_state.get("bookmark") if replication_key else None
    batch_size = int(configuration["batch_size"])

    # Use the appropriate sync method based on whether chunking is enabled for the table
    if plan.use_chunking and replication_key:
        log.info(f"{plan.stream}: Using chunked cursor processing")
        sync_table_chunked_cursors(
            connection=connection,
            plan=plan,
            state=state,
            bookmark=bookmark,
            batch_size=batch_size,
        )
    else:
        log.info(f"{plan.stream}: Using server-side cursor processing")
        sync_table_server_side_cursor(
            connection=connection,
            replication_key=replication_key,
            plan=plan,
            state=state,
            bookmark=bookmark,
            batch_size=batch_size,
        )


def _run_plan_with_pool(plan, pool, configuration, state):
    """
    Run a table plan using a connection from the pool.
    This function acquires a connection from the pool, runs the sync for the given plan,
    and then releases the connection back to the pool.
    Args:
        plan: TablePlan dataclass instance with sync details
        pool: _ConnectionPool instance for managing Redshift connections
        configuration: dict with connector configuration
        state: current state dictionary
    Returns:
        The name of the stream (table) that was synced.
    """
    # Acquire a connection from the pool
    connection = pool.acquire()
    try:
        # Sync the table using the acquired connection
        sync_table(connection=connection, configuration=configuration, plan=plan, state=state)
        return plan.stream
    finally:
        # Release the connection back to the pool
        pool.release(connection)


def run_single_worker_sync(plans, configuration, state):
    """
    Run the sync for all table plans using a single connection.
    This function is used when max_parallel_workers is set to 1.
    Args:
        plans: List of TablePlan dataclass instances with sync details
        configuration: dict with connector configuration
        state: current state dictionary
    """
    # connect to Redshift using configuration parameters
    connection = connect_redshift(configuration=configuration)
    try:
        for plan in plans:
            # sync each table plan sequentially
            sync_table(connection=connection, configuration=configuration, plan=plan, state=state)
            log.info(f"{plan.stream}: sync finished.")
    finally:
        # Close the connection after all plans are processed
        connection.close()
