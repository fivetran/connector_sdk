# Pindrop Connector SDK Example

## Connector overview

The Pindrop connector for Fivetran fetches nightly reports from the Pindrop API and syncs them to your data warehouse. This connector supports multiple report types including blacklist data, call analysis, audit logs, case management, account risk assessments, and enrollment data. The connector implements OAuth2 authentication and provides both initial and incremental sync capabilities with robust error handling and retry logic.

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
fivetran init <project-path> --template connectors/pindrop
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
The connector supports the following features:

- **Multiple report types**: Supports blacklist, calls, audit, cases, account_risk, and enrollment reports
- **OAuth2 authentication**: Secure authentication using client credentials flow with automatic token refresh
- **Incremental sync**: Initial sync from a configurable start date, incremental syncs look back 1 day
- **State management**: Maintains sync state to enable efficient incremental updates and resume capability
- **Error handling**: Comprehensive error handling with exponential backoff retry logic
- **Rate limiting**: Built-in rate limiting to respect API constraints
- **CSV data processing**: Handles CSV response format from Pindrop API endpoints

## Configuration file

The connector requires OAuth2 client credentials for authentication. The base URL and rate limiting are configured as constants in the connector code.

```json
{
  "client_id": "your_client_id_here",
  "client_secret": "your_client_secret_here"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require a `requirements.txt` file as all necessary dependencies are pre-installed in the Fivetran environment. The connector uses standard Python libraries (`json`, `datetime`, `time`, `csv`, `io`, `typing`) and the `requests` library, which are all available by default.

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. Additional dependencies are not required for this connector.

## Authentication

The connector uses OAuth2 client credentials flow for authentication with the Pindrop API. The authentication process is handled by the `OAuth2TokenManager` class which:

- Requests access tokens using client_id and client_secret
- Automatically refreshes tokens before expiration
- Implements retry logic with exponential backoff for token requests
- Handles authentication errors gracefully

To obtain the necessary credentials:
1. Contact your Pindrop account representative to set up API access
2. Request OAuth2 client credentials for the nightly reports API
3. Ensure your credentials have access to all required report types

## Pagination

The connector handles pagination by processing reports on a per-date basis. Each API call fetches a complete daily report for a specific report type and date. The pagination strategy involves:

* Processing reports chronologically by date
* Fetching one report type at a time for each date
* Using state management to track progress and enable resumption

Refer to the `generate_reports_to_process` function for pagination logic.

## Data handling

The connector processes CSV data from the Pindrop API and transforms it into structured records:

- **CSV parsing**: Uses the `parse_csv_data` function to convert CSV responses into dictionaries
- **Schema mapping**: Each record includes metadata fields (report_date, report_type, _fivetran_synced)
- **Data cleaning**: Handles null values and trims whitespace from string fields
- **Primary keys**: Generates unique IDs for records when not provided by the source

Data is delivered to Fivetran using upsert operations for each record, ensuring data consistency and enabling incremental updates.

## Error handling

The connector implements comprehensive error handling strategies:

- **Retry logic**: Exponential backoff for failed API requests (refer to `make_api_request` function)
- **Token refresh**: Automatic retry with fresh tokens on authentication failures
- **Partial failures**: Continues processing other reports if individual requests fail
- **State preservation**: Checkpoints progress to enable recovery from interruptions
- **Detailed logging**: Comprehensive logging at INFO, WARNING, and ERROR levels

Refer to the `OAuth2TokenManager._request_new_token` method for authentication error handling and the `fetch_report_data` function for API error handling.

## Tables created

The connector creates the following tables in your destination:

| Table name     | Primary key                   | Description |
|----------------|-------------------------------|-------------|
| `BLACKLIST`    | `[report_date, phone_number]` | Blacklisted phone numbers and associated data |
| `CALLS`        | `[report_date, id]`           | Call detail records and analysis |
| `AUDIT`        | `[report_date, id]`           | Audit logs and security events |
| `CASES`        | `[report_date, id]`           | Case management data |
| `ACCOUNT_RISK` | `[report_date, id]`           | Account risk assessment reports |
| `ENROLLMENT`   | `[report_date, id]`           | Enrollment and registration data |

All tables include the following metadata fields:
- `report_date`: Date of the report (YYYY-MM-DD)
- `report_type`: Type of report (lowercase)
- `_fivetran_synced`: Timestamp when the record was synced

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 