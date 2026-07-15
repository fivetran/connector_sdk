# Key-Based Pagination Connector Example

## Connector overview
This connector demonstrates how to implement keyset pagination for syncing data from a REST API that supports incremental fetching using a cursor or scroll token. The connector retrieves user records from a mock API that returns a `scroll_param` in its response, which is used to fetch subsequent pages of results.

This is a common pattern for APIs that do not support offset-based pagination, but instead provide a token (e.g. `updated_since`, `next_cursor`, `scroll_param`) to retrieve the next chunk of data.

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
fivetran init <project-path> --template examples/common_patterns/pagination/keyset
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates cursor-based (keyset) pagination.
- Fetches pages of data using a `scroll_param` token returned by the API.
- Tracks sync progress using a timestamp `updatedAt` checkpoint.
- Implements `op.checkpoint()` for resumable and incremental syncs.
- Parses and upserts all paginated results into a `USER` table.


## Configuration file
This example does not require a configuration file.

For production connectors, `configuration.json` might contain API tokens, initial cursors, or filters to narrow down API results.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not use authentication.

In real-world scenarios, modify `get_api_response()` to add `Authorization` headers or include API keys in query parameters.


## Pagination
Pagination is handled using a scroll key (cursor) from the response:
- On the first sync, the connector starts with updated_since = '0001-01-01T00:00:00Z'
- Each API response includes:
  - A list of data items 
  - A `scroll_param` token used to fetch the next page
- The connector continues fetching data until no `scroll_param` is returned


## Data handling
- Fetches and processes paginated records from a REST endpoint.
- Extracts and updates `state["last_updated_at"]` after each record.
- Syncs each item to Fivetran using `op.upsert(table="user", data=...)`.
- Periodically checkpoints state to support reliable resume.


## Error handling
- API errors raise exceptions via `raise_for_status()`.
- Empty pages halt pagination gracefully.
- Invalid responses (missing scroll keys or data) are handled implicitly.

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