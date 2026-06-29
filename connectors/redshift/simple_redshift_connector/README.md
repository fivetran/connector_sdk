# Redshift Connector Example

## Connector overview

This connector demonstrates how to sync records from a Redshift database using the Fivetran Connector SDK. It establishes a connection to a Redshift instance and incrementally extracts customer data based on an update timestamp, transforming the records into a standardized format for loading into the destination.

## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/redshift/simple_redshift_connector
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Direct connection to Redshift database
- Incremental data extraction based on timestamp
- Support for primary key identification

## Configuration file

The connector requires the following configuration parameters:

```
{
  "host": "<YOUR_REDSHIFT_HOST>",
  "database": "<YOUR_REDSHIFT_DATABASE>",
  "port": "<YOUR_REDSHIFT_PORT>",
  "user": "<YOUR_REDSHIFT_USER>",
  "password": "<YOUR_REDSHIFT_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the `redshift_connector` package to connect to Redshift databases.

```
redshift_connector
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses username and password authentication to connect to Redshift. The credentials are specified in the configuration file and passed to the `redshift_connector.connect()` function (refer to the `connect_to_redshift()` function).

To set up authentication:

1. Create a Redshift user with appropriate permissions to access the required tables.
2. Provide the username and password in the `configuration.json` file.
3. Ensure the user has `SELECT` permissions on the tables that need to be synced.

## Pagination

The connector implements a simple pagination strategy by fetching records in batches of 2 rows at a time (refer to the `cursor.fetchmany(2)` call in the `update()` function). After processing each batch, the connector:

- Performs upsert operations for each record
- Updates the state with the latest timestamp
- Performs a checkpoint operation to save progress

This approach ensures reliable processing of large datasets and allows the connector to resume from where it left off if interrupted.

## Data handling

The connector handles data as follows (refer to the `update()` function):

- Connects to the Redshift database using the provided configuration
- Retrieves the last sync timestamp from state (or uses a default date for initial sync)
- Executes a SQL query to fetch records modified after the last sync timestamp
- Transforms each database record into the target schema format
- Performs upsert operations for each record
- Maintains state with the latest processed timestamp

The `dt2str()` function handles timestamp formatting, converting database datetime objects to the required string format.

## Tables Created

The connector creates a single table named `customers` with the following schema (refer to the `schema()` function):

```json
 {
  "table": "customers",
  "primary_key": ["customer_id"],
  "columns": {
    "customer_id": "INT",
    "updated_at": "UTC_DATETIME"
  }
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
