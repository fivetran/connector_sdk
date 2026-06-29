# Resend Connector Example

## Connector overview
This connector demonstrates how to fetch email data from Resend and upsert it into your destination using the Fivetran Connector SDK. The custom connector synchronizes email records from your Resend account and implements pagination handling to efficiently process large datasets with incremental synchronization based on email IDs. The connector tracks the newest email ID from each sync and stops fetching when it encounters previously synced data, ensuring efficient incremental updates without fetching the entire dataset on each run.

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
fivetran init <project-path> --template connectors/resend
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Synchronizes emails from Resend's API `/emails` endpoint
- Supports incremental syncing by tracking the newest email ID and stopping at previously synced emails
- Implements cursor-based pagination handling for large datasets
- Checkpoints progress every 50 emails to ensure reliable sync resumption
- Comprehensive error handling with exponential backoff retry logic
- Proactive rate limit management with delays between pagination requests
- Flattens nested JSON structures for optimal table schemas

## Configuration file
The configuration key required for your connector is as follows:

```json
{
  "api_token": "<YOUR_RESEND_API_TOKEN>"
}
```

### Configuration parameters

- `api_token` (required) - Your Resend API token for authentication.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The connector uses the `requests` library for HTTP communication, which is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses Bearer token authentication with Resend API keys. To obtain your API key:

1. Log in to your Resend account.
2. Go to **API Keys** in your dashboard.
3. Click **Create API Key**.
4. Enter a descriptive name for the API key.
5. Select the appropriate permissions (ensure the key has read access to emails).
6. Make a note of the generated API key. You will use it as the `api_token` in your connector's `configuration.json` file.

Note: Resend API keys are shown only once upon creation. Store them securely.

## Pagination
The connector implements Resend's cursor-based pagination system using the `after` parameter. It processes emails in pages and uses the `has_more` flag to determine if additional pages exist. The connector uses the last email ID from each page to fetch subsequent pages.

The Resend API returns emails sorted by creation date in descending order (newest first). This ordering is leveraged for efficient incremental syncing as follows:

For the first sync, the connector fetches all emails using pagination and saves the newest (first) email ID to state. For subsequent syncs, the connector fetches emails starting from the newest and stops when it reaches the previously synced email ID. The state management stores the newest email ID from each sync in `files/state.json` for the next sync. Checkpointing creates checkpoints every 50 emails with the newest email ID for recovery.

Since the Resend API returns emails sorted newest-first without date filtering, the connector reads pages from newest to oldest, stops pagination when encountering a previously synced email, and only upserts new emails to prevent duplicates. This approach ensures efficient incremental syncing without fetching the entire dataset on each run.

Note: Refer to the `sync_emails` function for the implementation.

## Data handling
The connector processes email data from the `/emails` endpoint which contains email metadata including sender, recipients, subject, timestamps, and delivery status. All nested JSON structures are flattened using the `flatten_dict` function to create optimal table schemas.
Array fields (such as `to`, `cc`, `bcc`, and `reply_to`) are serialized to JSON strings for storage. This approach ensures compatibility with flat table schemas but requires downstream parsing if you need to access individual array elements.

## Error handling
The connector implements comprehensive error handling strategies. Refer to the `fetch_emails_from_api` function:

- HTTP timeout handling with 30-second timeouts
- Rate limiting detection (HTTP 429) with exponential backoff retry logic
- Proactive rate limit prevention with 0.6-second delays between pagination requests to respect Resend's 2 requests per second limit
- Server error handling (HTTP 5xx) with exponential backoff
- Maximum of 5 retry attempts with 1-second base delay
- Specific exception handling for timeout, HTTP errors, and request failures
- Graceful error logging without exposing sensitive information

## Tables created
The connector creates a single table named `EMAIL` with the following columns:

| Column Name | Type | Description |
|------------|------|-------------|
| `id` | STRING | Email ID (Primary Key) |
| `_from` | STRING | Sender email address |
| `_to` | STRING | Recipient email addresses (JSON array) |
| `subject` | STRING | Email subject line |
| `created_at` | STRING | Email creation timestamp |
| `last_event` | STRING | Last email event status (delivered, bounced, complained, etc.) |
| `cc` | STRING | CC recipients (JSON array) |
| `bcc` | STRING | BCC recipients (JSON array) |
| `reply_to` | STRING | Reply-to addresses (JSON array) |
| `scheduled_at` | STRING | Scheduled send time (if applicable) |

The table uses `id` as the primary key.

Note: Detailed event tracking (such as opens, clicks, individual event timestamps) is not available through the List Emails API. Resend provides this data through webhooks, which is outside the scope of this connector.

## Additional files
The example includes additional utility files for testing and data population:

- `populate_data.py` - Sends multiple test emails to Resend for testing the connector with sample data.
- `explore_data.py` - Explores the Resend API by fetching emails and displaying response structure.
- `test_connection.py` - Tests the API connection and validates the API token.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
