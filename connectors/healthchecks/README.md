# Healthchecks.io Connector Example

## Connector overview

This connector syncs health check monitoring data from Healthchecks.io to your data warehouse using the Fivetran Connector SDK. Healthchecks.io is a cron job and background task monitoring service that tracks whether scheduled jobs are running on time. This connector enables you to analyze health check performance, track uptime trends, identify reliability patterns, and integrate monitoring data with your broader data analytics infrastructure.

The connector retrieves data from four primary endpoints: health checks (monitors), pings (check-in events), flips (status changes), and integrations (notification channels). This allows you to build comprehensive dashboards for operational monitoring, SLA tracking, and incident analysis.

**Important**: This connector performs a full refresh on each sync because the Healthchecks.io API does not support timestamp-based filtering or pagination. State checkpointing is maintained for sync tracking purposes, but all data is fetched on every sync cycle.

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
fivetran init <project-path> --template connectors/healthchecks
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Full data refresh on each sync (API does not support incremental filtering)
- State management with checkpointing for sync tracking
- Automatic retry logic with exponential backoff for transient API failures
- Comprehensive data model covering checks, pings, status changes, and integrations
- Flattened schema design for easy querying and analysis
- Support for key Healthchecks.io Management API v3 endpoints
- Graceful error handling with detailed logging for troubleshooting

## Configuration file

The connector requires the following configuration parameter:

```json
{
  "api_key": "<YOUR_HEALTHCHECKS_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses only the standard libraries and packages pre-installed in the Fivetran environment. No additional dependencies are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses API key authentication to access the Healthchecks.io Management API v3. The API key is passed via the `X-Api-Key` HTTP header for all requests (refer to the `get_headers()` and `make_api_request()` functions).

To obtain your API key:

1. Log in to your Healthchecks.io account.
2. Navigate to **Settings > API Access**.
3. Copy your project-specific API key.
4. Add the API key to your `configuration.json` file.

**Note**: Healthchecks.io provides both read-write and read-only API keys. This connector requires a read-only key at a minimum, though a read-write key will also work.

## API limitations

The Healthchecks.io API has the following limitations that affect sync behavior:

- No incremental filtering: The API does not support timestamp-based filtering (no `updated_at`, `modified_since`, or similar parameters)
- No pagination: All endpoints return complete result sets in a single response
- Limited ping history: API returns the most recent events based on account limits (100 pings for free accounts, 1000 pings for paid accounts)
- Full refresh required: Due to the above limitations, the connector performs a full data refresh on each sync
- No batch endpoints: The API does not provide batch endpoints for fetching pings/flips across multiple checks

These limitations mean the connector is most suitable for accounts with modest data volumes (typically less than 100 health checks).

## Data handling

The connector transforms nested JSON responses from the Healthchecks.io API into flattened relational tables suitable for data warehouse storage (refer to the `flatten_check_record()`, `flatten_ping_record()`, `flatten_flip_record()`, and `flatten_integration_record()` functions).

For parent-child relationships, the connector:
- Flattens single nested JSON objects into the parent table
- Creates separate breakout tables for arrays of objects (pings and flips)
- Maintains referential integrity using foreign keys (`check_uuid` in pings and flips tables)
- Generates composite primary keys for child tables (`ping_id` and `flip_id`)

The connector maintains state with checkpointing to track sync progress. While the state timestamp is saved after each successful sync, it is not used for data filtering due to API limitations. Each sync performs a full refresh of all available data, with Fivetran's upsert operations handling data deduplication (refer to the `update()` function).

## Error handling

The connector implements comprehensive error-handling strategies (refer to the `make_api_request()` function):

- Automatic retry with exponential backoff for transient failures (HTTP 429, 500, 502, 503, 504)
- Maximum of 3 retry attempts with delays of 1s, 2s, and 4s
- Network timeout protection (30-second timeout for all requests)
- Graceful degradation for non-critical endpoints (pings, flips, and integration failures are logged but don't halt the sync)
- Detailed error logging using Fivetran SDK logging levels (info, warning, error)
- Fail-fast behavior for authentication errors and permanent failures (4xx errors)

## Tables created

The connector creates four tables in your destination:

### check

Contains health check configurations and monitoring settings.

| Column | Type | Description |
|--------|------|-------------|
| uuid | STRING | Unique identifier for the health check |
| name | STRING | Name of the health check |
| slug | STRING | URL-friendly identifier |
| tags | STRING | Space-separated list of tags |
| description | STRING | Description of the health check |
| grace | INT | Grace period in seconds |
| n_pings | INT | Total number of pings received |
| status | STRING | Current status (up, down, paused, etc.) |
| started | BOOLEAN | Whether the check has started |
| last_ping | UTC_DATETIME | Timestamp of the last ping received |
| next_ping | UTC_DATETIME | Expected timestamp of the next ping |
| manual_resume | BOOLEAN | Whether manual resume is required |
| methods | STRING | Comma-separated list of allowed HTTP methods |
| subject | STRING | Email subject filter pattern |
| subject_fail | STRING | Email subject filter pattern for failures |
| start_kw | STRING | Keywords indicating check start |
| success_kw | STRING | Keywords indicating success |
| failure_kw | STRING | Keywords indicating failure |
| filter_subject | BOOLEAN | Whether to filter by email subject |
| filter_body | BOOLEAN | Whether to filter by email body |
| badge_url | STRING | URL for the status badge |
| ping_url | STRING | URL to send pings to |
| update_url | STRING | URL for updating the check |
| pause_url | STRING | URL for pausing the check |
| resume_url | STRING | URL for resuming the check |
| channels | STRING | Comma-separated list of integration channel IDs |
| timeout | INT | Expected period in seconds |

### ping

Contains check-in events for health checks.

| Column | Type | Description |
|--------|------|-------------|
| ping_id | STRING | Unique identifier for the ping (composite: check_uuid + n) |
| check_uuid | STRING | Foreign key to the check table |
| n | INT | Sequential ping number |
| type | STRING | Type of ping (success, fail, start, etc.) |
| date | UTC_DATETIME | Timestamp when the ping was received |
| scheme | STRING | Protocol used (http, https, email, etc.) |
| remote_addr | STRING | IP address of the sender |
| method | STRING | HTTP method used |
| ua | STRING | User agent string |
| duration | FLOAT | Duration in seconds (for success pings) |

### flip

Contains status change events for health checks.

| Column | Type | Description |
|--------|------|-------------|
| flip_id | STRING | Unique identifier for the status change (composite: check_uuid + timestamp) |
| check_uuid | STRING | Foreign key to the check table |
| timestamp | UTC_DATETIME | When the status change occurred |
| up | INT | Status after the flip (1 for up, 0 for down) |

### integration

Contains notification channel configurations.

| Column | Type | Description |
|--------|------|-------------|
| id | STRING | Unique identifier for the integration |
| name | STRING | Name of the integration |
| kind | STRING | Type of integration (email, slack, webhook, etc.) |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
