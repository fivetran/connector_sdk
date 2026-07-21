# Next Page URL Pagination Connector Example

## Connector overview
This example demonstrates how to implement next-page URL-based pagination for REST APIs. The connector fetches records from a paginated API where the next page of results is retrieved via a `next_page_url` included in the API response. It syncs user data into a destination table named `USER`.

This pagination strategy is useful when:
- The API includes the full URL for the next page in each response
- Query parameters may vary or include tokens that must be preserved across page

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
fivetran init <project-path> --template examples/common_patterns/pagination/next_page_url
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates handling of `next_page_url` pagination logic.
- Tracks sync position using the `updatedAt` timestamp.
- Automatically follows next-page links across paginated API responses.
- Uses `op.checkpoint()` to safely store progress across runs.


## Configuration file
This example does not require a configuration file.

For production connectors, `configuration.json `might contain API tokens, initial cursors, or filters to narrow down API results.

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
Pagination is based on the next_page_url key provided in the API response:
```json
{
  "data": [...],
  "next_page_url": "https://api.example.com/page=2"
}
```
- The initial request includes `updated_since`, `order_by`, and `per_page`.
- If `next_page_url` is present, it is used as the next request's endpoint.
- Query parameters are cleared because they’re already embedded in the `next_page_url`.

Pagination continues until no `next_page_url` is returned.


## Data handling
- The connector fetches user records from each page.
- Each row is passed to `op.upsert()` for syncing into the `USER` table.
- The `state["last_updated_at"]` field is updated after processing each row.
- `op.checkpoint()` is called to persist the cursor across runs.

## Error handling
- API errors are raised via `response.raise_for_status()`.
- If no data or `next_page_url` is present, pagination ends gracefully.
- All actions are logged with `log.info()` and `log.warning()`.

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