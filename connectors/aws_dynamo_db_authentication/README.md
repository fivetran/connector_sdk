# AWS DynamoDB Connector Using IAM Role Authentication

## Connector overview
This connector demonstrates how to sync data from Amazon DynamoDB using the Fivetran Connector SDK and AWS IAM role-based authentication. It authenticates using assumed IAM roles via STS, discovers all tables, extracts their primary keys dynamically, and syncs each table using a parallel scan.

This example highlights:
- Authenticating with AWS via role assumption.
- Dynamically generating schema from DynamoDB metadata.
- Efficient record fetching with `aws_dynamodb_parallel_scan`.
- Safely syncing multiple tables in a single connector.

Refer to [Boto3 DynamoDB Docs](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html) for more detail on AWS client behavior.


## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/aws_dynamo_db_authentication
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Uses `boto3` STS to assume a role for DynamoDB access.
- Discovers all available tables using `list_tables()`.
- Dynamically builds schema by querying each table’s key schema.
- Uses `aws_dynamodb_parallel_scan` to perform fast, concurrent scans.
- Syncs paginated records via `op.upsert()`.
- Checkpoints sync state using `op.checkpoint()`.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "AWS_ACCESS_KEY_ID": "<YOUR_AWS_ACCESS_KEY_ID>",
  "AWS_SECRET_ACCESS_KEY": "<YOUR_AWS_SECRET_ACCESS_KEY>",
  "ROLE_ARN": "<YOUR_ROLE_ARN>",
  "REGION": "<YOUR_REGION>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
aws_dynamodb_parallel_scan==1.1.0
boto3==1.37.4
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector authenticates by:
- Using `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to create an STS client.
- Calling `sts.assume_role()` with the `ROLE_ARN`.
- Using the assumed role’s credentials to access DynamoDB.


## Pagination
Pagination is handled via:
- `aws_dynamodb_parallel_scan.get_paginator(`)
- Parallel scanning with `TotalSegments=4` and `Limit=10` per page.


## Data handling
- Schema is inferred by calling `describe_table()` on each table.
- Keys and values from each DynamoDB record are normalized using `map_item()`.
- Nested arrays are converted to strings.
- All tables are synced in parallel and checkpointed.


## Error handling
- Errors during schema discovery or sync are logged with `log.error()`.
- Exceptions are re-raised to surface failures in the connector.
- You can extend error handling with retry/backoff for robustness.


## Tables created
The connector creates a `CUSTOMERS` table:

```json
{
  "table": "customers",
  "primary_key": ["customer_id"],
  "columns": "inferred"
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.