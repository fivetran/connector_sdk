"""
This example demonstrates how to implement next-page-url pagination with multithreading for REST APIs,
including comprehensive error handling strategies for concurrent operations.
It fetches user data from a paginated API while processing records in parallel with robust error handling.
THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
(https://pypi.org/project/fivetran-api-playground/) TO RUN.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import requests to make HTTP calls to API
import requests as rq

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import time for retry check
import time

# Import to parse configuration
import json

# Import concurrency utilities
from concurrent.futures import ThreadPoolExecutor, as_completed

# Imported threading for multiprocessing
import threading

# For initilisation of required arguments in
from typing import List, Optional, Tuple
from collections import defaultdict

# Global variables for error tracking and thread safety
__ERROR_STATS = defaultdict(int)
__ERROR_STATS_LOCK = threading.Lock()
__PROCESSING_LOCK = threading.Lock()
__PARALLELISM = 4
__BASE_URL = "http://127.0.0.1:5001/pagination/next_page_url"
__PER_PAGE = 50
__MAX_RETRIES = 3
__ITEM_MAX_RETRIES = 2


class CircuitBreaker:
    """
    Circuit breaker pattern implementation to prevent cascading failures.
    When too many errors occur, the circuit "opens" and stops making requests temporarily.
    """

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
        self.lock = threading.Lock()

    def call(self, func, *args, **kwargs):
        """Execute a function with circuit breaker protection."""
        with self.lock:
            if self.state == "open":
                if time.time() - self.last_failure_time > self.timeout:
                    log.info("Circuit breaker: Transitioning to half-open state")
                    self.state = "half_open"
                else:
                    raise Exception(
                        "Circuit breaker is open due to too many failures. Waiting for timeout."
                    )

        try:
            result = func(*args, **kwargs)
            with self.lock:
                if self.state == "half_open":
                    log.info("Circuit breaker: Request successful, closing circuit")
                    self.state = "closed"
                    self.failure_count = 0
            return result
        except Exception as e:
            with self.lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                if self.failure_count >= self.failure_threshold:
                    log.error(
                        f"Circuit breaker: Opening circuit after {self.failure_count} failures"
                    )
                    self.state = "open"
            raise e


# Global circuit breaker instance
__CIRCUIT_BREAKER = CircuitBreaker(failure_threshold=5, timeout=60)


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
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
                "createdAt": "UTC_DATETIME",
            },
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    This implementation uses multithreading to process paginated API data with comprehensive error handling.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """

    log.warning(
        "Example: Common Patterns For Connectors - Complex Error Handling with Multithreading"
    )

    log.warning(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )

    # Retrieve the cursor from the state to determine the current position in the data sync.
    # If the cursor is not present in the state, start from the beginning of time ('0001-01-01T00:00:00Z').
    cursor = state.get("last_updated_at", "0001-01-01T00:00:00Z")

    # Get parallelism from global variable if not present in configuration
    max_workers = int(configuration.get("parallelism", __PARALLELISM))
    log.info(f"Using {max_workers} worker threads for parallel processing")

    params = {
        "order_by": "updatedAt",
        "order_type": "asc",
        "updated_since": cursor,
        "per_page": __PER_PAGE,
    }

    current_url = __BASE_URL  # Start with the base URL and initial params

    # Process the paginated API with multithreading
    sync_items_parallel(current_url, params, state, max_workers)

    # Log final error statistics
    log_error_statistics()


