# Oktopost Connector Example

## Connector overview
The Oktopost connector fetches export metadata and CSV data from the Oktopost BI Export API for data synchronization. This connector is designed to retrieve any active BI exports from the Oktopost API and write the results to a data warehouse. 

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
fivetran init <project-path> --template connectors/oktopost
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Export metadata retrieval: Fetches comprehensive export list metadata from Oktopost BI Export API
- Active export processing: Identifies and processes only active exports for data synchronization
- CSV data extraction: Downloads and processes CSV files from ZIP archives
- Flexible configuration: Supports custom base URLs and test export ID specification
- Robust error handling: Implements exponential backoff retry logic with comprehensive error handling
- Data validation: Validates configuration parameters and API responses
- Incremental sync support: Tracks sync timestamps for efficient data updates

## Configuration file
The configuration keys defined for the Oktopost connector are uploaded to Fivetran from the configuration.json file.

```json
{
    "account_id": "<YOUR_OKTOPOST_ACCOUNT_ID>",
    "api_key": "<YOUR_OKTOPOST_API_KEY>",
    "base_url": "<YOUR_OPTIONAL_BASE_URL_OR_LEAVE_DEFAULT>",
    "test_export_id": "<YOUR_OPTIONAL_TEST_EXPORT_ID>"
}
```

**Configuration parameters:**
- `account_id` (required): Your Oktopost account identifier
- `api_key` (required): Your Oktopost API key for authentication
- `base_url` (optional): Custom API base URL (defaults to https://api.oktopost.com/v2)
- `test_export_id` (optional): Specific export ID for testing purposes

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The Oktopost connector uses only built-in Python modules and pre-installed packages, so no `requirements.txt` file is needed.

The connector relies on:
- Built-in Python modules: `csv`, `zipfile`, `json`, `datetime`, `urllib.parse`
- Pre-installed packages: `fivetran_connector_sdk:latest` and `requests:latest`

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment.

## Authentication
The connector uses HTTP Basic Authentication with your Oktopost account ID and API key. 

## Pagination
The Oktopost BI Export API returns export metadata in a single response without pagination. The connector processes all available exports in one API call and then iterates through each export to retrieve detailed metadata and associated CSV files.

For CSV data processing, the connector handles multiple files within ZIP archives, processing each file sequentially to extract and transform the data.

## Data handling
The connector processes data through several stages:

1. **Export metadata retrieval**: Fetches export list from the API and stores metadata in the `export_list_metadata` table.
2. **Active export filtering**: Identifies exports with 'active' status for further processing.
3. **Detailed metadata extraction**: Retrieves comprehensive metadata for active exports and stores in `active_export_metadata` table.
4. **CSV file processing**: Downloads ZIP files, extracts CSV content, and processes data into structured tables.
5. **Data transformation**: Converts CSV data into JSON format with proper field mapping and data type handling.

**Schema mapping**: The connector automatically creates tables based on CSV file names, with automatic data type inference and null value handling.

## Error handling
The connector implements comprehensive error handling strategies:

- **Configuration validation**: Validates presence of required parameters and URL formats before processing (Refer to `validate_configuration` function)
- **Exponential backoff retry**: Implements retry logic with exponential backoff for transient failures (Refer to `make_api_request_with_retry` function)
- **HTTP status code handling**: Differentiates between client errors (4xx) and server errors (5xx) for appropriate retry behavior
- **Network error handling**: Handles timeouts and connection errors with automatic retry
- **Data processing errors**: Gracefully handles CSV parsing errors and continues processing other files
- **Detailed logging**: Provides comprehensive logging for debugging and monitoring

## Tables created

**Summary of tables replicated:**

1. **export_list_metadata**: Contains metadata for all available exports from Oktopost
   - Fields: Export ID, Name, Status, Created Date, Last Run Date, and sync timestamp

2. **active_export_metadata**: Contains detailed metadata for active exports only
   - Fields: Export details, file information, run status, and sync timestamp

3. **Dynamic CSV tables**: Tables created based on CSV file names from active exports
   - Fields: Mapped from CSV columns with automatic data type inference
   - Examples: `campaign_performance`, `post_analytics`, `engagement_metrics`

Each table includes a `sync_timestamp` field to track when the data was last synchronized.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
