# This is a simple example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to read csv file from amazon s3 and validate the data.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
# For testing the example, please refer the data.csv file from "./data" folder.

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log
from datetime import datetime

import pandas as pd

import json
import boto3
from io import StringIO

# Define the constant values
TABLE_NAME = "data"


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.


def schema(configuration: dict):
    return [
        {
            "table": TABLE_NAME,  # Name of the table in the destination.
            "primary_key": ["int_value"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "int_value": "INT",
                "long_value": "LONG",
                "bool_value": "BOOLEAN",
                "string_value": "STRING",
                "json_value": "JSON",
                "naive_date_value": "NAIVE_DATE",
                "naive_date_time_value": "NAIVE_DATETIME",
            },
        }
    ]


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    s3_client = create_s3_client(configuration)
    bucket_name = configuration["bucket_name"]
    file_key = configuration["file_key"]

    # Fetch the file from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=file_key)

    # Read the content of the file
    csv_content = response["Body"].read().decode("utf-8")

    # Load the CSV content into a Pandas DataFrame
    df = pd.read_csv(StringIO(csv_content), converters={col: str for col in range(100)})

    for index, row in df.iterrows():
        result = upsert_csv_row(row)
        if not result:
            log.warning(f"Skip the upsert for the row no {index + 1} of file {file_key}")


def upsert_csv_row(row):
    int_value = validate_int_value(row, row["int_column"])
    if int_value is None:
        return False

    long_value = validate_int_value(row, row["long_column"])
    if long_value is None:
        return False

    bool_value = validate_bool_value(row, row["bool_column"])
    if bool_value is None:
        return False

    string_value = validate_string_value(row, row["string_column"])
    if string_value is None:
        return False

    json_value = validate_json_value(row, row["json_column"])
    if json_value is None:
        return False

    naive_date_value = validate_naive_date_value(row, row["naive_date_column"])
    if naive_date_value is None:
        return False

    naive_date_time_value = validate_naive_date_time_value(row, row["naive_date_time_column"])
    if naive_date_time_value is None:
        return False

    data = {
        "int_value": int_value,
        "long_value": long_value,
        "bool_value": bool_value,
        "string_value": string_value,
        "json_value": json_value,
        "naive_date_value": naive_date_value.strftime("%Y-%m-%d"),
        "naive_date_time_value": naive_date_time_value.strftime("%Y-%m-%dT%H:%M:%S.%f"),
    }
    op.upsert(TABLE_NAME, data=data)
    return True


def validate_int_value(row, value: str):
    try:
        return int(value)
    except (ValueError, TypeError) as e:
        print_error_message(row, f"Invalid integer value: '{value}'")
        return None


def validate_bool_value(row, value: str):
    if not validate_string_value(row, value):
        print_error_message(row, f"Invalid boolean value: '{value}'")
        return None

    if value.lower() == "true" or value.lower() == "false":
        return value.lower() == "true"

    print_error_message(row, f"Invalid boolean value: '{value}'")
    return None


def validate_string_value(row, value: str):
    if value and value.strip():
        return value
    print_error_message(row, f"Invalid string value: '{value}'")
    return None


def validate_json_value(row, value: str):
    try:
        json_value = json.loads(value)  # Attempt to parse the JSON string
        return json_value
    except ValueError:
        print_error_message(row, f"Invalid json value: '{value}'")
        return None


def validate_naive_date_value(row, value: str):
    date_value_string = value.strip()
    try:
        return datetime.strptime(date_value_string, "%Y-%m-%d").date()
    except ValueError:
        print_error_message(row, f"Invalid naive date value: '{date_value_string}'")
        return None


def validate_naive_date_time_value(row, value: str):
    date_time_value_string = value.strip()
    try:
        return datetime.strptime(date_time_value_string, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        print_error_message(row, f"Invalid naive date time value: '{date_time_value_string}'")
        return None


def print_error_message(row, message: str):
    print(f"Error: Cannot upsert row '{row}', reason: {message}")


def create_s3_client(configuration):
    return boto3.client(
        "s3",
        aws_access_key_id=configuration["aws_access_key_id"],
        aws_secret_access_key=configuration["aws_secret_access_key"],
        region_name=configuration["region_name"],
    )


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
