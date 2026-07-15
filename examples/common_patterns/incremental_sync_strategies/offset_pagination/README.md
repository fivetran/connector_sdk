# Offset-based Pagination Incremental Sync Strategy Connector Example

**Complete Example Link:** [examples/common_patterns/incremental_sync_strategies/offset_pagination/](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/incremental_sync_strategies/offset_pagination/)

## Connector overview

This connector demonstrates **offset-based pagination** for incremental syncs using the Fivetran Connector SDK. This strategy uses timestamp-based filtering with offset pagination to fetch records in batches, saving the latest timestamp as state for the next sync.

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
fivetran init <project-path> --template examples/common_patterns/incremental_sync_strategies/offset_pagination
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features

- **Timestamp Filtering**: Uses `updated_since` parameter to filter records by timestamp
- **Offset Tracking**: Uses offset from API response to track pagination progress
- **State Management**: Saves the latest processed timestamp in connector state
- **Batch Processing**: Processes records in configurable page sizes
- **Incremental**: Only processes records updated since the last sync
- **Efficient**: Uses timestamp filtering to avoid reprocessing unchanged records
- **Reliable**: Handles large datasets with proper pagination

## Requirements file

* The connector requires no packages

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare it in your `requirements.txt`.

## API requirements

Your API should support:
- `updated_since` parameter to filter records by timestamp
- `order_by` and `order_type` parameters for consistent ordering
- `limit` parameter to specify the number of records per page
- Response should include `offset`, `limit`, and `total` fields
- Records with an `updatedAt` field for timestamp tracking

## API response format

The API should return responses in this format:
```json
{
  "data": [
    {"id": "1", "name": "John Doe", "updatedAt": "2024-01-15T10:30:00Z", ...},
    {"id": "2", "name": "Jane Smith", "updatedAt": "2024-01-15T11:00:00Z", ...}
  ],
  "offset": 0,
  "limit": 100,
  "total": 500
}
```

## State management

The connector saves state as:
```json
{
  "last_updated_at": "2024-01-15T10:30:00Z"
}
```

## Data handling

The connector processes data as follows:
- **Data Extraction**: Fetches records using offset-based pagination with timestamp filtering
- **Incremental Processing**: Only processes records updated since the last sync
- **Batch Processing**: Processes records in configurable page sizes
- **State Tracking**: Updates the timestamp after processing each batch


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

## When to use offset pagination

- APIs that support both timestamp filtering and offset pagination
- When you need truly incremental syncs with pagination
- Large datasets where you want to avoid reprocessing unchanged records
- APIs that return offset information in responses

## Error handling

The connector implements comprehensive error handling:
- **API Response Validation**: Checks for successful HTTP responses
- **Pagination Validation**: Ensures proper offset and total field handling
- **Data Validation**: Ensures data contains required fields
- **State Management**: Safely updates and checkpoints state
- **Detailed Logging**: Provides informative log messages for troubleshooting

## Important considerations

- **API Compatibility**: Requires specific API response format with offset/total fields
- **Timestamp Accuracy**: Requires accurate and consistent `updatedAt` timestamps
- **Ordering**: API must support consistent ordering by timestamp
- **Performance**: More efficient than simple offset pagination for incremental syncs

## Additional considerations

This example is intended for learning purposes and uses the fivetran-api-playground package to mock the API responses locally. It is not meant for production use.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 