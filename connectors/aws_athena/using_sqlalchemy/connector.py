# This is a simple example illustrating how to work with the fivetran_connector_sdk module.
# This is an example to show how we can sync records from AWS Athena by using Connector SDK and SQLAlchemy and PyAthena.
# You need to provide your credentials for this example to work.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
from sqlalchemy import create_engine
from sqlalchemy import text
import json  # Import the json module to handle JSON data.

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

TABLE_NAME = "test_rows"


# Define the schema function, which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [
        {
            "table": "customers",  # Name of the table in the destination.
            "primary_key": ["customer_id"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "customer_id": "STRING",  # String column for the first name.
            },
        }
    ]


def create_connection_engine(configuration):
    conn_str = f"awsathena+rest://{configuration['aws_access_key_id']}:{configuration['aws_secret_access_key']}@athena.{configuration['region_name']}.amazonaws.com:443/{configuration['database_name']}?s3_staging_dir={configuration['s3_staging_dir']}"
    return create_engine(conn_str)


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: a dictionary that contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary that contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync.
def update(configuration: dict, state: dict):
    engine = create_connection_engine(configuration)

    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT * FROM {TABLE_NAME}"))
        while True:
            rows = result.fetchmany(2)
            if len(rows) == 0:
                break

            for row in rows:
                op.upsert(
                    table="customers",
                    data={
                        "customer_id": row[0],  # Customer id.
                        "first_name": row[1],  # First Name.
                        "last_name": row[2],  # Last name.
                        "email": row[3],  # Email id.
                    },
                )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


# This creates the connector object that will use the update function defined in this connector.py file.
# This example does not use the schema() function. If it did, it would need to be included in the connector object definition.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Test it by using the `debug` command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)
