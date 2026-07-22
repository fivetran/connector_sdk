# All Supported Data Types Connector Example

## Connector overview
This connector provides a minimal working example to demonstrate how to define all supported data types using the Fivetran Connector SDK. It uses the `schema()` method to declare columns of every core type, and the `update()` method to sync a single row containing example values for each type.

This is useful for:
- Testing downstream pipelines and integrations.
- Learning how to define and format each Fivetran-supported data type.
- Building a schema reference or validation utility.

For full type details, refer to the [Technical Reference – Supported Data Types](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes).


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
fivetran init <project-path> --template examples/common_patterns/specified_types
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates every supported column data type, including:
  - `BOOLEAN`, `SHORT`, `LONG`, `DECIMAL`, `FLOAT`, `DOUBLE`
  - `NAIVE_DATE`, `NAIVE_DATETIME`, `UTC_DATETIME`
  - `BINARY`, `XML`, `STRING`, `JSON`
- Shows how to define precision/scale for `DECIMAL`.
- Handles null values using `None` in Python.
- Includes a valid row with sample values for testing ingestion.


## Configuration file
This example does not require a `configuration.json` file.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
No external dependencies are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is needed. This connector runs standalone for demonstration purposes.

## Pagination
Not applicable. This connector emits a single static row during each sync.


## Data handling
- The `schema()` function returns a full data-type definition for the specified table.
- The `update()` function constructs a dictionary containing values for each type.
- Binary and JSON fields are formatted using Python-native values.
- The connector make an `op.upsert()` call and checkpoints the state.


## Error handling
- Raises descriptive errors when configuration keys are missing.
- Uses `raise_for_status()` for failed SQL queries.
- Safely closes connections and cursors.

## Tables created
The connector creates one table:

```json
{
  "table": "specified",
  "primary_key": ["_bool"],
  "columns": {
    "_bool": "BOOLEAN",
    "_short": "SHORT",
    "_long": "LONG",
    "_dec": {
      "type": "DECIMAL",
      "precision": 15,
      "scale": 2
    },
    "_float": "FLOAT",
    "_double": "DOUBLE",
    "_ndate": "NAIVE_DATE",
    "_ndatetime": "NAIVE_DATETIME",
    "_utc": "UTC_DATETIME",
    "_binary": "BINARY",
    "_xml": "XML",
    "_str": "STRING",
    "_json": "JSON",
    "_null": "STRING"
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.