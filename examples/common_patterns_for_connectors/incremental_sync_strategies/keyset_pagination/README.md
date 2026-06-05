# Keyset Pagination Incremental Sync Strategy Connector Example

**Complete Example Link:** [examples/common_patterns_for_connectors/incremental_sync_strategies/keyset_pagination/](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies/keyset_pagination/)

## Connector overview

This connector demonstrates **keyset pagination** for incremental syncs using the Fivetran Connector SDK. Keyset pagination uses a cursor (typically an `updatedAt` timestamp) to fetch new and updated records since the last sync.

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
fivetran init <project-path> --template examples/common_patterns_for_connectors/incremental_sync_strategies/keyset_pagination
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features

- **Cursor-based**: Uses a cursor value (like `updatedAt` timestamp) to track the last processed record
- **State Management**: Saves the last `updatedAt` value in the connector state
- **Incremental Fetching**: Only fetches records where `updatedAt` is greater than the saved cursor
- **Scroll Support**: Handles APIs that use scroll parameters for pagination
- **Efficient**: Only processes new/updated records
- **Reliable**: Handles large datasets without missing records
- **Scalable**: Works well with APIs that support cursor-based pagination

## Requirements file

* The connector requires no packages

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare it in your `requirements.txt`.

## API requirements

Your API should support:
- `updated_since` parameter to filter records by timestamp
- Optional `scroll_param` for pagination continuation
- Records with an `updatedAt` field for cursor tracking

## State management

The connector saves state as:
```json
{
  "last_updated_at": "2024-01-15T10:30:00Z"
}
```

## Data handling

The connector processes data as follows:
- **Data Extraction**: Fetches records using cursor-based pagination
- **Incremental Processing**: Only processes records updated since the last sync
- **State Tracking**: Updates the cursor after processing each batch

## Tables created

The connector syncs data to the `USER` table with the following schema:

```json
{
   "table": "user",
   "primary_key": ["id"],
   "columns": {
      "id": "STRING",
      "name": "STRING",
      "email": "STRING",
      "address": "STRING",
      "company": "STRING",
      "job": "STRING",
      "updatedAt": "UTC_DATETIME",
      "createdAt": "UTC_DATETIME"
   }
}
```

## When to use keyset pagination

- APIs that support cursor-based pagination
- When you need to track record updates by timestamp
- Large datasets where you want to avoid reprocessing unchanged records
- APIs that provide scroll parameters for pagination continuation

## Error handling

The connector implements comprehensive error handling:
- **API Response Validation**: Checks for successful HTTP responses
- **Data Validation**: Ensures data contains required fields
- **State Management**: Safely updates and checkpoints state
- **Detailed Logging**: Provides informative log messages for troubleshooting

## Additional considerations

This example is intended for learning purposes and uses the fivetran-api-playground package to mock the API responses locally. It is not meant for production use.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 