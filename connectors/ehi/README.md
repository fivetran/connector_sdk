# Simple EHI Connector Example

## Connector overview

This connector demonstrates how to fetch data from a Microsoft SQL Server database such as Caboodle and sync it to your Fivetran destination using the Fivetran Connector SDK. The connector automatically discovers tables and schemas from your Microsoft SQL Server database and synchronizes data using full load and incremental sync methods.


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
fivetran init <project-path> --template connectors/ehi
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- Automated table and schema discovery from `INFORMATION_SCHEMA`
- Incremental data synchronization using a timestamp column (configurable via `__MODIFIED_COLUMN_NAME`)
- Batch processing for efficient data fetching
- Comprehensive error handling
- Limited to `__MAX_TABLES` tables (default: 10) for demonstration purposes


## Configuration file

The connector requires minimal configuration with only essential connection parameters:

```json
{
  "mssql_server": "<YOUR_CABOODLE_MSSQL_SERVER>",
  "mssql_database": "<YOUR_CABOODLE_MSSQL_DATABASE>",
  "mssql_user": "<YOUR_CABOODLE_MSSQL_USER>",
  "mssql_password": "<YOUR_CABOODLE_MSSQL_PASSWORD>",
  "mssql_port": "<YOUR_CABOODLE_MSSQL_PORT>"
}
```

- `mssql_server`(required): SQL Server hostname or IP address
- `mssql_database`(required): Database name to connect to
- `mssql_user`(required): Database username
- `mssql_password`(required): Database password
- `mssql_port`(required): SQL Server port

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file

The `requirements.txt` file specifies the Python libraries required by the connector:

```
python-tds==1.17.1
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication

The connector uses SQL Server authentication with username and password credentials. Ensure your database user has the following permissions:

- SELECT permissions on all tables you want to replicate
- Access to `INFORMATION_SCHEMA` views for automated schema discovery
- Network connectivity to the SQL Server instance

Note: The connector sets `validate_host=False` in the `pytds` connection, which disables TLS host-name verification. This is suitable for development environments or private networks. Enable host validation in production by removing this flag or setting it to `True`.


## Pagination

The connector implements batch processing to handle datasets efficiently using the `fetchmany()` method. Data is fetched in configurable batches and yielded one record at a time, keeping memory usage low regardless of table size. The default batch size is 1000 rows and checkpoint interval is 5000 records.

Refer to `__BATCH_SIZE` constant for configuring the batch size


## Data handling

The connector automatically discovers and maps data from SQL Server to Fivetran using the following process:

The schema discovery comprises the following steps (refer to the `schema()` function):
1. The connector queries `INFORMATION_SCHEMA.TABLES` to identify available tables (up to `__MAX_TABLES`), returning both `TABLE_SCHEMA` and `TABLE_NAME`
2. The connector discovers primary keys from `INFORMATION_SCHEMA.KEY_COLUMN_USAGE`, filtered by both schema and table name to avoid cross-schema ambiguity
3. The connector maps column names from `INFORMATION_SCHEMA.COLUMNS`, likewise filtered by both schema and table name
4. The connector creates table definitions using the destination table name format `{schema}_{table}` (e.g. `dbo_patients`).
5. The connector declares the `sync_history` table with `sync_timestamp` as its primary key for tracking the sync details

The data synchronization is implemented using the following (refer to the `update()` and `_get_table_data()` methods):

- Before the table loop, `_get_tables_with_modified_date()` issues a single bulk query against `INFORMATION_SCHEMA.COLUMNS` to identify all tables containing the `__MODIFIED_COLUMN_NAME` column. This avoids a per-table schema lookup inside the loop.

- Tables with `__MODIFIED_COLUMN_NAME`: If a table is in the set returned above:
  - Initial sync: Uses the sentinel date `1970-01-01 00:00:00` as `last_sync_time` so all rows are fetched via `WHERE __MODIFIED_COLUMN_NAME > last_sync_time ORDER BY __MODIFIED_COLUMN_NAME`
  - Incremental syncs: Uses the stored cursor from state as `last_sync_time`
  - State (`state[table_name]`) is updated to the latest `__MODIFIED_COLUMN_NAME` value seen after every record processed, ensuring the cursor at any checkpoint reflects the exact row last written to the destination.

- Tables without `__MODIFIED_COLUMN_NAME`: The connector performs a full resync every time


## Error handling

The connector implements the following error handling mechanisms:
- Detailed error logging for troubleshooting connectivity issues
- Configuration parameter validation before attempting connection
- If a table query fails (e.g. network timeout, SQL error), the exception propagates and aborts the current sync run


## Tables created

The connector replicates tables from the source after fetching the schema details from the source. These tables are named to match source table names and it includes all the columns from the source with exact primary keys. The number of tables replicated can be controlled using `__MAX_TABLES`.

Additionally, the connector creates the following tables:

### sync_history
This table contains one summary record per sync run, written at the end of each successful sync:
- `sync_timestamp` (primary key) — ISO timestamp of when the sync started
- `total_tables` — Number of tables processed in the sync
- `total_records` — Total number of records synchronized across all tables
- `tables_processed` — Comma-separated list of table names processed in the sync


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
