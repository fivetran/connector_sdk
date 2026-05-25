# Userflow Connector Example

## Connector overview
This connector shows how to sync data from Userflow using the Fivetran Connector SDK.  
It enables extraction of user records from the Userflow REST API and synchronization to your destination.  
The connector supports incremental updates based on a cursor (`starting_after`), allowing efficient, resumable data transfer.

## Requirements
* [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)  
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features
- Connects securely to the Userflow REST API using bearer token authentication.  
- Supports incremental user syncs using pagination (`limit` + `starting_after`).  
- Streams data efficiently in batches for large result-sets.  
- Implements state checkpointing for resumable syncs.  
- Provides structured logging and error handling.

## Configuration file
The connector requires the following configuration parameters:
```json
{
  "userflow_api_key": "<YOUR_USERFLOW_API_KEY>",
  "base_url": "<YOUR_USERFLOW_BASE_URL>"
}
```

Note: Do not commit this file (`configuration.json`) to version control, as it contains sensitive credentials.


## Authentication
The connector authenticates using your Userflow API key:

- Authorization: Bearer <YOUR_API_KEY>
- Userflow-Version: 2020-01-03
If you are using the EU region of Userflow, set "base_url": "https://api.eu.userflow.com"

## Pagination
- The Userflow API uses cursor-based pagination with limit and starting_after.
- The connector fetches pages until the response sets "has_more": false or next_page_url stops.
- The last seen user ID is stored as the incremental bookmark.
- Refer to the `fetch_users()` function in `connector.py` for the pagination implementation.

## Data handling
- Connects using the configured API key to /users
- Fetches records in batches up to page_size which is 100 by default.
- For each user, it extracts id, email, name, created_at, and signed_up_at, and stores the entire JSON payload in a raw column.
- Upserts each record into the users table.
- Updates state["bookmarks"]["users"]["last_seen_id"] for next sync.

## Error handling
- HTTP errors: handled via resp.raise_for_status() with detailed logs. 
- Timeouts: requests include timeout parameter to avoid indefinite waits.
- Pagination issues: handled gracefully with logs and safe exits.
- Retry logic: transient errors retried automatically.

## Tables created
The connector creates one table:
`users`

Schema:

```json
{
  "table": "users",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING",
    "email": "STRING",
    "name": "STRING",
    "created_at": "UTC_DATETIME",
    "signed_up_at": "UTC_DATETIME",
    "raw": "JSON",
    "_synced_at": "UTC_DATETIME"
  }
}
```

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.