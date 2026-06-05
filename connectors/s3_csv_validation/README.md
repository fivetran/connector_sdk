# S3 CSV File Reader with Data Validation Connector Example

## Connector overview
This connector demonstrates how to retrieve a CSV file from an Amazon S3 bucket, validate its contents, and sync the records into a destination table using the Fivetran Connector SDK.

Key features include:
- Reading and parsing CSV data using `pandas`.
- Field-level validation for multiple data types (INT, BOOLEAN, STRING, JSON, DATE, DATETIME).
- Skipping invalid rows with helpful error messages.
- Using AWS credentials to securely access private S3 buckets.

This example is ideal for:
- Validating and syncing files uploaded by external systems.
- Handling semi-structured input with field-type enforcement.
- Ingesting flat-file data from cloud object storage.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/s3_csv_validation
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to Amazon S3 using `boto3`.
- Reads a CSV file and loads it into a DataFrame.
- Validates:
  - Integers (`int`)
  - Longs (`int`)
  - Booleans (`true`/`false`)
  - Strings (non-empty)
  - JSON fields (stringified)
  - Naive dates (`%Y-%m-%d`)
  - Naive datetimes (`%Y-%m-%d %H:%M:%S`)
- Skips and logs invalid rows.
- Upserts valid rows into a table called `DATA`.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "aws_access_key_id": "<YOUR_AWS_ACCESS_KEY_ID>",
  "aws_secret_access_key": "<YOUR_AWS_SECRET_ACCESS_KEY>",
  "region_name": "<YOUR_AWS_REGION_NAME>",
  "bucket_name": "<YOUR_AWS_BUCKET_NAME>",
  "file_key": "<YOUR_AWS_FILE_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
boto3==1.35.97
pandas==2.2.3
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled via standard AWS credentials passed into the `boto3.client()` constructor.


## Pagination
Not Applicable for this connector, as it processes a single CSV file.


## Data handling
- CSV is read into a `pandas.DataFrame`.
- Each row is validated field-by-field.
- If any validation fails, the row is skipped.
- Valid rows are upserted using `op.upsert()`.


## Error handling
- Rows with invalid fields are skipped and logged using `log.warning()`.
- Errors include specific reasons (e.g., invalid format, missing value).
- The `print_error_message()` function outputs detailed validation failures.
- Sync state is checkpointed after processing all rows.


## Tables created
The connector creates a `DATA` table:

```json
{
  "table": "data",
  "primary_key": ["int_value"],
  "columns": {
    "int_value": "INT",
    "long_value": "LONG",
    "bool_value": "BOOLEAN",
    "string_value": "STRING",
    "json_value": "JSON",
    "naive_date_value": "NAIVE_DATE",
    "naive_date_time_value": "NAIVE_DATETIME"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.