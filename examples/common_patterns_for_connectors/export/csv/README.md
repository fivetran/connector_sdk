# CSV Export API Connector Example

## Connector overview
This example demonstrates how to build a Fivetran connector that consumes data from a REST API that returns CSV content (commonly used in export/reporting APIs). It fetches the CSV payload from a given URL, parses the content, and upserts each row into a table named `USER`.

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
fivetran init <project-path> --template examples/common_patterns_for_connectors/export/csv
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates handling of CSV responses from a REST API.
- Uses `csv.DictReader` to parse CSV into a list of dictionaries.
- Upserts rows into a single `USER` table.
- Logs data parsing steps and sync status.
- Includes `checkpoint()` for state persistence (though no incremental cursor is implemented).


## Configuration file
This example does not require any user-supplied configuration.

In a real-life implementation, you might include API keys, date ranges, or export task parameters in `configuration.json`.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This example uses a local development server without authentication.
In production scenarios, you may need to:
- Add headers for API key or Bearer token
- Sign requests with OAuth or session tokens

Modify `get_csv_response()` to add the appropriate headers based on your API’s requirements.


## Pagination
This connector does not support pagination.
To support multipage or batched CSV exports in the future, consider:
- Fetching files from a paginated endpoint.
- Streaming partial CSV responses.
- Polling export tasks and downloading files.


## Data handling
- The connector sends an HTTP GET request to the CSV endpoint.
- The raw text response is parsed using Python’s built-in csv module.
- Each CSV row is converted to a dictionary and upserted into the user table.
- State is checkpointed after the batch for safe resumption on subsequent runs.


## Error handling
- HTTP errors are raised using `raise_for_status()`.
- Parsing errors during CSV transformation are handled implicitly via Python’s `csv.DictReader`.
- `log.info()` is used for tracking sync steps and row-level operations.


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