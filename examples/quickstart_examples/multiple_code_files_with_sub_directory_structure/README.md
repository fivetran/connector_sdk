# Multiple Code Files with Custom Timestamp Serialization Example

## Connector overview
This example demonstrates how to build a modular connector using multiple Python files in a Fivetran Connector SDK project. It showcases the use of a `connector.py` and `timestamp_serializer.py`, for handling non-uniform timestamp formats from the source system.

This pattern is ideal when:
- Your source sends timestamps in different formats (e.g. both `yyyy-MM-dd` and `yyyy/MM/dd)`.
- You want to centralize logic for date normalization and reuse it across different sync flows.
- You need to parse raw date strings and convert them into standardized UTC ISO 8601 format.


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
fivetran init <project-path> --template examples/quickstart_examples/multiple_code_files_with_sub_directory_structure
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Handles timestamp fields in multiple formats:
  - `YYYY-MM-DD HH:mm:ss`
  - `YYYY/MM/DD HH:mm:ss`
- Converts all timestamps to UTC ISO 8601 format, as recommended by Fivetran.
- Organizes serialization logic in a reusable module.
- Emits normalized data to the event table.
- Uses `op.checkpoint()` to persist sync state.


## Configuration file
The connector does not require any configuration parameters.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Not Applicable - this example runs entirely on static test data.


## Pagination
Not applicable - only two records are processed per sync.


## Data handling
- Timestamps are parsed by the `TimestampSerializer` class using two predefined formats.
- Each parsed timestamp is converted to UTC and serialized in ISO 8601 format.
- The `update()` function syncs one row per event.


## Error handling
- If a timestamp string does not match any known format, a `ValueError` is raised with a descriptive message.
- Invalid formats are caught early via the `parse_timestamp()` method.
- Logs are recorded using the Fivetran SDK’s Logging module (`log.warning`, `log.debug`).


## Tables Created
The connector creates an `EVENT` table:

```json
{
  "table": "event",
  "primary_key": ["name"],
  "columns": {
    "name": "STRING",
    "timestamp": "UTC_DATETIME"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.