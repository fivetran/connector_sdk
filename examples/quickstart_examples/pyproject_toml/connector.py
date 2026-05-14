"""
This is an example for how to use pyproject.toml for dependency management with the Fivetran Connector SDK.
Instead of declaring dependencies in a requirements.txt file, this connector uses a pyproject.toml file.
The pyproject.toml file is the modern Python standard for declaring project metadata and dependencies.
The Connector SDK prioritizes pyproject.toml over requirements.txt when both are present.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

This connector fetches the latest exchange rates from the Frankfurter API (https://frankfurter.dev),
a free, open-source API that requires no authentication.
"""

import json  # Import the json module to handle JSON data.

import requests  # Import the requests module for making HTTP requests. Pre-installed in Fivetran environment.

# Import tenacity for robust API retry logic with exponential backoff.
# This dependency is declared in pyproject.toml under [project.dependencies].
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like update() and schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# API endpoint for the latest exchange rates.
__API_URL = "https://api.frankfurter.dev/v2/rates/latest?base={from_currency}&quotes={to_currency}"
__REQUEST_TIMEOUT = 60  # seconds for HTTP request timeout

# Retry configuration for the tenacity @retry decorator.
__MAX_RETRY_ATTEMPTS = 3  # Maximum number of attempts before giving up.
__RETRY_WAIT_MULTIPLIER = 2  # Exponential backoff multiplier.
__RETRY_WAIT_MIN_SECONDS = 2  # Minimum wait time between retries in seconds.
__RETRY_WAIT_MAX_SECONDS = 10  # Maximum wait time between retries in seconds.


def log_before_retry(retry_state):
    """
    Custom before_sleep callback that logs retry attempts using the Fivetran SDK logger.
    This is passed to tenacity's @retry decorator and invoked before each retry sleep.
    Args:
        retry_state: a tenacity RetryCallState object containing attempt_number,
            the raised exception (via outcome.exception()), and next_action.sleep.
    """
    log.warning(
        f"Retry attempt {retry_state.attempt_number} failed: {retry_state.outcome.exception()}. "
        f"Retrying in {retry_state.next_action.sleep:.0f}s..."
    )


# Use tenacity's @retry decorator to handle transient API failures automatically.
# - stop_after_attempt: Give up after __MAX_RETRY_ATTEMPTS failed attempts.
# - wait_exponential: Exponential backoff bounded by __RETRY_WAIT_MIN_SECONDS and __RETRY_WAIT_MAX_SECONDS.
# - retry_if_exception_type: Only retry on network/HTTP errors, not on programming errors.
# - before_sleep: Uses a custom callback to log retries via the Fivetran SDK logger (log.warning).
@retry(
    stop=stop_after_attempt(__MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=__RETRY_WAIT_MULTIPLIER,
        min=__RETRY_WAIT_MIN_SECONDS,
        max=__RETRY_WAIT_MAX_SECONDS,
    ),
    retry=retry_if_exception_type(requests.RequestException),
    before_sleep=log_before_retry,
    reraise=True,
)
def fetch_exchange_rates(url: str) -> list:
    """
    Fetch exchange rates from the Frankfurter API with automatic retry on failure.
    The @retry decorator retries the call up to __MAX_RETRY_ATTEMPTS times on
    requests.RequestException before re-raising the last exception to the caller.
    Args:
        url: the fully formatted Frankfurter API URL to request.
    Returns:
        A list of dictionaries, each containing a date, base currency, quote currency, and rate.
    Raises:
        requests.RequestException: if all retry attempts fail (network/HTTP errors).
    """
    log.info(f"Requesting: {url}")
    response = requests.get(url, timeout=__REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


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
            "table": "exchange_rates",  # Name of the table in the destination.
            "primary_key": ["date", "from_currency", "to_currency"],  # Composite primary key.
            "columns": {
                "date": "NAIVE_DATE",
                "from_currency": "STRING",
                "to_currency": "STRING",
                "rate": {"type": "DECIMAL", "precision": 15, "scale": 6},
            },
        }
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    for key in ("from_currency", "to_currency"):
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: '{key}'")


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: QuickStart Examples - pyproject.toml")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    from_currency = configuration["from_currency"]
    to_currency = configuration["to_currency"]
    log.info(f"Fetching latest exchange rate for {from_currency} -> {to_currency}")

    # Build the API URL for the latest exchange rates.
    url = __API_URL.format(from_currency=from_currency, to_currency=to_currency)

    # Fetch data using tenacity-powered retry logic (declared as a dependency in pyproject.toml).
    # tenacity retries up to __MAX_RETRY_ATTEMPTS times on network/HTTP errors with exponential backoff.
    # If all attempts fail, the exception is re-raised and caught below for graceful handling.
    try:
        exchange_rates = fetch_exchange_rates(url)
    except requests.RequestException as e:
        log.error(f"API request failed after {__MAX_RETRY_ATTEMPTS} retry attempts: {e}")
        raise RuntimeError(f"Failed to fetch exchange rates from API: {e}") from e

    # The API returns a single record for the configured currency pair.
    if not exchange_rates:
        log.warning("API returned no exchange rate records")
        return

    record = exchange_rates[0]
    log.info(
        f"Exchange rate for {record.get('date')}: {record.get('base')} -> {record.get('quote')} = {record.get('rate')}"
    )

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(
        table="exchange_rates",
        data={
            "date": record.get("date"),
            "from_currency": record.get("base"),
            "to_currency": record.get("quote"),
            "rate": str(record.get("rate", 0)),
        },
    )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


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

# Resulting table:
# ┌────────────┬───────────────┬─────────────┬───────────────┐
# │    date    │ from_currency │ to_currency │     rate      │
# ├────────────┼───────────────┼─────────────┼───────────────┤
# │ 2026-04-20 │ USD           │ INR         │     92.950000 │
# └────────────┴───────────────┴─────────────┴───────────────┘
