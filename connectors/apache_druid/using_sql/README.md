# Apache Druid Connector Example

## Connector overview

This connector syncs data from Apache Druid datasources into Fivetran, allowing you to replicate event and analytics data into your destination. The connector uses Druid's SQL API for querying and supports incremental sync using time-based filtering. Each datasource in your Druid cluster is synced as a separate table.

Apache Druid is a real-time analytics database designed for fast aggregations and queries on large event datasets. This connector provides access to your Druid datasources for analytics and reporting in your data warehouse.

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
fivetran init <project-path> --template connectors/apache_druid/using_sql
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental sync - Fetches only new records since the last sync using time-based filtering on the `__time` column
- Multi-datasource support - Syncs multiple Druid datasources in a single connector, each mapped to a separate destination table
- Time-based pagination - Paginates using the last seen timestamp instead of OFFSET, leveraging Druid's native segment pruning for performance
- Per-datasource state tracking - Tracks sync progress independently per datasource so adding a new datasource triggers only a full fetch for that datasource
- Retry logic with exponential backoff - Automatically retries failed requests up to 3 times with delays of 2s, 4s, and 8s
- Basic authentication support - Optional username and password authentication for secured Druid clusters
- Periodic checkpointing - Saves sync progress every 1000 records to enable safe resumption after interruption

## Configuration file

The connector requires a `configuration.json` file with the Druid connection details.

```json
{
  "host": "<YOUR_DRUID_HOST>",
  "port": "<YOUR_DRUID_PORT>",
  "datasources": "<YOUR_DRUID_DATASOURCES>"
}
```

For Druid clusters that require authentication, add the optional credentials:

```json
{
  "host": "<YOUR_DRUID_HOST>",
  "port": "<YOUR_DRUID_PORT>",
  "datasources": "<YOUR_DRUID_DATASOURCES>",
  "username": "<YOUR_DRUID_USERNAME>",
  "password": "<YOUR_DRUID_PASSWORD>"
}
```

Configuration parameters:
- `host` - Hostname or IP address of your Druid router or broker node (required)
- `port` - Port number for the Druid router or broker, typically 8888 (required)
- `datasources` - Comma-separated list of Druid datasource names to sync (required)
- `username` - Username for basic authentication (optional)
- `password` - Password for basic authentication (optional)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses only the pre-installed packages available in the Fivetran environment. No additional dependencies are required.

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector supports optional basic authentication for Druid clusters that require credentials. If `username` and `password` are provided in the configuration, the connector encodes them using Base64 and adds an `Authorization: Basic` header to all requests. If no credentials are provided, requests are sent without authentication.

The connector connects to Druid over HTTPS. Refer to `update()` in `connector.py` for the authentication implementation.

## Pagination

The connector uses time-based pagination for both full and incremental syncs. Each batch queries records with `__time` strictly greater than the current cursor, then advances the cursor to the last record's timestamp. Since results are ordered by `__time`, the last record in each batch is always the maximum timestamp.

For a full sync, the cursor starts at epoch (`1970-01-01T00:00:00+00:00`). For incremental syncs, it starts from the last synced timestamp stored in state. This approach leverages Druid's native time-based segment pruning, which is significantly faster than SQL `OFFSET` for large tables.

## Data handling

The connector processes Druid data through the following steps:

- Configuration validation - Validates all required fields (`host`, `port`, `datasources`) and optional fields before making any API calls. Refer to `validate_configuration()`.

- Connection setup - Builds the base URL from `host` and `port`, prepares request headers, and optionally adds the `Authorization` header for basic authentication. Refer to `update()`.

- Incremental filtering - Reads the per-datasource last sync timestamp from state. If none exists, defaults to epoch to trigger a full fetch. Refer to `fetch_datasource_data()`.

- Time-based pagination - Executes paginated SQL queries against the `/druid/v2/sql` endpoint using `WHERE __time > TIME_PARSE('{cursor}')`, advancing the cursor after each batch until fewer than `__BATCH_SIZE` records are returned. Refer to `fetch_datasource_data()`.

- Data upserting - Each record is upserted to the corresponding destination table. Fivetran automatically generates a `_fivetran_id` surrogate key as a hash of all row values, since Druid rows do not have a guaranteed unique key. Refer to `update()`.

- State checkpointing - Saves the maximum `__time` seen per datasource after each datasource completes. Also checkpoints every 1000 records during processing to enable safe resumption. Refer to `update()`.

## Error handling

The connector implements robust error handling to ensure reliable data synchronization:

- Retry logic with exponential backoff - Automatically retries failed requests up to 3 times, waiting 2s, 4s, and 8s between attempts. See `make_druid_request()`.
- HTTP error handling - Retries on 5xx server errors and fails immediately on 4xx client errors such as authentication failures. See `make_druid_request()`.
- Timeout handling - Each request times out after 30 seconds, and timeout errors are retried up to the maximum retry count. See `make_druid_request()`.
- Configuration validation - Validates all configuration parameters before making any API calls and provides clear error messages for missing or invalid fields. See `validate_configuration()`.
- State checkpointing - Checkpoints sync state after every 1000 records and after each datasource completes, enabling safe resumption without re-processing already-synced data.

## Tables created

The connector creates one table per Druid datasource specified in the `datasources` configuration. Table names are derived from datasource names by replacing any character that is not a letter, digit, or underscore with an underscore (for example, `koalas-to-the-max` becomes `koalas_to_the_max` and `my.datasource name` becomes `my_datasource_name`).

Column types are inferred from the data returned by Druid's SQL API and may vary depending on your datasource schema. All Druid datasources include a `__time` column representing when each event occurred. Dimension and metric columns vary per datasource.

Since Druid rows do not have a guaranteed unique key, no primary key is defined in the schema. Fivetran automatically generates a `_fivetran_id` column as a hash of all row values to uniquely identify each record.

Example data for a `wikipedia` datasource:

| `_fivetran_id` | `__time` | `channel` | `page` | `delta` |
|----------------|----------|-----------|--------|---------|
| a1b2c3d4... | 2024-01-15T10:30:00.000Z | #en.wikipedia | Python | 42 |
| e5f6g7h8... | 2024-01-15T10:31:00.000Z | #fr.wikipedia | Django | -5 |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
