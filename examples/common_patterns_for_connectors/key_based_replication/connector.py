# This is a simple example for how to work with the fivetran_connector_sdk module.
# This shows key based replication from DB sources.
# Replication keys are columns that are used to identify new and updated data for replication.
# When you set a table to use Incremental Replication, you’ll also need to define a replication key for that table.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import datetime for handling date and time conversions.
from datetime import datetime

# import duckdb to interact with DuckDB databases from within your Python code.
import duckdb

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

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
                "customer_id": "INT",  # Integer column for the customer_id.
                "first_name": "STRING",  # String column for the first name.
                "last_name": "STRING",  # String column for the last name.
                "email": "STRING",  # String column for the email.
                "updated_at": "UTC_DATETIME",  # UTC date-time column for the updated_at.
                # In this example we are using `updated_at` as the replication key
            },
        }
    ]


def dt2str(incoming: datetime) -> str:
    """
    Converts a datetime object to a string in the specified format.
    Args:
        incoming: datetime object to be converted.
    Returns:
        str: The formatted string representation of the datetime object.
    """
    return incoming.strftime(TIMESTAMP_FORMAT)


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
    log.warning("Example: Source Examples - Common Patterns - Key Based Replication")

    # Connect to your database instance instance.
    conn = duckdb.connect()

    """
    Ensure that the source has the required table and data.
    If the table and data are not present, the connector will not work as expected
    The connector expects the source to have a table named "customers" with the following schema:
    CREATE TABLE IF NOT EXISTS customers
    (customer_id INTEGER PRIMARY KEY,
    first_name VARCHAR,
    last_name VARCHAR,
    email VARCHAR,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

    Sample data in the "customers" table can be inserted using the following query:
    INSERT INTO customers (customer_id, first_name, last_name, email, updated_at)
    VALUES
    ('1', 'Mathew', 'Perry', 'mathew@fivetran.com', '2023-12-31T23:59:59Z'),
    ('2', 'Joe', 'Doe', 'joe@fivetran.com', '2024-01-31T23:04:39Z'),
    ('3', 'Jake', 'Anderson', 'jake@fivetran.com', '2023-11-01T23:59:59Z'),
    ('4', 'John', 'William', 'john@fivetran.com', '2024-02-14T22:59:59Z'),
    ('5', 'Ricky', 'Roma', 'ricky@fivetran.com', '2024-03-16T16:40:29Z')
    ON CONFLICT (customer_id)
    DO UPDATE SET
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    email = EXCLUDED.email,
    updated_at = EXCLUDED.updated_at
    """

    # If the cursor is not present in the state, starting from ('2024-01-01T00:00:00Z') to represent incremental syncs.
    last_updated_at = (
        state["last_updated_at"] if "last_updated_at" in state else "2024-01-01T00:00:00Z"
    )

    # Fetch records from DB sorted in ascending order.
    query = (
        f"SELECT customer_id, first_name, last_name, email, updated_at FROM customers WHERE {REPLICATION_KEY} > "
        f"'{last_updated_at}' ORDER BY {REPLICATION_KEY}"
    )
    # This log message will only show while debugging.
    log.debug(f"fetching records from `customer` table modified after {last_updated_at}")
    result = conn.execute(query).fetchall()

    # Upsert operation to insert/update the row in the "customers" table.
    for row in result:
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


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug()

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
