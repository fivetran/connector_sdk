# Multiple Schema Connector Example

Note: The multiple schema feature demonstrated in this example is currently in private preview and is not available to all accounts by default. If you want to use this feature, reach out to [Fivetran Support](https://support.fivetran.com/hc/en-us) to request access before trying this example.

## Connector overview
This connector demonstrates how to define and write to multiple schemas in a single connector by using the `schema()` function and the `op.upsert()`, `op.update()`, `op.delete()`, and `op.truncate()` operations.

## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/multiple_schema
```

`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connectors/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Declares two separate destination schemas using `schema()`.
- Declares two tables, `sample_table` and `sample_table_2`, within `schema_1`, in addition to `schema_2.sample_table`, to show that a single schema can host multiple tables.
- Upserts multiple sample records to `schema_1.sample_table` and `schema_2.sample_table`.
- Upserts sample records to `schema_1.sample_table_2`.
- Demonstrates `op.update()` against a schema-scoped table.
- Demonstrates `op.delete()` against a schema-scoped table.
- Demonstrates `op.truncate()` against a schema-scoped table.
- Persists sync progress through `op.checkpoint(state)`.

## Configuration file
This example does not require any custom configuration fields.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector does not require authentication because it writes static sample data to demonstrate multiple-schema behavior.

## Data handling
The `schema()` function defines three tables across the two schemas: `schema_1.sample_table`, `schema_1.sample_table_2`, and `schema_2.sample_table`. `schema_1` hosts two different tables, while `schema_2` shares the same table structure as `schema_1.sample_table`, to show how a single connector can mix shared and schema-specific tables:

```json
[
  {
    "schema": "schema_1",
    "table": "sample_table",
    "primary_key": ["id"],
    "columns": {
      "id": "INT",
      "sample_column": "INT"
    }
  },
  {
    "schema": "schema_1",
    "table": "sample_table_2",
    "primary_key": ["id"],
    "columns": {
      "id": "INT",
      "sample_column": "INT"
    }
  },
  {
    "schema": "schema_2",
    "table": "sample_table",
    "primary_key": ["id"],
    "columns": {
      "id": "INT",
      "sample_column": "INT"
    }
  }
]
```

The `update()` function in `connector.py` creates multiple sample rows, upserts them into `schema_1.sample_table` and `schema_2.sample_table`, upserts additional sample rows into `schema_1.sample_table_2`, updates one row in `schema_1.sample_table` with a new value, deletes a row from `schema_2.sample_table`, truncates `schema_1.sample_table`, and then checkpoints state. This pattern is useful when a single connector needs to write data to multiple logical destinations, including multiple tables within the same schema, without creating separate connectors.

## Tables created
The connector creates three tables across the two schemas:

Schema: `schema_1` and Table: `sample_table`

| id       | sample_column | fivetran_deleted |
|----------|:-------------:|-----------------:|
| 1        |      100      |             true |
| 2        |      43       |             true |
| 3        |      44       |             true |

Schema: `schema_1` and Table: `sample_table_2`

| id       | sample_column | fivetran_deleted |
|----------|:-------------:|-----------------:|
| 1        |      100      |            false |
| 2        |      200      |            false |

Schema: `schema_2` and Table: `sample_table`

| id       | sample_column | fivetran_deleted |
|----------|:-------------:|-----------------:|
| 1        |      42       |             true |
| 2        |      43       |            false |
| 3        |      44       |            false |


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
