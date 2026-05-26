# History Mode Mimicry Using Composite Primary Key

## Connector overview

The [Fivetran history mode](https://fivetran.com/docs/core-concepts/sync-modes/history-mode) is a sync mode that preserves all historical versions of a record in the destination. Instead of overwriting a row when a source record changes, history mode inserts a new row for every observed state, keeping a full audit trail.

The Connector SDK does not support history mode natively. However, you can mimic its behavior by including a timestamp column as part of a composite primary key.

This connector demonstrates that pattern using a Microsoft SQL Server source. For every table that contains the configured incremental column (e.g. `_LastUpdatedInstant`), the connector appends it to the table's natural primary keys to form a composite primary key. When a record's timestamp changes between syncs, Fivetran inserts a new row rather than overwriting the existing one — history mode behavior without native history mode support.

## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init --template examples/common_patterns_for_connectors/history_mode
```

`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Mimics Fivetran's history mode without requiring native History Mode support.
- Dynamically discovers tables in the configured schema using `INFORMATION_SCHEMA`.
- Builds composite primary keys at runtime: `natural_pks + [incremental_column]`.
- Uses the incremental column as a cursor for incremental syncs — only changed rows are fetched.
- Keyset pagination handles timestamp ties: rows sharing the same timestamp are never skipped at batch boundaries.
- Checkpoints state per table every `5000` records and after each table completes.
- Type-maps SQL Server column types to Fivetran SDK types automatically.


## Configuration file

The connector requires a `configuration.json` file with the following fields:

```json
{
    "mssql_server": "<YOUR_SQL_SERVER_HOST>",
    "mssql_cert_server": "<YOUR_CERT_SERVER_OR_EMPTY>",
    "mssql_port": "<YOUR_PORT>",
    "mssql_database": "<YOUR_DATABASE>",
    "mssql_user": "<YOUR_USERNAME>",
    "mssql_password": "<YOUR_PASSWORD>",
    "mssql_schema": "<YOUR_SCHEMA>",
    "incremental_column": "<YOUR_INCREMENTAL_COLUMN>"
}
```
Configuration parameters:

- `mssql_server` (required) — hostname or IP of the SQL Server instance.
- `mssql_cert_server` (optional) — TLS certificate server name; leave empty to skip validation.
- `mssql_port` (required) — TCP port (typically `1433`).
- `mssql_database` (required) — database name to connect to.
- `mssql_user` (required) — SQL Server login username.
- `mssql_password` (required) — SQL Server login password.
- `mssql_schema` (optional) — schema to discover tables from; defaults to `dbo` if not provided.
- `incremental_column` (required) — column used as the incremental cursor and composite PK component (e.g. `_LastUpdatedInstant`).

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file

This connector requires the `python-tds` package for SQL Server connectivity:

```text
python-tds==1.17.1
```

>Note: [Some packages](https://fivetran.com/docs/connector-sdk/technical-reference#preinstalledpackages) are pre-installed in the Connector SDK runtime environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses SQL Server login authentication. Provide the `mssql_user` and `mssql_password` fields in `configuration.json`. The connector validates all required fields at startup via `validate_configuration()` before any database connection is attempted.


## Pagination

Rows are fetched from SQL Server in batches of `1000` using `cursor.fetchmany()`.

For single-primary-key tables, keyset pagination is used to handle timestamp ties at batch boundaries:

```sql
WHERE (incremental_col > cursor_value)
   OR (incremental_col = cursor_value AND pk_col > last_pk_value)
ORDER BY incremental_col, pk_col
```

For tables with no natural primary key or a composite natural primary key, the connector falls back to a simple `WHERE incremental_col > cursor_value` filter.


## Data handling

- Tables are discovered dynamically from `INFORMATION_SCHEMA.TABLES` in the configured schema (up to 10 tables).
- Natural primary keys are resolved from `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` joined with `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`.
- The composite primary key for each table is `natural_pks + [incremental_column]`. This is the key mechanism for history mode mimicry.
- Column types are mapped from SQL Server types to Fivetran SDK types via `_map_sql_type()`.
- `Decimal` values are serialized to `float` before upsert for SDK compatibility.
- Destination table names follow the pattern `{schema_name}_{table_name}` (e.g. `dbo_Users`).
- Per-table state is stored as `{"cursor": <timestamp_string>, "last_pk": <pk_value>}`.
- Cursor values use `str()` (space-separated datetime, e.g. `"2026-04-24 04:57:58"`) rather than `isoformat()`, which SQL Server accepts directly.


## Error handling

The connector handles specific `pytds` exception types:

- `pytds.LoginError` — wrong username or password; logs and re-raises (permanent failure).
- `pytds.InterfaceError` — wrong host, port, or lost connection; logs and re-raises (may be transient).
- `pytds.ProgrammingError` — bad SQL query or schema mismatch; logs and re-raises (permanent failure).


## Tables created

Tables are created dynamically based on schema discovery. For each discovered table, the connector creates a destination table named `{SCHEMA_NAME}_{TABLE_NAME}` with:

- All columns type-mapped from SQL Server types
- Composite primary key: `[natural_pk_columns..., incremental_column]`

For example, a source table `dbo.Users` with natural PK `UserId` and incremental column `_LastUpdatedInstant` produces:

```text
table: DBO_USERS
primary_key: ["UserId", "_LastUpdatedInstant"]
```

## Additional considerations

- The incremental column must be reliable and monotonically increasing per record. If two updates to the same record can share the same timestamp, the older row will be overwritten rather than preserved.
- Do not use a low-granularity timestamp (e.g. date-only) as the composite key — two updates on the same day would collapse into one row.
- Tables without the incremental column fall back to a full scan on every sync and do not get the history mode composite PK.
- To adapt this pattern to a different source, replace the `pytds` connection with your driver and adjust `_fetch_rows()` accordingly. The composite PK logic in `schema()` applies to any source.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
