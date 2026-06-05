# Connector SDK GreytHR API Connector Example

## Connector overview
This connector syncs Employee, Leave Transactions, and Attendance Insights data from the greytHR API to Fivetran destinations. greytHR is a cloud-based HR and payroll management platform that provides comprehensive employee data management capabilities. This connector implements incremental syncing with proper state management and handles the greytHR API's 31-day date range limitation for Leave and Attendance endpoints through intelligent date windowing.

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
fivetran init <project-path> --template connectors/grey_hr
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- OAuth2 client credentials authentication for secure API access
- Automatic token refresh on expiration (401 errors) for uninterrupted syncing
- Incremental syncing for Employee data based on lastModified timestamp
- Incremental syncing for Leave Transactions and Attendance Insights with date-based state management
- Automatic date windowing to handle greytHR's 31-day maximum date range limit
- Pagination support for the Employee endpoint with configurable page size
- Automatic flattening of nested JSON objects into destination table columns
- Breakout tables for array data (leave transaction children, attendance metrics)
- Exponential backoff retry logic for transient API errors
- Comprehensive error handling for authentication and API request failures
- Checkpoint after each page and date window for reliable resumption

## Configuration file

```json
{
  "api_username": "<YOUR_GREYTHR_API_USERNAME>",
  "api_password": "<YOUR_GREYTHR_API_PASSWORD>",
  "greythr_domain": "<YOUR_GREYTHR_DOMAIN>",
  "sync_start_date": "SYNC_START_DATE_YYYY-MM-DD"
}
```

`api_username` - Your greytHR API username (client ID) obtained from greytHR API registration
`api_password` - Your greytHR API password (client secret) obtained from greytHR API registration
`greythr_domain` - Your organization's greytHR domain (e.g., moxemo6127dato.greythr.com)
`sync_start_date` - The starting date for syncing leave transactions and attendance data in YYYY-MM-DD format (e.g., 2020-01-01). If not provided, defaults to 1900-01-01

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector does not require any additional Python packages beyond what is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses OAuth2 client credentials flow for authentication. The authentication process is implemented in the `get_access_token()` function.

To obtain your API credentials:

1. Log in to your greytHR account as an administrator.
2. Navigate to the API settings section in the greytHR portal.
3. Register your application to obtain an API username (client ID) and API password (client secret).
4. Add these credentials to the `configuration.json` file along with your greytHR domain.
5. The connector automatically obtains and uses an access token for all API requests.

## Pagination
The Employee endpoint uses offset-based pagination implemented in the `sync_employees()` function. The connector fetches employees page by page with a configurable page size (default: 100 records per page). The pagination continues until the `hasNext` field in the API response is `false`, indicating all pages have been retrieved.

## Data handling
The connector processes data from three main greytHR API endpoints:

- Employee data is synced incrementally using the `modifiedSince` parameter based on the `lastModified` timestamp stored in state (refer to `sync_employees()` function).
- Leave Transactions are synced using 31-day date windows due to the greytHR API's maximum date range restriction. The connector automatically splits the sync period into 31-day chunks and tracks progress using the `leave_last_sync_end_date` state variable (refer to `sync_leave_transactions()` function).
- Attendance Insights follow the same date windowing strategy as leave transactions (refer to `sync_attendance_insights()` function).

Nested JSON objects are flattened using underscore notation (e.g., `employee.name` becomes `employee_name`). Arrays of objects are extracted into separate child tables with appropriate foreign key relationships to maintain data integrity.

## Error handling
The connector implements comprehensive error handling with exponential backoff retry logic and automatic token refresh (refer to `get_access_token()` and `make_api_request()` functions):

- HTTP 401 authentication errors automatically trigger token refresh and request retry
- Network timeouts and connection errors are retried up to three times with exponential backoff (2s, 4s, 8s)
- HTTP 5xx server errors and 429 rate limit errors trigger automatic retries
- HTTP 403 access forbidden errors fail immediately without retries
- HTTP 404 resource not found errors are logged as warnings and processing continues
- All retry attempts and failures are logged with appropriate severity levels

## Tables created

| Table Name | Primary Key | Description |
|-----------|-------------|-------------|
| `employee` | `employeeId` | Contains flattened employee data including personal information, employment details, and timestamps. All nested objects are flattened into columns with underscore notation. |
| `leave_transaction` | `id` | Contains flattened leave transaction data including leave type, transaction type, dates, and employee information. Nested objects like `employee`, `leaveTypeCategory`, and `leaveTransactionType` are flattened. |
| `leave_transaction_child` | `id`, `parent_id` | Contains individual daily leave records that are part of a multi-day leave transaction. `parent_id` is the foreign key linking to the parent `leave_transaction` table. |
| `attendance_insight` | `employee`, `sync_start_date`, `sync_end_date` | Base table for attendance insights per employee per sync period. Used as a parent for detailed attendance metrics. |
| `attendance_average` | `employee`, `sync_start_date`, `sync_end_date`, `type` | Contains average metrics like work hours, actual work hours, in time, and out time. Child table linked to `attendance_insight`. |
| `attendance_day` | `employee`, `sync_start_date`, `sync_end_date`, `type` | Contains day counts for penalties, late ins, early outs, and exceptions. Child table linked to `attendance_insight`. |
| `attendance_status` | `employee`, `sync_start_date`, `sync_end_date`, `type` | Contains attendance status counts (Present, Absent, etc.). Child table linked to `attendance_insight`. |

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
