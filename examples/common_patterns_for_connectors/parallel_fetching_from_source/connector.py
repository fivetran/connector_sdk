# This is a simple example for how to work with the fivetran_connector_sdk module.
# It defines a simple `update` method, which uses boto3 to fetch files from AWS S3 bucket and upserts the data in parallel
# The data is processed such that for each file, the records are upserted sequentially.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
# # Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import (
    Connector,
)  # For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import (
    Operations as op,
)  # For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Logging as log  # For enabling Logs in your connector code

# Import required libraries
import csv  # For reading CSV files
import json  # For parsing JSON data
import os  # For file path operations
import boto3  # For AWS S3 operations
from io import TextIOWrapper  # For wrapping the binary stream in a text decoder
from concurrent.futures import ThreadPoolExecutor, as_completed  # For parallel processing


# This method is used to create an S3 client using the boto3 library.
# The method takes the configuration dictionary as a parameter and returns the S3 client.
# The S3 client is used to interact with the AWS S3 service.
def create_s3_client(configuration: dict):
    # Set default values for parallelism and prefix if not provided
    if "parallelism" not in configuration:
        log.warning("parallelism is not set in the configuration, defaulting to 4 threads.")
        configuration["parallelism"] = 4
    if "prefix" not in configuration:
        log.warning("prefix is not set in the configuration, defaulting to '/' prefix.")
        configuration["prefix"] = "/"

    # Check if the required keys are present in the configuration
    required_keys = ["aws_access_key_id", "aws_secret_access_key", "region_name", "bucket_name"]
    for key in required_keys:
        if key not in configuration:
            # Raise an error if any required key is missing
            raise ValueError(f"Missing required configuration key: {key}")

    return boto3.client(
        "s3",
        aws_access_key_id=configuration["aws_access_key_id"],
        aws_secret_access_key=configuration["aws_secret_access_key"],
        region_name=configuration["region_name"],
    )


# This method is used to get the list of CSV files from the S3 bucket.
# The method takes the S3 client, bucket name, and prefix as parameters.
# The method returns a list of tuples containing the file key and table name.
# The tables names are extracted from the file names by removing the ".csv" extension.
# You can modify this method to select and process only specific files based on your requirements.
def get_file_table_pairs(s3_client, bucket_name: str, prefix: str):
    # List all CSV files in the specified prefix
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    file_table_pairs = []
    if "Contents" in response:
        for obj in response["Contents"]:
            if obj["Key"].endswith(".csv"):
                table_name = os.path.basename(obj["Key"]).replace(".csv", "")
                file_table_pairs.append((obj["Key"], table_name))
    return file_table_pairs


# This method is used to process a single file from the S3 bucket.
# The method takes the S3 client, bucket name, file key, and table name as parameters.
# The method upserts records one by one and does not return anything.
# You can modify this method to process each record and upsert.
def process_file_get_stream(s3_client, bucket_name, file_key, table_name):
    log.info(f"Processing file: {file_key} for table: {table_name}")

    # Get the S3 object using get_object, which returns a streaming response
    # This is more efficient than loading the entire file in memory
    response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
    # The response['Body'] is a streaming body, which is a binary stream
    streaming_body = response["Body"]

    # Wrap the binary stream in a text decoder
    # This allows us to read the CSV content as text
    text_stream = TextIOWrapper(streaming_body, encoding="utf-8")
    # The csv.DictReader reads the CSV content and returns an iterator of dictionaries
    csv_reader = csv.DictReader(text_stream)

    # Iterate over the CSV rows
    for record in csv_reader:
        try:
            # Parse any JSON fields in the record, if needed
            # You can modify it to handle specific fields
            for key, value in record.items():
                if (
                    value
                    and isinstance(value, str)
                    and value.startswith("{")
                    and value.endswith("}")
                ):
                    try:
                        record[key] = json.loads(value)
                    except json.JSONDecodeError:
                        # Keep as string if JSON parsing fails
                        pass
            # The 'upsert' operation inserts the data into the destination.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table_name, data=record)
        except Exception as e:
            log.error(f"Error processing record from {file_key}", e)
            # Continue processing other records even if one fails
            continue


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [
        {
            "table": "campaigns",  # Name of the table
            "primary_key": ["campaign_id"],  # Primary key(s) for the table
            "columns": {"campaign_id": "STRING", "target_demographics": "JSON"},
        },
        {
            "table": "customers",
            "primary_key": ["customer_id"],
            "columns": {
                "customer_id": "STRING",
            },
        },
        {
            "table": "employees",
            "primary_key": ["employee_id"],
            "columns": {
                "employee_id": "STRING",
            },
        },
        {
            "table": "inventory",
            "primary_key": ["inventory_id"],
            "columns": {
                "inventory_id": "STRING",
            },
        },
        {
            "table": "orders",
            "primary_key": ["order_id"],
            "columns": {
                "order_id": "STRING",
            },
        },
        {
            "table": "products",
            "primary_key": ["product_id"],
            "columns": {
                "product_id": "STRING",
            },
        },
        {
            "table": "tickets",
            "primary_key": ["ticket_id"],
            "columns": {
                "ticket_id": "STRING",
            },
        },
        {
            "table": "transactions",
            "primary_key": ["transaction_id"],
            "columns": {
                "transaction_id": "STRING",
            },
        },
    ]


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    log.warning("Example: Common Pattern for Connectors Examples - Parallel Fetching from Source")

    # create S3 client using the configuration
    s3_client = create_s3_client(configuration)
    bucket_name = configuration["bucket_name"]
    parallelism = int(configuration.get("parallelism"))
    prefix = configuration.get("prefix", "/")  # default to root prefix

    # get the list of CSV files and their corresponding table names
    # This will return a list of tuples (file_key, table_name)
    # The table names are extracted from the file names by removing the ".csv" extension.
    file_table_pairs = get_file_table_pairs(s3_client, bucket_name, prefix)
    log.info(f"Found {len(file_table_pairs)} CSV files in {prefix} folder")

    # Process files in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        # Submit all tasks to the executor
        futures_dict = {
            executor.submit(
                process_file_get_stream, s3_client, bucket_name, file_key, table_name
            ): table_name
            for file_key, table_name in file_table_pairs
        }

        # The as_completed function is a standard library function that returns an iterator yielding futures as they complete
        # enabling immediate handling of results or errors for each file as they complete
        for future in as_completed(futures_dict):
            table_name = str(futures_dict[future])
            try:
                future.result()
            except Exception as e:
                log.error(f"Error processing file for table {table_name}", e)

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
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Allows testing the connector directly
    connector.debug(configuration=configuration)
