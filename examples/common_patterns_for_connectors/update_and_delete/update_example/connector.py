# This is a simple example for how to work with the fivetran_connector_sdk module.
# It shows the update operations you can use when the primary key is composite.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

import json
from typing import Dict, List, Any
import psycopg2
import psycopg2.extras

# Import required classes from fivetran_connector_sdk
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
        )  # Connect to the database and return the connection object
        self.push_sample_data()  # Push sample data to the database

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
            cursor = self.connection.cursor()
            cursor.execute("DROP TABLE IF EXISTS product_inventory")
            self.connection.commit()
            log.info("Dropped product_inventory table from database.")
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
            "table": "product_inventory",
            "primary_key": ["product_id", "warehouse_id"],
            # The primary key is a composite key consisting of two columns: product_id and warehouse_id.
            # No columns are defined, meaning the types will be inferred.
        }
    ]


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
    log.warning("Example: Common Patterns For Connectors - Update Operation")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    conn = PostgresClient(configuration)

    # IMPORTANT: This connector requires the following prerequisites in your PostgreSQL database:
    # 1. A table named 'product_inventory' with the following schema:
    #    - product_id (INT): Part of composite primary key
    #    - warehouse_id (INT): Part of composite primary key
    #    - quantity (INT): Available product quantity
    #    - last_updated (TIMESTAMP): Last update timestamp
    #
    # The table should be created with a statement similar to:
    # CREATE TABLE IF NOT EXISTS product_inventory (
    #     product_id INT,
    #     warehouse_id INT,
    #     quantity INT,
    #     last_updated TIMESTAMP,
    #     PRIMARY KEY (product_id, warehouse_id)
    # )
    # The structure of the original product_inventory is present at the end of this file.
    try:
        query = "SELECT * FROM product_inventory"
        records = conn.fetch_data(query)
        log.info(f"Retrieved {len(records)} records from product_inventory")

        # upsert each record into the destination table
        for record in records:
            op.upsert("product_inventory", record)
        op.checkpoint(state)

        # CASE 1: Updating single record with product_id=102 and warehouse_id=2
        log.info("Updating record with product_id=102 and warehouse_id=2")
        op.update(
            table="product_inventory",
            modified={
                "product_id": 102,
                "warehouse_id": 2,
                "quantity": 75,
                "last_updated": "2025-03-16",
            },
        )

        # CASE 2: Updating all records with product_id=101
        log.info("Updating all records with product_id=101")
        # Select specific records for updating by their complete primary keys
        query = "SELECT product_id, warehouse_id FROM product_inventory WHERE product_id=101"
        records = conn.fetch_data(query)

        # The fetched records contain: {'product_id': 101, 'warehouse_id': 1} and {'product_id': 101, 'warehouse_id': 2}
        for record in records:
            updated_values = {"quantity": 100, "last_updated": "2025-03-14"}
            # join both the dictionary to include primary key-value pairs and updated key-value pairs
            record.update(updated_values)
            # It is important to include all the primary key columns defined in scheme to update the desired row values.
            op.update(table="product_inventory", modified=record)

        # Updating the records with incomplete primary keys will raise an error.
        # Below are the examples of such incorrect cases:
        # op.update(table="product_inventory", modified={"product_id": 101})
        # op.update(table="product_inventory", modified={"warehouse_id": 1})

        op.checkpoint(state)

    except Exception as e:
        raise ValueError(f"Error updating records: {e}")

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
# Original table before any updates:
# ┌──────────────────────────────────────────────────────┐
# │ product_id │ warehouse_id│ quantity │ last_updated   │
# ├──────────────────────────────────────────────────────┤
# │ 101        │ 1           │ 50       │ 2024-03-01     │
# │ 101        │ 2           │ 30       │ 2024-03-01     │
# │ 102        │ 1           │ 20       │ 2024-03-01     │
# │ 102        │ 2           │ 15       │ 2024-03-01     │
# │ 103        │ 1           │ 10       │ 2024-03-01     │
# └──────────────────────────────────────────────────────┘

# CASE 1: After updating rows with product_id=102 and warehouse_id=2
# ┌──────────────────────────────────────────────────────┐
# │ product_id │ warehouse_id│ quantity │ last_updated   │
# ├──────────────────────────────────────────────────────┤
# │ 101        │ 1           │ 50       │ 2024-03-01     │
# │ 101        │ 2           │ 50       │ 2025-03-01     │
# │ 102        │ 1           │ 20       │ 2024-03-01     │
# │ 102        │ 2           │ 75       │ 2025-03-16     │ <- Updated quantity and last_updated
# │ 103        │ 1           │ 10       │ 2024-03-01     │
# └──────────────────────────────────────────────────────┘

# CASE 2: After updating all rows with product_id=101
# ┌──────────────────────────────────────────────────────┐
# │ product_id │ warehouse_id│ quantity │ last_updated   │
# ├──────────────────────────────────────────────────────┤
# │ 101        │ 1           │ 100      │ 2025-03-14     │ <- Updated quantity and last_updated
# │ 101        │ 2           │ 100      │ 2025-03-14     │ <- Updated quantity and last_updated
# │ 102        │ 1           │ 20       │ 2024-03-01     │
# │ 102        │ 2           │ 75       │ 2024-03-16     │
# │ 103        │ 1           │ 10       │ 2024-03-01     │
# └──────────────────────────────────────────────────────┘

# IMPORTANT: When updating records, you must provide ALL the primary keys as defined in the schema.
# Using only a subset of the primary key components (such as only product_id or only warehouse_id from a composite key) will cause the sync to fail with an error.
# Always ensure that update operations include all primary key fields.
