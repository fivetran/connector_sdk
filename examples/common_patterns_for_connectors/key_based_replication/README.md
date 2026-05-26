# Key-Based Incremental Replication Connector Example

## Connector overview
This connector demonstrates how to implement incremental replication using a column-based replication key. It simulates syncing from a DuckDB table where the `updated_at` timestamp is used to identify newly inserted or modified rows.

This example is useful when:
- You're building a connector to a database or API that includes a "last updated" column
- You want to implement efficient, stateful syncs that only fetch new or changed data since the last run

This connector uses hardcoded sample data in DuckDB to simulate the behavior of a real database source.


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/key_based_replication
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Simulates a DuckDB source with a `CUSTOMERS` table.
- Uses `updated_at` column as a replication key.
- Fetches only records updated since the last sync.
- Implements `op.checkpoint()` to store the latest timestamp state.
- Demonstrates how to build connectors for source databases using key-based replication.


## Configuration file
This example does not require any external configuration.

For production connectors, you may provide database credentials, connection strings, or optional filtering parameters in a `configuration.json `file.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
duckdb
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This example runs against an in-memory DuckDB instance and does not require authentication.

In real-world use, your connector would authenticate to a source database using credentials and a connection string stored in the configuration.


## Pagination
This connector relies on a timestamp cursor, `updated_at`, instead of pagination. It fetches all rows greater than the last synced value.

To handle pagination for large datasets, use a cursor in combination with LIMIT/OFFSET or keyset pagination (e.g. WHERE updated_at > ? LIMIT 1000).


## Data handling
- On the first sync, the connector starts from a default cursor (2024-01-01T00:00:00Z).
- It fetches all rows where `updated_at > last_synced_timestamp`.
- It syncs each row via `op.upsert()` to the `CUSTOMERS` table.
- After syncing all new data, it updates the state with the latest updated_at value.
- The `schema()` function explicitly defines columns and primary key (customer_id).


## Error handling
- If the DuckDB engine or SQL query fails, the connector raises an exception.
- Use `log.debug()` and `log.warning()` to debug cursor values and row counts.
- The use of `op.checkpoint()` ensures recoverability on restart.


## Tables created
The connector creates the `CUSTOMERS` table:

```
{
  "table": "customers",
  "primary_key": ["customer_id"],
  "columns": {
    "customer_id": "INT",
    "first_name": "STRING",
    "last_name": "STRING",
    "email": "STRING",
    "updated_at": "UTC_DATETIME"
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.