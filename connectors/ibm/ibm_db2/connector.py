# This is a simple example for how to work with the fivetran_connector_sdk module.
# It defines an `update` method, which upserts data from an IBM DB2 database hosted on IBM Cloud.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import the ibm_db module for connecting to IBM DB2
# The ibm_db contains:
#   ibm_db driver: Python driver for IBM Db2 for LUW and IBM Db2 for z/OS databases.
#   Uses the IBM Data Server Driver for ODBC and CLI APIs to connect to IBM Db2 for LUW.
#   ibm_db_dbi: Python driver for IBM Db2 for LUW that complies to the DB-API 2.0 specification.
import ibm_db
import json
from datetime import datetime, timezone  # This is used for handling timestamps

# Set the checkpoint interval to 1000 rows
CHECKPOINT_INTERVAL = 1000


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    return [
        {
            "table": "employee",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "id": "INT",  # Contains a dictionary of column names and data types
                "first_name": "STRING",
                "last_name": "STRING",
                "email": "STRING",
                "department": "STRING",
                "hire_date": "NAIVE_DATE",
            },
            # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        }
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required fields.
    This function checks if the necessary parameters for connecting to the IBM DB2 database are present.
    If any required parameter is missing, it raises a ValueError with an appropriate message.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Check if the configuration dictionary has all the required keys
    required_keys = [
        "hostname",
        "port",
        "database",
        "user_id",
        "password",
        "schema_name",
        "table_name",
    ]
    for key in required_keys:
        if key not in configuration:
            raise ValueError(f"Missing required configuration key: {key}")


def create_connection_string(configuration: dict):
    """
    Create a connection string for the IBM DB2 database using the provided configuration dictionary.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        str: A formatted connection string for the IBM DB2 database.
    """
    # Extract the necessary parameters from the configuration dictionary
    hostname = configuration.get("hostname")
    port = configuration.get("port")
    database = configuration.get("database")
    user_id = configuration.get("user_id")
    password = configuration.get("password")

    # return the connection string
    return (
        f"DATABASE={database};"
        f"HOSTNAME={hostname};"
        f"PORT={port};"
        f"PROTOCOL=TCPIP;"
        f"UID={user_id};"
        f"PWD={password};"
        "SECURITY=SSL"  # This is required for secure connections to cloud IBM DB2 databases
    )


def connect_to_db(configuration: dict):
    """
    Connect to the IBM DB2 database using the provided configuration dictionary.
    This function uses the ibm_db module to establish a connection to the database.
    It creates a connection string using the create_connection_string function and attempts to connect.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        conn: A connection object if the connection is successful.
    """
    # Get the connection string
    conn_str = create_connection_string(configuration)

    # Connect to the database
    try:
        conn = ibm_db.connect(conn_str, "", "")
        log.info("Connected to database successfully!")
        return conn
    except Exception as e:
        log.error("Connection failed", e)
        raise RuntimeError("Connection failed") from e


def standardize_row_data(row):
    """
    Standardize the row data by converting all values to strings.
    This is useful for ensuring consistent data types when processing rows.
    Args:
        row: A dictionary representing a row of data fetched from the database.
    Returns:
        A new dictionary with all values converted to strings.
    """
    row_data = {}
    for key, value in row.items():
        key = key.lower()  # Convert key to lowercase for consistency
        if isinstance(value, int):
            row_data[key] = int(value)
        elif isinstance(value, float):
            row_data[key] = float(value)
        elif isinstance(value, str):
            row_data[key] = value
        elif value is None:
            row_data[key] = None
        else:
            row_data[key] = str(value)  # Convert other types to string

    return row_data


def fetch_and_upsert_data(conn, schema_name, table_name, last_hired):
    """
    Fetch data from the IBM DB2 database table and upsert the row to destination.
    This function executes a SQL query to retrieve rows from the specified table where the hire date is greater than the last hired date.
    It processes each row, standardizes the data, and performs an upsert operation for each row.
    Args:
        conn: A connection object to the IBM DB2 database.
        schema_name: The name of the schema in which the table resides.
        table_name: The name of the table from which to fetch data.
        last_hired: The date of the last hire, used to filter rows.
    """
    latest_hire = last_hired

    # Query to select rows with hire_date greater than the last hired date
    select_sql = f"SELECT ID, FIRST_NAME, LAST_NAME, EMAIL, DEPARTMENT, SALARY, HIRE_DATE FROM {schema_name}.{table_name} WHERE HIRE_DATE > '{latest_hire}' ORDER BY HIRE_DATE"
    statement = ibm_db.exec_immediate(conn, select_sql)

    if not statement:
        # If the statement execution fails, raise an exception
        raise RuntimeError(f"Failed to execute query: {select_sql}")

    row_count = 0
    latest_hire = parse_state_timestamp(timestamp_str=latest_hire)
    while True:
        # Fetch the record from the result set
        # The ibm_db.fetch_assoc method fetches the next row from the result set as a dictionary
        row = ibm_db.fetch_assoc(statement)
        # If no more rows are available, break the loop
        if not row:
            break

        # Standardize the row data and performs an upsert operation
        row_data = standardize_row_data(row)

        # The 'upsert' operation is used to insert or update the data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into, in this case, "employee".
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="employee", data=row_data)
        row_count += 1

        # Update the latest hire date if the current row's hire date is more recent
        if "hire_date" in row_data and row_data["hire_date"] > latest_hire:
            latest_hire = row_data["hire_date"]

        if row_count % CHECKPOINT_INTERVAL == 0:
            # Checkpoint operation every CHECKPOINT_INTERVAL rows
            new_state = {"last_hire_date": latest_hire.isoformat()}
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(new_state)

    log.info(f"Upserted {row_count} rows from {schema_name}.{table_name}.")

    # After processing all rows, a final checkpoint with the latest hire date
    new_state = {"last_hire_date": latest_hire.isoformat()}
    op.checkpoint(new_state)


def parse_state_timestamp(timestamp_str):
    """
    Parse the last_timestamp from the state dictionary.
    If the timestamp is not present or invalid, return a default datetime.
    Args:
        timestamp_str: A string representing the timestamp from the state dictionary.
    Returns:
        A datetime object representing the last processed timestamp.
    """
    if not timestamp_str:
        return datetime(1990, 1, 1, tzinfo=timezone.utc)
    try:
        # Handle possible 'Z'
        timestamp_str = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if timestamp_str.tzinfo is None:
            timestamp_str = timestamp_str.replace(tzinfo=timezone.utc)
        return timestamp_str
    except ValueError:
        return datetime(1990, 1, 1, tzinfo=timezone.utc)


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
    log.warning("Example: Source Examples: IBM DB2")

    # Validate the configuration dictionary to ensure it contains all required fields
    validate_configuration(configuration)

    # Connect to the IBM DB2 database
    conn = connect_to_db(configuration)

    # Load the state from the state dictionary
    last_hired = state.get("last_hire_date", "1990-01-01T00:00:00")

    # fetch data from the IBM DB2 database table and upsert the data to destination
    fetch_and_upsert_data(
        conn, configuration["schema_name"], configuration["table_name"], last_hired
    )

    # Close the database connection after the operation is complete
    if "conn" in locals() and conn:
        ibm_db.close(conn)
        log.info("Connection to IBM DB2 closed")


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)
