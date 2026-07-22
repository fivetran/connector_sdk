# Offset-Based Pagination Connector Example

## Connector overview
This connector demonstrates how to use offset-based pagination for fetching data from a paginated REST API. It uses a `limit` and `offset` strategy to retrieve records in chunks and syncs the results into a `USER` table. The connector tracks progress using the updatedAt timestamp and resumes from the last state during subsequent syncs.

This pagination method is most suitable when the API:
- Supports numerical `offset` and page size `limit`.
- Returns total number of records `total)`.
- Supports ordering by an update key `updatedAt`.

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
fivetran init <project-path> --template examples/common_patterns/pagination/offset_based
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates classic offset-based pagination with `limit` and `offset`.
- Filters results using an `updated_since` timestamp for incremental syncs.
- Supports safe and resumable state checkpointing using `op.checkpoint()`.
- Updates the replication cursor based on `updatedAt` timestamp from the latest record.


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
Pagination is handled using the following parameters:
- `offset`: Current position in the record set.
- `limit`: Number of records per page (e.g., 50).
- `total`: Total number of records available (from API response).

Pagination logic:
- Continues requesting pages while `(offset + page_size) < total`.
- Advances the offset by the number of records returned.
- Ends when the full dataset has been consumed.


## Data handling
- Starts sync with` updated_since = '0001-01-01T00:00:00Z'` if no state is present.
- Each record is passed to `op.upsert()` with destination table `USER`.
- The state is updated with the latest `updatedAt` value from each page.
- After each page, `op.checkpoint()` saves progress to ensure resumability.

## Error handling
- API errors are raised via `response.raise_for_status()`.
- Handles empty pages or partial results gracefully.
- Logs the start of each page and first record ID for traceability.

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