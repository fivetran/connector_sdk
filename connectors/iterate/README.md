# Iterate NPS Survey Connector Example

## Connector overview
This custom Fivetran connector extracts NPS survey data from the [Iterate](https://iteratehq.com/) REST API and loads it into your destination. The connector fetches NPS surveys and their individual responses, providing complete survey analytics data for downstream analysis.

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
fivetran init <project-path> --template connectors/iterate
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Extracts survey metadata from the `/surveys` endpoint
- Extracts individual survey responses from the `/surveys/{id}/responses` endpoint
- Uses the`start_date` parameter with strict UTC format validation for incremental syncs
- Processes all paginated data automatically using links object within a single sync
- Implements exponential backoff for API reliability (3 retries with progressive delays)
- Flattens nested JSON structures into table columns automatically
- Simple checkpointing only upon the successful completion of a sync
- UTC date/time enforcement eliminates timezone ambiguity

## Configuration file
The configuration requires your Iterate API access token and optionally a start date for the initial sync.

```
{
  "api_token": "<YOUR_ITERATE_API_TOKEN>",
  "start_date": "<YOUR_OPTIONAL_START_DATE>"
}
```

Configuration parameters:
- `api_token` (required): Your Iterate API access token.
- `start_date` (optional): UTC datetime in ISO 8601 format with 'Z' suffix (e.g., "2023-01-01T00:00:00Z"). If not provided, sync starts from EPOCH time (1970-01-01T00:00:00Z) to capture all historical data.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The `requirements.txt` file specifies additional Python libraries required by the connector. Following Fivetran best practices, this connector doesn't require additional dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses API key authentication via the `x-api-key` header. To obtain your API access token:

1. Log into your Iterate account.
2. Go to **Account settings**.
3. Find and make a note of your API access token.
4. Add the token to your `configuration.json` file as shown above.

## Pagination
The connector handles pagination automatically using Iterate API's `links` object structure. When the API returns a `links.next` URL, the connector continues fetching additional pages until all data is retrieved within a single sync operation.

- Each sync processes all paginated data completely using `fetch_survey_responses()`.
- Pagination state is not persisted between sync runs for cleaner state management.
- Uses the `start_date` Unix timestamp parameter to filter responses from API directly.
- Each sync fetches all relevant data from start_date to current time.

The `fetch_survey_responses()` function handles both initial requests and paginated follow-ups using the appropriate API call method.

## Data handling
The connector processes survey and response data with an optimized incremental sync strategy:

- **Survey data**: Fetches all surveys using `/surveys` endpoint and flattens nested JSON structures into columns.
- **Response data**: For each survey, fetches individual responses using `/surveys/{id}/responses` endpoint with date-based filtering and automatic pagination.

### Enhanced sync strategy
- Initial sync uses `start_date` from configuration (if provided) or EPOCH time (1970-01-01T00:00:00Z) as a fallback solution
- Incremental syncs use `last_survey_sync` timestamp from state to fetch only new responses since the last successful sync
- UTC consistency for all datetime operations with the 'Z' suffix format (`YYYY-MM-DDTHH:MM:SSZ`)
- Single checkpoint saves the state only after a complete successful sync to prevent data gaps from partial failures

### Data transformation
- JSON flattening converts nested dictionaries to underscore-separated columns (e.g., `author.id` -> `author_id`)
- List handling converts arrays to JSON strings for storage
- Foreign keys maintain relationships with `survey_id` field included in each response
- Type safety through configuration validation ensuring required fields exist before processing

### Key functions
- `parse_iso_datetime_to_unix()`: Handles strict UTC datetime parsing with validation
- `make_iterate_api_call()`: Centralized API calling with common headers and error handling
- `flatten_dict()`: Recursive JSON structure flattening for table columns
- `validate_configuration()`: Comprehensive config validation with datetime format checking

The connector maintains a clean state with only the `last_survey_sync` timestamp, automatically advancing after each successful sync to ensure reliable incremental syncs without data duplication or gaps.

## Error handling
The connector implements comprehensive error handling with multiple layers of protection:

### Configuration validation (`validate_configuration()`)
- Validates required `api_token` field exists and is not empty
- Provides clear error messages for configuration issues with format examples

### API request resilience (`make_api_request()`)
- Implements retry logic with exponential backoff (3 attempts with progressive delays)
- Handles HTTP errors, timeouts, and network issues gracefully
- Detailed logging for debugging API connectivity problems

### Centralized API logic (`make_iterate_api_call()`)
- Consistent header management and authentication for all API calls
- Automatic API version parameter inclusion
- Unified error handling across all endpoints

### Data processing safeguards
- Graceful handling of missing or malformed API response structures
- Safe dictionary access patterns to prevent KeyError exceptions
- Proper exception propagation with descriptive RuntimeError messages

All exceptions are caught at the top level and re-raised as `RuntimeError` with descriptive messages, making troubleshooting easier for users and Fivetran support.

## Tables created

The connector creates the following tables in your destination:

| Table name | Primary key | Description |
|------------|-------------|-------------|
| `SURVEY`   | `id`        | Survey metadata and configuration with flattened JSON properties |
| `RESPONSE` | `id`        | Individual survey responses with relationship to parent survey (includes `survey_id` foreign key) |

All tables include flattened versions of complex nested objects, with nested properties converted to underscore-separated columns (e.g., `author.id` becomes `author_id`).

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
