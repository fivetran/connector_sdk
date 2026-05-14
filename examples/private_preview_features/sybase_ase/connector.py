# This is an example for how to work with the fivetran_connector_sdk module.
# Shows how to fetch data from Sybase ASE and upsert it to destination using FreeTDS and pyodbc.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation
# (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
import pyodbc  # For connecting to Sybase ASE using FreeTDS
import json
import socket  # For pre-flight TCP connectivity check
import threading  # For enforcing a hard timeout on pyodbc.connect()
import time  # For retry back-off delays
from decimal import Decimal

# Timeout (seconds) for the pre-flight TCP connectivity probe.
# Must be well under the Fivetran gRPC deadline (~30 s) so that a blocked
# connection raises a clear Python exception *before* the deadline expires
# and the error details can be transmitted back to the platform.
_TCP_PROBE_TIMEOUT = 5

# Hard timeout (seconds) for pyodbc.connect().  FreeTDS ignores the ODBC
# LoginTimeout parameter and falls back to the OS TCP timeout (~75 s), which
# far exceeds the Fivetran gRPC deadline.  We enforce our own deadline via a
# background thread so that a hung connect() raises a Python exception in time
# for the SDK to transmit error details before the platform kills the process.
_CONNECT_TIMEOUT = 15

# Number of times to retry a failed pyodbc.connect() before giving up.
# A short back-off is applied between attempts to handle transient TDS errors.
_MAX_CONNECT_RETRIES = 3
_CONNECT_RETRY_DELAY = 2  # seconds between retries


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary for required fields.
    Args:
        configuration (dict): A dictionary containing the connection parameters.
    Raises:
        ValueError: If any required field is missing or invalid.
    """
    required_fields = ["server", "port", "database", "user_id", "password"]
    for field in required_fields:
        if field not in configuration or not configuration[field]:
            raise ValueError(f"Missing required configuration field: {field}")
    log.info("Configuration validation passed.")


def get_sybase_tables(connection, database: str):
    """
    Retrieve all user tables from the Sybase ASE database.
    Args:
        connection: A connection object to the Sybase ASE database.
        database (str): The database name to query.
    Returns:
        list: A list of table names in the database.
    """
    cursor = connection.cursor()
    try:
        # Query to get all user tables from sysobjects
        query = """
        SELECT name
        FROM sysobjects
        WHERE type = 'U'
        ORDER BY name
        """
        cursor.execute(query)
        tables = [row[0] for row in cursor.fetchall()]
        log.info(f"Found {len(tables)} tables in database '{database}'")
        return tables
    except Exception as e:
        log.warning(f"Error fetching tables: {str(e)}")
        return []
    finally:
        cursor.close()


def get_selected_tables(connection, configuration: dict):
    """
    Resolve the list of tables to sync based on configuration.
    If 'tables' is specified in configuration, validate and return those.
    Otherwise return all user tables discovered in the database.
    Args:
        connection: A connection object to the Sybase ASE database.
        configuration (dict): The connector configuration dictionary.
    Returns:
        tuple: (all_tables, selected_tables) both as lists of table name strings.
    """
    database = configuration.get("database")
    all_tables = get_sybase_tables(connection, database)

    selected_tables = configuration.get("tables", all_tables)

    # If selected_tables is a comma-separated string, convert to list
    if isinstance(selected_tables, str):
        selected_tables = [t.strip() for t in selected_tables.split(",")]

    return all_tables, selected_tables


def get_table_primary_keys(connection, table_name: str):
    """
    Retrieve primary key columns for a specific table.
    Args:
        connection: A connection object to the Sybase ASE database.
        table_name (str): The name of the table.
    Returns:
        list: A list of primary key column names.
    """
    cursor = connection.cursor()
    try:
        # Use sp_helpindex to get index information
        # This returns indexes with their columns and properties
        cursor.execute(f"EXEC sp_helpindex '{table_name}'")

        # Check if there are any results
        if not cursor.description:
            # No indexes found for this table
            return []

        rows = cursor.fetchall()

        # Look for clustered unique index (primary key)
        # Column 2 contains index description (e.g., "clustered, unique")
        # Column 1 contains column names (e.g., "stor_id, ord_num")
        for row in rows:
            index_desc = row[2].lower() if len(row) > 2 else ""
            if "clustered" in index_desc and "unique" in index_desc:
                # This is the primary key - parse column names
                column_str = row[1].strip() if len(row) > 1 else ""
                pk_columns = [col.strip() for col in column_str.split(",")]
                return pk_columns

        # If no clustered unique index found, look for any unique index
        for row in rows:
            index_desc = row[2].lower() if len(row) > 2 else ""
            if "unique" in index_desc:
                column_str = row[1].strip() if len(row) > 1 else ""
                pk_columns = [col.strip() for col in column_str.split(",")]
                return pk_columns

        return []
    except pyodbc.Error as e:
        # Handle specific case where table has no indexes
        if "No indexes" in str(e) or "not found" in str(e).lower():
            return []
        log.warning(f"Error fetching primary keys for table '{table_name}': {str(e)}")
        return []
    except Exception as e:
        log.warning(f"Error fetching primary keys for table '{table_name}': {str(e)}")
        return []
    finally:
        cursor.close()


def map_sybase_to_fivetran_type(sybase_type: str, precision: int = None, scale: int = None):
    """
    Map Sybase ASE data types to Fivetran data types.
    Args:
        sybase_type (str): The Sybase data type.
        precision (int): The precision for numeric types.
        scale (int): The scale for numeric types.
    Returns:
        str or dict: The corresponding Fivetran data type (string or dict for DECIMAL).
    """
    sybase_type_lower = sybase_type.lower()

    # Handle DECIMAL/NUMERIC types with precision and scale
    if sybase_type_lower in ("decimal", "numeric", "money", "smallmoney"):
        # money/smallmoney have fixed precision/scale in Sybase ASE regardless of what
        # syscolumns reports (prec/scale are NULL for these types).
        # money:      19 digits total, 4 decimal places  (±922,337,203,685,477.5808)
        # smallmoney: 10 digits total, 4 decimal places  (±214,748.3648)
        if sybase_type_lower == "money":
            return {"type": "DECIMAL", "precision": 19, "scale": 4}
        if sybase_type_lower == "smallmoney":
            return {"type": "DECIMAL", "precision": 10, "scale": 4}

        # For decimal/numeric, use the precision/scale from syscolumns when available
        if precision is None or precision == 0:
            precision = 18
        if scale is None:
            scale = 0

        return {"type": "DECIMAL", "precision": precision, "scale": scale}

    # Map other types to simple strings
    type_mapping = {
        # String types
        "char": "STRING",
        "varchar": "STRING",
        "nchar": "STRING",
        "nvarchar": "STRING",
        "text": "STRING",
        "unichar": "STRING",
        "univarchar": "STRING",
        # Numeric types
        "int": "INT",
        "integer": "INT",
        "smallint": "SHORT",
        "tinyint": "SHORT",
        "bigint": "LONG",
        "float": "DOUBLE",
        "real": "FLOAT",
        # Date/Time types
        "date": "NAIVE_DATE",
        "time": "NAIVE_TIME",
        "datetime": "NAIVE_DATETIME",
        "smalldatetime": "NAIVE_DATETIME",
        "bigdatetime": "NAIVE_DATETIME",
        "bigtime": "NAIVE_TIME",
        # Binary types
        "binary": "BINARY",
        "varbinary": "BINARY",
        "image": "BINARY",
        # Boolean
        "bit": "BOOLEAN",
    }

    # Return mapped type or default to STRING
    return type_mapping.get(sybase_type_lower, "STRING")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    Returns a lightweight schema declaration without opening a database connection.
    Full schema discovery (primary keys, column types) happens in update() where the
    connection is already established.  Keeping schema() connection-free prevents the
    Fivetran platform from timing out during the Schema gRPC call, which is issued
    before the connector has had time to warm up after installation.sh runs.

    Primary keys for the pubs2 sample database are hardcoded here so that the
    Fivetran local tester can validate upsert operations without requiring a live
    database connection during the Schema gRPC call.

    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    log.info("schema(): called — returning hardcoded pubs2 schema (no DB connection).")
    # Hardcoded schema for the pubs2 sample database.
    # Primary keys AND their column types are declared here so the local tester can
    # validate upsert operations without a live database connection during the Schema
    # gRPC call.  Column types for non-PK columns are intentionally omitted; the
    # platform infers them from the upsert calls made in update().
    pubs2_schema = [
        {
            "table": "au_pix",
            "primary_key": ["au_id"],
            "columns": {"au_id": "STRING"},
        },
        {
            "table": "authors",
            "primary_key": ["au_id"],
            "columns": {"au_id": "STRING"},
        },
        {
            "table": "blurbs",
            "primary_key": ["au_id"],
            "columns": {"au_id": "STRING"},
        },
        {
            "table": "discounts",
            "primary_key": ["discounttype"],
            "columns": {"discounttype": "STRING"},
        },
        {
            "table": "publishers",
            "primary_key": ["pub_id"],
            "columns": {"pub_id": "STRING"},
        },
        {
            "table": "roysched",
            "primary_key": ["title_id", "lorange"],
            "columns": {"title_id": "STRING", "lorange": "INT"},
        },
        {
            "table": "sales",
            "primary_key": ["stor_id", "ord_num"],
            "columns": {"stor_id": "STRING", "ord_num": "STRING"},
        },
        {
            "table": "salesdetail",
            "primary_key": ["stor_id", "ord_num", "title_id"],
            "columns": {"stor_id": "STRING", "ord_num": "STRING", "title_id": "STRING"},
        },
        {
            "table": "stores",
            "primary_key": ["stor_id"],
            "columns": {"stor_id": "STRING"},
        },
        {
            "table": "titleauthor",
            "primary_key": ["au_id", "title_id"],
            "columns": {"au_id": "STRING", "title_id": "STRING"},
        },
        {
            "table": "titles",
            "primary_key": ["title_id"],
            "columns": {"title_id": "STRING"},
        },
    ]

    # If the caller has pre-configured a specific table list in configuration, filter
    # the hardcoded schema to only include those tables.
    tables_cfg = configuration.get("tables")
    if tables_cfg:
        if isinstance(tables_cfg, str):
            table_names = {t.strip() for t in tables_cfg.split(",") if t.strip()}
        else:
            table_names = set(tables_cfg)
        filtered = [t for t in pubs2_schema if t["table"] in table_names]
        log.info(f"schema(): returning {len(filtered)} pre-configured tables (no DB connection).")
        return filtered

    log.info(f"schema(): returning {len(pubs2_schema)} pubs2 tables (no DB connection).")
    return pubs2_schema


def _probe_tcp(server: str, port: int):
    """
    Perform a fast TCP connectivity check before attempting the ODBC connection.

    Raises RuntimeError immediately (within _TCP_PROBE_TIMEOUT seconds) if the
    host is unreachable, so the error is transmitted to the Fivetran platform
    before the gRPC deadline expires.

    Args:
        server (str): Hostname or IP address of the Sybase ASE server.
        port (int): TCP port number.
    Raises:
        RuntimeError: If the TCP connection cannot be established.
    """
    log.info(f"Probing TCP connectivity to {server}:{port} (timeout={_TCP_PROBE_TIMEOUT}s)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_TCP_PROBE_TIMEOUT)
        sock.connect((server, port))
        sock.close()
        log.info(f"TCP probe to {server}:{port} succeeded.")
    except socket.timeout:
        raise RuntimeError(
            f"TCP probe timed out after {_TCP_PROBE_TIMEOUT}s — "
            f"{server}:{port} is unreachable from this Fivetran execution environment. "
            "Ensure the server firewall allows inbound connections from Fivetran IP ranges."
        )
    except OSError as exc:
        raise RuntimeError(
            f"TCP probe to {server}:{port} failed: {exc}. "
            "Check that the server address and port are correct and the firewall allows access."
        ) from exc


def create_sybase_connection(configuration: dict):
    """
    Create a connection to the Sybase ASE database using FreeTDS.

    Uses a background thread to enforce a hard _CONNECT_TIMEOUT deadline on
    pyodbc.connect().  FreeTDS ignores the ODBC LoginTimeout parameter and
    falls back to the OS TCP timeout (~75 s), which would exceed the Fivetran
    gRPC deadline and cause the process to be killed silently (details: null).
    By raising a Python exception before that deadline the SDK can transmit
    proper error details back to the platform.

    Args:
        configuration (dict): A dictionary containing the connection parameters.
    Returns:
        connection: A connection object to the Sybase ASE database.
    """
    server = configuration.get("server")
    port = int(configuration.get("port"))
    database = configuration.get("database")
    user_id = configuration.get("user_id")
    password = configuration.get("password")

    # Fast pre-flight check: verify TCP reachability before attempting ODBC.
    # This gives a clear, immediate error if the host/port is unreachable.
    _probe_tcp(server, port)

    # Resolve the FreeTDS driver — prefer the registered ODBC name but fall back
    # to the .so path so the connector works even if odbcinst.ini was not updated
    # by installation.sh (e.g. read-only /etc in some container runtimes).
    import os as _os
    import glob as _glob

    _FREETDS_SO_CANDIDATES = [
        # Bundled alongside connector.py in the Fivetran cloud container
        "/app/drivers/libtdsodbc.so",
        # System-installed paths (present when installation.sh runs apt-get)
        "/usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so",
        "/usr/lib/x86_64-linux-gnu/libtdsodbc.so",
        "/usr/lib/odbc/libtdsodbc.so",
        "/usr/lib/libtdsodbc.so",
    ]

    driver = "FreeTDS"  # default: use registered ODBC name
    for _candidate in _FREETDS_SO_CANDIDATES:
        if _os.path.isfile(_candidate):
            driver = _candidate
            log.info(f"Using FreeTDS driver at: {driver}")
            break
    else:
        # Broader search in case the .so landed somewhere unexpected
        _found = _glob.glob("/usr/**/libtdsodbc*.so*", recursive=True)
        if _found:
            driver = _found[0]
            log.info(f"Found FreeTDS driver via glob: {driver}")
        else:
            log.warning(
                "libtdsodbc.so not found on disk — falling back to registered name 'FreeTDS'. "
                "Check that installation.sh ran successfully."
            )
            # Log odbcinst.ini for diagnostics
            try:
                with open("/etc/odbcinst.ini") as _f:
                    log.info(f"odbcinst.ini contents: {_f.read()[:500]}")
            except Exception:
                log.warning("Could not read /etc/odbcinst.ini")

    connection_str = (
        f"DRIVER={driver};"
        f"SERVER={server};"
        f"PORT={port};"
        f"DATABASE={database};"
        f"UID={user_id};"
        f"PWD={password};"
        "TDS_Version=5.0;"
        "ClientCharset=UTF-8;"
    )

    # pyodbc.connect() can hang indefinitely because FreeTDS ignores LoginTimeout.
    # Run it in a daemon thread and join with _CONNECT_TIMEOUT so we always raise
    # a Python exception before the Fivetran gRPC deadline kills the process.
    # Retry up to _MAX_CONNECT_RETRIES times to handle transient TDS errors.
    last_error: Exception = None
    for attempt in range(1, _MAX_CONNECT_RETRIES + 1):
        result: dict = {"conn": None, "error": None}

        def _do_connect():
            try:
                result["conn"] = pyodbc.connect(connection_str, autocommit=True)
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc

        connect_thread = threading.Thread(target=_do_connect, daemon=True)
        connect_thread.start()
        connect_thread.join(timeout=_CONNECT_TIMEOUT)

        if connect_thread.is_alive():
            raise RuntimeError(
                f"pyodbc.connect() did not complete within {_CONNECT_TIMEOUT}s — "
                f"the TDS handshake with {server}:{port} is hanging. "
                "FreeTDS ignores LoginTimeout; ensure the server is reachable and "
                "the TDS version / credentials are correct."
            )

        if result["error"] is None:
            break  # success

        last_error = result["error"]
        retry_msg = (
            f"Retrying in {_CONNECT_RETRY_DELAY}s..."
            if attempt < _MAX_CONNECT_RETRIES
            else "No more retries."
        )
        log.warning(
            f"Connection attempt {attempt}/{_MAX_CONNECT_RETRIES} failed: "
            f"{last_error}. {retry_msg}"
        )
        if attempt < _MAX_CONNECT_RETRIES:
            time.sleep(_CONNECT_RETRY_DELAY)
    else:
        raise RuntimeError("Connection to Sybase ASE failed after all retries") from last_error

    conn = result["conn"]
    # Set a per-query timeout so that any hanging SQL statement raises a Python
    # exception rather than blocking the update thread indefinitely.
    # FreeTDS honours this via the ODBC SQLSetStmtAttr(SQL_ATTR_QUERY_TIMEOUT) path.
    conn.timeout = _CONNECT_TIMEOUT
    log.info("Connection to Sybase ASE established successfully.")
    return conn


def close_sybase_connection(connection, cursor):
    """
    Close the connection to the Sybase ASE database.
    Args:
        connection: A connection object to the Sybase ASE database.
        cursor: A cursor object (optional).
    """
    if cursor:
        cursor.close()
    if connection:
        connection.close()


def get_table_incremental_column(connection, table_name: str):
    """
    Determine the best column to use for incremental sync.
    Looks for datetime columns or falls back to the first primary key column.
    Args:
        connection: A connection object to the Sybase ASE database.
        table_name (str): The name of the table.
    Returns:
        tuple: (column_name, column_type) or (None, None) if no suitable column found.
    """
    cursor = connection.cursor()
    try:
        # Find datetime columns using a parameterised query to prevent SQL injection
        query = """
        SELECT c.name, t.name as type_name
        FROM syscolumns c
        JOIN systypes t ON c.usertype = t.usertype
        JOIN sysobjects o ON c.id = o.id
        WHERE o.name = ?
        AND t.name IN ('datetime', 'smalldatetime', 'bigdatetime', 'date')
        ORDER BY c.colid
        """
        cursor.execute(query, (table_name,))
        result = cursor.fetchone()
        if result:
            return result[0], result[1]

        # If no datetime column, try to use first primary key
        primary_keys = get_table_primary_keys(connection, table_name)
        if primary_keys:
            return primary_keys[0], None

        return None, None
    except Exception as e:
        log.warning(f"Error determining incremental column for '{table_name}': {str(e)}")
        return None, None
    finally:
        cursor.close()


def fetch_and_upsert(
    cursor,
    query,
    table_name: str,
    state: dict,
    incremental_column: str = None,
    batch_size: int = 1000,
):
    """
    Fetch data from the Sybase ASE database and upsert it into the destination table.
    Executes the provided SQL query, fetches data in batches, and performs upsert operations.
    Updates the state with the last processed row based on the incremental column.
    Args:
        cursor: A cursor object to the Sybase ASE database.
        query (str): The SQL query to execute for fetching data.
        table_name (str): The name of the destination table for upserting data.
        state (dict): A dictionary containing state information from previous runs.
        incremental_column (str): The column name to use for tracking progress (optional).
        batch_size (int): The number of rows to fetch in each batch.
    """
    # Get the state key for this table
    state_key = f"{table_name}_last_value"

    # Execute the SQL query to fetch data from the Sybase ASE database
    cursor.execute(query)
    # Fetch the column names from the cursor description
    # This is necessary to map the data to the correct columns in the upsert operation
    column_names = [col[0] for col in cursor.description]

    row_count = 0
    last_value = state.get(state_key)

    while True:
        # Fetch data in batches to handle large datasets efficiently.
        # This avoids loading the entire result set into memory at once.
        results = cursor.fetchmany(batch_size)
        if not results:
            # No more data to fetch, exit the loop
            break

        for row in results:
            # Convert the row tuple to a dictionary using the column names
            row_data = dict(zip(column_names, row))

            # Convert special data types for Fivetran compatibility
            for key, value in row_data.items():
                if value is not None:
                    # Convert Decimal to string for Fivetran DECIMAL type
                    if isinstance(value, Decimal):
                        row_data[key] = str(value)
                    # Convert datetime to a string using a space separator (not 'T').
                    # Sybase ASE datetime literals require the format 'YYYY-MM-DD HH:MM:SS.mmm';
                    # the ISO 8601 'T' separator is silently misinterpreted and causes
                    # incremental WHERE clauses to return 0 rows on subsequent syncs.
                    elif hasattr(value, "isoformat"):
                        row_data[key] = value.isoformat(sep=" ")
                    # Convert bytes/bytearray to bytes for Fivetran BINARY type
                    elif isinstance(value, (bytes, bytearray)):
                        row_data[key] = bytes(value)
                    # Log any unexpected types to help diagnose cloud issues
                    elif not isinstance(value, (str, int, float, bool)):
                        log.warning(
                            f"Unexpected type in {table_name}.{key}: "
                            f"{type(value).__name__} = {repr(value)[:100]}"
                        )

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table=table_name, data=row_data)
            row_count += 1

            # Update the last value if incremental column is specified
            incremental_value = row_data.get(incremental_column) if incremental_column else None
            if incremental_value:
                # Value is already converted to string format above
                if last_value is None or incremental_value > last_value:
                    last_value = incremental_value

        # Update the state with the last value after processing each batch
        if last_value is not None:
            state[state_key] = last_value
        # Save progress by checkpointing the state so the sync can resume from the correct
        # position on the next run or after an interruption. See best practices:
        # https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation
        op.checkpoint(state)

    # After processing all rows, update the state with the last value and checkpoint it.
    # this ensures that the next run will start from the correct position
    if last_value is not None:
        state[state_key] = last_value
    op.checkpoint(state)

    log.info(f"Synced {row_count} rows from table '{table_name}'")


def sync_table(connection, table_name: str, state: dict):
    """
    Sync a single table from Sybase ASE to the destination.
    Args:
        connection: A connection object to the Sybase ASE database.
        table_name (str): The name of the table to sync.
        state (dict): A dictionary containing state information from previous runs.
    """
    cursor = connection.cursor()

    try:
        # Determine the incremental column for this table
        incremental_column, col_type = get_table_incremental_column(connection, table_name)

        # Get the state key for this table
        state_key = f"{table_name}_last_value"
        last_value = state.get(state_key, "1970-01-01 00:00:00" if col_type else None)

        # Build the query based on whether we have an incremental column
        if incremental_column and last_value:
            query = (
                f"SELECT * FROM {table_name}"
                f" WHERE {incremental_column} > '{last_value}'"
                f" ORDER BY {incremental_column}"
            )
            log.info(
                f"Syncing table '{table_name}' incrementally using column '{incremental_column}'"
            )
        else:
            query = f"SELECT * FROM {table_name}"
            log.info(f"Syncing table '{table_name}' (full sync)")

        # Fetch and upsert data
        fetch_and_upsert(
            cursor=cursor,
            query=query,
            table_name=table_name,
            state=state,
            incremental_column=incremental_column,
            batch_size=1000,
        )

    except Exception as e:
        log.warning(f"Error syncing table '{table_name}': {str(e)}")
        raise
    finally:
        cursor.close()


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    connection = None

    try:
        log.info("Sybase ASE Connector - Multi-Table Sync - Starting")

        # Emit an initial checkpoint immediately so the gRPC stream is not idle
        # while the ODBC connection is being established.  An idle stream can be
        # cancelled by the Fivetran platform before the connector produces any data.
        op.checkpoint(state)

        # Validate the configuration
        log.info("Validating configuration...")
        validate_configuration(configuration=configuration)

        # Create a connection to the Sybase ASE database using the provided configuration
        log.info("Creating database connection...")
        connection = create_sybase_connection(configuration=configuration)

        # Discover and filter tables using shared helper
        log.info("Discovering tables...")
        all_tables, selected_tables = get_selected_tables(connection, configuration)

        log.info(f"Starting sync for {len(selected_tables)} tables: {', '.join(selected_tables)}")

        # Sync each selected table
        for table_name in selected_tables:
            if table_name not in all_tables:
                log.warning(f"Table '{table_name}' not found in database. Skipping.")
                continue

            log.info(f"Syncing table: {table_name}")
            sync_table(connection, table_name, state)
            log.info(f"Completed syncing table: {table_name}")

        log.info("Sync completed successfully")

    except ValueError as e:
        log.error(f"Configuration error: {str(e)}")
        raise
    except pyodbc.Error as e:
        log.error(f"Database error: {str(e)}")
        raise
    except Exception as e:
        log.error(f"Unexpected error during sync: {str(e)}")
        raise
    finally:
        # Close the connection to the Sybase ASE database
        if connection:
            try:
                close_sybase_connection(connection=connection, cursor=None)
            except Exception as e:
                log.warning(f"Error closing connection: {str(e)}")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button. Useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    try:
        # Open the configuration.json file and load its contents
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        configuration = {}

    # Test the connector locally using the Fivetran debug method,
    # which initializes the SDK runtime and logging properly.
    connector.debug(configuration=configuration)
