# RethinkDB Connector Example

## Connector overview
This example demonstrates how to use the Fivetran Connector SDK to sync data from RethinkDB, an open-source database designed for real-time applications. RethinkDB is known for its changefeeds feature that pushes data to applications in real-time, making it ideal for collaborative apps, multiplayer games, streaming analytics, and IoT systems. This connector enables organizations to replicate their RethinkDB data to a data warehouse for analysis, reporting, and business intelligence.

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
fivetran init <project-path> --template connectors/rethink_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Automatic schema discovery that detects all tables and their primary keys in the RethinkDB database
- Intelligent incremental sync using timestamp fields (updated_at, modified_at, timestamp, created_at)
- Automatic fallback to full table sync for tables without timestamp fields
- Complex data type handling that converts nested objects and arrays to JSON strings
- SSL/TLS support for secure connections to RethinkDB clusters
- Checkpointing every 100 records to enable resumable syncs for large datasets
- Connection pooling and proper resource cleanup

## Configuration file
The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_RETHINKDB_HOST>",
  "port": "<YOUR_RETHINKDB_PORT>",
  "database": "<YOUR_RETHINKDB_DATABASE>",
  "username": "<YOUR_RETHINKDB_USERNAME>",
  "password": "<YOUR_RETHINKDB_PASSWORD>",
  "use_ssl": "<TRUE_OR_FALSE_DEFAULT_FALSE>"
}
```

Configuration parameters:

- `host`: Your RethinkDB server hostname or IP address
- `port`: RethinkDB server port (default: 28015)
- `database`: Name of the RethinkDB database to sync
- `username`: Username for authentication (optional, leave empty for unauthenticated connections)
- `password`: Password for authentication (optional, leave empty for unauthenticated connections)
- `use_ssl`: Enable SSL/TLS encryption for secure connections (true or false, defaults to false)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The connector requires the `rethinkdb` package to connect to RethinkDB databases.

```
rethinkdb
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector supports both authenticated and unauthenticated connections to RethinkDB. Authentication is configured in the `connect_to_rethinkdb()` function.

For authenticated connections:
1. Create a RethinkDB user with appropriate permissions to access the required tables.
2. Provide the username and password in the `configuration.json` file.
3. Ensure the user has `read` permissions on all tables that need to be synced.

For unauthenticated connections (typically for local development):
1. Leave the `username` and `password` fields empty in the configuration.
2. Ensure your RethinkDB instance allows unauthenticated connections.

SSL/TLS connections:
1. Set `use_ssl` to `true` in the configuration to enable encrypted connections.
2. The connector uses Python's default SSL context for secure connections.

## Pagination
This connector does not use pagination. RethinkDB cursors automatically stream data from tables without requiring pagination logic. The connector processes records sequentially using cursor iteration (refer to the `sync_table_data()` function at line 281), with checkpointing every 100 records to handle large datasets efficiently.

## Data handling
The connector processes RethinkDB data as follows:

Schema discovery: The `schema()` function dynamically discovers all tables in the database and retrieves their primary key definitions using `table.info()`. This ensures the connector adapts to schema changes automatically.

Incremental sync: The connector implements intelligent incremental syncing by automatically detecting timestamp fields in each table. The `get_timestamp_field()` function searches for common timestamp field names (updated_at, modified_at, timestamp, created_at, last_modified) in priority order. When a timestamp field is found, subsequent syncs only retrieve records with timestamps newer than the last sync, significantly reducing data transfer and processing time. Tables without timestamp fields automatically fall back to full table sync.

Data transformation: The `transform_record()` function handles complex RethinkDB data types by converting nested objects and arrays to JSON strings, making them compatible with the Fivetran SDK supported data types.

Streaming: The connector uses RethinkDB cursors to stream data from tables, avoiding loading entire tables into memory. This enables efficient handling of large datasets.

Checkpointing: Progress is checkpointed every 100 records (configured via `__CHECKPOINT_INTERVAL`) to enable resumable syncs in case of interruptions. The state also tracks the maximum timestamp for each table to support incremental syncs. Refer to the `sync_table_data()` function.

## Error handling
Error handling is implemented throughout the connector:

Connection errors: The `connect_to_rethinkdb()` function catches connection failures and raises descriptive errors to help diagnose network or authentication issues.

Table access errors: The `get_all_tables()` and `get_table_primary_key()` functions handle cases where tables cannot be accessed or primary keys cannot be determined, falling back to default values where appropriate.

Data sync errors: The `sync_table_data()` function wraps the sync logic in try-except blocks to catch and log errors during data processing, ensuring partial sync progress is preserved via checkpoints.

Resource cleanup: All functions use try-finally blocks to ensure RethinkDB connections are properly closed, preventing connection leaks.

## Tables created

The connector dynamically creates tables based on the schema discovered in your RethinkDB database. For the example collaboration application dataset:

| Table name | Primary key | Description |
|------------|-------------|-------------|
| `USERS` | `id` | User accounts with roles, contact information, and profile settings stored as JSON |
| `PROJECTS` | `id` | Project records including status, team members (as JSON array), and metadata |
| `TASKS` | `id` | Task records with assignments, priorities, tags (as JSON array), and due dates |
| `COMMENTS` | `id` | Comments on tasks with reactions stored as JSON objects |
| `ACTIVITY_LOG` | `id` | Real-time activity tracking with action details stored as JSON |

Note: The connector automatically detects the primary key for each table. Complex data types like arrays and nested objects are converted to JSON strings for storage in the destination warehouse.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
