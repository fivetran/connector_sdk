# Page Number-Based Pagination Connector Example

## Connector overview
This connector demonstrates how to implement page number-based pagination when syncing data from a REST API. It fetches paginated results using `page`, `per_page`, and `total_pages` values returned by the API and upserts them into a table named `USER`.

This is a common strategy used by REST APIs that support explicit control of pagination through numbered pages rather than offset, cursors, or next-page tokens.

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
fivetran init <project-path> --template examples/common_patterns/pagination/page_number
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates page-by-page data retrieval from an API using `page` and `per_page`.
- Tracks sync progress with `updatedAt` as the replication cursor.
- Implements `op.checkpoint()` after each page to support resumability.
- Automatically ends pagination when all pages are processed.


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
Pagination is handled via numeric page control:
- Query parameters:
  - `page`, `per_page`, `order_by`, `order_type` and `updated_since`.
- API response must contain:
  - `page`: current page number.
  - `total_pages`: total number of pages.


## Data handling
- Fetches users in ascending `updatedAt` order.
- Upserts each item into the user table via `op.upsert()`.
- Saves the updatedAt of the last item as a checkpoint after every page.
- Continues to the next page until all pages are exhausted.

## Error handling
- HTTP request errors are raised via `raise_for_status()`.
- Empty pages end pagination gracefully.
- Pagination stops when the current page matches total_pages.

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