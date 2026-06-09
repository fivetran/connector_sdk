# This is a simple example for how to work with the fivetran_connector_sdk module.
# This is an example to show how we can sync records from AWS Athena via Connector SDK using boto3.
# You need to provide your credentials for this example to work.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
import boto3
import json  # Import the json module to handle JSON data.

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
import time

TABLE_NAME = "test_rows"
NEXT_TOKEN = "NextToken"


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


def create_athena_client(configuration):
    return boto3.client(
        "athena",
        aws_access_key_id=configuration["aws_access_key_id"],
        aws_secret_access_key=configuration["aws_secret_access_key"],
        region_name=configuration["region_name"],
    )


def process_and_upsert_response(response):
    # Skipping first row as it contains only metadata
    for row in response["ResultSet"]["Rows"][1:]:
        row_data = []
        for cell in row["Data"]:
            if "VarCharValue" in cell:
                row_data.append(cell["VarCharValue"])
            elif "BigIntValue" in cell:
                row_data.append(int(cell["BigIntValue"]))
            elif "DoubleValue" in cell:
                row_data.append(float(cell["DoubleValue"]))
            elif "BooleanValue" in cell:
                row_data.append(bool(cell["BooleanValue"]))
            else:
                row_data.append(None)
        op.upsert(
            table="customers",
            data={
                "customer_id": row_data[0],  # Customer id.
                "first_name": row_data[1],  # First Name.
                "last_name": row_data[2],  # Last name.
                "email": row_data[3],  # Email id.
            },
        )


def get_query_results(athena_client, query_execution_id):
    response = athena_client.get_query_results(QueryExecutionId=query_execution_id)

    while True:
        response = (
            athena_client.get_query_results(
                QueryExecutionId=query_execution_id, NextToken=response[NEXT_TOKEN]
            )
            if NEXT_TOKEN in response
            else athena_client.get_query_results(QueryExecutionId=query_execution_id)
        )

        process_and_upsert_response(response)
        if NEXT_TOKEN not in response:
            break


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: a dictionary that contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary that contains whatever state you have chosen to checkpoint during the prior sync.
# The state dictionary is empty for the first sync or for any full re-sync.
def update(configuration: dict, state: dict):
    athena_client = create_athena_client(configuration)

    query = f"SELECT * FROM {TABLE_NAME}"
    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": configuration["database_name"]},
        ResultConfiguration={"OutputLocation": configuration["s3_staging_dir"]},
    )

    query_execution_id = response["QueryExecutionId"]

    # Wait for query completion (adjust polling interval as needed)
    while True:
        response = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
        status = response["QueryExecution"]["Status"]["State"]
        if status in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break

        time.sleep(5)

    if status == "SUCCEEDED":
        get_query_results(athena_client, query_execution_id)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)
    else:
        print(f"Query failed with status: {status}")


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
