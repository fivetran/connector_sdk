# Accelo API Connector Example

## Connector overview
This connector demonstrates how to sync data from the Accelo API using the Fivetran Connector SDK. It leverages OAuth2.0 Client Credentials flow for authentication and uses multithreading to improve performance by making parallel API calls.

It supports syncing multiple Accelo entities including:
- `COMPANIES`
- `INVOICES`
- `PAYMENTS`
- `PROSPECTS`
- `JOBS`
- `STAFF`

The connector is designed for incremental sync using timestamp fields and safely handles rate limits and retries.

This example was contributed by community member Ahmed Zedan.
API reference: [Accelo API Docs](https://api.accelo.com/docs/#introduction).


## Accreditation

This example was contributed by our amazing community member Ahmed Zedan


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
fivetran init <project-path> --template connectors/oauth2_and_accelo_api_connector_multithreading_enabled
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- OAuth2.0 Client Credentials flow.
- Multithreaded API fetching.
- Paginated API handling.
- Incremental sync using timestamps.
- Dynamic state tracking per entity.
- Rate limit-aware with retries and exponential backoff.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "deployment": "<DEPLOYMENT>",
  "client_id": "<YOUR_CLIENT_ID>",
  "client_secret": "<YOUR_CLIENT_SECRET>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
python-dateutil==2.9.0.post0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector uses OAuth 2.0 Client Credentials flow to obtain an access token.


## Pagination and multithreading
This connector uses parallel page fetching with `ThreadPoolExecutor`. Each entity is fetched in batches, and API calls are made concurrently to reduce overall sync time.

Multithreading guidelines:
- Only API calls are threaded (not SDK operations like `op.upsert()` or `op.checkpoint()`).
- Thread-safe state is managed using `threading.local()`.

## Rate Limiting & Retries
- Accelo rate limit: 5000 requests/hour
- Retries: 3 attempts per call
- Retry backoff: Exponential (e.g., 2s, 4s, 8s)


## Data handling
- Entity-based incremental sync using timestamp cursors like `date_modified` or `date_created`.
- Multithreaded API fetching improves performance while avoiding race conditions—only API calls are threaded.
- Type-safe transformations convert strings to `int`, `float`, `datetime`, or `boolean`, with fallbacks to `None` for invalid values.
- Per-record preprocessing ensures consistent formatting and clean upserts to Fivetran.
- State is checkpointed after each entity sync using `threading.local()` to isolate sync progress per thread.


## Error handling
- Each API call has retry logic and logs detailed errors.
- Conversion errors (int/float/date) are logged per field and skipped safely.
- Sync failures are logged and halted with detailed traceback for debugging.


## Tables created
The connector creates the following table in the destination:
- `COMPANIES`
- `INVOICES`
- `PAYMENTS`
- `PROSPECTS`
- `JOBS`
- `STAFF`

Here is an example of the schema for the `COMPANIES` table:

```json
{
  "table": "companies",
  "primary_key": ["id"],
  "columns": {
    "id": "INT",
    "name": "STRING",
    "website": "STRING",
    "phone": "STRING",
    "date_created": "UTC_DATETIME",
    "date_modified": "UTC_DATETIME",
    "date_last_interacted": "UTC_DATETIME",
    "comments": "STRING",
    "standing": "STRING",
    "status": "INT",
    "postal_address": "INT",
    "default_affiliation": "INT"
  }
}
```
Complete table definitions are generated in the `schema()` function.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.