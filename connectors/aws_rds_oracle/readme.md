# AWS RDS Oracle Connector Example

## Connector overview

This connector demonstrates how to sync records from an AWS RDS Oracle database using the Fivetran Connector SDK. It establishes a connection to an Oracle instance and incrementally extracts table data based on an update timestamp, transforming the records into a standardized format for loading into the destination.

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
fivetran init <project-path> --template connectors/aws_rds_oracle
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

-   Direct connection to AWS RDS Oracle database
-   Incremental data extraction based on the `LAST_UPDATED` column
-   Support for primary key identification
-   Easy configuration via JSON file

## Configuration file

The connector requires the following configuration parameters in `configuration.json`:

```json
{
"host": "<YOUR_RDS_ORACLE_HOST>",
"port": "<YOUR_AWS_RDS_ORACLE_PORT_DEFAULT_1521>",
"service_name": "<YOUR_SERVICE_NAME>",
"user": "<YOUR_DB_USERNAME>",
"password": "<YOUR_DB_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the `oracledb` package to connect to Oracle databases.

```
oracledb==3.3.0
```

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses username and password authentication to connect to Oracle. The credentials are specified in the configuration file and passed to the `oracledb.connect()` function (see the `connect_oracle()` function).

To set up authentication:

-   Create an Oracle user with appropriate permissions to access the required tables.
-   Provide the username and password in the `configuration.json` file.
-   Ensure the user has `SELECT` permissions on the tables that need to be synced.

## Pagination

The connector handles pagination by filtering rows with `_build_incremental_query()` and processing results in batches through `_iterate_records()`.The Oracle cursor uses `cursor.fetchmany()` with a configured `arraysize`, so the connector efficiently streams rows without requiring manual page tokens.

## Data handling

The connector handles data as follows (see the `update()` function):

1.  Connects to the Oracle database using the provided configuration.
2.  Retrieves the last sync timestamp from state (or uses a default date for the initial sync).
3.  Executes a SQL query to fetch records modified after the last sync timestamp.
4.  Transforms each database record into the target schema format.
5.  Performs upsert operations for each record.
6.  Maintains state with the latest processed timestamp.

## Error handling

- `validate_configuration()` verifies all required configuration keys before any work begins and raises descriptive errors when values are missing
- `connect_oracle()` catches invalid port values 
- `update()` function logs connection failures with `log.error()` before re-raising the exception.
- During syncs, the connector wraps Oracle interactions in a `try/finally` block to ensure the database connection is closed
- Progress checkpoints are created with `op.checkpoint()` to prevent re-processing if an error occurs mid-batch.

## Tables created

The connector is configured to sync the following table (see the `TABLES` list in `connector.py`):

```json
{
"table": "FIVETRAN_LOGMINER_TEST",
"primary_key": ["ID"],
"columns": {
    "ID": "INT",
    "NAME": "STRING",
    "LAST_UPDATED": "UTC_DATETIME"
  }
}
```

You can add more tables to the `TABLES` list in `connector.py` as needed.

## Additional files

This connector doesn’t require any additional files, apart from the standard ones listed below:

-   `connector.py` contains the `update()` and `schema()` implementations for this example.
-   `configuration.json` provides a placeholder configuration you can copy and fill with your Oracle credentials.
-   `requirements.txt` declares the Oracle driver dependency used at runtime.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
