# This is a simple example for how to work with the fivetran_connector_sdk module.
# The code will retrieve data from tables in a Firebird DB, based on the tables defined in the schema.py file
# You will need to provide your own Firebird DB and credentials for this to work --> see configuration.json
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import modules for connection to Firebird and multi-threading
import firebirdsql
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from datetime import datetime, timedelta, date, timezone
import json
from schema import table_list

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
batch_process_size = 1000
batch_query_size = 10000
MAX_WORKERS = 10  # Adjust as needed


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    result = [
        {"table": table["table_name"], "primary_key": table["primary_key"]} for table in table_list
    ]
    return result


# Utilizes configuration.json credentials to establish connection to Firebird
def connect_to_firebird(configuration):
    # Connect to the Firebird database
    conn = firebirdsql.connect(
        host=configuration.get("host"),
        port=3050,
        database=configuration.get("database"),
        user=configuration.get("user"),
        password=configuration.get("password"),
    )

    # Create a cursor to interact with the database
    cursor = conn.cursor()
    return cursor, conn


# Generate query for Firebird table and return a list of N(batch_size) records as list of dictionaries
# This function is called by the process_table() functions and takes in four parameters
# - table_name: Name of the table to query
# - incremental_column: High watermark column to paginate through tables via filtering
# - table_cursor_value: Current value of the incremental_column to filter on
# - batch_size: Number of records to retrieve
# And returns one object:
# - query: Query to execute on Firebird
def get_query(table_name, incremental_column, table_cursor_value, batch_size):
    if not table_cursor_value:
        query = f"SELECT FIRST {batch_size} * FROM {table_name} order by {incremental_column} asc;"
    else:
        query = f"select FIRST {batch_size} * from {table_name} where {incremental_column} >= '{table_cursor_value}' order by {incremental_column} asc"
    log.info(query)
    return query


# Helper function to convert datetimes to strings
def dt2str(incoming: datetime) -> str:
    if isinstance(incoming, (datetime, date)):
        return incoming.strftime(TIMESTAMP_FORMAT)
    else:
        return incoming


state_lock = threading.Lock()  # guards the shared checkpoint dict


# Retrieve and process all data from a Firebird table
# Function takes in size inputs:
# - configuration: configuration.json variables to connect to Firebird
# - table: Name of table to query
# - state: state dictionary to determine cursor value to filter on
# - shared_timestamps: dictionary that is updated each query to maintain state
# - batch_size: Number of records to query each query
# - batch_fetch: Number of records to process each upsert invocation
def process_table(
    configuration, table, state, shared_timestamps: dict, batch_size: int, batch_fetch: int
):

    cursor, conn = connect_to_firebird(configuration)
    try:
        name = table["table_name"]
        incr_col = table["incremental_column"]
        cursor_key = f"{name}_cursor"
        last_value = state.get(cursor_key)  # resume here
        batch_no = 0

        while True:
            query = get_query(name, incr_col, last_value, batch_size)
            cursor.execute(query)
            cols = [d[0] for d in cursor.description]
            batch_no += 1
            log.info(f"[{name}] batch #{batch_no} ({batch_size} rows/query)")

            rows = cursor.fetchmany(batch_fetch)
            if not rows:
                break

            while rows:
                # ── stream this chunk ──────────────────────────
                for row in rows:
                    rec = {c: dt2str(v) for c, v in zip(cols, row)}
                    last_value = rec[incr_col]  # advance cursor
                    op.upsert(name.replace(".", "_"), rec)

                # ── checkpoint right after a successful chunk ──
                with state_lock:
                    shared_timestamps[cursor_key] = last_value
                    op.checkpoint(dict(shared_timestamps))  # copy!

                # stop early if short chunk (end of data)
                if len(rows) < batch_fetch:
                    rows = []
                else:
                    rows = cursor.fetchmany(batch_fetch)

            # finished this query; stop if we didn’t fill it
            if cursor.rowcount < batch_size:
                break

    finally:
        cursor.close()
        conn.close()


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    shared_timestamps = dict(state)  # start from prior state
    done = []
    end_all = threading.Event()  # flipped when all threads done

    def worker(tbl):
        try:
            process_table(
                configuration, tbl, state, shared_timestamps, batch_query_size, batch_process_size
            )
        except Exception as exc:
            log.error(f"[{tbl['table_name']}] thread error: {exc}")
        finally:
            done.append(tbl["table_name"])
            if len(done) == len(table_list):
                end_all.set()  # last thread finished

    # launch threads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for tbl in table_list:
            pool.submit(worker, tbl)

        # main loop: stream queue until everything done
        while not end_all.is_set():
            continue


# Instantiate the Connector object
connector = Connector(update=update, schema=schema)

# Entry point for running the connector
if __name__ == "__main__":
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    connector.debug(configuration=configuration)
