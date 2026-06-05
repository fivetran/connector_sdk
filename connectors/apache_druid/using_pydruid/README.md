# Apache Druid Connector Example

## Connector overview

This connector syncs data from Apache Druid datasources into Fivetran using the PyDruid Python library, allowing you to replicate event and analytics data into your destination. The connector leverages PyDruid's native query capabilities and supports incremental sync using time-based filtering. Each datasource in your Druid cluster is synced as a separate table.

Apache Druid is a real-time analytics database designed for fast aggregations and queries on large event datasets. This PyDruid-based connector provides enhanced performance and native Druid query optimization for accessing your Druid datasources for analytics and reporting in your data warehouse.

The connector can connect to Apache Druid clusters that either allow unauthenticated access or use HTTP Basic authentication.

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
fivetran init <project-path> --template connectors/apache_druid/using_pydruid
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental sync - Fetches only new records since the last sync using time-based filtering on the `__time` column
- Multi-datasource support - Syncs multiple Druid datasources in a single connector, each mapped to a separate destination table
- Native PyDruid queries - Uses PyDruid's native query capabilities for optimized data retrieval
- Per-datasource state tracking - Tracks sync progress independently per datasource
- Basic authentication support - Optional username and password authentication for secured Druid clusters

## Configuration file

The connector requires a `configuration.json` file with the Druid connection details.

```json
{
  "host": "<YOUR_DRUID_HOST>",
  "port": "<YOUR_DRUID_PORT>",
  "protocol": "https",
  "datasources": "<YOUR_DRUID_DATASOURCES>"
}
```

For Druid clusters that require authentication:

```json
{
  "host": "<YOUR_DRUID_HOST>",
  "port": "<YOUR_DRUID_PORT>",
  "protocol": "https",
  "datasources": "<YOUR_DRUID_DATASOURCES>",
  "username": "<YOUR_DRUID_USERNAME>",
  "password": "<YOUR_DRUID_PASSWORD>"
}
```

Configuration parameters:
- `host` - Hostname or IP address of your Druid broker node (required)
- `port` - Port number for the Druid broker, typically 8888 (required)
- `datasources` - Comma-separated list of Druid datasource names to sync (required)
- `protocol` - Connection protocol: "http" or "https" (optional, defaults to "https")
- `username` - Username for basic authentication (optional)
- `password` - Password for basic authentication (optional)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector requires the PyDruid library for native Druid connectivity:

```
pydruid==0.6.5
```

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector works with Apache Druid clusters that either allow unauthenticated access or use HTTP Basic authentication.

If your Druid cluster requires HTTP Basic authentication, provide the `username` and `password` values in the connector configuration. The connector uses PyDruid to include Basic authentication headers in all requests.

If credentials are not provided, requests are sent without authentication.

## Pagination

This connector does not use traditional API pagination since Apache Druid uses scan queries rather than paginated endpoints. Instead, the connector implements batching and progress tracking:

- Batch processing - Processes data in configurable batches of 10,000 records per datasource request (`BATCH_SIZE`)
- Progress tracking - Logs sync progress every 1,000 records processed
- Incremental sync - Uses time-based filtering on the `__time` column to fetch only new records since the last sync
- Checkpointing - Saves sync state every 1,000 records to enable safe resumption from interruptions

## Data handling

The connector efficiently processes large datasets from Druid datasources:

### Query approach
- Uses Druid's native scan queries for optimal data retrieval through PyDruid
- Supports various timestamp formats (Unix milliseconds, ISO strings, datetime objects)
- Automatic timezone handling for proper incremental sync

### Processing workflow
1. Configuration validation - Validates all required fields before making any API calls
2. PyDruid client setup - Initializes client with authentication settings and connection parameters
3. Incremental filtering - Reads per-datasource last sync timestamp from state (defaults to epoch for full fetch)
4. Query execution - Uses PyDruid scan queries with time-based filtering
5. Data upserting - Each record is upserted to the corresponding destination table
6. State checkpointing - Saves the maximum `__time` seen per datasource after processing

## Error handling

The connector implements robust error handling for reliable data synchronization:

- PyDruid client exceptions - Handles PyDruid client and connection errors gracefully
- Retry logic with exponential backoff - Automatically retries failed requests with configurable delays
- Resource management - Proper connection cleanup and efficient memory usage
- Recovery mechanisms - Checkpointing enables safe resumption from failures or interruptions

## Tables created

The connector creates one table per Druid datasource specified in the `datasources` configuration. Table names are derived from datasource names by replacing any character that is not a letter, digit, or underscore with an underscore.

### Schema structure

Each table follows this general schema structure:

| Column Name | Data Type | Primary Key | Description |
|-------------|-----------|-------------|-------------|
| `__time` | `TIMESTAMP` | No | Event timestamp (always present in Druid datasources) |
| `_fivetran_id` | `STRING` | Yes | Fivetran-generated unique identifier (hash of row values) |
| `_fivetran_synced` | `TIMESTAMP` | No | Fivetran sync timestamp |
| `[dimension_columns]` | `STRING/NUMERIC` | No | Datasource-specific dimension columns (vary by datasource) |
| `[metric_columns]` | `NUMERIC` | No | Datasource-specific metric columns (vary by datasource) |

Key Points:
- Column types are automatically detected from PyDruid query results and may vary by datasource
- All Druid datasources include a `__time` column representing when each event occurred
- Dimension and metric columns vary per datasource based on your Druid schema
- Since Druid rows do not have a guaranteed unique key, Fivetran generates `_fivetran_id` as the primary key
- The `_fivetran_id` is a hash of all row values to uniquely identify each record

## Additional files

This connector includes additional helper modules beyond the core files:
- `client.py` - PyDruid client wrapper with connection management, retry logic, and error handling

The `client.py` module provides a reusable DruidPyDruidClient class that handles:
- PyDruid client initialization and configuration
- Connection retry logic with exponential backoff
- Error handling for Druid-specific exceptions
- Timestamp parsing and validation utilities

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.