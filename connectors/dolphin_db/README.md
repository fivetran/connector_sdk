# DolphinDB Connector Example

## Connector overview

This connector syncs data from DolphinDB, a high-performance time series columnar database. The connector implements efficient data processing through batching to manage large datasets without memory overflow. The connector supports incremental updates, ensuring that only new or modified data is synced after the initial load.

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
fivetran init <project-path> --template connectors/dolphin_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connects to DolphinDB databases and syncs data
- Processes large datasets efficiently using batch processing
- Implements checkpointing for resumable syncs and handles incremental updates using timestamp-based tracking
- Provides clear logging for monitoring and debugging

## Configuration file

The connector requires the following configuration parameters for connecting to the `DolphinDB` source:

```json
{
  "HOST": "<YOUR_DOLPHINDB_HOST>",
  "PORT": "<YOUR_DOLPHINDB_PORT>",
  "DATABASE": "<YOUR_DOLPHINDB_DATABASE>",
  "TABLE_NAME": "<YOUR_DOLPHINDB_TABLE_NAME>",
  "USERNAME": "<YOUR_DOLPHINDB_USERNAME>",
  "PASSWORD": "<YOUR_DOLPHINDB_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the following Python packages:

```
numpy==1.17.3
pandas==1.3.5
dolphindb==3.0.2.4
pydolphindb==1.1.2
sqlalchemy==1.4.54
```

The `pydolphindb` package is used to connect to the DolphinDB database, while `pandas` and `numpy` are used for data manipulation and processing. `SQLAlchemy` is included for database interaction. `dolphindb` is a pre-requisite for `pydolphindb`, which is a Python client for DolphinDB.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

Authentication with DolphinDB is handled using `username` and `password` credentials provided in the `configuration.json` file. Ensure the configured user has appropriate permissions to read from the specified table.

## Data handling

The connector performs the following data handling operations:

1. Fetches data from DolphinDB using configurable batch sizes (default: 1000 rows).
2. Maintains state between runs using the `last_timestamp`. This allows the connector to only fetch new or updated records since the last successful sync.
3. The data is fetched in batches to prevent memory overflow errors, especially for large datasets. Refer to `execute_query_and_upsert` function for the implementation of batch processing and checkpointing.

## Error handling

The connector implements several error handling mechanisms:

1. Configuration validation to ensure all required parameters are provided (refer to `validate_configuration` function).
2. Exception handling for database connection failures with descriptive error messages.
3. Proper resource cleanup in a `finally` block to ensure database connections are closed.

## Tables created

The connector creates a single table named `trade` in the destination database. The table schema is defined as follows:

```json
{
  "table": "trade",
  "primary_key": [],
  "columns": {
    "symbol": "STRING",
    "timestamp": "UTC_DATETIME",
    "price": "FLOAT",
    "volume": "INT"
  }
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.