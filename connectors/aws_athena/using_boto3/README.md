# AWS Athena Connector Example - Using Boto3

## Connector overview
This example demonstrates how to sync data from Amazon Athena into a Fivetran destination table using the Fivetran Connector SDK and the `boto3` AWS SDK for Python. The connector executes a query against Athena, polls for the result, and streams the resulting rows using `op.upsert()`.

This pattern is ideal for:
- Syncing query results from Athena-backed datasets.
- Working with large result sets using paginated tokens (`NextToken`).
- Handling cloud data access via AWS credentials.

Note: You must provide your AWS credentials and an S3 staging location for Athena query results.


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
fivetran init <project-path> --template connectors/aws_athena/using_boto3
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to AWS Athena using `boto3`.
- Starts a query execution and polls until complete.
- Uses `get_query_results()` to fetch paginated results using NextToken.
- Transforms Athena records into Python-native types.
- Uses `op.upsert()` to sync rows into the customers table.
- Uses `op.checkpoint()` to persist state.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "aws_access_key_id": "<YOUR_AWS_ACCESS_KEY_ID>",
  "aws_secret_access_key": "<YOUR_AWS_SECRETS_ACCESS_KEY>",
  "region_name": "<YOUR_REGION_NAME>",
  "database_name": "<YOUR_DATABASE_NAME>",
  "s3_staging_dir": "<YOUR_S3_STAGING_DIRECTORY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
boto3
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
AWS authentication is handled via the `boto3.client()` function using the credentials provided in the configuration file. Make sure these credentials are secure and limited in scope (e.g., read-only access).


## Pagination
The connector handles paginated Athena results using `NextToken`:
- It skips the first row (header).
- If `NextToken` is present, it fetches the next page.
- Continues until all rows are processed.


## Data handling
- Query string: `SELECT * FROM test_rows`.
- Response rows are transformed and emitted to the `CUSTOMERS` table.
- Supported Athena data types include `VarCharValue`, `BigIntValue`, `DoubleValue`, `BooleanValue`.
- Null fields are handled and converted to Python `None`.


## Error handling
- If Athena query fails, the sync ends and prints the failure state.
- The connector checks for terminal statuses: `SUCCEEDED`, `FAILED`, or `CANCELLED`.
- All paginated results are upserted directly as they are retrieved.
- You can enhance it by:
  - Adding timeout logic for long-running queries.
  - Adding retry handling for transient AWS errors.


## Tables created
The connector creates a `CUSTOMERS` table:

```json
{
  "table": "customers",
  "primary_key": ["customer_id"],
  "columns": {
    "customer_id": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.