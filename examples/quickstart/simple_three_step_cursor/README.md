# Simple Three-Step Cursor Connector Example

## Connector overview
This connector demonstrates a minimal use case for implementing a cursor-based sync using the Fivetran Connector SDK. It uses a local list of static data (`SOURCE_DATA`) and syncs one row per run based on a simple cursor stored in the connector's state.

This example is ideal for learning how to:
- Use a basic cursor to track sync progress.
- Emit upserts one row at a time.
- Define a schema with partial column specification.
- Safely checkpoint after each sync.

Note: This connector will sync 3 records across 3 runs. A fourth run will raise a controlled error to simulate end-of-data handling in development.


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
fivetran init <project-path> --template examples/quickstart/simple_three_step_cursor
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Uses a hardcoded data source (`SOURCE_DATA`).
- Syncs one record per run using a basic integer cursor.
- Demonstrates `op.upsert()` and `op.checkpoint()` usage.
- Implements a `schema()` function with partial column definition (Fivetran will infer missing types).


## Configuration file
The connector does not require any configuration parameters.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Not Applicable - this connector uses local static data.


## Pagination
Not applicable - this example uses a simple positional cursor (`state["cursor"]`) to control sync flow.


## Data handling
- `SOURCE_DATA` is a list of dictionaries (`records`).
- Only one record is synced per run, based on the current cursor.
- Once all records are synced, a controlled `list index out of range` error is raised.


## Error handling
- If the cursor exceeds the bounds of `SOURCE_DATA`, an exception is raised intentionally to simulate exhaustion.
- State is checkpointed after each successful upsert.


## Tables Created
The connector creates a `HELLO_WORLD` table:

```json
{
  "table": "hello_world",
  "primary_key": ["id"],
  "columns": {
    "message": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.