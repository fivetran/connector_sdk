# This is an example for how to work with the fivetran_connector_sdk module.
# It fetches the data from IBM Informix database using JayDeBeApi package and upserts it using Fivetran Connector SDK.
# It requires the Informix JDBC driver and BSON library to be installed in the environment using installation.sh script.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import json for handling JSON data
import json

# Import the JayDeBeApi library for connecting to the Informix database.
import jaydebeapi


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [
        {
            "table": "sample_table",
            "primary_key": ["id"],
            "columns": {"id": "STRING", "title": "STRING", "name": "STRING", "city": "STRING"},
        }
    ]


# This method sets up the connection to the Informix database using the JayDeBeApi library.
# It takes a configuration dictionary as an argument, which contains the necessary connection parameters.
# The function checks if the required keys are present in the configuration dictionary and raises a ValueError if any are missing.
# It then extracts the connection parameters from the configuration dictionary and attempts to establish a connection to the database.
def set_up_connection(configuration: dict):
    # Check if the configuration dictionary has all the required keys
    required_keys = [
        "hostname",
        "port",
        "database",
        "username",
        "password",
        "informix_server",
        "table_name",
    ]
    for key in required_keys:
        if key not in configuration:
            raise ValueError(f"Missing required configuration key: {key}")

    # Extract the configuration values
    database = configuration.get("database")
    informix_server = configuration.get("informix_server")
    host = configuration.get("hostname")
    user = configuration.get("username")
    password = configuration.get("password")
    port = int(configuration.get("port"))

    try:
        # Establish a connection to the Informix database using JayDeBeApi
        # The jar files for the Informix JDBC driver and BSON library are specified in the connection call.
        # installation.sh script is provided to install the required jar files.
        connection = jaydebeapi.connect(
            "com.informix.jdbc.IfxDriver",
            f"jdbc:informix-sqli://{host}:{port}/{database}:INFORMIXSERVER={informix_server}",
            [user, password],
            "/opt/informix/jdbc-15.0.0.1.1.jar:/opt/informix/bson-3.8.0.jar",
        )

        # return the connection object
        return connection
    except Exception as e:
        # In case of an error, log the error message and raise the exception
        log.error("Error establishing connection", e)
        raise e


# This method closes the cursor and connection objects to free up resources.
# It takes two parameters:
# - cursor: the cursor object used to execute SQL queries
# - connection: the connection object used to connect to the database
# The method checks if the cursor and connection objects are not None before attempting to close them.
def close_connection(cursor, connection):
    if cursor:
        try:
            cursor.close()
            log.info("Cursor closed and references cleared")
        except Exception as e:
            log.warning(f"Error closing cursor: {e}")

    if connection:
        try:
            connection.close()
            log.info("Connection closed and references cleared")
        except Exception as e:
            log.warning(f"Error closing connection: {e}")


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    log.info(
        "Example: Source Examples - Fetching data from IBM Informix database using JayDeBeApi"
    )

    # Initialize the connection and cursor variables to None
    connection = None
    cursor = None

    try:
        # Set up the connection to the Informix database using the provided configuration
        connection = set_up_connection(configuration)

        # get the cursor object from the connection
        # cursor is used to execute SQL queries and fetch results
        cursor = connection.cursor()
        # get the table name from the configuration
        table = configuration.get("table_name")

        # SQL query to fetch all rows from the specified table in configuration
        # You can modify this to adapt to your needs as per your requirements
        sql_query = f"SELECT * FROM {table}"
        cursor.execute(sql_query)

        # Map the column names to the values in each row
        # The data fetched from cursor is a list of tuples, where each tuple represents a row in the table
        # To convert it to a list of dictionaries, we use the cursor.description attribute to get the column names
        # This ensures that each row is represented as a dictionary with column names as keys, which can be upserted using the Fivetran Connector SDK
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for row in rows:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into, in this case, "sample_table".
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table="sample_table", data=row)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
    except Exception as e:
        # In case of an error, log the error message and raise the exception
        log.error("Error during update", e)
        raise e
    finally:
        # Ensure that the cursor and connection are closed properly in the finally block
        close_connection(cursor, connection)


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
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
