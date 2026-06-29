# DragonflyDB Connector Example

## Connector overview

This connector syncs high-performance in-memory data from DragonflyDB to your Fivetran destination. DragonflyDB is a modern, Redis-compatible in-memory datastore designed for cloud environments. The connector enables you to replicate caching layers, session stores, real-time analytics data, rate limiters, and high-throughput key-value stores from DragonflyDB to your data warehouse for historical analysis, compliance, and business intelligence.

The connector is particularly valuable for organizations using DragonflyDB as a high-performance data layer that need to analyze historical patterns, monitor cache effectiveness, track session behavior, or maintain audit trails of their in-memory data operations.

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
fivetran init <project-path> --template connectors/dragonfly_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Only syncs new or modified keys using deterministic MD5 hashing
- Aautomatically detects and removes keys deleted from DragonflyDB
- Automatic detection and timestamp-based incremental sync for RedisTimeSeries keys
- Synchronizes all Redis-compatible data types: strings, hashes, lists, sets, and sorted sets
- High-performance data extraction leveraging DragonflyDB's multi-threaded architecture
- Configurable key pattern filtering for targeted data extraction
- Captures comprehensive metadata including TTL, data type, size, and timestamps
- Implements cursor-based pagination using `SCAN` for memory-efficient processing
- Resumable syncs with state management and checkpointing every 1000 records
- Multi-database support for database numbers 0-15
- SSL/TLS connection support for secure communication
- Password and username authentication for protected instances

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_DRAGONFLY_HOST>",
  "port": "<YOUR_DRAGONFLY_PORT>",
  "username": "<YOUR_DRAGONFLY_USERNAME>",
  "password": "<YOUR_DRAGONFLY_PASSWORD>",
  "database": "<YOUR_DRAGONFLY_DATABASE_NUMBER>",
  "ssl": "<TRUE_OR_FALSE>",
  "table_name": "<YOUR_DESTINATION_TABLE_NAME>",
  "key_pattern": "<YOUR_KEY_PATTERN>",
  "batch_size": "<YOUR_BATCH_SIZE>"
}
```

Configuration parameters:

- `host` (required) - DragonflyDB server hostname or IP address.
- `port` (required) - DragonflyDB server port (typically 6379).
- `username` (optional) - DragonflyDB authentication username.
- `password` (optional) - DragonflyDB authentication password.
- `database` (optional) - Database number 0-15 (defaults to `0`).
- `ssl` (optional) - Enable SSL/TLS connection - `true` or `false` (defaults to `false`).
- `table_name` (optional) - Destination table name (defaults to `dragonfly_data`).
- `key_pattern` (optional) - Pattern to match keys - supports wildcards (defaults to `*` for all keys).
- `batch_size` (optional) - Number of keys to process per batch (defaults to `100`).

Key pattern examples:
- `*` - All keys
- `cache:*` - All cache keys
- `session:*` - All session keys
- `user:*:profile` - All user profile keys
- `rate_limit:*` - All rate limiter keys

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector uses the `redis` library for connecting to DragonflyDB (Redis-compatible protocol):

```
redis
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector supports flexible authentication options compatible with DragonflyDB deployments (refer to the `build_connection_params` function in [connector.py](connector.py)).

Basic configuration without authentication:
```json
{
  "host": "localhost",
  "port": "6379",
  "password": ""
}
```

Password-protected DragonflyDB:
```json
{
  "host": "dragonfly.example.com",
  "port": "6379",
  "password": "<YOUR_PASSWORD>"
}
```

Username and password authentication:
```json
{
  "host": "dragonfly.example.com",
  "port": "6379",
  "username": "<YOUR_USERNAME>",
  "password": "<YOUR_PASSWORD>"
}
```

SSL/TLS configuration:
```json
{
  "host": "dragonfly.example.com",
  "port": "6380",
  "username": "<YOUR_USERNAME>",
  "password": "<YOUR_PASSWORD>",
  "ssl": "true"
}
```

## Pagination

The connector implements the `SCAN` command for efficient, non-blocking key iteration (refer to the `scan_keys` function in [connector.py](connector.py)):

- Uses cursor-based iteration starting from cursor position 0
- Processes keys in configurable batches (default: 100 keys per `SCAN` operation)
- Returns next cursor position for resuming iteration
- Cursor = 0 indicates scan completion
- Implements checkpointing every 1000 keys in the `sync_dragonfly_data` function
- State tracking allows resumption from last cursor position after interruptions

The `SCAN` operation is memory-efficient, non-blocking, and allows other DragonflyDB operations to continue during data extraction.

## Data handling

The connector performs comprehensive data extraction and transformation (refer to the following functions in [connector.py](connector.py)):

- `get_key_info` - Retrieves comprehensive information about a key
- `extract_value_by_type` - Handles type-specific value extraction
- `process_batch` - Processes batches of keys
- `sync_dragonfly_data` - Orchestrates the complete sync process

Data handling workflow:

1. Key discovery - Uses `SCAN` command with optional pattern filtering to discover matching keys
2. Type detection - Identifies data type for each key (string, hash, list, set, zset)
3. Value extraction - Retrieves values using type-specific commands:
  - Strings - Direct value extraction with `GET`
  - Hashes - Extracted with `HGETALL` and converted to JSON objects
  - Lists - Retrieved with `LRANGE` and converted to JSON arrays
  - Sets - Extracted with `SMEMBERS` and converted to JSON arrays
  - Sorted sets - Retrieved with `ZRANGE` including scores, converted to JSON arrays of [member, score] pairs
4. Metadata collection - Gathers TTL (Time-To-Live), size, and timestamp for each key
5. Upsert operations - All records are upserted to handle both new and updated keys

## Error handling

The connector implements comprehensive error handling strategies (refer to the following functions in [connector.py](connector.py)):

- Connection validation with retry logic (`create_dragonfly_client` function) - Tests DragonflyDB connectivity during client creation with ping operation, implements exponential backoff retry logic for transient failures (max 3 attempts), handles SSL configuration errors, raises RuntimeError on failure.
- Configuration validation (`validate_configuration` function) - Ensures required parameters (host, port) are present, raises ValueError for missing configuration.
- Key access errors (`get_key_info` function) - Handles expired or deleted keys gracefully during scanning, logs warnings for failed key access, returns error record instead of failing.
- Network timeouts (`build_connection_params` function) - Configured 30-second socket timeout for connection resilience.
- Connection cleanup (`update` function finally block) - Ensures connections are properly closed even on errors using try-finally pattern.

## Tables created

The connector creates a table in the destination based on your configuration (configurable via the `table_name` parameter, defaults to `DRAGONFLY_DATA`):

| Column | Type | Description |
|--------|------|-------------|
| `key` | STRING | Key name (Primary Key) |
| `value` | STRING | Value - JSON string for complex types (hashes, lists, sets, sorted sets) |
| `data_type` | STRING | Data type: string, hash, list, set, or zset |
| `ttl` | INT | Time to live in seconds (-1 = no expiry, -2 = expired/non-existent) |
| `last_modified` | UTC_DATETIME | Timestamp when key was last processed by connector |
| `size` | INT | Size metric - length for strings, count for collections |

The table uses `key` as the primary key, enabling upserts for handling updated values across syncs.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
