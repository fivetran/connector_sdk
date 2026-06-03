# Database LIMIT/OFFSET Pagination Connector Example

## Connector overview

This connector demonstrates how to implement LIMIT/OFFSET pagination for syncing data from a PostgreSQL database.

LIMIT/OFFSET pagination adds `LIMIT <N> OFFSET <k>` to every query. It is simple to implement but has two important limitations compared to [keyset pagination](../database_keyset):
- Row-shift: if rows are inserted or deleted while paging, later offsets can shift, causing gaps or duplicate rows.
- Performance: the database must scan and skip `OFFSET` rows for every page, so queries become progressively slower as the offset grows.

For large or frequently updated tables, prefer the [database keyset pagination example](../database_keyset) instead.

This example is intended for learning purposes. It is not meant for production use.


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
fivetran init --template examples/common_patterns_for_connectors/pagination/database_limit_offset
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- Demonstrates LIMIT/OFFSET pagination against a PostgreSQL database.
- Tracks sync progress using a numeric `offset` stored in state.
- Implements `op.checkpoint()` for resumable syncs.
- Parses and upserts all paginated results into a `user` table.


## Configuration file

The connector requires the following configuration keys in the `configuration.json` file:

```json
{
  "hostname": "<YOUR_POSTGRESQL_HOSTNAME>",
  "port": "<YOUR_POSTGRESQL_PORT>",
  "database": "<YOUR_POSTGRESQL_DATABASE_NAME>",
  "username": "<YOUR_POSTGRESQL_USERNAME>",
  "password": "<YOUR_POSTGRESQL_PASSWORD>",
  "sslmode": "<YOUR_SSL_MODE>",
  "table_name": "<YOUR_POSTGRESQL_TABLE_NAME>"
}
```

Configuration parameters:

- `hostname` (required): PostgreSQL server hostname or IP address.
- `port` (required): PostgreSQL server port (typically 5432).
- `database` (required): Name of the database to connect to.
- `username` (required): Database username for authentication.
- `password` (required): Database password for authentication.
- `table_name` (required): Name of the source table to sync data from.
- `sslmode` (optional): SSL mode for connection security. Valid values: `disable`, `require`, or empty string. Defaults to `disable`.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file

The `requirements.txt` file specifies the Python libraries required by the connector:

```
psycopg2_binary==2.9.12
```

- `psycopg2_binary`: PostgreSQL database adapter for Python, used to establish connections and execute queries.

> Note: [Some packages](https://fivetran.com/docs/connector-sdk/technical-reference#preinstalledpackages) are pre-installed in the Connector SDK runtime environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication

The connector uses standard PostgreSQL username/password authentication.

Ensure the database user has `SELECT` privilege on the source table and `CONNECT` privilege on the database.


## Pagination

Pagination tracks a numeric `offset` — the count of rows already processed, stored in state. Each query uses this value in a `LIMIT %s OFFSET %s` clause to fetch the next set of rows.

- On the first sync, `offset` starts at `0`.
- Each query fetches `__ROWS_PER_PAGE` rows starting at the current offset: `LIMIT __ROWS_PER_PAGE OFFSET <offset>`.
- After each page, the offset advances by the actual number of rows returned.
- State is checkpointed every `__CHECKPOINT_INTERVAL` records and at the end of each page.
- Pagination ends when the query returns no rows.
- A deterministic `ORDER BY updated_at, id` is used on every query to ensure a consistent row order across requests.


## Data handling

- Fetches rows in pages of `__ROWS_PER_PAGE` using LIMIT/OFFSET.
- Converts psycopg2 row tuples to dictionaries using `cursor.description` for column names.
- Syncs each row to Fivetran using `op.upsert(table="user", data=...)`.
- Checkpoints state every `__CHECKPOINT_INTERVAL` records and at the end of each page.


## Error handling

- Validates all required configuration parameters before connecting.
- Validates `sslmode` against allowed values.
- Wraps sync failures in `RuntimeError` with the original exception preserved.
- Database connection is always closed in a `finally` block in `update()`.
- Cursor is always closed in a `finally` block in `sync_items()`.
- Empty result sets halt pagination gracefully.


## Tables created

The connector creates the `USER` table:

```
{
  "table": "user",
  "primary_key": ["id"],
  "columns": {
    "id": "INT",
    "name": "STRING",
    "email": "STRING",
    "updated_at": "UTC_DATETIME"
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
