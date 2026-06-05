# MailerLite Connector Example

## Connector overview
This connector demonstrates how to fetch email marketing data from [MailerLite](https://www.mailerlite.com/) and upsert it into your destination using the Fivetran Connector SDK. The connector synchronizes the most important entities: subscribers, groups, campaigns, and custom fields from your MailerLite account. It implements pagination handling for large datasets and includes incremental synchronization capabilities using cursor-based and page-based pagination depending on the endpoint.

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
fivetran init <project-path> --template connectors/mailerlite
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Synchronizes subscribers with custom fields and metadata
- Fetches groups and group membership relationships
- Retrieves email campaigns with performance data
- Fetches custom field definitions
- Implements pagination handling with both cursor-based and page-based approaches
- Client-side incremental sync for subscribers and campaigns
- Includes checkpointing at regular intervals for resumable syncs
- Generic sync function to reduce code duplication
- Comprehensive error handling with exponential backoff retry logic
- Rate limit handling with automatic retries

## Configuration file
The configuration keys required for your connector are as follows:

```json
{
  "api_key": "<YOUR_MAILERLITE_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The connector uses the `requests` library for HTTP communication, which is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses MailerLite API keys for authentication. To obtain your API key:

1. Log in to your [MailerLite account](https://www.mailerlite.com/).
2. Navigate to **Integrations** > **MailerLite API**.
3. Click **Generate new token**.
4. Enter a descriptive name for the token.
5. Make a note of the generated API key. You will use it as the `api_key` in your connector's `configuration.json` file.

The API key is passed as a Bearer token in the Authorization header for all API requests (refer to the `update()` function).

## Pagination
The connector implements two pagination strategies based on MailerLite API endpoint requirements:

- Cursor-based pagination: Used for subscribers and group subscribers endpoints. The connector processes data in batches and uses the `next_cursor` from the response metadata to fetch subsequent pages (refer to the `sync_paginated_data()` and `sync_group_subscribers()` functions).
- Page-based pagination: Used for groups, fields, and campaigns endpoints. The connector increments page numbers to fetch all data (refer to the `sync_paginated_data()` and `sync_groups()` functions).

The connector checks for pagination continuation tokens and breaks the loop when no more data is available. The generic `sync_paginated_data()` function handles both pagination types, reducing code duplication.

## Incremental sync
The connector implements client-side incremental sync for subscribers and campaigns using timestamp-based filtering:

- State tracking: The connector stores `last_sync_timestamp` and maximum `updated_at` timestamps for each entity in the state
- Client-side filtering: During subsequent syncs, the connector fetches all records from the API but only upserts records with `updated_at` timestamps newer than the last sync
- Skipped records: Unchanged records are skipped to reduce database write operations
- Timestamp conversion: ISO 8601 timestamps from the API are converted to milliseconds since epoch for comparison (refer to the `iso_to_timestamp()` function)
- Generic implementation: The `sync_paginated_data()` function accepts an `enable_incremental` parameter to enable incremental sync for any entity

Note: MailerLite API does not support server-side timestamp filtering, so the connector must fetch all records and perform client-side filtering. This ensures data completeness while minimizing database operations.

## Data handling
The connector processes data from multiple MailerLite API endpoints and flattens nested JSON structures for optimal table schemas. The `flatten_dict()` function recursively processes nested objects by concatenating keys with underscores, while arrays are converted to JSON strings for storage. Single nested JSON objects are flattened into the same table, while arrays of objects are stored as JSON strings. All data is upserted using the primary key defined in the schema, ensuring idempotent operations.

## Error handling
The connector implements comprehensive error handling strategies (refer to the `make_api_request()` function):

- HTTP timeout handling with 30-second timeout per request
- Rate limiting detection with exponential backoff retry logic
- Maximum 5 retry attempts for transient errors
- Specific exception handling for timeout, HTTP errors, and request failures
- Retry logic for 429 rate limit and 5xx server errors
- Immediate failure for non-retryable errors
- Detailed error logging without exposing sensitive information

## Tables created
The connector creates the following tables for the most important MailerLite entities:

| Table Name | Primary Key | Description | Incremental Sync |
|------------|-------------|-------------|------------------|
| `subscriber` | `id` | Subscriber records with email addresses, names, custom fields, and subscription status | Yes |
| `group` | `id` | Group definitions for organizing subscribers | No |
| `group_subscriber` | `group_id`, `subscriber_id` | Many-to-many relationship between groups and subscribers | No |
| `field` | `id` | Custom field definitions including field name, type, and metadata | No |
| `campaign` | `id` | Email campaign records with subject lines, sender information, and performance metrics | Yes |

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
