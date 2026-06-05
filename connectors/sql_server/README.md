# SQL Server Connector Example

## Connector overview
This connector demonstrates how to connect to a Microsoft SQL Server database using `pyodbc` and the Fivetran Connector SDK. It retrieves records from the `EMPLOYEE_DETAILS` table and syncs only those that have changed since the last run, using the `updated_time` column for incremental replication.

This example covers:
- SQL Server authentication via ODBC.
- Full table schema definition with primary keys.
- Date-based incremental sync logic.
- Batched reads using `fetchmany()`.
- State checkpointing after each run.


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
fivetran init <project-path> --template connectors/sql_server
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to a SQL Server database using `pyodbc`.
- Defines a static schema using the `schema()` method.
- Uses `updated_time` to identify records modified since the last sync.
- Supports batched record processing using `fetchmany()`.
- Emits each row with `op.upsert()` and saves progress with `op.checkpoint()`.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "driver": "YOUR_ODBC_DRIVER_LIKE='{ODBC Driver 18 for SQL Server}'",
  "server": "YOUR_SERVER_ADDRESS_LIKE='tcp:sql_test.database.windows.net,1433'",
  "database": "YOUR_DATABASE_NAME",
  "user": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
pyodbc
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled via the SQL Server username and password specified in the configuration.


## Pagination
The connector uses cursor-based pagination via the `updated_time` column. Batching is implemented using `cursor.fetchmany(batch_size)`. This allows large datasets to be processed incrementally and avoids loading the full result set into memory.


## Data handling
- The connector only syncs records where `updated_time > last_checkpoint_time`.
- All fields are explicitly mapped in the schema.
- Sync state is updated to the latest `updated_time` seen in the batch.


## Error handling
- Database connection errors are caught and logged with descriptive messages.
- Queries are validated before execution.
- Connections and cursors are closed safely with `try/finally` blocks.
- State is checkpointed even if only partial sync is completed.


## Tables created
The connector creates an `EMPLOYEE_DETAILS` table:

```json
{
  "table": "employee_details",
  "primary_key": ["employee_id"],
  "columns": {
    "employee_id": "INT",
    "hire_date": "NAIVE_DATE",
    "salary": "LONG",
    "updated_time": "NAIVE_DATETIME"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.