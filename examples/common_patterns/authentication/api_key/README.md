# API Key Auth Connector Example

## Connector overview
This is a simple example that demonstrates how to implement API key authentication with a REST API using the Fivetran Connector SDK. The connector retrieves user records from a mock API and upserts them into a table named `USER`. It illustrates core concepts such as schema definition, data sync via the update method, state checkpointing, and API request handling using the `requests` library.

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
fivetran init <project-path> --template examples/common_patterns/authentication/api_key
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Demonstrates API key authentication pattern.
- Retrieves user data from a mock API using `requests`.
- Implements the update method to upsert rows into the `USER` table.
- Uses checkpointing to persist sync state.
- Suitable for understanding SDK fundamentals and debugging connector behavior locally.

## Configuration file
The connector requires the following configuration parameters: 

```
{
  "api_key": "<YOUR_API_KEY>"
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
Authentication is handled via an API key, which is sent in the `Authorization` header of each API request.
Example:
`Authorization: apiKey <YOUR_API_KEY>`

## Pagination
This connector retrieves all data in a single request (no pagination). If extending to a paginated API, modify the `sync_items()` function to loop through pages using cursor tokens or offsets.

## Data handling
- Data is retrieved from a mock REST API endpoint: `http://127.0.0.1:5001/auth/api_key`.
- The `sync_items()` function sends a GET request and reads the JSON payload.
- Each user object is passed to `op.upsert()` for syncing to Fivetran.
- The state object is checkpointed at the end of each sync for incremental syncs in the future.

## Error handling
- Missing API key in configuration raises a ValueError.
- HTTP errors are raised via `response.raise_for_status()` in `get_api_response()`.
- Logging is handled via `fivetran_connector_sdk.Logging`.

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
