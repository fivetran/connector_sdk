# Replay Incremental Sync Strategy Connector Example

**Complete Example Link:** [examples/common_patterns_for_connectors/incremental_sync_strategies/replay_sync/](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies/replay_sync/)

## Connector overview

This connector demonstrates **replay incremental sync with buffer** using the Fivetran Connector SDK. This strategy uses timestamp-based sync with a configurable buffer (goes back X hours from the last timestamp) to handle read-replica scenarios with replication lag.

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
fivetran init <project-path> --template examples/common_patterns/incremental_sync_strategies/replay_sync
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features

- **Buffer-based Filtering**: Applies a time buffer to the last processed timestamp
- **Replication Lag Handling**: Accounts for delays in read-replica systems
- **State Management**: Saves the latest processed timestamp in connector state
- **Overlap Processing**: Re-processes some records to ensure no data is missed
- **Replication Lag Safe**: Handles delays in read-replica systems
- **Data Consistency**: Ensures no records are missed due to timing issues
- **Configurable Buffer**: Adjustable buffer time for different replication scenarios
- **Reliable**: Robust against timing-related data inconsistencies

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
- **Data Extraction**: Fetches records using timestamp-based filtering with buffer
- **Buffer Application**: Applies time buffer to handle replication lag
- **Incremental Processing**: Only processes records updated since the buffered timestamp
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

## When to use replay sync

- **Read-replica scenarios**: When reading from a replica with potential replication lag
- **High-availability systems**: Where data consistency is critical
- **Distributed databases**: With eventual consistency models
- **APIs with timing delays**: Where updates may not be immediately available
- **Critical data scenarios**: Where missing records is not acceptable

## Error handling

The connector implements comprehensive error handling:
- **API Response Validation**: Checks for successful HTTP responses
- **Timestamp Validation**: Ensures proper timestamp format and buffer calculation
- **Data Validation**: Ensures data contains required fields
- **State Management**: Safely updates and checkpoints state
- **Detailed Logging**: Provides informative log messages for troubleshooting

## Buffer configuration

The `buffer_hours` parameter determines how far back to look from the last timestamp:

- **Small buffer (1-2 hours)**: For systems with minimal replication lag
- **Medium buffer (2-6 hours)**: For typical read-replica scenarios
- **Large buffer (6+ hours)**: For systems with significant replication delays

## Important considerations

- **Overlap Processing**: This strategy may re-process some records due to the buffer
- **Performance Impact**: Larger buffers mean more data processing
- **Duplicate Handling**: The connector uses upsert to handle potential duplicates
- **Buffer Sizing**: Choose buffer size based on your replication lag characteristics

## Example buffer calculation

If your last timestamp was `2024-01-15T10:30:00Z` and buffer_hours is 2:
- Buffer timestamp: `2024-01-15T08:30:00Z`
- The connector will fetch all records updated since 8:30 AM instead of 10:30 AM
- This ensures any records that were delayed in replication are captured

## Additional considerations

This example is intended for learning purposes and uses the fivetran-api-playground package to mock the API responses locally. It is not meant for production use.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 