# LeaveDates API Connector Example

## Connector overview
The [LeaveDates](https://app.leavedates.com/) connector fetches leave report data from the LeaveDates  API `/reports/leave` endpoint and syncs it to your destination. The connector retrieves detailed leave information including employee names, leave types, amounts, dates, status, and other related metadata. It supports incremental synchronization based on timestamps and handles pagination automatically to ensure all leave records are captured efficiently. The connector uses the LeaveDates detail-report format to provide comprehensive leave data for analytics and reporting purposes.


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
fivetran init <project-path> --template connectors/leavedates
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Incremental data synchronization based on timestamps using `within` parameter
- Automatic pagination handling for large datasets (pages tracked automatically)
- Retry logic with exponential backoff and jitter for API requests
- Flattened data structure with underscore-separated keys for easy querying
- Configurable date range for historical data fetching
- Bearer token authentication for secure API access
- Comprehensive error handling and logging
- State management with checkpointing for sync resumption


## Configuration file
The connector requires the following configuration parameters in the `configuration.json` file:

```
{
  "api_token": "<YOUR_LEAVE_DATES_API_TOKEN>",
  "company_id": "<YOUR_LEAVE_DATES_COMPANY_ID>",
  "start_date": "<OPTIONAL_START_DATE>"
}
```

**Required fields:**
- `api_token` - Your LeaveDates API authentication token
- `company_id` - Your company UUID from LeaveDates

**Optional fields:**
- `start_date` - ISO format timestamp for historical data sync (defaults to 1900-01-01 if not provided)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector example uses the standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses Bearer token authentication to access the LeaveDates API. To obtain your API token:

1. Log in to your LeaveDates.com account.
2. Navigate to the API settings in your account dashboard.
3. Generate or copy your API token.
4. Add the token to your `configuration.json` file.
5. Ensure you have the correct company ID from your LeaveDates account.


## Pagination
The connector handles pagination automatically by iterating through all pages of results. It starts from page 1 and continues until all data is retrieved. The pagination logic is implemented in the `fetch_leave_reports` function, which tracks the current page and total pages to ensure complete data retrieval.


## Data handling
The connector processes leave report data by flattening nested JSON structures into a tabular format suitable for database storage. The `flatten_record` function converts nested objects into underscore-separated keys and handles arrays by converting them to JSON strings. Data is processed in the `update` function and upserted into the `leave_reports` table with incremental synchronization based on the last sync timestamp. The `schema` function defines the table structure with `id` as the primary key.


## Error handling
The connector implements comprehensive error handling including retry logic with exponential backoff for API requests. The `make_api_request_with_retry` function handles transient network errors and API rate limits. Configuration validation is performed by the `validate_configuration` function, which ensures all required parameters are present before execution.


## Tables created

The connector creates the following table in your destination:

| Table name     | Primary key | Description                                                                                       |
|----------------|-------------|---------------------------------------------------------------------------------------------------|
| `LEAVE_REPORT` | `id`        | Leave report data with flattened employee leave information including dates, status, and metadata |

The table includes flattened versions of nested objects using underscore notation, with arrays converted to JSON strings for storage.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
