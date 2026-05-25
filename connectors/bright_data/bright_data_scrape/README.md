# Bright Data Web Scraper Connector Example

## Connector overview

This connector syncs web scraping data from Bright Data's Web Scraper API to your Fivetran destination. Bright Data provides a scalable web scraping platform that allows you to extract data from websites while handling proxies, CAPTCHAs, and other web scraping challenges. The connector retrieves scraped page content, metadata, and extracted data from configured URLs, enabling you to analyze web data in your data warehouse.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs scraped web page data including content, metadata, and extracted fields
- Supports multiple URL input formats (single URL, comma-separated, newline-separated, JSON array)
- Processes URLs in batch for efficient data collection
- Handles asynchronous scraping jobs with automatic polling for completion
- Dynamically discovers schema fields from scraped data
- Flattens nested JSON structures for easy analysis
- Supports incremental syncing with state management
- Includes retry logic with exponential backoff for API rate limits and transient errors

## Configuration file

```json
{
  "api_token": "<YOUR_BRIGHT_DATA_API_TOKEN>",
  "dataset_id": "<YOUR_BRIGHT_DATA_DATASET_ID>",
  "scrape_url": "<YOUR_BRIGHT_DATA_SCRAPE_URL>"
}
```

Configuration parameters:

- `api_token` (required): Your Bright Data API token (Bearer token format, obtained from Bright Data dashboard)
- `dataset_id` (required): The ID of the Bright Data dataset to use for scraping (e.g., `"gd_lyy3tktm25m4avu764"`)
- `scrape_url` (required): URL(s) to scrape. Supports multiple formats:
  - Single URL: `"https://www.example.com"`
  - Comma-separated: `"https://www.example.com,https://www.example2.com"`
  - Newline-separated: `"https://www.example.com\nhttps://www.example2.com"`
  - JSON array string: `"[\"https://www.example.com\",\"https://www.example2.com\"]"`

Some Bright Data datasets require specific query parameters to be included in the API request. The connector automatically applies dataset-specific query parameters based on the `dataset_id` value. For example, the dataset `gd_lyy3tktm25m4avu764` automatically includes `discover_by=profile_url` and `type=discover_new` parameters. This logic is implemented in the `sync_scrape_urls()` function in `connector.py`. If you need to add query parameters for additional datasets, modify the dataset-specific conditional logic in that function.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector requires the following dependencies in `requirements.txt`:

```
pyyaml==6.0.3
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The Bright Data API uses Bearer token authentication. To obtain your API token:

1. Visit the [Bright Data website](https://brightdata.com).
2. Create an account or log in to your existing account.
3. Navigate to **Settings > Users** or visit https://brightdata.com/cp/setting/users.
4. Generate and make a note of your API token.
5. Add the API token to your `configuration.json` file as the value for the `api_token` parameter.

The API token is included in all API requests as a Bearer token in the Authorization header (refer to the `perform_scrape()` function in `helpers/scrape.py`).

## Data handling

The connector processes data in the following order:

1. URL Parsing - Normalizes the `scrape_url` input into a list of URLs, supporting multiple input formats (refer to the `parse_scrape_urls()` function)
2. Job Triggering - Sends a POST request to `/datasets/v3/trigger` with the URLs to scrape (refer to the `_trigger_scrape()` function in `helpers/scrape.py`)
3. Snapshot Polling - Polls the `/datasets/v3/snapshot/{snapshot_id}` endpoint until results are ready (refer to the `_poll_snapshot()` function in `helpers/scrape.py`)
4. Result Processing - Flattens nested JSON structures and processes each result (refer to the `process_scrape_results()` and `process_and_upsert_results()` functions)
5. Schema Discovery - Dynamically discovers fields from scraped data and documents them in `fields.yaml` (refer to the `collect_all_fields()` and `update_fields_yaml()` functions in helpers)
6. Data Upsertion - Upserts processed records to the destination table (refer to the `process_and_upsert_results()` function)

All data is upserted to the destination, allowing for incremental updates. Records are uniquely identified by the combination of `url` and `result_index`, which form the primary key. The connector tracks state for synced URLs to enable efficient incremental syncs.

## Error handling

The connector implements comprehensive error handling:

- Retry logic - Transient errors (408, 429, 500, 502, 503, 504) trigger exponential backoff retries up to 3 attempts (refer to the retry logic in `helpers/scrape.py`)
- Timeout handling - Request timeouts are handled with configurable timeout values (default: 120 seconds)
- HTTP error codes - 400/422 errors fail immediately with detailed error messages, 404 errors raise errors for invalid snapshots, other errors are logged and raised (refer to error handling in `helpers/scrape.py` and `helpers/common.py`)
- Request exceptions - Network errors trigger retries with exponential backoff
- Snapshot polling - Handles 202 (Accepted) status codes by waiting and retrying, continues polling indefinitely until snapshot is ready or failed

## Tables created

| Table Name        | Primary Key                          | Description                                                                                                                                                                                                                            |
|-------------------|--------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `SCRAPE_RESULTS`  | `url`, `result_index` | Contains scraped web page data including content, metadata, and extracted fields. Each row represents a single result from a scraped URL. The `url` field identifies the source URL, and `result_index` distinguishes multiple results from the same URL. Nested JSON structures are flattened with underscore separators (e.g., `user_name`, `user_details_age`).|

## Additional files

The connector uses the following additional files:

- `helpers/validation.py` - Configuration parameter validation
- `helpers/scrape.py` - Bright Data API interaction, job triggering, and snapshot polling
- `helpers/schema_management.py` - Dynamic schema discovery and fields.yaml management
- `helpers/data_processing.py` - Data flattening and result processing utilities
- `helpers/common.py` - Shared constants, error handling, and response parsing utilities

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
