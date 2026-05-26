# This is a simple example for how to work with the fivetran_connector_sdk module.
# This shows how to authenticate to Aws using IAM role credentials and connector to DynamoDb to fetch records.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Refer boto3 docs (https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html)

import json  # Import the json module to handle JSON data.

# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
import boto3
import aws_dynamodb_parallel_scan


def get_dynamo_db_client(configuration: dict):
    # create security token service client
    sts = boto3.client(
        "sts",
        aws_access_key_id=configuration["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=configuration["AWS_SECRET_ACCESS_KEY"],
    )

    # get role credentials
    credentials = sts.assume_role(RoleArn=configuration["ROLE_ARN"], RoleSessionName="sdkSession")[
        "Credentials"
    ]

    # create dynamo_db_client using role credentials
    dynamo_db_client = boto3.client(
        "dynamodb",
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=configuration["REGION"],
    )

    return dynamo_db_client


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    dynamo_client = get_dynamo_db_client(configuration)
    schema = []

    try:
        # fetch and iterate over table names
        for table in dynamo_client.list_tables()["TableNames"]:
            # fetch table_meta_data, see https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/client/describe_table.html
            table_meta_data = dynamo_client.describe_table(TableName=table)
            table_schema = {
                "table": table,
                "primary_key": list(
                    map(
                        lambda keySchema: keySchema["AttributeName"],
                        table_meta_data["Table"]["KeySchema"],
                    )
                ),
            }
            schema.append(table_schema)
    except Exception as e:
        log.error("Failed to get schema", e)

    return schema


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary containing any secrets or payloads you configure when deploying the connector.
# - state: a dictionary containing the state checkpointed during the prior sync.
#   The state dictionary is empty for the first sync or for any full re-sync.
def update(configuration: dict, state: dict):
    log.warning("Example: Source Examples - AWS DynamoDb Authentication")

    dynamo_client = get_dynamo_db_client(configuration)

    try:
        # get paginator for parallel scan
        paginator = aws_dynamodb_parallel_scan.get_paginator(dynamo_client)
        # fetch and iterate over table names
        for table in dynamo_client.list_tables()["TableNames"]:
            # get pages of 10 items and 4 parallel threads
            page_iterator = paginator.paginate(
                TableName=table, Limit=10, TotalSegments=4, ConsistentRead=True
            )
            for page in page_iterator:
                items = list(map(map_item, page["Items"]))
                for item in items:
                    op.upsert(table, item)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        log.info("Finished syncing...")
    except Exception as e:
        log.error("Sync failed", e)
        raise


def map_item(item: dict):
    result = {}
    for key, value in item.items():
        for nested_key, nested_value in value.items():
            if type(nested_value) is list:
                result[key] = str(nested_value)
            else:
                result[key] = nested_value
    return result


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the "fivetran debug" command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
