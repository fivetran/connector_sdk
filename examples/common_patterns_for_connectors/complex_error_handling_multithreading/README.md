# Complex Error Handling with Multithreading Connector Example

## Connector overview
This example demonstrates how to implement next-page URL-based pagination for REST APIs with multithreading and comprehensive error handling strategies. The connector fetches records from a paginated API, processes them in parallel using multiple threads, and implements robust error handling mechanisms to ensure reliability and resilience.

This example combines three important patterns:
- Pagination: Uses next-page URL pagination to fetch all records from the API
- Multithreading: Processes records in parallel for improved performance
- Error Handling: Implements circuit breaker, retry logic, error categorization, and graceful degradation

This pagination and multithreading strategy is useful when:
- The API includes the full URL for the next page in each response
- You need to process large volumes of data efficiently
- You want to build resilient connectors that handle transient failures gracefully
- You need detailed error tracking and monitoring capabilities

Note: This example is intended for learning purposes and uses the [fivetran-api-playground](https://pypi.org/project/fivetran-api-playground/) package to mock the API responses locally. It is not meant for production use.


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/complex_error_handling_multithreading
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

### Pagination
- Handles `next_page_url` pagination logic
- Tracks sync position using the `updatedAt` timestamp
- Automatically follows next-page links across paginated API responses
- Uses `op.checkpoint()` to safely store progress after each page

### Multithreading
- Processes records in parallel using `ThreadPoolExecutor` for improved performance
- Supports a configurable number of worker threads (default: 4, recommended: 4-8)
- Offers thread-safe state management with proper locking mechanisms
- Efficiently utilizes resources with bounded thread pools

### Comprehensive error handling
- Circuit Breaker Pattern: Prevents cascading failures by opening the circuit when too many errors occur
- Retry Logic with Exponential Backoff: Automatically retries failed requests with increasing wait times
- Error Categorization: Tracks different types of errors (timeouts, connection errors, rate limits, validation errors)
- Graceful Degradation: Individual record failures don't stop the entire sync
- Rate Limit Handling: Respects API rate limits with proper backoff
- Thread-Safe Error Statistics: Collects and reports error metrics across all threads
- Timeout Protection: Prevents hanging requests with configurable timeouts
- Data Validation: Validates required fields before processing


## Configuration file
This example supports optional configuration for parallelism:

```json
{
  "parallelism": 4
}
```
Configuration parameter:
- `parallelism`: Number of worker threads to use for parallel processing (optional, defaults to 4)

For production connectors, `configuration.json` might also contain API tokens, initial cursors, or filters to narrow down API results.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires no extra Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not use authentication.

In real-world scenarios, modify `get_api_response()` to add `Authorization` headers or include API keys in query parameters.


## Pagination
Pagination is based on the `next_page_url` key provided in the API response:
```json
{
  "data": [],
  "next_page_url": "https://api.example.com/page=2"
}
```
- The initial request includes `updated_since`, `order_by`, and `per_page`
- If `next_page_url` is present, it is used as the next request's endpoint
- Query parameters are cleared because they're already embedded in the `next_page_url`
- Pages are fetched sequentially to maintain order, but records within each page are processed in parallel

Pagination continues until no `next_page_url` is returned.


## Multithreading architecture

### Thread pool configuration
- Uses `ThreadPoolExecutor` with configurable worker threads
- Default: 4 workers (recommended: 4-8 for production)
- Each page of records is processed in parallel
- Thread-safe operations with proper locking

### Processing flow
1. Page Fetching: Pages are fetched sequentially to maintain order
2. Parallel Processing: Records within each page are processed concurrently
3. State Management: Thread-safe state updates ensure consistency
4. Error Isolation: Individual record failures don't affect other records

### Thread safety considerations
- `processing_lock`: Protects state dictionary updates
- `error_stats_lock`: Protects error statistics tracking
- Circuit breaker has internal locking for state management
- SDK operations (upsert, checkpoint) are thread-safe by design


## Error handling

### Circuit breaker pattern
The connector implements a circuit breaker with three states:
- Closed (normal): Requests flow through normally
- Open (failed): Too many errors detected, requests blocked temporarily
- Half-Open (testing): Testing if service has recovered

Configuration:
- Failure threshold: 5 consecutive failures trigger circuit opening
- Timeout: 60 seconds before attempting recovery

### Retry logic with exponential backoff
Failed requests are automatically retried with increasing wait times:
- Attempt 1: Immediate
- Attempt 2: Wait 1 second
- Attempt 3: Wait 2 seconds
- Attempt 4: Wait 4 seconds

### Error categorization
The connector tracks and reports different error types:
- Timeout Errors: Request took too long to complete
- Connection Errors: Network connectivity issues
- Rate Limit Errors: API rate limits exceeded (429 status)
- Server Errors: API server issues (5xx status)
- Client Errors: Request errors (4xx status except 429)
- Validation Errors: Data validation failures
- Processing Errors: Errors during record processing
- Fatal Page Errors: Unrecoverable page-level errors

### Rate limit handling
Special handling for HTTP 429 (Too Many Requests):
- Respects `Retry-After` header from API
- Default wait time: 60 seconds if header not present
- Automatic retry after waiting

### Graceful degradation
- Individual record failures are logged but don't stop the sync
- Page-level errors are retried with backoff
- Failed records are tracked in error statistics
- Sync continues processing other records

### Data validation
Each record is validated before processing:
- Required field checks (id, updatedAt)
- Type validation
- Validation errors are categorized separately

### Timeout protection
All API requests have a 30-second timeout to prevent hanging:
- Prevents infinite waiting
- Triggers retry logic on timeout
- Tracked in timeout error statistics


## Data handling
- The connector fetches user records from each page sequentially
- Records within each page are processed in parallel using thread pool
- Each record is validated before processing
- Each row is passed to `op.upsert()` for syncing into the `USER` table
- The `state["last_updated_at"]` field is updated with thread-safe locking
- `op.checkpoint()` is called after each page to persist the cursor


## Error reporting
At the end of each sync, the connector logs comprehensive error statistics:
```
Error Statistics Summary:
  timeout_errors: 3
  rate_limit_errors: 1
  failed_items: 5
  validation_errors: 2
```

This helps with:
- Monitoring connector health
- Identifying systemic issues
- Debugging failures
- Performance tuning


## Performance considerations

### Thread configuration
- Recommended: 4-8 worker threads for production
- Default: 4 workers (good balance for most use cases)
Note: More threads don't necessarily provide better performance. Higher thread counts can increase overhead, trigger rate limits more frequently and exhaust system resources.

### Memory management
- Records are processed as they arrive (streaming)
- No large data structures held in memory
- Thread pool size bounds concurrent operations

### Checkpoint strategy
- State is checkpointed after each page
- Allows resuming from last successful page
- Minimizes data re-processing on failures


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


## Functions

### Main functions
- `update()`: Entry point, orchestrates pagination and parallel processing
- `sync_items_parallel()`: Handles paginated API calls and parallel processing
- `process_items_parallel()`: Manages thread pool for processing records
- `process_single_item()`: Processes individual records with validation and retry

### Error handling functions
- `get_api_response_with_retry()`: API calls with retry logic and circuit breaker
- `get_api_response()`: Basic API call with timeout
- `log_error_statistics()`: Reports error metrics

### Pagination functions
- `should_continue_pagination()`: Determines if more pages exist
- `get_next_page_url_from_response()`: Extracts next page URL

### Utility classes
- `CircuitBreaker`: Implements circuit breaker pattern

## Testing recommendations

1. Test with various error scenarios:
   - Network timeouts
   - Connection failures
   - Rate limiting
   - Invalid data
   - Server errors

2. Test thread safety:
   - Run with different thread counts
   - Verify state consistency
   - Check for race conditions

3. Test circuit breaker:
   - Trigger circuit opening with repeated failures
   - Verify circuit closes after recovery
   - Check behavior in half-open state

4. Monitor error statistics:
   - Verify all error types are tracked
   - Check error counts are accurate
   - Confirm logging is comprehensive


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