def sync_items_parallel(current_url: str, params: dict, state: dict, max_workers: int):
    """
    The sync_items_parallel function handles the retrieval and processing of paginated API data using multithreading.
    It performs the following tasks:
        1. Fetches pages from the API sequentially to respect pagination order
        2. Processes records from each page in parallel using a thread pool
        3. Implements comprehensive error handling for network failures and data issues
        4. Maintains thread-safe state updates
        5. Uses circuit breaker pattern to prevent cascading failures
    Args:
        current_url: The URL to the API endpoint, which may be updated with the next page's URL during pagination.
        params: A dictionary of query parameters to be sent with the API request.
        state: A dictionary representing the current state of the sync, including the last 'updatedAt' timestamp.
        max_workers: Maximum number of worker threads for parallel processing.
    """
    more_data = True
    page_count = 0

    while more_data:
        page_count += 1
        try:
            # Fetch the current page with retry logic and circuit breaker
            response_page = get_api_response_with_retry(
                current_url, params, max_retries=__MAX_RETRIES
            )

            # Process the items from this page in parallel
            items = response_page.get("data", [])
            if not items:
                log.info("No more items to process, ending pagination")
                more_data = False
                break

            log.info(
                f"Processing page {page_count} with {len(items)} items using {max_workers} workers"
            )

            # Process items in parallel with error handling
            process_items_parallel(items, state, max_workers)

            # Check if we should continue pagination
            current_url, more_data, params = should_continue_pagination(
                current_url, params, response_page
            )

            # Save the progress by checkpointing the state after each page.
            # This is important for ensuring that the sync process can resume from the correct position.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

        except Exception as e:
            log.error(f"Fatal error processing page {page_count}", e)
            # Record error and re-raise to fail the sync
            with __ERROR_STATS_LOCK:
                __ERROR_STATS["fatal_page_errors"] += 1
            raise


def process_items_parallel(items: List[dict], state: dict, max_workers: int):
    """
    Process a list of items in parallel using ThreadPoolExecutor with comprehensive error handling.
    This function demonstrates:
        1. Parallel processing of records with bounded thread pool
        2. Individual error handling for each record (fail gracefully, continue processing)
        3. Thread-safe state management
        4. Error categorization and statistics tracking
    Args:
        items: List of items to process
        state: State dictionary for tracking sync progress
        max_workers: Maximum number of worker threads
    """
    successful_items = 0
    failed_items = 0

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all items for processing
        future_to_item = {executor.submit(process_single_item, item): item for item in items}

        # Process results as they complete
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                # Get the result (will raise exception if processing failed)
                updated_at = future.result()

                # Thread-safe state update
                with __PROCESSING_LOCK:
                    # Update the state with the latest timestamp
                    if "last_updated_at" not in state or updated_at > state["last_updated_at"]:
                        state["last_updated_at"] = updated_at

                successful_items += 1

            except Exception as e:
                failed_items += 1
                item_id = item.get("id", "unknown")
                log.warning(f"Failed to process item {item_id}: {str(e)}")
                with __ERROR_STATS_LOCK:
                    __ERROR_STATS["failed_items"] += 1

    log.info(f"Batch processing complete: {successful_items} successful, {failed_items} failed")


def process_single_item(item: dict) -> str:
    """
    Process a single item with validation and error handling.
    This function demonstrates:
        1. Data validation before processing
        2. Retry logic for transient failures
        3. Proper error categorization
    Args:
        item: The item to process
    Returns:
        The updatedAt timestamp of the processed item
    Raises:
        Exception: If item processing fails after retries
    """
    try:
        # Validate required fields
        if "id" not in item:
            raise ValueError("Item missing required 'id' field")

        if "updatedAt" not in item:
            raise ValueError(f"Item {item['id']} missing required 'updatedAt' field")

        # Attempt to upsert with retry logic
        max_retries = __ITEM_MAX_RETRIES
        for attempt in range(max_retries):
            try:
                # The 'upsert' operation inserts the data into the destination.
                # This is thread-safe as the SDK handles internal synchronization.
                op.upsert(table="user", data=item)
                return item["updatedAt"]

            except Exception as e:
                if attempt < max_retries - 1:
                    # Wait before retry with exponential backoff
                    wait_time = (2**attempt) * 0.1
                    time.sleep(wait_time)
                    log.debug(f"Retrying item {item['id']} after error: {str(e)}")
                else:
                    # Final attempt failed
                    raise

    except ValueError as e:
        # Data validation errors - log and re-raise
        log.warning(f"Data validation error: {str(e)}")
        with __ERROR_STATS_LOCK:
            __ERROR_STATS["validation_errors"] += 1
        raise
    except Exception as e:
        # Other errors - log and re-raise
        log.warning(f"Error processing item: {str(e)}")
        with __ERROR_STATS_LOCK:
            __ERROR_STATS["processing_errors"] += 1
        raise


