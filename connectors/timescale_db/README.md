# TimescaleDB Example Connector

## Connector overview

The TimescaleDB connector allows you to extract time-series data and vector data from a TimescaleDB database and load it into your destination. This connector is designed to handle vector data efficiently using incremental sync patterns with proper checkpointing.

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
fivetran init <project-path> --template connectors/timescale_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connects to TimescaleDb database using `psycopg2`
- Supports incremental data extraction using timestamps with checkpointing
- Handles both standard time-series data and vector data
- Uses server-side cursors for memory-efficient data streaming
- Serialization of datetime objects and vector data

## Configuration file

The connector requires the following configuration parameters in your `configuration.json` file:

```json
{
  "HOST": "<YOUR_TIMESCALEDB_DATABASE_HOST>",
  "PORT": "<YOUR_TIMESCALEDB_DATABASE_PORT>",
  "DATABASE": "<YOUR_TIMESCALEDB_DATABASE_NAME>",
  "USERNAME": "<YOUR_TIMESCALEDB_DATABASE_USERNAME>",
  "PASSWORD": "<YOUR_TIMESCALEDB_DATABASE_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the `psycopg2` library to connect to TimescaleDB. Include it in your `requirements.txt` file:

```
psycopg2-binary==2.9.10
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses standard `PostgreSQL` authentication with a `username` and `password`. These credentials must be provided in the configuration file. Ensure the database user has appropriate read permissions on the tables you want to sync.

## Pagination

Pagination is handled through server-side cursors in the TimescaleDB client (refer to `timescaleclient.py` lines 85-112).

The connector:

1. Creates a named cursor during connection initialization.
2. Executes a time-bounded query to fetch only new data.
3. Uses `fetchmany()` with a `batch_size` parameter (default: 1000) to retrieve rows incrementally.
4. Processes each batch and upsert records before fetching the next batch. This approach prevents loading the entire result set into memory at once, making the connector suitable for large datasets.

## Data handling

The connector processes and transforms data as follows (refer to `timescaleclient.py` lines 148-158):

1. Queries data from TimescaleDb filtered by a timestamp column.
2. Converts row results to dictionaries using psycopg2's `RealDictCursor`.
3. Converts vector data (iterables) to lists for proper JSON serialization.
4. Tracks the latest timestamp for each table to support incremental syncs.

## Error handling

Error handling is implemented at several levels:

1. Connection errors: Wrapped in a `ConnectionError` with a descriptive message (line 44 in `timescaleclient.py`).
2. Configuration validation: Checks for required parameters before attempting connection (lines 24-32 in `connector.py`).
3. Graceful disconnect: Ensures all database resources are properly closed (lines 48-56 in `timescaleclient.py`).
4. Logging: Uses SDK logging facilities to record important operations and potential issues.

## Tables created

The connector creates two tables in the destination. `sensor_data`contains time-series sensor data and `sensor_embeddings` contains vector embeddings related to sensors.

The schemas for these tables are as follows:

```json
{
  "table": "sensor_data",
  "primary_key": ["sensor_id"],  
  "columns":{
    "sensor_id": "INT",
    "time": "UTC_DATETIME"
  }
}
```

```json
{
  "table": "sensor_embeddings",
  "primary_key": ["id"],
  "columns": {
    "id": "INT",
    "embedding_type": "STRING",
    "vector_data": "JSON",
    "created_at": "UTC_DATETIME"
  }
}
```

## Additional files

- `timescaleclient.py` – This file handles the connection and data extraction from `TimescaleDb`, implementing server-side cursors, batch processing, and data serialization.


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
