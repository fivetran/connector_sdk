# This is a simple example for how to work with the fivetran_connector_sdk module.
# This is an example to show how we can sync records from redshift DB via Connector SDK.
# You would need to provide your redshift credentials for this example to work.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

import json  # Import the json module to handle JSON data.

# Import datetime for handling date and time conversions.
from datetime import datetime

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
import redshift_connector

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# This column is the replication key which helps determine which records are updated
REPLICATION_KEY = "updated_at"


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
            "table": "customers",  # Name of the table in the destination.
            "primary_key": ["customer_id"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "customer_id": "INT",  # INT column for the customer id.
                "updated_at": "UTC_DATETIME",  # UTC date-time column for the updated_at.
                # In this example we are using `updated_at` as the replication key
            },
        }
    ]


def dt2str(incoming: datetime) -> str:
    return incoming.strftime(TIMESTAMP_FORMAT)


def connect_to_redshift(configuration):
    return redshift_connector.connect(
        host=configuration["host"],
        database=configuration["database"],
        port=configuration["port"],
        user=configuration["user"],
        password=configuration["password"],
    )


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
    log.warning("Example: Source Examples - Redshift")

    # Connect to your database instance instance.
    conn = connect_to_redshift(configuration)
    cursor = conn.cursor()

    # IMPORTANT: This connector requires the following prerequisites in your Redshift database:
    # 1. A table named 'customers' with the following schema:
    #    - customer_id (INTEGER): Primary key
    #    - first_name (VARCHAR): Customer's first name
    #    - last_name (VARCHAR): Customer's last name
    #    - email (VARCHAR): Customer's email address
    #    - city (VARCHAR): Customer's city
    #    - state (VARCHAR): Customer's state/region
    #    - country (VARCHAR): Customer's country
    #    - updated_at (TIMESTAMP WITH TIME ZONE): Record's last update timestamp
    #
    # 2. The table should be created with a statement similar to:
    # CREATE TABLE IF NOT EXISTS testers.customers (
    #    customer_id INTEGER PRIMARY KEY,
    #    first_name VARCHAR,
    #    last_name VARCHAR,
    #    email VARCHAR,
    #    city VARCHAR,
    #    state VARCHAR,
    #    country VARCHAR,
    #    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    # ) SORTKEY (updated_at);
    #
    # Sample data must be present in your source Redshift instance before running this connector.
    # The connector expects to find records with customer information and timestamps.
    # If these prerequisites are not met, the connector will not function correctly.

    # If the cursor is not present in the state, starting from ('2024-01-01T00:00:00Z') to represent incremental syncs.
    last_updated_at = (
        state["last_updated_at"] if "last_updated_at" in state else "2024-01-01T00:00:00Z"
    )

    # Fetch records from DB sorted in ascending order.
    # REPLICATION_KEY is updated_at column.
    query = (
        f"SELECT customer_id, first_name, last_name, email, updated_at FROM testers.customers WHERE {REPLICATION_KEY} > "
        f"'{last_updated_at}' ORDER BY {REPLICATION_KEY}"
    )

    # This log message will only show while debugging.
    log.debug(f"fetching records from `customer` table modified after {last_updated_at}")
    cursor.execute(query)

    while True:
        # Fetching 2 rows at a time so that we keep checkpointing in intervals.
        result = cursor.fetchmany(2)
        if len(result) == 0:
            break
        # An upsert operation to insert/update the row in the "customers" table.
        for row in result:
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into, in this case, "customers".
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(
                table="customers",
                data={
                    "customer_id": row[0],  # Customer id.
                    "first_name": row[1],  # First Name.
                    "last_name": row[2],  # Last name.
                    "email": row[3],  # Email id.
                    "updated_at": dt2str(row[4]),  # record updated at.
                },
            )
            # Storing `updated_at` of last fetched record
            last_updated_at = dt2str(row[4])
        # Update the state to the updated_at of the last record.
        state["last_updated_at"] = last_updated_at

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)


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

# Source table:
# ┌───────────────────┬───────────────────┬───────────────────────────────────────────┬────────────────────────────┐
# │     customer_id   │   first_name      │     last_name     │       email           │       updated_at           │
# │         int16     │      varchar      │     varchar       │       varchar         │   timestamp with time zone │
# ├───────────────────┼───────────────────┼───────────────────┼───────────────────────┤────────────────────────────│
# │         1         │       Mathew      │     Perry         │ mathew@fivetran.com   │    2023-12-31 23:59:59.000 │
# │         2         │       Joe         │     Doe           │ joe@fivetran.com      │    2024-01-31 23:04:39.000 │
# │         3         │       Jake        │     Anderson      │ jake@fivetran.com     │    2023-11-01 23:59:59.000 │
# │         4         │       John        │     William       │ john@fivetran.com     │    2024-02-14 22:59:59.000 │
# │         5         │       Ricky       │     Roma          │ ricky@fivetran.com    │    2024-03-16 16:40:29.000 │
# ├───────────────────┴───────────────────┴───────────────────┴────────────────────────────────────────────────────┤
# │ 5 rows                                                                                               5 columns │
# └────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘


# Resulting table:
# ┌─────────────────────┬───────────────────┬────────────────────────────────────────┬────────────────────────────┐
# │     customer_id     │   first_name      │     last_name     │       email        │       updated_at           │
# │         int16       │      varchar      │     varchar       │       varchar      │   timestamp with time zone │
# ├─────────────────────┼───────────────────┼───────────────────┼────────────────────┤────────────────────────────│
# │         2           │       Joe         │     Doe           │ joe@fivetran.com   │    2024-01-31T23:04:39Z    │
# │         4           │       John        │     William       │ john@fivetran.com  │    2024-02-14T22:59:59Z    │
# │         5           │       Ricky       │     Roma          │ ricky@fivetran.com │    2024-03-16T16:40:29Z    │
# ├─────────────────────┴───────────────────┴───────────────────┴─────────────────────────────────────────────────┤
# │ 3 rows                                                                                              5 columns │
# └───────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
