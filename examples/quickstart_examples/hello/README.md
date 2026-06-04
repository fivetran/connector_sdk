# Hello World Connector Example

## Connector overview
This is the simplest possible connector using the Fivetran Connector SDK. It defines only the `update()` function and emits a single row containing the message "hello, world!" to a table named `HELLO`.

This example is useful as a bare-minimum test or template to:
- Understand connector structure and generator usage.
- Validate SDK setup and basic sync mechanics.
- Experiment with debug-mode execution.

Note: This example omits the `schema()` function and therefore does not explicitly declare column types, which is not recommended for production connectors. See [Best Practices](https://fivetran.com/docs/connector-sdk/best-practices#declaringprimarykeys) for more.


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
fivetran init <project-path> --template examples/quickstart_examples/hello
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Implements only the `update()` function.
- Sends a single record with one string field: `"hello, world!"`.
- Uses `op.upsert()` to insert the row.
- Uses `op.checkpoint()` to safely track sync state.


## Configuration file
No configuration file is required for this example.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not require authentication - this connector emits static local data.


## Pagination
Not applicable - no API or iteration logic is present.


## Data handling
- The `update()` function emits one hardcoded row.
- No schema is declared, so Fivetran infers the column name and type automatically.


## Error handling
- No error handling is implemented, as this example does not interact with external systems.


## Tables Created
The connector creates a `HELLO` table:

```json
{
  "table": "hello",
  "primary_key": ["_fivetran_id"],
  "columns": {
    "_fivetran": "STRING",
    "message": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.