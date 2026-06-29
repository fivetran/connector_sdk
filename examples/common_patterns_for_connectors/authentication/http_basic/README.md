# HTTP Basic Auth Connector Example

## Connector overview
This is a simple example that demonstrates how to implement HTTP basic authentication with a REST API using the Fivetran Connector SDK. The connector fetches user records from a mock API and upserts them into a table named `USER`. It serves as a learning resource for implementing HTTP Basic Auth, schema management, state checkpointing, and syncing data to Fivetran destinations.

This example is intended for learning purposes and uses the [fivetran-api-playground](https://pypi.org/project/fivetran-api-playground/) package to mock the API responses locally. It is not meant for production use.

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
fivetran init <project-path> --template examples/common_patterns_for_connectors/authentication/http_basic
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Demonstrates how to use HTTP basic authentication.
- Retrieves mock user data using the `requests` library.
- Defines a `schema()` function to register Fivetran-compatible output.
- Uses the `update()` method to process and upsert rows.
- Saves sync state to support incremental or resumable runs.

## Configuration file
The connector requires the following configuration parameters: 

```
{
  "username": "<YOUR_USERNAME>",
  "password": "<YOUR_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector requires the following Python dependencies:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector authenticates using HTTP basic auth. The credentials (username and password) are base64-encoded and passed in the `Authorization` header of each API request.
Example:
`Authorization: Basic <base64_encoded_credentials>`

## Pagination
This connector retrieves all data in a single request (no pagination). If extending to a paginated API, modify the `sync_items()` function to loop through pages using cursor tokens or offsets.

## Data handling
- The connector calls a mock endpoint at `http://127.0.0.1:5001/auth/http_basic`.
- Data returned from the API is processed in `sync_items()`, and then each user object is passed to `op.upsert()` for syncing to Fivetran.
- After all items are processed, the current state is saved using `op.checkpoint()` to support future incremental syncs.

## Error handling
- If authentication fields (username or password) are missing, `get_auth_headers()` raises a ValueError.
- HTTP errors are caught via `raise_for_status()` in the `get_api_response()` function.
- Logging is done using the `fivetran_connector_sdk.Logging` module.

## Tables created
The connector creates the `USER` table:

```
{
  "table": "user",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING",
    "name": "STRING",
    "email": "STRING",
    "address": "STRING",
    "company": "STRING",
    "job": "STRING",
    "updatedAt": "UTC_DATETIME",
    "createdAt": "UTC_DATETIME"
  }
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
