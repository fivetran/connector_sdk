"""
This example demonstrates six backoff strategies for handling 429 Too Many Requests responses.
The strategy is selected via the 'backoff_strategy' field in configuration.json.

Requires the fivetran-api-playground package to run:
  playground start --rate-limit --capacity 1

See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# For reading configuration from a JSON file
import json

# For randomized jitter in exponential backoff
import random

# For retry delays and exponential backoff
import time

# For making API requests to the source
import requests as rq

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__API_URL = "http://127.0.0.1:5001/pagination/next_page_url"
__MAX_RETRIES = 5
__REQUEST_TIMEOUT_SECONDS = 10
__FIXED_DELAY = 2
__BASE_DELAY = 0.5
__MAX_DELAY = 10
__CHECKPOINT_INTERVAL = 50

__VALID_STRATEGIES = {
    # Use the same delay for every retry.
    "fixed",
    # Increase delay by a fixed amount on each retry.
    "linear",
    # Double the delay on each retry.
    "exponential",
    # Double the delay but cap it at the maximum delay.
    "exponential_with_cap",
    # Randomize the exponential delay to avoid synchronized retries.
    "exponential_with_jitter",
    # Honor Retry-After on rate limits and fall back to capped exponential backoff.
    "retry_after",
}


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
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


def validate_configuration(configuration: dict):
    """
    Validate that 'backoff_strategy' is present and one of the supported values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if the strategy is missing or unsupported.
    """
    strategy = configuration.get("backoff_strategy")
    if not strategy:
        raise ValueError("Missing required configuration value: 'backoff_strategy'")
    if strategy not in __VALID_STRATEGIES:
        raise ValueError(
            f"Invalid backoff_strategy '{strategy}'. Must be one of: {sorted(__VALID_STRATEGIES)}"
        )


def compute_delay(strategy: str, attempt: int, retry_after_seconds: float = None) -> float:
    """
    Compute the delay in seconds before the next retry attempt.

    Strategies:
      fixed                  — constant delay regardless of attempt number
      linear                 — delay grows linearly with each attempt
      exponential            — delay doubles after each attempt
      exponential_with_cap   — exponential growth capped at __MAX_DELAY
      exponential_with_jitter — randomised exponential to avoid thundering-herd
      retry_after            — honour the server's Retry-After header; fall back to exponential_with_cap

    Args:
        strategy: the backoff strategy name from configuration.
        attempt: 1-based retry attempt number.
        retry_after_seconds: value of the Retry-After response header, if present.
    Returns:
        Seconds to sleep before the next request.
    """
    if strategy == "fixed":
        return __FIXED_DELAY

    if strategy == "linear":
        return __BASE_DELAY * attempt

    if strategy == "exponential":
        return __BASE_DELAY * (2**attempt)

    if strategy == "exponential_with_cap":
        return min(__MAX_DELAY, __BASE_DELAY * (2**attempt))

    if strategy == "exponential_with_jitter":
        return random.uniform(0, __BASE_DELAY * (2**attempt))

    if strategy == "retry_after":
        if retry_after_seconds is not None:
            return retry_after_seconds
        log.warning("Could not get Retry-After header. Falling back to exponential with cap.")
        return min(__MAX_DELAY, __BASE_DELAY * (2**attempt))

    raise ValueError(f"Unknown strategy: {strategy}")


def is_retryable_response(response) -> bool:
    """
    Check whether an HTTP response should be retried.
    Args:
        response: the HTTP response returned by requests.
    Returns:
        True when the status code is retryable, otherwise False.
    """
    return response.status_code == 429 or 500 <= response.status_code < 600


def retry_or_raise(url: str, strategy: str, attempt: int, response=None, error=None):
    """
    Sleep before the next retry or raise when retry attempts are exhausted.
    Args:
        url: the endpoint URL.
        strategy: the backoff strategy name.
        attempt: 1-based retry attempt number.
        response: the HTTP response, when one is available.
        error: the request exception, when one is available.
    Raises:
        Exception: when the response is non-retryable or retry attempts are exhausted.
    """
    if response is not None and not is_retryable_response(response):
        raise Exception(
            f"Non-retryable HTTP response for {url}: HTTP {response.status_code}, "
            f"response body: {response.text}"
        )

    if error is not None:
        reason = f"Request failed ({type(error).__name__}): {error}"
    elif response.status_code == 429:
        reason = "Rate limited (429)"
    else:
        reason = f"Server error ({response.status_code})"

    if attempt == __MAX_RETRIES:
        raise Exception(f"API request failed after {__MAX_RETRIES} attempts for {url}: {reason}")

    retry_after_seconds = None
    if response is not None and response.status_code == 429 and strategy == "retry_after":
        retry_after_header = response.headers.get("Retry-After")
        if retry_after_header is not None:
            try:
                retry_after_seconds = float(retry_after_header)
            except ValueError:
                pass

    delay = compute_delay(strategy, attempt, retry_after_seconds)
    log.warning(f"{reason}. Strategy='{strategy}', attempt={attempt}, sleeping {delay:.2f}s")
    time.sleep(delay)


def get_api_response(url: str, params: dict, strategy: str) -> dict:
    """
    Send a GET request and retry transient failures using the chosen backoff strategy.
    Args:
        url: the endpoint URL.
        params: query parameters for the request.
        strategy: the backoff strategy name.
    Returns:
        Parsed JSON response as a dictionary.
    Raises:
        Exception: when __MAX_RETRIES is exceeded or a non-retryable HTTP error occurs.
    """
    for attempt in range(1, __MAX_RETRIES + 1):
        log.info(f"API call attempt {attempt}/{__MAX_RETRIES}: {url}")
        try:
            response = rq.get(url, params=params, timeout=__REQUEST_TIMEOUT_SECONDS)

            if response.status_code == 200:
                return response.json()

            retry_or_raise(url, strategy, attempt, response=response)
        except rq.RequestException as exc:
            retry_or_raise(url, strategy, attempt, error=exc)

        continue

    raise Exception(f"Exceeded {__MAX_RETRIES} retries for {url}")


def sync_items(current_url: str, params: dict, state: dict, strategy: str):
    """
    Fetch all pages from the API, upsert rows, and checkpoint periodically.
    Args:
        current_url: starting endpoint URL.
        params: initial query parameters.
        state: connector state dict (modified in place).
        strategy: the backoff strategy name.
    """
    more_data = True
    rows_since_checkpoint = 0

    while more_data:
        response_page = get_api_response(current_url, params, strategy)

        items = response_page.get("data", [])
        if not items:
            more_data = False
            break

        log.info(f"Processing page with {len(items)} items")

        for user in items:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="USER", data=user)
            state["last_updated_at"] = user["updatedAt"]
            rows_since_checkpoint += 1

            if rows_since_checkpoint >= __CHECKPOINT_INTERVAL:
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state)
                log.info(f"Checkpoint saved at cursor: {state['last_updated_at']}")
                rows_since_checkpoint = 0

        # Checkpoint at the end of every page as well
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)
        log.info(f"Page complete. Cursor: {state['last_updated_at']}")
        rows_since_checkpoint = 0

        next_page_url = response_page.get("next_page_url")
        if next_page_url:
            current_url = next_page_url
            params = {}
        else:
            more_data = False


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Common Patterns For Connectors : Backoff Strategies")

    validate_configuration(configuration)

    strategy = configuration["backoff_strategy"]
    log.info(f"Using backoff strategy: '{strategy}'")

    cursor = state.get("last_updated_at", "0001-01-01T00:00:00Z")
    params = {
        "order_by": "updatedAt",
        "order_type": "asc",
        "updated_since": cursor,
        "per_page": 50,
    }

    sync_items(__API_URL, params, state, strategy)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
