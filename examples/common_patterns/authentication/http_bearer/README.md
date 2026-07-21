# HTTP Bearer Auth Connector Example

## Connector overview
This connector demonstrates how to implement HTTP bearer token authentication for a REST API using the Fivetran Connector SDK. It retrieves mock user data from a REST endpoint and upserts it into a table named `USER`.

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
fivetran init <project-path> --template examples/common_patterns/authentication/http_bearer
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Implements bearer token-based API authentication.
- Syncs data from a mock REST endpoint using the `requests` library.
- Upserts user data into a Fivetran-compatible destination table.
- Demonstrates the use of `update()` and `op.checkpoint` for resumable syncs.
- Easily debuggable and extensible for prototyping and SDK exploration.

## Configuration file
The connector requires the following configuration parameters: 

```
{
  "bearer_token": "<YOUR_BEARER_TOKEN>"
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
Authentication is handled using a Bearer Token included in the `Authorization` header of each API request.
Example:
`Authorization: Bearer <YOUR_BEARER_TOKEN>`

## Pagination
This connector retrieves all data in a single request (no pagination). If extending to a paginated API, modify the `sync_items()` function to loop through pages using cursor tokens or offsets.

## Data handling
- The connector calls a mock endpoint at `http://127.0.0.1:5001/auth/http_bearer`.
- Data returned from the API is processed in `sync_items()`, and then each user object is passed to `op.upsert()` for syncing to Fivetran.
- After all items are processed, the current state is saved using `op.checkpoint()` to support future incremental syncs.

## Error handling
- Missing or invalid bearer_token in the configuration raises a ValueError.
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
