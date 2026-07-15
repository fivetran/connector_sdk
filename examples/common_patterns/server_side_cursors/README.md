# Server-Side Cursors Example Connector

## Connector overview

This example demonstrates how to fetch data from a PostgreSQL database using different cursor strategies to minimize memory usage and optimize performance for large datasets. The connector showcases two cursor approaches:

- **CLIENT mode**: Uses a regular client-side cursor with explicit `fetchmany()` batching. Simpler to implement but may buffer larger result sets in client memory.
- **NAMED mode** (recommended): Uses a server-side (named) cursor that keeps rows on the server and streams them in controlled batches, significantly reducing client memory footprint for large table scans.

This pattern is essential for building connectors that need to handle large volumes of data efficiently without running into memory constraints. The connector implements incremental syncing based on a `last_updated` timestamp column and includes checkpointing after each batch to ensure sync reliability.

Note: This example implements the core logic of server-side cursors for PostgreSQL database. There are multiple source databases which support server-side cursors; the concepts here can be adapted accordingly.

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
fivetran init <project-path> --template examples/common_patterns/server_side_cursors
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Two cursor strategies (CLIENT and NAMED) for different performance and memory trade-offs
- Configurable batch size for controlled memory usage
- Incremental sync using `last_updated` timestamp tracking
- Automatic checkpointing after each batch for reliable sync resumption
- Comprehensive error handling with exception chaining for better debugging
- SSL support for secure database connections
- Memory-efficient streaming for large datasets

## Configuration file

The connector requires the following configuration keys in the `configuration.json` file:

```json
{
  "hostname": "<YOUR_POSTGRESQL_HOSTNAME>",
  "port": "<YOUR_POSTGRESQL_PORT>",
  "database": "<YOUR_POSTGRESQL_DATABASE_NAME>",
  "username": "<YOUR_POSTGRESQL_USERNAME>",
  "password": "<YOUR_POSTGRESQL_PASSWORD>",
  "sslmode": "<YOUR_SSL_MODE>",
  "table_name": "<YOUR_POSTGRESQL_TABLE_NAME>",
  "batch_size": "<YOUR_BATCH_SIZE>",
  "cursor_mode": "<YOUR_CURSOR_MODE>"
}
```
Configuration parameters:

- `hostname` (required): PostgreSQL server hostname or IP address.
- `port` (required): PostgreSQL server port (typically 5432).
- `database` (required): Name of the database to connect to.
- `username` (required): Database username for authentication.
- `password` (required): Database password for authentication.
- `table_name` (required): Name of the source table to sync data from.
- `sslmode` (optional): SSL mode for connection security. Valid values: `disable`, `require`, or empty string. Defaults to `disable`.
- `batch_size` (optional): Number of rows to fetch per batch. Defaults to `5000`. Adjust based on memory constraints and network latency.
- `cursor_mode` (optional): Cursor strategy to use. Valid values: `CLIENT` or `NAMED`. Defaults to `NAMED`.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The `requirements.txt` file specifies the Python libraries required by the connector:

```
psycopg2-binary==2.9.10
```

- `psycopg2-binary`: PostgreSQL database adapter for Python, used to establish connections and execute queries against PostgreSQL databases.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses standard PostgreSQL username/password authentication. To obtain the necessary credentials:

1. Contact your PostgreSQL database administrator to obtain:
   - Database hostname and port
   - Database name
   - Username and password with READ permissions on the target table

2. Ensure the database user has the following minimum permissions:
   - `SELECT` privilege on the target table
   - `CONNECT` privilege on the database

3. For server-side cursors (NAMED mode), ensure the database allows persistent connections during the sync process.


## Pagination

The connector does not implement traditional pagination since it uses cursor-based fetching to retrieve data in batches. Depending on the selected `cursor_mode`, the connector fetches rows in controlled batches using either a client-side cursor or a server-side named cursor.


## Data handling

The connector supports two cursor strategies, configurable via the `cursor_mode` parameter. Refer to functions `_regular_client_cursor_stream` and `_named_server_side_cursor_stream`.

The `CLIENT` mode uses a regular client-side cursor with explicit `fetchmany()` batching.

- Executes `SELECT * FROM table WHERE last_updated > timestamp ORDER BY last_updated`
- Uses a default (unnamed) cursor and repeatedly calls `fetchmany(batch_size)`
- The driver may buffer the entire result set client-side, depending on implementation

The `NAMED` mode uses a server-side (named) cursor for memory-efficient streaming.

- Creates a named cursor (portal) on the server; rows remain on the server
- Sets `cursor.itersize = batch_size` to hint how many rows to fetch per network round-trip
- Repeatedly calls `fetchmany(batch_size)`; the server sends rows in small chunks
- Uses explicit transaction management to ensure cursor validity throughout iteration


The connector implements incremental data synchronization using a timestamp-based approach. Refer to the `update` function.

The incremental sync process works as follows:
1. Retrieves the `last_updated` timestamp from the state dictionary (defaults to `1990-01-01T00:00:00+00:00` for initial sync).
2. Queries the source table for rows where `last_updated > last_synced_timestamp`, ordered by `last_updated`.
3. Fetches data in configurable batches using the selected cursor strategy.
4. Upserts each row to the destination table using `op.upsert()`.
5. Tracks the maximum `last_updated` timestamp seen in the current batch.
6. Checkpoints the state with the new `last_updated` timestamp after processing each batch.


## Error handling

The connector implements comprehensive error handling to ensure reliability and debuggability.

- Validates all required configuration parameters are present and non-empty
- Validates `sslmode` value against allowed options
- Raises `ValueError` with descriptive messages for invalid configurations
- Wraps connection exceptions in `RuntimeError` with context
- Preserves original exception chain using `from e` for better debugging
- Logs successful connections for operational visibility
- Implements try/except/finally blocks to ensure cursor cleanup


## Tables created

The connector creates a single table in the destination based on the `table_name` configuration parameter. For example, `table_name` is set to `people`, the following table will be created:

### `PEOPLE` 

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key; unique identifier for each row. |
| `last_updated` | UTC_DATETIME | Timestamp of when the row was last updated; used for incremental syncs. |
| Additional columns | (inferred) | All other columns from the source table are automatically inferred and synced. |

The `last_updated` column is critical for incremental syncing. Ensure your source table has this column and that it's updated whenever a row changes.


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
