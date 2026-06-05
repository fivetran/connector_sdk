# Zigpoll Connector Example

## Connector overview
This connector retrieves survey response data from [Zigpoll](https://apidocs.zigpoll.com/reference) API and syncs it using Fivetran Connector SDK. The connector fetches data from all accounts accessible via the provided API token. It also handles pagination and incremental syncing to efficiently process large datasets.
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
fivetran init <project-path> --template connectors/zigpoll
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Fetches survey response data from all accessible Zigpoll accounts
- Supports cursor-based pagination for efficient data retrieval
- Incremental sync using timestamp-based checkpointing
- Flattens metadata dictionaries into separate columns
- Automatic retry logic with exponential backoff for API requests
- Modular architecture with dedicated functions for account management and pagination
- Comprehensive error handling and logging
- Client-side timestamp filtering to prevent duplicate data processing

## Configuration file
The connector requires an API token to authenticate with Zigpoll's API and optionally accepts a start date for initial sync. Obtain your API token from your Zigpoll account settings.

```
{
  "api_token": "<YOUR_ZIGPOLL_API_TOKEN>",
  "start_date": "<YOUR_OPTIONAL_START_DATE_AS_YYYY-MM-DD>"
}
```

Configuration Parameters:
- `api_token` (required): Your Zigpoll API authentication token
- `start_date` (optional): Date in YYYY-MM-DD format to start syncing data from (e.g., `"2023-01-01"`). If not provided, sync will start from EPOCH time

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The `requirements.txt` file specifies Python libraries required by the connector. This connector uses only the pre-installed packages in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses API token authentication. To obtain your API token:
1. Log in to your Zigpoll account.
2. Navigate to account settings or API settings.
3. Generate or copy your API token.
4. Add the token to your `configuration.json` file.

## Pagination
The connector handles cursor-based pagination automatically through modular functions:
- `get_account_ids` function retrieves all accessible account IDs
- `process_responses_page` function handles individual page processing with client-side filtering
- `sync_account_responses` function manages the pagination loop for each account

The pagination processes responses in batches of 100 records per request and uses the `endCursor` from each response to fetch subsequent pages. The connector includes safeguards against infinite loops by detecting when the API returns the same cursor consecutively, which can occur when using timestamp filters with the Zigpoll API.

## Data handling
Survey response data is processed and transformed through a modular approach:
- Primary data structure preserved with `_id` as the primary key
- Metadata dictionaries are flattened into separate columns with `metadata_` prefix
- Data types are inferred by Fivetran except for the primary key which is defined as STRING
- Each response is upserted individually to handle updates to existing records
- Client-side timestamp filtering ensures only new data since the last sync is processed
- State management with checkpointing enables incremental syncing and resumability

## Error handling
The connector implements comprehensive error handling through multiple layers:
- Configuration validation ensures required parameters are present
- API requests include retry logic with exponential backoff for transient errors
- Specific exception catching for HTTP request failures, authentication errors, and rate limiting
- Detailed error logging with context information for debugging
- Graceful handling of pagination edge cases including infinite loop prevention
- Runtime error wrapping for sync failures to provide clear error messages

## Tables created
This connector creates a single table, `RESPONSE`, which contains all survey response data from Zigpoll accounts.

| Column        | Type                 | Description                             |
|---------------|----------------------|-----------------------------------------|
| _id           | STRING (Primary Key) | Unique identifier for each response     |
| createdAt     | STRING               | Timestamp when response was created     |
| accountId     | STRING               | Account identifier                      |
| pollId        | STRING               | Survey/poll identifier                  |
| slideId       | STRING               | Specific question/slide identifier      |
| participantId | STRING               | Participant identifier                  |
| response      | STRING               | The actual response content             |
| userAgent     | STRING               | Browser/device information              |
| valueType     | STRING               | Type of response (vote, response, etc.) |
| metadata_*    | STRING               | Flattened metadata fields with prefix   |

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.