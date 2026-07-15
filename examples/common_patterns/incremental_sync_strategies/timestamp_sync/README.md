# Timestamp-based Incremental Sync Strategy Connector Example

**Complete Example Link:** [examples/common_patterns/incremental_sync_strategies/timestamp_sync/](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/incremental_sync_strategies/timestamp_sync/)

## Connector overview

This connector demonstrates **timestamp-based incremental sync** using the Fivetran Connector SDK. This strategy uses a timestamp to fetch all records updated since the last sync, saving the latest timestamp as state for the next sync.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting Started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns/incremental_sync_strategies/timestamp_sync
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features

- **Time-based Filtering**: Uses a timestamp to filter records updated since the last sync
- **State Management**: Saves the latest processed timestamp in connector state
- **Incremental Processing**: Only fetches records with `updatedAt` greater than the saved timestamp
- **Efficient Updates**: Processes only new and modified records
- **Truly Incremental**: Only processes records that have changed since the last sync
- **Efficient**: Minimizes API calls and data processing
- **Reliable**: Handles large datasets without performance degradation
- **Simple**: Easy to implement and maintain

## Requirements file

* The connector requires no packages

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare it in your `requirements.txt`.

## API requirements

Your API should support:
- `since` parameter to filter records by timestamp
- Records with an `updatedAt` field for timestamp tracking
- Consistent timestamp format (ISO 8601 recommended)
- Ability to return all records updated since a given timestamp

## State management

The connector saves state as:
```json
{
  "last_timestamp": "2024-01-15T10:30:00Z"
}
```

## Data handling

The connector processes data as follows:
- **Data Extraction**: Fetches records using timestamp-based filtering
- **Incremental Processing**: Only processes records updated since the last sync
- **State Tracking**: Updates the timestamp after processing all records


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

## When to use timestamp-based sync

- APIs that support timestamp-based filtering
- When you need truly incremental syncs
- Large datasets where efficiency is important
- When records have reliable `updatedAt` timestamps
- APIs that can return all changes since a given timestamp

## Error handling

The connector implements comprehensive error handling:
- **API Response Validation**: Checks for successful HTTP responses
- **Data Validation**: Ensures data contains required fields
- **State Management**: Safely updates and checkpoints state
- **Detailed Logging**: Provides informative log messages for troubleshooting

## Important considerations

- **Timestamp Accuracy**: Requires accurate and consistent `updatedAt` timestamps
- **Time Zones**: Ensure consistent timezone handling
- **API Limitations**: Some APIs may have limits on how far back you can query
- **Data Consistency**: Assumes records are updated with current timestamps

## Additional considerations

This example is intended for learning purposes and uses the fivetran-api-playground package to mock the API responses locally. It is not meant for production use.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 