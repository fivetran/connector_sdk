# Key-Based Pagination Connector Example

## Connector overview
This connector demonstrates the [Priority-First Sync (PFS)](https://fivetran.com/docs/using-fivetran/features#priorityfirstsync) strategy, designed to sync recent data first while gradually backfilling historical records.
- Targets high-volume historical syncs where fresh data is prioritized for early availability.
- Alternates between:
  - Incremental Syncs: Pulls new or recently updated records.
  - Historical Syncs: Walks backward in time until a defined limit.
- Maintains separate cursors for incremental and historical progress per table.
- Currently supports the `USER` table as an example, using keyset pagination based on `updated_at`.

Ideal for connectors with large datasets where early access to recent records is critical.


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
fivetran init <project-path> --template examples/common_patterns/priority_first_sync_for_high_volume_initial_syncs
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Uses `Faker` to generate diverse test `USER` data.
- Syncs from a mock API with offset-based pagination.
- Demonstrates modular connector design using `users_sync.py`.
- Implements incremental sync logic using a timestamp field `updatedAt`.


## Configuration file
This example does not require a configuration file.

In production, a `configuration.json` might contain API tokens, initial cursors, or filters to narrow down API results.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
Faker==30.3.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector connects to a local mock server and does not require authentication. In a production scenario, use headers or token-based authentication in your request logic within `users_sync.py`.


## Pagination
- Pagination is handled within `users_sync.sync_users()` using a mock API response simulating `has_more` flags.
- For incremental syncs, data is paginated forward using the `updated_at` field, fetching records newer than the incremental cursor.
- For historical syncs, pagination proceeds backward in time, using a decreasing historical cursor until the historical limit is reached.
- Each response is processed in sequence, and `last_updated_at` is updated as the cursor.
- The `has_more` flag determines whether to continue paginating in the current batch.


## Data handling
- Uses two time-based cursors per endpoint:
  - `incremental_cursor` for recent data.
  - `historical_cursor` for older data.
- Sync alternates between incremental and historical runs to prioritize freshness while backfilling history.
- Data is pulled using the `updated_since` param and batched by time range (1-day chunks).
- Cursors are updated after each batch, ensuring resume-safe and idempotent syncs.
- Checkpointing is performed after every successful data load.


## Error handling
- Basic error handling is implemented via `response.raise_for_status()`.
- Invalid API responses or missing fields are skipped with log warnings.
- Sync will resume from the last checkpointed state if interrupted.


## Tables created
The connector creates a `USER` table:

```
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


## Additional files
The connector requires two additional files: 
- `mock_api.py` – A FastAPI-based server that simulates a REST API for serving `Faker`-generated user data.
- `users_sync.py` – A utility module that contains the `sync_users()` function, which handles all API requests, pagination logic, and sync state management.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.