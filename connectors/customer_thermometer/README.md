# Customer Thermometer API Connector Example

## Connector overview

The [Customer Thermometer](https://www.customerthermometer.com/) custom Fivetran connector fetches customer feedback data from the Customer Thermometer API and syncs it to your destination. This connector supports multiple endpoints including comments, blast results, recipient lists, thermometers, and feedback metrics. 

The connector implements API key authentication, parses XML responses, and is stateless, following Fivetran best practices for reliability, security, and maintainability.

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
fivetran init <project-path> --template connectors/customer_thermometer
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

The connector supports the following features:

- Multiple endpoints: Supports comment, blast result, recipient list, thermometer, and metric data
- API key authentication: Secure authentication using Customer Thermometer API keys
- XML parsing: Converts XML API responses to structured records with empty response handling
- Incremental sync: Supports incremental data synchronization using replication keys and state management
- Retry logic: Implements exponential backoff retry mechanism for transient API failures
- Error handling: Comprehensive error handling for individual records and API failures without stopping entire sync
- Comprehensive logging: Uses Fivetran's logging framework for troubleshooting and monitoring

## Configuration file

The connector requires API key authentication for the Customer Thermometer API. An optional from_date parameter controls the initial sync behavior.

```json
{
  "api_key": "<YOUR_CUSTOMER_THERMOMETER_API_KEY>",
  "from_date": "<YOUR_OPTIONAL_FROM_DATE_AS_YYYY-MM-DD>"
}
```

- `api_key`: (Required) Your Customer Thermometer API key
- `from_date`: (Optional) Start date for initial data retrieval in YYYY-MM-DD format. If not provided, incremental sync will start from EPOCH (1970-01-01) for the initial sync, then use state-based incremental sync for subsequent runs.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector example uses standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses API key authentication with the Customer Thermometer API. Authentication is handled in the `make_api_request` and `validate_configuration` functions:

- Uses a pre-configured API key for all API requests with automatic retry logic
- Passes the key as a parameter in each request with exponential backoff on failures
- Validates key presence and format during connector initialization
- Handles authentication errors gracefully with detailed logging and retry attempts (up to 3 retries)
- Implements 30-second timeout per request to prevent hanging connections

To obtain the necessary credentials:
1. Log in to your Customer Thermometer account.
2. Navigate to **Account Settings** > **API**.
3. Generate a new API key or use an existing one.

## Data handling

The connector processes XML data from the Customer Thermometer API and transforms it into structured records using specialized functions:

- XML parsing: Uses `parse_xml_response` to convert XML to dictionaries with empty response handling
- Incremental sync: Implements state-based incremental synchronization for efficient data retrieval
- Date range management: Automatically determines sync ranges using last checkpoint timestamps
- Data preservation: Maintains all original field names and values where possible
- Primary key generation: Uses natural keys from the API (id fields)
- Upsert operations: Delivers data to Fivetran using upsert operations with proper checkpoint management
- State management: Accumulates state across all tables and performs single checkpoint at sync completion

## Error handling

The connector implements comprehensive error handling strategies in the `update` function and API request helpers:

- Individual record handling: Failed records don't stop the entire sync process
- API error management: HTTP and XML errors are caught and logged with severity levels
- Retry mechanism: Implements exponential backoff with up to 3 retry attempts for transient failures
- Empty response handling: Gracefully processes empty API responses without errors
- Timeout configuration: 30-second timeout for API requests to prevent hanging
- State preservation: Ensures state is properly maintained even during partial failures
- Detailed logging: Uses Fivetran's logging framework (INFO, WARNING, ERROR levels) with response content logging for debugging

## Tables created

The connector creates the following tables in your destination:

| Table name       | Primary key                                 | Description                                 |
|------------------|---------------------------------------------|---------------------------------------------|
| `COMMENT`        | `[response_id, date_submitted]`             | Customer feedback comments                  |
| `BLAST_RESULT`   | `[blast_id, response_id, thermometer_id, date_submitted]` | Results from feedback collection campaigns  |
| `RECIPIENT_LIST` | `[id]`                                      | Lists of feedback recipients                |
| `THERMOMETER`    | `[id]`                                      | Configured feedback collection tools        |
| `METRIC`         | `[metric_name, recorded_at]`                | Aggregated feedback metrics                 |

All tables include flattened versions of complex nested objects where applicable.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.