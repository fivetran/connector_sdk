# Prometheus Connector Example

## Connector overview

This connector syncs metrics metadata and time series data from Prometheus, an open-source monitoring and alerting system. It syncs data with support for incremental syncs, multiple authentication methods (none, basic, bearer token), and configurable metric filtering. You need to provide your Prometheus server URL and optional authentication credentials for this example to work.

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
fivetran init <project-path> --template connectors/prometheus
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Syncs metrics metadata including metric names, types, and help text
- Extracts time-series data points with labels and timestamps
- Supports incremental syncs based on last sync timestamp
- Configurable authentication methods including none, basic auth, and bearer token
- Optional metric filtering to control which metrics to sync
- Configurable lookback period for initial sync
- Automatic retry logic with exponential backoff for API failures
- Batched checkpointing to ensure sync resumability

## Configuration file

The connector uses the following configuration parameters:

```json
{
  "prometheus_url": "<YOUR_PROMETHEUS_SERVER_URL>",
  "auth_type": "<AUTH_TYPE_NONE_BASIC_OR_BEARER>",
  "username": "<YOUR_USERNAME_FOR_BASIC_AUTH>",
  "password": "<YOUR_PASSWORD_FOR_BASIC_AUTH>",
  "bearer_token": "<YOUR_BEARER_TOKEN_FOR_BEARER_AUTH>",
  "lookback_hours": "<HOURS_TO_LOOKBACK_DEFAULT_24>",
  "metrics_filter": "<OPTIONAL_LIST_OF_METRIC_NAMES_TO_SYNC>"
}
```

Configuration parameters:

- `prometheus_url` (required) - The base URL of your Prometheus server (e.g., `http://localhost:9090`)
- `auth_type` (optional, defaults to `none`) - Authentication method: `none`, `basic`, or `bearer`
- `username` (required only if `auth_type` is basic) - Username for basic authentication
- `password` (required only if `auth_type` is basic) - Password for basic authentication
- `bearer_token` (required only if `auth_type` is bearer) - Bearer token for token-based authentication 
- `lookback_hours` (optional, defaults to 24) - Number of hours to look back for initial sync
- `metrics_filter` (optional) - Comma-separated list or JSON array of specific metric names to sync. If omitted, all metrics are synced.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses only standard library packages and requests, which are pre-installed in the Fivetran environment. No additional dependencies are required, so no `requirements.txt` file is needed.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment.

## Authentication

This connector supports three authentication methods:

- None - No authentication (default for local Prometheus instances)
- Basic authentication - Username and password-based authentication
- Bearer token - Token-based authentication

To configure authentication:

1. Determine which authentication method your Prometheus server requires.
2. Set the `auth_type` field in `configuration.json` to `none`, `basic`, or `bearer`.
  - If using basic authentication:
    1. Obtain or create a username and password for your Prometheus server.
    2. Add the `username` and `password` fields to `configuration.json`.
  - If using bearer token authentication:
    1. Obtain a valid bearer token from your authentication provider.
    2. Add the `bearer_token` field to `configuration.json`.
3. For local testing with Docker Compose, use the none `auth_type` as no authentication is configured by default.

The authentication logic is implemented in the `get_auth_headers()` function which builds the appropriate HTTP headers based on the configured authentication type.

## Data handling

The connector processes data as follows:

Metrics metadata sync - The connector first fetches all available metric names from Prometheus using the `/api/v1/label/__name__/values` endpoint. For each metric, a record is created with the metric name. 

Note: Metric type and help text are set to default values (unknown and empty string) rather than being fetched from the `/api/v1/targets/metadata` endpoint, as this endpoint is not universally available across all Prometheus deployments (e.g., Grafana Cloud). This data is upserted into the metrics table. Refer to the `sync_metrics_metadata()` function in connector.py.

Time-series data sync:

- The connector fetches actual time-series data using range queries via the `/api/v1/query_range` endpoint.
- Each metric is queried separately with a configurable step duration (default 15 seconds).
- The results include metric labels, timestamps, and values, which are processed into individual data points.
- Each data point is assigned a unique series identifier based on the metric name and label combination (refer to the `generate_series_id()` function in connector.py).
- The data is upserted into the `time_series` table.

The connector handles data sync and batching as follows:

- Incremental syncs: Uses the `last_sync_timestamp` from state to query only new data since the last successful sync.
- Initial syncs: Uses a configurable lookback period (default 24 hours) to fetch historical data.
- Batching and checkpointing: Processes data in batches, checkpointing every 1000 data points to ensure the sync can resume from the correct position if interrupted.

Refer to the `sync_time_series_for_metrics()` function in `connector.py` for implementation details.

## Error handling

The connector implements comprehensive error handling:

- API request retry logic: All HTTP requests to Prometheus include automatic retry logic with exponential backoff. The connector retries up to 3 times for transient errors (timeouts and HTTP status codes 429, 500, 502, 503, 504). The retry delay doubles with each attempt, starting from 1 second. Non-retryable errors like authentication failures result in immediate failure. This is implemented in the `make_api_request()` function in `connector.py`.
- Specific exception handling: The connector catches specific exception types including `requests.Timeout` and `requests.RequestException` rather than generic exceptions. All errors are logged at the error level with detailed error messages before raising RuntimeError to fail the sync.
- Response validation: All API responses are validated to ensure the status field is success before processing data. Invalid responses trigger errors with detailed information about what went wrong.

## Tables created

The connector creates the `METRICS` and `TIME_SERIES` tables in your destination.

### METRICS

This table contains metadata about each metric available in Prometheus.

- `metric_name` (STRING) - Primary key. Unique identifier for the metric.
- `metric_type` (STRING) - Type of metric (counter, gauge, histogram, or summary).
- `help_text` (STRING) - Description of what the metric measures.

### TIME_SERIES

This table contains the actual time series data points. Each row represents a single measurement at a specific point in time.

- `series_id` (STRING) - Primary key. Unique hash generated from the metric name and label combination.
- `metric_name` (STRING) - Name of the metric.
- `labels` (JSON) - JSON object with all label key-value pairs for the time series.
- `timestamp` (UTC_DATETIME) - Primary key. When the measurement was taken.
- `value` (DOUBLE) - Numeric metric value.


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
