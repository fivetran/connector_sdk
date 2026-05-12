# Scroll Token Pagination Connector Example

## Connector overview

This connector demonstrates how to implement scroll token pagination for syncing data from a REST API that returns an opaque token in each response. The connector retrieves user records from a mock API that returns a `scroll_param` token, which is passed back on each subsequent request to fetch the next page of results.

Scroll tokens are a common pattern for APIs that maintain server-side scroll state and return an opaque identifier (sometimes called `cursor`, `next_cursor`, `scroll_id`, or `scroll_param` depending on the API). The connector continues fetching pages until the API returns no token, then clears the token from state so the next sync starts fresh.

This example is intended for learning purposes and uses the [fivetran-api-playground](https://pypi.org/project/fivetran-api-playground/) package to mock the API responses locally. It is not meant for production use.


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
fivetran init --template examples/common_patterns_for_connectors/pagination/scroll_token
```


`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`. For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/connector-sdk-commands#fivetraninit).


## Features

- Demonstrates pure scroll token pagination.
- Fetches pages of data using an opaque `scroll_param` token returned by the API.
- Persists the scroll token in state after each page for mid-sync resumability.
- Clears the token from state when the full dataset has been synced.
- Implements `op.checkpoint()` for resumable syncs.
- Parses and upserts all paginated results into a `user` table.


## Configuration file

This example does not require a configuration file.

For production connectors, `configuration.json` might contain API tokens or base URLs.

> Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file

This connector has no additional runtime Python dependencies beyond what the Fivetran SDK environment already provides.

For local testing of this example, you must install and run the [fivetran-api-playground](https://pypi.org/project/fivetran-api-playground/) mock server as described in [Getting started](#getting-started). This is a local development dependency and should not be added to your `requirements.txt`.

> Note: [Some packages](https://fivetran.com/docs/connector-sdk/technical-reference#preinstalledpackages) are pre-installed in the Connector SDK runtime environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`. 


## Authentication

This connector does not use authentication.

In real-world scenarios, modify `get_api_response()` to add `Authorization` headers or include API keys in query parameters.


## Pagination

Pagination is handled using a scroll token from the API response:
- On the first request, no token is sent — the API returns the first page of results and a scroll token.
- Each subsequent request passes the scroll token as `scroll_param` to fetch the next page.
- When the API returns no scroll token, all data has been retrieved.
- The token is persisted in state after each page so a mid-sync interruption can resume from the last page.
- When the full scroll completes, the token is cleared from state so the next sync starts from the beginning.

> Note: different APIs use different field names for the scroll token (e.g. `cursor`, `next_cursor`, `scroll_id`). Update the field names in `sync_items()` and `get_api_response()` to match your API's response structure.


## Data handling

- Fetches and processes paginated records from a REST endpoint.
- Syncs each item to Fivetran using `op.upsert(table="user", data=...)`.
- Checkpoints state after each page to support reliable resume.


## Error handling

- API errors raise exceptions via `raise_for_status()`.
- Empty pages and missing scroll token are both treated as end of data — state is cleared and checkpointed before exiting.


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
