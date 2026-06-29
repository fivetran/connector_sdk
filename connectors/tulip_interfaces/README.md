# Tulip Interfaces Connector Example

## Connector overview

This connector syncs data from Tulip to Fivetran destinations. Tulip is a frontline operations platform that enables manufacturers to build apps without code, connect machines and devices, and analyze data to improve operations. This connector allows you to sync Tulip Tables data and load it into your destination for analysis and reporting. It is designed for manufacturing operations and supply chain teams who need to analyze production data, track quality metrics, and monitor operational performance across their data warehouse ecosystem.

To use this connector, you need access to a Tulip instance and a Tulip API key with tables read scope.

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/tulip_interfaces
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

This connector provides incremental data replication from Tulip Tables using the Tulip Table API with a two-phase synchronization strategy. It supports:

- Two-phase sync strategy: Efficient historical load (BOOTSTRAP) followed by incremental updates (INCREMENTAL)
- Cursor-based pagination: Uses `_sequenceNumber` as primary cursor to avoid offset-based pagination overhead
- Dynamic schema discovery: Automatically maps Tulip field types to warehouse column types
- Late commit handling: 60-second lookback window on `_updatedAt` prevents data loss from concurrent updates
- Custom filtering: Supports Tulip API filter syntax to sync only relevant records
- Automatic field optimization: Excludes tableLink fields to reduce database load on Tulip API
- Workspace support: Can sync tables from workspace-scoped or instance-level endpoints
- Automatic checkpointing: Saves state every 500 records for resumable syncs
- Robust error handling: Exponential backoff retry logic for rate limiting and transient errors

## Configuration file

The connector requires the following configuration keys in `configuration.json`:

```json
{
  "subdomain": "<YOUR_TULIP_SUBDOMAIN>",
  "api_key": "<YOUR_TULIP_API_KEY>",
  "api_secret": "<YOUR_TULIP_API_SECRET>",
  "table_id": "<YOUR_TULIP_TABLE_ID>",
  "workspace_id": "<YOUR_TULIP_WORKSPACE_ID_OPTIONAL>",
  "sync_from_date": "<YOUR_SYNC_FROM_DATE_ISO8601_OPTIONAL>",
  "custom_filter_json": "<YOUR_CUSTOM_FILTER_JSON_OPTIONAL>"
}
```

Configuration parameters:

