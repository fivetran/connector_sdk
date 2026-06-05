# Connector SDK Courier API Connector Example

## Connector overview

This connector fetches data from the Courier API, a multi-channel notification platform that enables businesses to send notifications across email, SMS, push, and other channels. The connector syncs key operational data including audit events for compliance tracking, brand configurations, audience segments, message logs, subscriber lists, and notification templates. This enables organizations to analyze notification delivery patterns, track user engagement, monitor system usage for compliance, and optimize their messaging strategies.

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
fivetran init <project-path> --template connectors/courier
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Syncs audit events with timestamp-based incremental updates for compliance tracking
- Syncs brand configuration data with update tracking
- Syncs audience segments using cursor-based pagination
- Syncs message logs for delivery tracking
- Syncs subscriber lists for contact management
- Syncs notification templates
- Implements exponential backoff retry logic for transient API failures
- Supports checkpointing for reliable state management and resumption
- Flattens nested JSON structures for simplified analytics

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "api_key": "<YOUR_COURIER_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require any additional packages beyond the pre-installed libraries in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses Bearer token authentication to access the Courier API. The API key is passed in the Authorization header as a Bearer token for all requests (refer to the `get_headers()` function).

To obtain your API key:

1. Log in to your [Courier account](https://app.courier.com).
2. Navigate to **Settings > API Keys**.
3. Make a note of your API key (either test key for testing or production key for live data).
4. Add the API key to your `configuration.json` file.

## Pagination

The connector implements different pagination strategies based on the endpoint (refer to individual fetch functions):

- Cursor-based pagination – Used for the audiences, messages, and notifications endpoints. The connector processes pages sequentially using cursor tokens returned in the API response and checkpoints after each page (refer to the `fetch_audiences()`, `fetch_messages()`, and `fetch_notifications()` functions).
- Next URL-based pagination – Used for the tenants endpoint. The connector follows the `next_url` field in the API response to retrieve subsequent pages (refer to the `fetch_tenants()` function).
- Offset pagination – Used for lists, brands, and audit events endpoints. These endpoints return paginated results with a `more` indicator in the paging object.
  
## Data handling

The connector processes data as follows:

- Flattening - All nested JSON objects are flattened into single-level dictionaries with underscore-separated key names using the `flatten_nested_object()` function. For example, `settings.colors.primary` becomes `settings_colors_primary`.
- Incremental sync - The connector tracks the latest timestamp for brands and audit events in the state to enable incremental updates on subsequent syncs.
- Streaming - Data is processed record-by-record without loading entire datasets into memory, enabling efficient handling of large data volumes.
- Type inference - Column data types are automatically inferred by Fivetran based on the data values.

## Error handling

The connector implements comprehensive error handling strategies (refer to the `make_api_request()` function):

- Retry logic - Implements exponential backoff for retryable HTTP status codes (429, 500, 502, 503, 504) with up to 3 retry attempts. The delay doubles with each attempt starting from 1 second.
- Network errors - Automatically retries on timeout and connection errors using the same exponential backoff strategy.
- Non-retryable errors - Immediately raises exceptions for client errors (4xx status codes except 429) without retry attempts.
- Validation - Validates required configuration parameters at the start of each sync (refer to the `validate_configuration()` function).

## Tables created

The connector creates the following tables in your destination:

| Table name     | Primary key    | Description                                                                   |
|----------------|----------------|-------------------------------------------------------------------------------|
| `BRAND`        | `id`           | Brand configuration data with update tracking                                 |
| `AUDIENCE`     | `id`           | Audience segments synced via cursor-based pagination                          |
| `AUDIT_EVENT`  | `auditEventId` | Audit events with timestamp-based incremental updates for compliance tracking |
| `LIST`         | `id`           | Subscriber lists for contact management                                       |
| `MESSAGE`      | `id`           | Message logs for delivery tracking                                            |
| `NOTIFICATION` | `id`           | Notification templates                                                        |
| `TENANT`       | `id`           | Tenant configuration data                                                     |

All tables include flattened versions of complex nested objects, with nested properties converted to underscore-separated columns (e.g., `settings.colors.primary` becomes `settings_colors_primary`). Column data types are automatically inferred by Fivetran based on the API response data.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
