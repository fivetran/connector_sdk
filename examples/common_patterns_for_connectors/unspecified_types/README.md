# Unspecified Column Types Connector Example

## Connector overview
This connector demonstrates how the Fivetran Connector SDK automatically infers column names and data types from the data you send when the `schema()` method does not explicitly declare them. It’s a helpful example when:
- You want to quickly prototype a connector.
- The schema may vary over time or is dynamic.
- You want to see how Fivetran interprets Python-native types into SDK-compatible column definitions.

Each sync emits a single row containing a variety of types — strings, numbers, dates, JSON, binary, XML, and null values — into a table called `UNSPECIFIED`.

For more details on supported types and inference logic, refer to the [Technical Reference - Data Types](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes).


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/unspecified_types
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Sends a variety of Python-native types without defining any columns in the schema.
- Demonstrates automatic type inference by Fivetran.
- Syncs a row using `op.upsert()` and checkpoints state for safe resumability.
- Uses null handling `None` to test how missing values are interpreted.


## Configuration file
This example does not require a `configuration.json` file.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
No external dependencies are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is required.

## Pagination
Not applicable - this connector emits a single static row each sync.


## Data handling
- The `schema()` function defines only the table name and primary key (id).
- All column names and types are inferred from the keys and values in the data dictionary.
- Supported types are inferred from:
  - `int`, `float`, `bool`, `str`, `dict`, `bytes`, `datetime` (in string form), and `None`.


## Tables created
The connector creates one table:

```json
{
  "table": "as_specified_in_connector.py",
  "primary_key": ["id"],
  "columns": "inferred"
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.