# Session Token Auth Connector Example

## Connector overview
This example demonstrates how to implement session token authentication for a REST API using the Fivetran Connector SDK. It simulates a login flow where credentials are exchanged for a temporary session token, which is then used to authorize subsequent API requests. The connector retrieves user records and upserts them into a destination table named `USER`.

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
fivetran init <project-path> --template examples/common_patterns_for_connectors/authentication/session_token
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Authenticates via a temporary session token obtained through a `/login` endpoint.
- Handles token expiry by detecting HTTP 401 responses, re-authenticating, and retrying the request once.
- Separates credential handling and data retrieval in dedicated helper functions.
- Retrieves and syncs user records into a Fivetran-managed destination table.
- Demonstrates session-based authentication handling, error recovery, and state checkpointing.

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
Authentication is done via a two-step session process:
- The connector calls a login endpoint `(/login)` with username and password.
- The response includes a session token, which is used in the `Authorization` header for subsequent data API calls.

Example:
`Authorization: Token <SESSION_TOKEN>`

## Pagination
This connector retrieves all data in a single request (no pagination). If extending to a paginated API, modify the `sync_items()` function to loop through pages using cursor tokens or offsets.

## Data handling
- Logs in to the mock API at `http://127.0.0.1:5001/auth/session_token/login` to retrieve a session token.
- Retrieves user records from the `/data` endpoint using the token.
- Data is processed and passed to `op.upsert()` for syncing into Fivetran.
- `op.checkpoint()` is called to persist state after a successful sync.

## Error handling
- Missing credentials trigger a ValueError in `validate_configuration()`.
- HTTP 401 responses (expired token) trigger a single re-authentication and retry in `sync_items()`.
- All other HTTP errors are caught via `raise_for_status()`.
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
