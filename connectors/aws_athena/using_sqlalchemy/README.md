# AWS Athena Connector Example - Using SQLAlchemy and PyAthena

## Connector overview
This connector demonstrates how to use SQLAlchemy with PyAthena to connect to Amazon Athena, execute a query, and stream the results to Fivetran using the Connector SDK. It shows how to work with paginated result sets using `fetchmany()` and how to construct Athena-compatible connection strings using credentials and S3 staging configuration.

This pattern is helpful when:
- You want to connect to Athena using SQLAlchemy ORM abstraction.
- You prefer PyAthena’s REST-based driver over raw `boto3` usage.
- You need to work with large Athena query results efficiently.

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
fivetran init <project-path> --template connectors/aws_athena/using_sqlalchemy
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to Athena using SQLAlchemy + PyAthena REST dialect.
- Streams query results in chunks using `fetchmany()`.
- Emits each row using `op.upsert()` into the `CUSTOMERS` table.
- Performs state checkpointing to support resumable syncs.


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
PyAthena
sqlalchemy
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled via the credentials passed into the SQLAlchemy connection string:
```
awsathena+rest://<access_key>:<secret_key>@athena.<region>.amazonaws.com:443/<database>?s3_staging_dir=<bucket>
```


## Pagination
- The result set is streamed in chunks using `result.fetchmany(2)`.
- This helps prevent memory overload for large Athena results.


## Data handling
- Query executed: `SELECT * FROM test_rows`.
- Assumes the table contains: `customer_id`, `first_name`, `last_name`, `email`.
- Each row is upserted as a dictionary using `op.upsert()`.

## Error handling
- Query results are paginated safely via `fetchmany()`.
- If the connection string is invalid or credentials are wrong, the connector will raise an error.
- Consider wrapping query execution in a `try/except` block for production use.


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