def get_api_response_with_retry(current_url: str, params: dict, max_retries: int = 3) -> dict:
    """
    The get_api_response_with_retry function sends an HTTP GET request with retry logic and circuit breaker.
    It performs the following tasks:
        1. Implements exponential backoff retry strategy
        2. Uses circuit breaker to prevent cascading failures
        3. Handles different types of HTTP errors appropriately
        4. Provides detailed error logging
    Args:
        current_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
        max_retries: Maximum number of retry attempts for failed requests.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    Raises:
        Exception: If all retry attempts fail or circuit breaker is open.
    """
    for attempt in range(max_retries):
        try:
            # Use circuit breaker to protect against cascading failures
            response_page = __CIRCUIT_BREAKER.call(get_api_response, current_url, params)
            return response_page

        except rq.exceptions.Timeout as e:
            log.warning(f"Request timeout on attempt {attempt + 1}/{max_retries}: {str(e)}")
            with __ERROR_STATS_LOCK:
                __ERROR_STATS["timeout_errors"] += 1
            if sleep_for_attempt(attempt, current_url, max_retries) is False:
                raise

        except rq.exceptions.ConnectionError as e:
            log.warning(f"Connection error on attempt {attempt + 1}/{max_retries}: {str(e)}")
            with __ERROR_STATS_LOCK:
                __ERROR_STATS["connection_errors"] += 1
            if sleep_for_attempt(attempt, current_url, max_retries) is False:
                raise

        except rq.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            # Handle rate limiting (429) with longer backoff
            if status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                log.warning(f"Rate limited (429), waiting {retry_after} seconds")
                with __ERROR_STATS_LOCK:
                    __ERROR_STATS["rate_limit_errors"] += 1
                time.sleep(retry_after)
                if attempt < max_retries - 1:
                    continue
                else:
                    raise

            # Handle server errors (5xx) with retry
            elif status_code and 500 <= status_code < 600:
                log.warning(f"Server error {status_code} on attempt {attempt + 1}/{max_retries}")
                with __ERROR_STATS_LOCK:
                    __ERROR_STATS["server_errors"] += 1
                if sleep_for_attempt(attempt, current_url, max_retries) is False:
                    raise

            # Client errors (4xx) except 429 - don't retry
            else:
                log.error(f"HTTP error {status_code}", e)
                with __ERROR_STATS_LOCK:
                    __ERROR_STATS["client_errors"] += 1
                raise

        except Exception as e:
            # Unexpected errors
            log.error(f"Unexpected error on attempt {attempt + 1}/{max_retries}", e)
            with __ERROR_STATS_LOCK:
                __ERROR_STATS["unexpected_errors"] += 1

    # Should not reach here, but just in case
    raise Exception(f"Failed to fetch data after {max_retries} attempts")


def sleep_for_attempt(attempt, current_url, max_retries):
    if attempt < max_retries - 1:
        wait_time = 2**attempt
        log.info(f"Waiting {wait_time} seconds before retry...")
        time.sleep(wait_time)
        return True
    else:
        log.error(f"Max retries exceeded for URL: {current_url}")
        return False


