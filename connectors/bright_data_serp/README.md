# Bright Data SERP Connector Example

## Connector overview

This connector syncs search engine results from Bright Data's SERP REST API to your Fivetran destination. It supports Google, Bing, and Yandex searches, accepts multiple query input formats, flattens nested JSON responses, and upserts results to a single `search_results` table.

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
fivetran init <project-path> --template connectors/bright_data_serp
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Features

- Syncs SERP data from Google, Bing, and Yandex
- Supports multiple query input formats (single query, comma-separated, newline-separated, JSON array string)
- Flattens nested JSON structures for analysis
- Dynamically discovers fields from search results
- Includes retry logic with exponential backoff for transient API errors
- Checkpoints state after each sync

## Configuration file

Note: All configuration values must be provided as strings per Fivetran SDK requirements.

```json
{
  "api_token": "<YOUR_BRIGHT_DATA_API_TOKEN>",
  "search_query": "<YOUR_SEARCH_QUERY>",
  "search_engine": "google",
  "search_zone": "serp_api1",
  "country": "us",
  "format": "json"
}
```

Configuration parameters:

- `api_token` (required): Your Bright Data API token (Bearer token from the Bright Data dashboard)
- `search_query` (required): Search query or queries. Supports a single string, comma-separated values, newline-separated values, or a JSON array string
- `search_engine` (optional): Search engine to use (`google`, `bing`, or `yandex`). Defaults to `google`
- `search_zone` (optional): Bright Data SERP zone identifier. Defaults to `serp_api1`
- `country` (optional): ISO 3166-1 alpha-2 country code for geolocation targeting. Defaults to `us`
- `format` (optional): Response format from Bright Data (`json` or `html`). Defaults to `json`

## Requirements file

This connector does not require any additional Python packages beyond what is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The Bright Data API uses Bearer token authentication. To obtain your API token:

1. Visit the [Bright Data website](https://brightdata.com).
2. Create an account or log in to your existing account.
3. Navigate to **Settings > Users** or visit https://brightdata.com/cp/setting/users.
4. Generate and make a note of your API token.
5. Add the API token to your `configuration.json` file as the value for the `api_token` parameter.

## Data handling

The connector processes data in the following order:

1. Configuration validation - Validates required parameters (refer to `validate_configuration()` in `helpers/validation.py`)
2. Query parsing - Normalizes `search_query` into a list of queries (refer to `parse_search_queries()`)
3. API requests - Sends POST requests to Bright Data's `/request` endpoint (refer to `perform_search()` in `helpers/search.py`)
4. Result processing - Flattens nested JSON and adds metadata columns (refer to `process_search_result()` in `helpers/data_processing.py`)
5. Schema discovery - Collects the union of fields across results (refer to `collect_all_fields()`)
6. Data upsertion - Upserts rows to the destination (refer to `process_and_upsert_results()`)
7. State checkpointing - Saves sync progress (refer to `op.checkpoint()` in `update()`)

## Error handling

- Retry logic - Transient errors (408, 429, 500, 502, 503, 504) trigger exponential backoff retries up to 3 attempts (refer to `_execute_search_request()` in `helpers/search.py`)
- HTTP errors - Non-retryable failures raise `RuntimeError` with error details from the API response
- Request exceptions - Network errors trigger retries with exponential backoff before failing
- Primary key validation - Missing or mistyped primary keys are corrected with warnings logged once per sync (refer to `process_and_upsert_results()`)

## Tables created

| Table Name       | Primary Key              | Description                                                                                                                                 |
|------------------|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `SEARCH_RESULTS` | `query`, `result_index`  | Contains flattened search engine results. Each row represents one result for a query. Nested JSON is flattened with underscore separators. |

## Additional files

- `helpers/validation.py` - Configuration parameter validation
- `helpers/search.py` - Bright Data SERP API interaction and retry logic
- `helpers/data_processing.py` - Data flattening, field discovery, and upsert utilities

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