- `subdomain` (required) - Your Tulip instance subdomain (e.g., "acme" for acme.tulip.co).
- `api_key` (required) - Tulip API key obtained from API settings in Tulip, note API key needs table read scope.
- `api_secret` (required) - Tulip API secret corresponding to the API key.
- `table_id` (required) - Unique identifier of the Tulip table to sync (e.g., "T65jBaGMgiexWy5yS")
- `workspace_id` (optional) - Workspace ID for workspace-scoped tables (omit for instance-level api keys or instances without workspaces).
- `sync_from_date` (optional) - ISO 8601 timestamp to start initial sync (defaults to beginning of time if omitted).
- `custom_filter_json` (optional) - JSON array of Tulip API filter objects, refer to [Tulip API docs for JSON definition](https://support.tulip.co/apidocs/list-records-of-a-tulip-table#:~:text=false-,filters,-An%20optional%20array) (defaults to empty array if omitted).

Note: The connector automatically excludes Linked Table Fields (`tableLink` type) to reduce database load on the Tulip API. System fields (`id`, `_createdAt`, `_updatedAt`, `_sequenceNumber`) and all non-`tableLink` custom fields are always included.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

This connector uses HTTP Basic Authentication with Tulip API credentials:

1. Log into your [Tulip instance](https://tulip.co/login/).
2. Navigate to **Account Settings** > **API Tokens**.
3. Create a new API token.
4. Make a note of the **API Key** and **API Secret** from the token configuration. You will need to add it to the `configuration.json`.
5. Ensure the API key has `table:read` permissions to access the target table.

The connector passes the API key and secret as HTTP Basic Auth credentials to all Tulip API endpoints.

Refer to the `def schema()` and `def update()` funtions for implementation details.

## Pagination

The connector implements a two-phase cursor-based synchronization strategy to handle large datasets efficiently.

Refer to `def update()` function for implementation details.

### Phase 1: BOOTSTRAP mode (historical data load)
- Uses `_sequenceNumber` as primary cursor to avoid offset pagination overhead
- Filters: `_sequenceNumber > last_sequence` (and optionally `_updatedAt > sync_from_date`)
- Sorts by `_sequenceNumber` in ascending order
- Fetches records in batches of 100 until API returns fewer than 100 records
- Transitions to INCREMENTAL mode when bootstrap completes

### Phase 2: INCREMENTAL mode (ongoing updates)
- Primary cursor: `_sequenceNumber > last_sequence`
- Secondary filter: `_updatedAt > (last_updated_at - 60s)` (60-second lookback)
- Sorts by `_sequenceNumber` in ascending order
- The lookback window catches records that were committed after the previous sync's cursor update
- Prevents infinite loops when multiple records share the same `_updatedAt` timestamp

### Checkpointing
- State is checkpointed every 500 records with: `cursor_mode`, `last_sequence`, and `last_updated_at`
- Enables resumable syncs if connector fails mid-batch

## Data handling

The connector transforms Tulip Tables data through several stages:

1. Schema discovery:
   - Fetches table metadata from Tulip API
   - Maps Tulip data types to Fivetran types using `_map_tulip_type_to_fivetran()`
   - Generates human-readable column names from field labels and IDs
   - Includes system fields: `id` (primary key), `_createdAt`, `_updatedAt`, `_sequenceNumber`
   - Automatically excludes Linked Table Fields (tableLink type) to reduce database load

2. Type mapping:
   - `integer` maps to `INT`
   - `float` maps to `DOUBLE`
   - `boolean` maps to `BOOLEAN`
   - `timestamp` and `datetime` map to `UTC_DATETIME`
   - `interval` maps to `INT` (stored as seconds)
   - `user` maps to `STRING`
   - All other types default to `STRING`

3. Record transformation:
   - Transforms field IDs to human-readable column names using `generate_column_name()`
   - Column naming format: `label__id` (e.g., `customer_name__rqoqm`)
   - Normalizes labels: lowercase, replaces spaces with underscores, removes special characters
   - Preserves system fields in their original format

4. Two-phase sync (BOOTSTRAP and INCREMENTAL):
   - BOOTSTRAP: Filters by `_sequenceNumber > last_sequence` for efficient historical load
   - INCREMENTAL: Filters by `_sequenceNumber > last_sequence` AND `_updatedAt > (last_updated_at - 60s)` to catch late commits
   - Updates cursors (`last_sequence`, `last_updated_at`) after each batch is processed
   - Automatically transitions from BOOTSTRAP to INCREMENTAL when historical load completes

Refer to the `def schema()`, `def _map_tulip_type_to_fivetran()`, `def generate_column_name()`, and `def _transform_record()` functions for implementation details.

## Error handling

The connector implements robust error handling:

- Rate limiting: Detects HTTP 429 responses and retries with exponential backoff (5s, 10s, 20s)
- Request failures: Automatically retries transient errors up to 3 attempts
- Specific exception handling: Catches and logs `KeyError`, `json.JSONDecodeError`, `requests.exceptions.HTTPError`
- Structured logging: Uses Python logging module with appropriate levels (INFO, WARNING, ERROR, CRITICAL)
- State preservation: Checkpoints every 500 records to minimize data loss on failure

Refer to the `def _fetch_with_retry()` function for implementation details.

## Tables created

The connector creates a single table per each Tulip table synced. The table name is generated from the Tulip table label and ID in the format `label__id`.

Example table schema for a Tulip table named `KitsDummy`:

Table: `kitsdummy__t65jbagmgiexwy5ys`

System columns (always present):
- `id` (STRING, primary key) - Unique record identifier
- `_createdAt` (UTC_DATETIME) - Record creation timestamp
- `_updatedAt` (UTC_DATETIME) - Record last update timestamp
- `_sequenceNumber` (INT) - Monotonically increasing sequence number used for cursor-based pagination

Custom columns are generated based on the Tulip table schema and follow the naming pattern `fieldlabel__fieldid`. For example:
- `customer_name__rqoqm` (STRING)
- `kit_number__pxwol` (INT)
- `kit_start_datetime__rzkek_kit_start_date_time` (UTC_DATETIME)
- `spectrapath_data_success__pybts_spectra_path_data_success` (BOOLEAN)

The schema is automatically discovered on the first sync and updated when new fields are added to the Tulip table.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
