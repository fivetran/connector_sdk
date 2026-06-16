# This is a simple example for how to work with the fivetran_connector_sdk module.
# It shows the delete operations you can use when the primary key is composite.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.

import json
from typing import Dict, List, Any
import psycopg2
import psycopg2.extras

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

cred = ["HOST", "DATABASE", "USERNAME", "PASSWORD", "PORT"]


# Define the PostgresClient class to handle database operations.
class PostgresClient:
    def __init__(self, config):
        self.host = config.get("HOST")
        self.port = config.get("PORT")
        self.database = config.get("DATABASE")
        self.user = config.get("USERNAME")
        self.password = config.get("PASSWORD")
        self.connection = (
            self.connect()
        )  # Connect to the database and return the connection object.

    def connect(self):
        try:
            return psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
        except Exception as e:
            raise ConnectionError(f"Error connecting to PostgreSQL database: {e}")

    def disconnect(self) -> None:
        if self.connection:
            log.info("starting the drop table sequence")
            cursor = self.connection.cursor()
            cursor.execute("DROP TABLE IF EXISTS sample_table")
            log.info("Dropped sample table from database.")
            self.connection.commit()
            log.info("Committed sample table from database.")

            self.connection.close()
            log.info("Database connection closed.")

    def fetch_data(self, query: str) -> List[Dict[str, Any]]:
        try:
            if not self.connection:
                self.connect()

            cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in result]
        except Exception as e:
            raise ValueError(f"Error fetching data from PostgreSQL: {e}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Check if the credentials for connecting to database is present in the configuration.
    for key in cred:
        if key not in configuration:
            raise ValueError(f"Missing required configuration: {key}")
    return [
        {
            "table": "sample_table",  # Name of the table in the destination.
            "primary_key": ["id", "department_id"],  # Primary key column(s) for the table.
            # The primary key is a composite key consisting of two columns: id and department_id.
            # No columns are defined, meaning the types will be inferred.
        }
    ]


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
    for key in cred:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Common Patterns For Connectors - Delete Operation")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    conn = PostgresClient(configuration)
    log.info("Connected to PostgreSQL database.")

    # IMPORTANT: This connector requires the following prerequisites in your PostgreSQL database:
    # 1. A table named 'sample_table' with the following schema:
    #    - id (INT): Part of composite primary key
    #    - name (VARCHAR(255)): Person's name
    #    - department_id (INT): Part of composite primary key
    #    - address (VARCHAR(255)): Person's address
    #
    # The table should be created with a statement similar to:
    # CREATE TABLE IF NOT EXISTS sample_table (
    #     id INT,
    #     name VARCHAR(255),
    #     department_id INT,
    #     address VARCHAR(255),
    #     PRIMARY KEY(id, department_id)
    # )
    #
    # The structure of the 'sample_table' is present at the end of this file
    try:
        query = "SELECT * FROM sample_table"
        records = conn.fetch_data(query)
        log.info(f"Retrieved {len(records)} records from sample_table")

        # upsert each record into the destination table
        for record in records:
            op.upsert(table="sample_table", data=record)
        op.checkpoint(state)

        # CASE 1: Deleting single record with id=3 and department_id=1
        log.info("Deleting record with id=3 and department_id=1")
        op.delete(table="sample_table", keys={"id": 3, "department_id": 1})

        # CASE 2: Deleting all records with department_id=1
        log.info("Deleting all records with department_id=1")
        # Select specific records for deletion by their complete primary keys
        query = "SELECT id, department_id FROM sample_table WHERE id=1"
        records = conn.fetch_data(query)

        # The fetched records contain: {'id': 1, 'department_id': 1} and {'id': 1, 'department_id': 2}
        for record in records:
            # It is important to provide all the primary key defined in schema to delete the record.
            op.delete(table="sample_table", keys=record)

        # Deleting the records with incomplete primary keys will raise an error.
        # Below are the examples of such cases:
        # op.delete(table="sample_table", keys={"id": 1})
        # op.delete(table="sample_table", keys={"department_id": 3})

        op.checkpoint(state)

    except Exception as e:
        raise ValueError(f"Error deleting records: {e}")

    finally:
        conn.disconnect()


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
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


# Resulting table after each operation:
# Original table before any deletes:
# ┌─────────────────────────────────────────────────────────────┐
# │ id │ name  │ department_id│ address      │ _fivetran_deleted│
# ├─────────────────────────────────────────────────────────────┤
# │ 1  │ John  │ 1            │ 123 Main St  │ false            │
# │ 1  │ John  │ 2            │ 123 Main St  │ false            │
# │ 2  │ Jane  │ 3            │ 456 Elm St   │ false            │
# │ 3  │ Alice │ 3            │ 789 Oak St   │ false            │
# │ 3  │ Alice │ 1            │ 789 Oak St   │ false            │
# │ 4  │ Bob   │ 3            │ 1012 Pine St │ false            │
# └─────────────────────────────────────────────────────────────┘

# CASE 1: After deleting rows with id=3 and department_id=1
# ┌─────────────────────────────────────────────────────────────┐
# │ id │ name  │ department_id│ address      │ _fivetran_deleted│
# ├─────────────────────────────────────────────────────────────┤
# │ 1  │ John  │ 1            │ 123 Main St  │ false            │
# │ 1  │ John  │ 2            │ 123 Main St  │ false            │
# │ 2  │ Jane  │ 3            │ 456 Elm St   │ false            │
# │ 3  │ Alice │ 3            │ 789 Oak St   │ false            │
# │ 3  │ Alice │ 1            │ 789 Oak St   │ true             │ <- Marked as deleted
# │ 4  │ Bob   │ 3            │ 1012 Pine St │ false            │
# └─────────────────────────────────────────────────────────────┘

# CASE 2: After deleting all rows with id=1
# ┌─────────────────────────────────────────────────────────────┐
# │ id │ name  │ department_id│ address      │ _fivetran_deleted│
# ├─────────────────────────────────────────────────────────────┤
# │ 1  │ John  │ 1            │ 123 Main St  │ true             │ <- Marked as deleted
# │ 1  │ John  │ 2            │ 123 Main St  │ true             │ <- Marked as deleted
# │ 2  │ Jane  │ 3            │ 456 Elm St   │ false            │
# │ 3  │ Alice │ 3            │ 789 Oak St   │ false            │
# │ 3  │ Alice │ 1            │ 789 Oak St   │ true             │
# │ 4  │ Bob   │ 3            │ 1012 Pine St │ false            │
# └─────────────────────────────────────────────────────────────┘

# IMPORTANT: When deleting records, you must provide ALL the primary keys as defined in the schema.
# Using only a subset of the primary key components (such as only id or only department_id from a composite key) will cause the sync to fail with an error.
# Always ensure that delete operations include all primary key fields.
