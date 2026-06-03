# Better Stack Uptime Connector Example

## Connector overview

This connector syncs uptime monitoring data from Better Stack's Uptime API. It retrieves monitors, status pages, monitor groups, heartbeats, heartbeat groups, incidents, and on-call calendars, enabling unified monitoring and incident management analytics. The connector implements incremental syncing based on record update timestamps and supports pagination for large datasets.

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
fivetran init <project-path> --template connectors/betterstack
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental syncing based on `updated_at` timestamps for all endpoints
- Automatic pagination handling for large datasets
- Retry logic with exponential backoff for transient failures
- Flattening of nested JSON objects for simplified schema
- Support for child tables with foreign key relationships
- State checkpointing after each endpoint sync

## Configuration file

The connector requires the following configuration parameter:

```json
{
  "api_key": "<YOUR_BETTERSTACK_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses only the standard library and SDK-provided packages. No additional dependencies are required in `requirements.txt`.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses bearer token authentication to access the Better Stack Uptime API.

To obtain your API key:

1. Log in to your Better Stack account.
2. Navigate to **Settings** > **API Tokens**.
3. Click **Create API Token**.
4. Make a note of the generated token and add it to the `api_key` field in your `configuration.json` file.

The API key is passed in the Authorization header as a bearer token (refer to the `get_headers()` function).

## Pagination

Better Stack API uses page-based pagination with `per_page` and `page` query parameters. The API returns a `pagination` object in each response containing `next`, `prev`, `first`, and `last` URLs.

The connector handles pagination automatically (refer to the `fetch_paginated_data()` function):

- Follows the `pagination.next` URL to retrieve subsequent pages
- Stops when `pagination.next` is `null`, indicating the last page
- Uses `per_page=100` to minimize API calls
- Logs progress after each page

## Data handling

The connector processes data as follows (refer to the `sync_endpoint()` and `flatten_record()` functions):

- Fetches records page by page to avoid loading all data into memory
- Flattens nested `attributes` objects into the parent record for simplified schema
- Extracts child relationships (e.g., on-call users) into separate tables with foreign keys
- Filters records based on `updated_at` timestamp for incremental syncing
- Tracks the latest `updated_at` value per endpoint for state management

## Error handling

The connector implements comprehensive error handling (refer to the `make_api_request()` function):

- Retries transient errors (HTTP 429, 500, 502, 503, 504) up to 3 times
- Uses exponential backoff strategy (2, 4, 8 seconds) between retries
- Logs warnings for retry attempts and errors for failures
- Raises `RuntimeError` for permanent failures after exhausting retries
- Catches network errors (`Timeout`, `ConnectionError`) with retry logic

## Tables created

The connector creates the following tables (refer to the `schema()` function):

| Table Name | Primary Key | Description |
|------------|-------------|-------------|
| `MONITORS` | `id` | Website/API uptime monitors with configuration including URL, monitor type, check frequency, regions, and status |
| `STATUS_PAGES` | `id` | Public-facing status pages with company info, subdomain, custom domain, theme, and display settings |
| `MONITOR_GROUPS` | `id` | Logical groupings for monitors with name, sort order, team assignment, and pause status |
| `HEARTBEATS` | `id` | Cron job and scheduled task monitoring with period, grace time, alert settings, and heartbeat group assignment |
| `HEARTBEAT_GROUPS` | `id` | Logical groupings for heartbeats with name, sort order, team assignment, and pause status |
| `INCIDENTS` | `id` | Downtime and monitoring failure incidents with cause, timestamps, acknowledgment, resolution details, and alert settings |
| `INCIDENT_MONITOR` | `incident_id`, `id` | Links incidents to their related monitors (child table with foreign key `incident_id`) |
| `ON_CALL_CALENDARS` | `id` | On-call scheduling calendars with name, default status, and team assignment |
| `ON_CALL_USERS` | `on_call_calendar_id`, `id` | Links users to on-call calendars (child table with foreign key `on_call_calendar_id`) |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
