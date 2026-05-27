# Importing External Drivers using installation.sh script file.
import datetime

# This module implements a connector that requires external driver installation using installation.sh file
# It is an example of using default-libmysqlclient-dev and build-essential
# to communicate with MySql db and iterate over the data to update the connector

# NOTE: libpq5 and libpq-dev are pre-installed in our connector-sdk base imagee.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import datetime for handling date and time conversions.
import time
import json

# Import MySQLdb to communicate with db
import MySQLdb
from fivetran_connector_sdk import Connector, Logging as log, Operations as op


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [
        {
            "table": "orders",
            "primary_key": ["id"],
            "columns": {
                "id": "LONG",
                "title": "STRING",
                "name": "STRING",
                "city": "STRING",
                "mobile": "STRING",
                "datetime": "STRING",
            },
        }
    ]


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    validate_configuration(configuration)
    try:
        host = configuration.get("host")
        database = configuration.get("database")
        user = configuration.get("user")
        password = configuration.get("password")
        port = configuration.get("port")
        table_name = configuration.get("table_name")
        log.info("Fetching the CSV from desired location.")
        read_postgres_and_upsert(host, database, user, password, port, table_name)

        state["timestamp"] = time.time()
        op.checkpoint(state)
    except Exception as e:
        log.error("An error occurred", e)


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    required_configs = ["host", "database", "user", "password", "port", "table_name"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def read_postgres_and_upsert(host, database, user, password, port, table_name):
    """
    Connects to a MySql database, reads all rows from a specified table,
    and prints them.

    Args:
        host (str): The MySql server hostname or IP address.
        database (str): The database name.
        user (str): The database username.
        password (str): The database password.
        port (int): The database port.
        table_name (str): The name of the table to read from.
    """
    try:
        # Establish a connection to the Sql database
        # Connect to the database
        conn = MySQLdb.connect(
            host=host, user=user, password=password, database=database, port=int(port)
        )
        cursor = conn.cursor()

        # Execute a SELECT query to retrieve all rows from the table
        cursor.execute(f"SELECT * FROM {table_name}")

        # Fetch all rows from the result set
        rows = cursor.fetchall()

        headers = ["id", "title", "name", "city", "mobile", "datetime"]
        log.info("Iterating over the downloaded data.")
        for row in rows:
            upsert_line = {}
            for col_index, value in enumerate(row):
                if isinstance(value, datetime.date):
                    value = str(value)
                upsert_line[headers[col_index]] = value
            op.upsert("orders", upsert_line)

        # Close the cursor and connection
        cursor.close()
        conn.close()

    except Exception as e:
        log.error("Error", e)
        raise e


connector = Connector(update=update, schema=schema)

# required inputs docs https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
