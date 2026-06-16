"""This connector fetches leave data from the LeaveDates.com API and syncs it to the destination.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json
from typing import Any

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to the LeaveDates API
import requests

# For handling date and time operations
from datetime import datetime, timezone

# For implementing retry logic with exponential backoff
import time

# For handling random delays in retry logic
import random

__BASE_URL = "https://api.leavedates.com"  # Base URL for the LeaveDates API
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__BASE_DELAY = 1  # Base delay in seconds for API request retries
__DEFAULT_START_DATE = (
    "1900-01-01T00:00:00+00:00"  # Default start date if not provided in configuration
)
__REQUEST_TIMEOUT = 30  # Timeout for API requests in seconds


def validate_datetime_format(date_string: str, field_name: str = "date"):
    """
    Validate that a date string is in proper ISO format with timezone information.
    This function requires the datetime to include both time and timezone components.
    Args:
        date_string: The date string to validate.
        field_name: The name of the field being validated (for error messages).
    Raises:
        ValueError: If the date string is not in a valid ISO format with timezone.
    """
    expected_format = "Expected ISO format with timezone (e.g., '2023-01-01T00:00:00+00:00' or '2023-01-01T00:00:00Z')"

    if not date_string or not date_string.strip():
        raise ValueError(f"{field_name} cannot be empty")

    # Check for required components
    if "T" not in date_string:
        raise ValueError(f"Invalid {field_name} format: '{date_string}'. {expected_format}")

    # Check for timezone information (either Z or +/-offset)
    has_timezone = date_string.endswith("Z") or (
        "+" in date_string or "-" in date_string.split("T")[1]
    )
    if not has_timezone:
        raise ValueError(f"Invalid {field_name} format: '{date_string}'. {expected_format}")

    try:
        # Handle 'Z' timezone suffix by converting to '+00:00'
        normalized_date = date_string.replace("Z", "+00:00")
        datetime.fromisoformat(normalized_date)
    except ValueError as e:
        raise ValueError(
            f"Invalid {field_name} format: '{date_string}'. {expected_format}: {str(e)}"
        )


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
    required_configs = ["api_token", "company_id"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate start_date format if provided
    if "start_date" in configuration:
        start_date = configuration.get("start_date")
        if start_date and start_date.strip():
            validate_datetime_format(start_date, "start_date")


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
            "table": "leave_report",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
            # Columns will be inferred from the data structure by Fivetran
        },
    ]


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

    log.warning("Example: Source Connector : LeaveDates Leave Reports")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    api_token = configuration.get("api_token")
    company_id = configuration.get("company_id")
    start_date = configuration.get("start_date", __DEFAULT_START_DATE)

    # Get the state variable for the sync, if needed
    last_sync_time = state.get("last_sync_time", start_date)
    current_time = datetime.now(timezone.utc).isoformat()

    try:
        # Process leave reports data page by page to avoid memory issues
        total_records_processed = fetch_and_process_leave_reports(
            api_token, company_id, last_sync_time, current_time
        )

        log.info(f"Successfully processed {total_records_processed} leave reports in total")

        # Update state with the current sync time for the next run
        new_state = {"last_sync_time": current_time}

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(new_state)

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync leave reports data: {str(e)}")


def fetch_and_process_leave_reports(
    api_token: str, company_id: str, start_date: str, end_date: str
) -> int:
    """
    Fetch leave reports data from the LeaveDates API with pagination and process each page immediately.
    This function processes data page by page to avoid memory issues with large datasets.
    Args:
        api_token: The API token for authentication.
        company_id: The company ID to fetch reports for.
        start_date: The start date for fetching reports.
        end_date: The end date for fetching reports.
    Returns:
        The total number of records processed.
    """
    total_records_processed = 0
    page = 1

    # Construct the date range parameter for the API
    within_param = f"{start_date},{end_date}"

    while True:
        # Make API request with retry logic
        url = f"{__BASE_URL}/reports/leave"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "X-CSRF-TOKEN": "",
        }
        params = {
            "company": company_id,
            "page": page,
            "within": within_param,
            "report_type": "detail-report",
        }

        response_data = make_api_request_with_retry(url, headers, params)

        # Extract data from response
        reports = response_data.get("data", [])
        if not reports:
            break

        # Process each record from this page immediately
        page_records_processed = 0
        for record in reports:
            try:
                # Flatten the record to handle nested data structures
                flattened_record = flatten_record(record)

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted,
                op.upsert(table="leave_report", data=flattened_record)
                page_records_processed += 1

            except Exception as e:
                log.warning(f"Failed to process record: {str(e)}. Skipping record and continuing.")
                continue

        total_records_processed += page_records_processed
        log.info(f"Processed {page_records_processed} records from page {page}")

        # Check if there are more pages
        current_page = response_data.get("current_page", 1)
        per_page = response_data.get("per_page", 1)
        total_records = response_data.get("total", 0)

        # Ensure per_page is valid to avoid division by zero
        if per_page <= 0:
            log.warning(
                f"API returned invalid per_page value: {per_page}. Using default value of 1."
            )
            per_page = 1

        # Calculate total pages safely
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 0

        if current_page >= total_pages:
            log.info(f"Reached last page ({current_page}/{total_pages})")
            break

        page += 1

    return total_records_processed


def make_api_request_with_retry(url: str, headers: dict, params: dict) -> Any | None:
    """
    Make an API request with retry logic and exponential backoff.
    This function implements retry strategy for handling transient API errors.
    Args:
        url: The API endpoint URL.
        headers: Request headers including authentication.
        params: Query parameters for the request.
    Returns:
        The JSON response data.
    Raises:
        RuntimeError: If all retry attempts fail.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            if attempt == __MAX_RETRIES - 1:
                raise RuntimeError(f"API request failed after {__MAX_RETRIES} attempts: {str(e)}")

            # Calculate delay with exponential backoff and jitter
            delay = __BASE_DELAY * (2**attempt) + random.uniform(0, 1)
            log.warning(
                f"API request failed (attempt {attempt + 1}/{__MAX_RETRIES}), retrying in {delay:.2f} seconds: {str(e)}"
            )
            time.sleep(delay)
    return None


def flatten_record(record: dict, prefix: str = "", separator: str = "_") -> dict:
    """
    Flatten a nested dictionary record to create a flat structure suitable for database storage.
    This function converts nested JSON objects into a flat key-value structure using separator notation.
    Args:
        record: The dictionary record to flatten.
        prefix: Prefix to add to keys (used for recursion).
        separator: Separator to use between nested keys.
    Returns:
        A flattened dictionary with all nested keys converted using separator notation.
    """
    if not isinstance(record, dict):
        raise ValueError("Input record must be a dictionary")

    flattened = {}

    for key, value in record.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            flattened.update(flatten_record(value, new_key, separator))
        elif isinstance(value, list):
            # Convert lists to JSON strings for storage
            flattened[new_key] = json.dumps(value) if value else None
        else:
            # Base case: primitive value
            flattened[new_key] = value

    return flattened


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
