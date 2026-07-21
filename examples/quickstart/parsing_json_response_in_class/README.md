# Parsing JSON Response in Class Connector Example

## Connector overview
This example connector demonstrates how to fetch JSON data from a public API and map it into a Python dataclass (POJO-style object) for easy parsing and transformation using the fivetran_connector_sdk library. It fetches data from the [https://jsonplaceholder.typicode.com/posts](https://jsonplaceholder.typicode.com/posts) endpoint and parses it into Python objects. It is a simple demonstration of how to:
- Use `dataclass` to model API responses.
- Implement retry logic with exponential backoff.
- Map parsed JSON objects to upsert operations.

This pattern is useful for APIs with structured JSON responses and promotes readability and testability.

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
fivetran init <project-path> --template examples/quickstart/parsing_json_response_in_class
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features
- Converts API JSON responses into structured Python data classes.
- Predefined schema maps the structure of incoming data to Fivetran-compatible tables.
- Uses `op.upsert` to sync and deduplicate data efficiently.


## Configuration file
No configuration file is required for this example, as it connects to a public API.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:
```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not require authentication - as it connects to a public API that doesn't require any authentication.


## Pagination
Not applicable - as this example fetches all data from a single endpoint without pagination.


## Data handling
- API responses are parsed directly into Python data classes (`Post`) using dataclass for clean and reliable access to fields.
- Data is extracted from the `Post` object and explicitly mapped to expected types (`INT`, `STRING`) before being upserted into the `POSTS` table.
- This simple connector does not use state-based pagination or checkpoints, as the API returns all available records per call.


## Error handling
- Any record that fails deserialization or processing is logged and skipped, preventing sync interruption.
- A capped exponential backoff ensures the connector gracefully retries failed API requests before exiting.


## Tables created
The connector creates the `POSTS` table:

```json
{
  "table": "posts",
  "primary_key": [
    "id"
  ],
  "columns": {
    "id": "INT",
    "userId": "INT",
    "title": "STRING",
    "body": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
