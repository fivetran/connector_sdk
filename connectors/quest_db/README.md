# QuestDB Connector Example

## Connector overview

This connector syncs high-performance time series data from QuestDB to your Fivetran destination. QuestDB is a high-performance time-series database designed for rapid ingestion and fast SQL queries, commonly used in IoT sensor monitoring, financial market data, industrial telemetry, and capital markets applications. The connector retrieves data from specified tables using QuestDB's REST API and supports pagination for efficient processing of large datasets.

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
fivetran init <project-path> --template connectors/quest_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Syncs time series data from multiple QuestDB tables
- Timestamp-based incremental syncs which only fetch new records
- Supports pagination for handling large datasets efficiently
- Implements retry logic with exponential backoff for API rate limits and transient errors
- Configurable batch size for optimized data retrieval
- State management with checkpointing to support resumable syncs
- Optional HTTP basic authentication support
- Dynamic schema discovery based on table structure

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_QUESTDB_HOST>",
  "port": "<YOUR_QUESTDB_REST_API_PORT>",
  "username": "<YOUR_QUESTDB_USERNAME>",
  "password": "<YOUR_QUESTDB_PASSWORD>",
  "tables": "<COMMA_SEPARATED_TABLE_NAMES_TO_SYNC>",
  "batch_size": "<BATCH_SIZE_FOR_PAGINATION>",
  "timestamp_column": "<TIMESTAMP_COLUMN_NAME>"
}
```

Configuration parameters:


- `tables`  (required) - Comma-separated list of table names to sync (e.g., `SENSOR_DATA`, `MARKET_TICKS`)
- `host` (optional) - QuestDB server hostname or IP address (defaults to `localhost`)
- `port` (optional) - QuestDB REST API port (defaults to `9000`)
- `username` (optional) - QuestDB username for HTTP basic authentication
- `password` (optional) - QuestDB password for HTTP basic authentication
- `batch_size` (optional) - Number of records to fetch per API request (defaults to `1000`)
- `timestamp_column` (optional) - Column name for timestamp-based incremental sync (defaults to `timestamp`)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require a `requirements.txt` file as it only uses standard library modules and the `requests` library, which is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

QuestDB supports HTTP basic authentication for securing REST API access. Authentication is optional and depends on your QuestDB configuration.

To set up authentication:

1. Configure QuestDB with HTTP authentication by setting `http.user` and `http.password` in `server.conf`.
2. Provide the username and password in the `configuration.json` file.
3. If authentication is not configured in QuestDB, leave the `username` and `password` fields empty.

The connector builds HTTP Basic authentication headers automatically when credentials are provided (refer to the `build_auth_header()` function).

## Pagination

The connector implements pagination using SQL LIMIT clauses with incremental filtering:

- Uses SQL `LIMIT offset,batch_size` syntax to fetch data in chunks (refer to the `sync_table_data()` function)
- Configurable batch size via the `batch_size` configuration parameter
- Orders results by timestamp column for consistent incremental sync
- Continues fetching pages until an empty result set is returned
- Checkpoints state after processing every 5000 records to enable resumption

## Data handling

The connector processes data in the following manner (refer to the `update()` and `sync_table_data()` functions):

- Table iteration - Processes each table specified in the `tables` configuration parameter sequentially
- Incremental sync - Implements timestamp-based incremental sync where first sync fetches all records ordered by timestamp, and subsequent syncs only fetch records where timestamp is greater than last synced timestamp
- Pagination loop - For each table, fetches data in batches using offset-based pagination with configurable batch size
- Record transformation - Converts QuestDB response format to dictionary records with column names as keys
- Timestamp tracking - Tracks the maximum timestamp value seen in each batch for state management
- Unique primary key - Generates `_fivetran_synced_key` using format `{table}_{timestamp}_{row_index}` to ensure uniqueness
- Upsert operation - Inserts or updates each record in the destination table
- State management - Stores last synced timestamp per table and checkpoints progress after every 5000 records

All data is upserted to the destination, and the connector maintains timestamp state per table to support efficient incremental syncs without re-processing historical data.

## Error handling

The connector implements comprehensive error handling:

- Retry logic - HTTP errors (429, 500, 502, 503, 504) and network timeouts trigger exponential backoff retries up to 3 attempts (refer to the `execute_questdb_query()` function)
- Timeout handling - Request timeouts are caught and retried with exponential backoff
- Authentication errors - Non-retryable errors (401, 403) fail immediately without retry
- Connection errors - Network exceptions trigger retry logic with exponential backoff
- Query failures - SQL errors and malformed queries are logged and raised as RuntimeError

## Tables created

The connector creates tables based on the table names specified in the `tables` configuration parameter. The schema is dynamically discovered from QuestDB table structure (refer to the `schema()` function).

Each table includes:

- All columns from the source QuestDB table with data types inferred by Fivetran.
- A synthetic primary key (STRING), `_fivetran_synced_key`, generated by the connector for record identification.

Example schema for a table named `SENSOR_DATA`:

| Column Name | Data Type | Primary Key |
|-------------|-----------|-------------|
| `_fivetran_synced_key` | STRING | Yes |
| `timestamp` | UTC_DATETIME | No |
| `sensor_id` | STRING | No |
| `temperature` | DOUBLE | No |
| `humidity` | DOUBLE | No |
| `pressure` | DOUBLE | No |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
