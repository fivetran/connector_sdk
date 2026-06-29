# FRED API Connector Example

## Connector overview

This connector syncs economic data from the Federal Reserve Economic Data (FRED) API to your Fivetran destination. FRED is a database of economic data maintained by the Federal Reserve Bank of St. Louis, containing hundreds of thousands of economic time series from various sources. The connector retrieves series metadata, observations (data points), categories, and releases, enabling you to analyze economic trends and indicators in your data warehouse.

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
fivetran init <project-path> --template connectors/fred
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Syncs series metadata including title, frequency, units, and seasonal adjustment information
- Retrieves time series observations with incremental sync support
- Fetches economic data categories for organizational context
- Retrieves release information for data provenance tracking
- Implements pagination for large datasets
- Supports incremental syncing with state management
- Includes retry logic with exponential backoff for API rate limits
- Configurable checkpoint intervals for efficient state management

## Configuration file


```json
{
  "api_key": "<YOUR_FRED_API_KEY>",
  "series_ids": "<COMMA_SEPARATED_SERIES_IDS>",
  "sync_start_date": "<YOUR_OPTIONAL_SYNC_START_DATE_AS_YYYY-MM-DD>"
}
```

### Configuration parameters

- `api_key`: Your FRED API key (32 character alphanumeric string)
- `series_ids`: Comma-separated list of series IDs to sync (e.g., "GNPCA,UNRATE,CPIAUCSL")
- `sync_start_date`: Optional start date for syncing observations in YYYY-MM-DD format (defaults to 2020-01-01)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require a `requirements.txt` file as it only uses standard library modules and the `requests` library, which is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The FRED API uses API key authentication. To obtain your API key:

1. Visit the [FRED website](https://fred.stlouisfed.org).
2. Create an account or log in to your existing account.
3. Navigate to **My Account > API Keys**.
4. Click **Request API Key** and follow the prompts.
5. Copy the generated 32-character API key.
6. Add the API key to your `configuration.json` file.

The API key is included in all API requests as a query parameter (refer to the `make_api_request()` function).

## Pagination

The FRED API supports pagination using `limit` and `offset` parameters. The connector handles pagination automatically:

- For releases, the connector uses offset-based pagination, fetching up to 1,000 records per request (refer to the `sync_releases()` function)
- For series observations, the connector combines pagination with date-based filtering to efficiently retrieve historical data (refer to the `sync_series_observations()` function)
- The connector continues fetching pages until an empty result set is returned, indicating all data has been retrieved
- State is checkpointed after each page to enable resumption in case of interruptions

## Data handling

The connector processes data in the following order:

1. Categories - Fetches child categories from the root category to understand the data organization (refer to the `sync_categories()` function)
2. Releases - Retrieves all economic data releases with pagination support (refer to the `sync_releases()` function)
3. Series - For each configured series ID, fetches series metadata (refer to the `sync_single_series()` function)
4. Observations - Retrieves time series data points with incremental sync support, tracking the last observation date per series (refer to the `sync_series_observations()` function)

All data is upserted to the destination, allowing for incremental updates. The connector tracks state per series to enable efficient incremental syncs.

## Error handling

The connector implements comprehensive error handling:

- Retry logic - Transient errors (429, 500, 502, 503, 504) trigger exponential backoff retries up to 3 attempts (refer to the `handle_retryable_error()` function)
- Timeout handling - Request timeouts are retried with exponential backoff (refer to the `handle_timeout_error()` function)
- HTTP error codes - 400 errors fail immediately, 404 errors return empty results, other errors are logged and raised (refer to the `handle_api_response()` function)
- Request exceptions - Network errors trigger retries with exponential backoff (refer to the `handle_request_exception()` function)

## Tables created

| Table Name            | Primary Key         | Description                                                                                                                                                             |
|-----------------------|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `series`              | `id`                | Contains metadata about economic data series including title, frequency, units, seasonal adjustment information, observation dates, popularity, and notes.              |
| `series_observations` | `series_id`, `date` | Contains time series data points for each series with values, series identifier, observation date, and realtime start/end dates indicating when the data was available. |
| `categories`          | `id`                | Contains economic data categories with category ID, name, and parent category ID for hierarchical organization.                                                         |
| `releases`            | `id`                | Contains economic data releases with release ID, name, realtime dates, press release flag, and link to additional information.                                          |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
