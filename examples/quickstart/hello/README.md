# Hello World Connector Example

## Connector overview
This is the simplest possible connector using the Fivetran Connector SDK. It defines only the `update()` function and emits a single row containing the message "hello, world!" to a table named `HELLO`.

This example is useful as a bare-minimum test to:
- Understand connector structure.
- Validate your SDK setup and environment.
- Experiment with local debug execution before building a real connector.

Note: This example omits the `schema()` function and therefore does not explicitly declare column types, which is not recommended for production connectors. See [Best Practices](https://fivetran.com/docs/connector-sdk/best-practices#declaringprimarykeys) for more.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to set up your environment.

To start from this example, run:

```bash
fivetran init <project-path> --template examples/quickstart/hello
```

`fivetran init` creates a new project directory with the connector file and supporting configuration. If you omit `<project-path>`, Fivetran creates the project in your current directory. For more information, see the [`fivetran init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Implements only the `update()` function.
- Sends a single record with one string field: `"hello, world!"`.
- Uses `op.upsert()` to insert the row.
- Uses `op.checkpoint()` to safely track sync state.


## Configuration file
No configuration file is required for this example.

Note: Ensure that `configuration.json` is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not require authentication — it emits static local data.


## Pagination
Not applicable — no API or iteration logic is present.


## Data handling
- The `update()` function emits one hardcoded row.
- No schema is declared, so Fivetran infers the column name and type automatically.


## Error handling
No error handling is implemented, as this example does not interact with external systems.


## Tables created
The connector creates a `HELLO` table:

```json
{
  "table": "hello",
  "primary_key": ["_fivetran_id"],
  "columns": {
    "_fivetran_id": "STRING",
    "message": "STRING"
  }
}
```


## Running and debugging locally

### 1. Run the connector

This example does not need configuration values, but SDK v2.11.0 and later require a `configuration.json` file for `fivetran debug`. Keep the template's configuration file, or create one containing `{}` if it is missing.

The same file is needed when running `connector.py` directly from your IDE. From your project directory, run:

```bash
fivetran debug
```

`fivetran debug` runs your connector locally and emulates the Fivetran sync environment. After a successful run, it creates the following files in a `files/` directory inside your project:

- `warehouse.db` — A DuckDB database representing the data your connector would deliver to a destination.
- `state.json` — The connector state saved after the sync, used as the starting point for the next run.

### 2. Inspect the results

The `HELLO` table in `warehouse.db` contains one row after a successful run:

```
┌───────────────┐
│    message    │
│    varchar    │
├───────────────┤
│ hello, world! │
└───────────────┘
```

You can query `warehouse.db` directly using the [DuckDB CLI](https://duckdb.org/docs/installation/) or a DuckDB-compatible tool such as [DBeaver](https://dbeaver.io/):

```bash
duckdb files/warehouse.db "SELECT * FROM hello"
```

### 3. Reset and re-run

To test a fresh initial sync, delete the local state and warehouse data:

```bash
fivetran reset
```

Then run `fivetran debug` again. `fivetran reset` only removes the local `files/state.json` and `files/warehouse.db` — it does not affect any deployed connection.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
