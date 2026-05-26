"""
This is a simple example for how to work with the fivetran_connector_sdk module.
This is an example to show how we can sync records from SQL Server Db via Connector SDK.
You would need to provide your SQL Server Db credentials for this example to work.
Also, you need the driver locally installed on your machine to make 'fivetran debug' work.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import the json module to handle JSON data.
import json

# Import datetime for handling date and time conversions.
from datetime import datetime

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import pyodbc which is used to connect with SQL Server Db
import pyodbc

# batch size to control how many records are processed in memory at a time during syncing
__BATCH_SIZE = 100
# checkpoint interval to control how often the state is checkpointed during syncing
__CHECKPOINT_INTERVAL = 1000


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "employee_details",  # Name of the table in the destination.
            "primary_key": ["employee_id"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "employee_id": "INT",  # INT column for employee_id.
                "hire_date": "NAIVE_DATE",  # NAIVE_DATE column for the hire_date.
                "salary": "LONG",
                "updated_time": "NAIVE_DATETIME",  # NAIVE_DATETIME column for the updated_time.
            },
        }
    ]


def connect_to_database(configuration):
    """
    Establishes a connection to the SQL Server database using the provided configuration.
    Args:
        configuration: A dictionary containing connection details
    Returns:
        A connection object if the connection is successful, or None if there is an error.
    """
    connection_string = (
        "DRIVER={" + configuration.get("driver") + "};"
        "SERVER={" + configuration.get("server") + "};"
        "DATABASE={" + configuration.get("database") + "};"
        "UID={" + configuration.get("user") + "};"
        "PWD={" + configuration.get("password") + "};"
    )

    try:
        # Establish connection
        connection = pyodbc.connect(connection_string)
        log.info("Connection established!")
        return connection
    except pyodbc.Error as e:
        log.error(f"Error connecting to database: {e}")
        raise e
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        raise e


def probe(connection):
    """
    Probes the database connection to ensure it is valid and can be used for syncing data.
    Args:
        connection: A connection object to the database
    """
    try:
        with connection.cursor() as cursor:
            # Execute a simple query to test the connection
            cursor.execute("SELECT 1")
            log.info("Database connection tested successfully")
    except pyodbc.Error as e:
        log.error(f"Error testing database connection: {e}")
        raise e
    except Exception as e:
        log.error(f"Unexpected error during testing database connection: {e}")
        raise e


def close_database_connection(connection):
    """
    Closes the database connection.
    Args:
        connection: The database connection object to be closed.
    """
    try:
        if connection is not None:
            connection.close()
        log.info("Connection closed")
    except Exception as e:
        log.error(f"Error closing database connection: {e}")
        raise e


def format_record_for_syncing(row):
    """
    Formats a database record (row) into a dictionary format suitable for syncing to the destination.
    You can modify this function to fit your needs
    Args:
        row: A tuple representing a record fetched from the database.
    Returns:
        A dictionary containing the formatted record ready for syncing.
    """
    return {
        "employee_id": row[0],  # Employee Id.
        "first_name": row[1],  # First Name.
        "last_name": row[2],  # Last Name.
        "hire_date": row[3],  # Hire Date.
        "salary": row[4],  # Salary.
        "updated_time": row[5],  # Updated time.
    }


def sync_data(connection, sql_query, last_query_date, state):
    """
    Executes the provided SQL query and syncs the data to the destination using upsert operations.
    You can modify this function to fit your needs
    Args:
        connection: A connection object to the database
        sql_query: The SQL query to execute for fetching data
        last_query_date: The timestamp of the last successful query execution, used for incremental syncing
        state: A dictionary containing state information from previous runs
    """
    max_query_date = last_query_date
    record_count = 0

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql_query)
            log.info("Query executed successfully. Syncing data")

            while True:
                # Fetch a batch of records.
                rows = cursor.fetchmany(__BATCH_SIZE)
                if not rows:
                    # Exit the loop when there are no more records.
                    break

                for row in rows:
                    upsert_record = format_record_for_syncing(row)
                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The first argument is the name of the destination table.
                    # The second argument is a dictionary containing the record to be upserted.
                    op.upsert(table="employee_details", data=upsert_record)

                    record_count += 1

                    if row[5] > max_query_date:
                        # Update max_query_date to the latest updated_time
                        max_query_date = row[5]

                    if record_count % __CHECKPOINT_INTERVAL == 0:
                        # checkpoint after every __CHECKPOINT_INTERVAL records
                        state["employee_details"] = max_query_date.isoformat()
                        op.checkpoint(state)

        return max_query_date

    except pyodbc.Error as e:
        log.error(f"Error executing query: {e}")
        raise e
    except Exception as e:
        log.error(f"Unexpected error during syncing data: {e}")
        raise e


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["driver", "server", "database", "user", "password"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


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
    log.warning("Example: Connectors - SQL Server")

    # Validate the configuration
    validate_configuration(configuration)

    # IMPORTANT: This connector requires the following prerequisites in your SQL server:
    # 1. A database named as specified in your configuration
    # 2. A table named 'employee_details' with the following schema:
    #    - employee_id (INT): Primary key
    #    - first_name (VARCHAR): First name of employee
    #    - last_name (VARCHAR): Last name of employee
    #    - hire_date (DATE): Date of hire
    #    - salary (INT): Employee salary
    #    - updated_time (DATETIME): Timestamp of the last update
    #
    # The table should be created with a statement similar to:
    # CREATE TABLE employee_details (
    #    employee_id INT IDENTITY(1,1) PRIMARY KEY,
    #    first_name NVARCHAR(50) NOT NULL,
    #    last_name NVARCHAR(50) NOT NULL,
    #    hire_date DATE NOT NULL,
    #    salary INT NOT NULL,
    #    updated_time DATETIME
    # );
    #
    # Make sure you have proper permissions to access this table
    # If these prerequisites are not met, the connector will not function correctly.

    last_query = state.get("employee_details", "1970-01-01T00:00:00")
    last_query_date = datetime.fromisoformat(last_query)

    # you can modify the query to fit your needs
    sql_query = f"SELECT * FROM employee_details WHERE updated_time > {last_query}"

    # Connect to the database using the provided configuration
    connection = connect_to_database(configuration)

    try:
        # Probe the database connection to ensure it is valid before attempting to sync data
        # This helps catch connection issues early and prevents unnecessary processing.
        probe(connection)

        # Sync the data by executing the SQL query and upserting the results to the destination.
        last_query_date = sync_data(connection, sql_query, last_query_date, state)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        state["employee_details"] = last_query_date.isoformat()
        op.checkpoint(state)

    finally:
        # Close the database connection after sync is complete.
        close_database_connection(connection)


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

# Resulting table:
# ┌───────────────┬─────────────┬─────────────┬─────────────┬───────────────┬─────────────────────┐
# │ employee_id   │ first_name  │ last_name   │ hire_date   │   salary      │     updated_time    │
# │      int      │   varchar   │   varchar   │    date     │     int       │       datetime      │
# ├───────────────┼─────────────┼─────────────┼─────────────┼───────────────┼─────────────────────┤
# │       1       │    John     │    Doe      │ 2020-05-15  │    55000      │ 2025-08-01 10:00:00 │
# │       2       │    Jane     │   Smith     │ 2018-03-22  │    62000      │ 2025-08-02 12:30:00 │
# │       3       │    Alice    │  Johnson    │ 2019-07-30  │    58000      │ 2025-08-03 09:45:00 │
# │       4       │     Bob     │   Brown     │ 2021-11-01  │    54000      │ 2025-08-04 14:20:00 │
# │       5       │   Charlie   │  Taylor     │ 2017-06-10  │    67000      │ 2025-08-05 16:10:00 │
# │       6       │    Diana    │  Wilson     │ 2022-01-20  │    51000      │ 2025-08-06 11:05:00 │
# │       7       │     Eve     │   Martin    │ 2015-12-15  │    75000      │ 2025-08-07 13:55:00 │
# │       8       │    Frank    │   Moore     │ 2023-04-05  │    52000      │ 2025-08-08 15:40:00 │
# │       9       │    Grace    │    Hall     │ 2020-09-14  │    60000      │ 2025-08-09 10:25:00 │
# │      10       │     Hank    │     Lee     │ 2021-03-18  │    53000      │ 2025-08-10 12:15:00 │
# └───────────────┴─────────────┴─────────────┴─────────────┴───────────────┴─────────────────────┘
