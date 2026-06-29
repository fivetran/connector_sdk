# TiDB Connector Example

## Connector overview
This example demonstrates a source connector that reads rows from a TiDB database and upserts them into a Fivetran destination using the Connector SDK. It supports incremental replication based on a `created_at` timestamp, vector column parsing (optional), and stores per-table progress in the connector `state`.

The connector is well suited for the following use cases: 
- Incremental sync of application tables
- Vector/embedding export for ML workflows
- Incremental change capture for analytics

## Contributor
This example was contributed by [Nikhil Mankani](https://www.linkedin.com/in/nikhilmankani/).

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
fivetran init <project-path> --template connectors/tidb
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Incremental replication driven by `created_at` timestamp.
- Configurable table list and primary keys via `TABLES_PRIMARY_KEY_COLUMNS`.
- Optional support for vector columns: Parse serialized embeddings into proper JSON lists via `VECTOR_TABLES_DATA`.
- Robust error handling with per-table error markers stored in the connector `state`.

## Configuration file
The connector expects a `configuration.json` file when running locally.

```
{
  "TIDB_HOST": "<YOUR_TIDB_HOST>",
  "TIDB_USER": "<YOUR_TIDB_USERNAME>",
  "TIDB_PASS": "<YOUR_TIDB_PASSWORD>",
  "TIDB_PORT": "<YOUR_TIDB_PORT>",
  "TIDB_DATABASE": "<YOUR_TIDB_DATABASE>",
  "TABLES_PRIMARY_KEY_COLUMNS": "<JSON_STRING_OF_TABLE_TO_PRIMARY_KEY_MAPPING>",
  "VECTOR_TABLES_DATA": "<JSON_STRING_OF_VECTOR_TABLE_CONFIGURATION>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

Configuration parameters:

- `TIDB_HOST` (required): Hostname or IP address of the TiDB server.
- `TIDB_USER` (required): Username for TiDB connection.
- `TIDB_PASS` (required): Password for the TiDB user.
- `TIDB_PORT` (required): Port number for TiDB connection.
- `TIDB_DATABASE` (required): Name of your TiDB database.
- `TABLES_PRIMARY_KEY_COLUMNS` (required): A JSON object where keys are table names and values are the primary key column names.
- `VECTOR_TABLES_DATA` (optional): A JSON object for tables containing vector/embedding columns. Each table requires:
  - `primary_key_column`: The primary key column name.
  - `vector_column`: The column containing vector data.


## Requirements file

Include the following dependencies in your `requirements.txt` file:

```
pytidb>=0.0.11
certifi>=2025.8.3
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses username and password authentication to connect to TiDB. The credentials are specified in the configuration file.

To set up authentication:

1. Create a TiDB user with appropriate permissions to access the required tables.
2. Ensure the user has `SELECT` permissions on the tables you want to sync.
3. Provide the username and password in the `configuration.json` file.

For details on creating users and granting privileges, see [TiDB documentation](https://docs.pingcap.com/tidb/stable/manage-users-and-privileges).

Note: For production usage, use secure secret storage and avoid checking credentials into source control.

## Pagination
The connector implements offset-based pagination using the limit and offset parameters in the `fetch_and_upsert_data` function, processing data in batches of 50 rows at a time. This approach helps manage memory usage and allows incremental reads of large tables without loading all matching rows into memory at once. If you need to adjust the batch size or use a different pagination strategy (such as keyset pagination), you can modify the relevant logic in `fetch_and_upsert_data`. For tables that require a different incremental column or cursor-based pagination, update the function accordingly.

## Data handling
- Rows are fetched and passed to `process_row` for normalization.
- `process_row` ensures naive datetimes are made timezone-aware (UTC) and attempts to parse vector columns into Python lists when `VECTOR_TABLES_DATA` is configured.
- The declared schema (the `schema` function) depends on the `TABLES_PRIMARY_KEY_COLUMNS` and optional `VECTOR_TABLES_DATA` configuration for typed JSON columns.

## Error handling
- Query-level failures (for example, missing `created_at` column) are logged, added to `state` under `{table_name}_last_error`, and the connector checkpoints state so operators can inspect errors without losing progress on other tables. See `fetch_and_upsert_data`.
- Row-level failures are logged, and a sample of the row is stored in state under `{table_name}_last_row_error_sample` for debugging. See `fetch_and_upsert_data` and `process_row`.
- Connection-level failures are recorded in the state under `last_connection_error`, and the exception is raised to allow the runtime to retry according to its backoff policy. See `create_tidb_connection` and `update`.

## Tables created

The connector creates tables based on the `TABLES_PRIMARY_KEY_COLUMNS` configuration. Each table is defined with its primary key. The SDK runtime handles creating destination tables according to these schema declarations.

Example schema for a typical configuration:

```json
{
  "table": "customers",
  "primary_key": ["customer_id"]
}
```

For vector tables (if configured), the schema includes typed JSON columns:

```json
{
  "table": "product_embeddings",
  "primary_key": ["product_id"],
  "columns": {
    "embedding_vector": "JSON"
  }
}
```

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