def should_continue_pagination(
    current_url: str, params: dict, response_page: dict
) -> Tuple[str, bool, dict]:
    """
    The should_continue_pagination function checks whether pagination should continue based on the presence of a
    next page URL in the API response.
    It performs the following tasks:
        1. Retrieves the URL for the next page of data using the get_next_page_url_from_response function.
        2. If a next page URL is found, updates the current URL to this new URL and clears the existing query parameters,
        as they are included in the next URL.
        3. If no next page URL is found, sets the flag to end the pagination process.

    Api response looks like:
        {
          "data": [
            {"id": "c8fda876-6869-4aae-b989-b514a8e45dc6", "name": "Mark Taylor", ... },
            {"id": "3910cbb0-27d4-47f5-9003-a401338eff6e", "name": "Alan Taylor", ... }
            ...
          ],
          "total_items": 200,
          "page": 1,
          "per_page": 10,
          "next_page_url": "http://127.0.0.1:5001/pagination/next_page_url?page=2&per_page=10&order_by=updatedAt&order_type=asc"
          }
        }
    For real API example you can refer Drift's Account Listing API: https://devdocs.drift.com/docs/listing-accounts
    Args:
        current_url: The current URL being used to fetch data from the API. It will be updated if a next page URL is found.
        params: A dictionary of query parameters used in the API request. It will be cleared if a next page URL is found.
        response_page: A dictionary representing the parsed JSON response from the API.
    Returns:
        current_url: The updated URL for the next page, or the same URL if no next page URL is found.
        has_more_pages: A boolean indicating whether there are more pages to retrieve.
        params: The updated or cleared query parameters for the next API request.
    """
    has_more_pages = True

    # Check if there is a next page URL in the response to continue the pagination
    next_page_url = get_next_page_url_from_response(response_page)

    if next_page_url:
        current_url = next_page_url
        params = {}  # Clear params since the next URL contains the query params
        log.debug(f"Continuing to next page: {current_url}")
    else:
        has_more_pages = False  # End pagination if there is no 'next' URL in the response.
        log.info("No next_page_url found, pagination complete")

    return current_url, has_more_pages, params


def get_api_response(current_url: str, params: dict) -> dict:
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        current_url: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    Raises:
        requests.exceptions.HTTPError: For HTTP error responses
        requests.exceptions.Timeout: For request timeouts
        requests.exceptions.ConnectionError: For connection issues
    """
    log.debug(f"Making API call to url: {current_url} with params: {params}")

    # Set reasonable timeout to prevent hanging requests
    timeout = 30

    response = rq.get(current_url, params=params, timeout=timeout)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    return response_page


def get_next_page_url_from_response(response_page: dict) -> Optional[str]:
    """
    The get_next_page_url_from_response function extracts the URL for the next page of data from the API response.
    Args:
        response_page: A dictionary representing the parsed JSON response from the API.
    Returns:
         The URL for the next page if it exists, otherwise None.
    """
    return response_page.get("next_page_url")


def log_error_statistics():
    """
    Log comprehensive error statistics collected during the sync.
    This helps with monitoring and debugging connector behavior.
    """
    if __ERROR_STATS:
        log.warning("Error Statistics Summary:")
        with __ERROR_STATS_LOCK:
            for error_type, count in __ERROR_STATS.items():
                log.warning(f"  {error_type}: {count}")
    else:
        log.info("No errors encountered during sync")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)

# Resulting table:
# ┌───────────────────────────────────────┬───────────────┬────────────────────────┬──────────────────────────┬───────────────────────────┐
# │                 id                    │      name     │         job            │        updatedAt         │        createdAt          │
# │               string                  │     string    │       string           │      timestamp with UTC  │      timestamp with UTC   │
# ├───────────────────────────────────────┼───────────────┼────────────────────────┼──────────────────────────┼───────────────────────────┤
# │ c8fda876-6869-4aae-b989-b514a8e45dc6  │ Mark Taylor   │   Pilot, airline       │ 2024-09-22T19:35:41Z     │ 2024-09-22T18:50:06Z      │
# │ 3910cbb0-27d4-47f5-9003-a401338eff6e  │ Alan Taylor   │   Dispensing optician  │ 2024-09-22T20:28:11Z     │ 2024-09-22T19:58:38Z      │
# ├───────────────────────────────────────┴───────────────┴────────────────────────┴──────────────────────────┴───────────────────────────┤
# │  2 rows                                                                                                                     5 columns │
# └───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
