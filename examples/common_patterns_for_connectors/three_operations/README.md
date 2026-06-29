# Three Operations Connector Example

## Connector overview
This connector illustrates how to perform all three core operations supported by the Fivetran Connector SDK:
- `op.upsert()` – Insert or update records.
- `op.update()` – Modify specific fields of an existing record.
- `op.delete()` – Delete records from the destination.

The connector generates synthetic data using Python’s `uuid` library and applies each of the operations on a test table named `THREE`. It is ideal for learning how the SDK interprets different change types and for validating downstream sync behavior.


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/three_operations
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates use of all supported Operations methods:
  - `op.upsert()` to insert new records.
  - `op.update()` to partially modify existing records.
  - `op.delete()` to remove records from the destination.
- Generates unique identifiers using `uuid.uuid4()`.
- Captures and logs operations via the `Logging` module.
- Uses checkpointing to persist sync progress.


## Configuration file
This example does not require a `configuration.json` file.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
No external dependencies are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is needed. This connector runs standalone for demonstration purposes.

## Pagination
Not applicable. This connector emits a static test dataset in each run.


## Data handling
Each sync run performs the following:
- Upsert 3 rows
  - Three unique UUIDs are generated.
  - Rows are inserted into the `THREE` table with `id`, `val1`, and `val2`.
- Update one row
  - The second row `val1` is changed to `"abc"`.
- Delete one row
  - The third row is removed from the destination using `op.delete()`.
- Checkpoint
  - The sync concludes by checkpointing the current state.


## Tables created
The connector creates the `THREE` table:

```json
{
  "table": "three",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING",
    "val1": "STRING",
    "val2": "INT"
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.