"""Zigpoll Connector for Fivetran Connector SDK.
This connector fetches survey response data from Zigpoll API and syncs it to Fivetran destinations.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For handling HTTP requests to Zigpoll API
import requests

# For date/time operations and timestamp handling
from datetime import datetime

# For handling retry logic with exponential backoff
import time
import random

# For type hints
from typing import Optional

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Constants for API configuration
__ZIGPOLL_BASE_URL = "https://v1.zigpoll.com"
__ACCOUNTS_ENDPOINT = "/accounts"
__RESPONSES_ENDPOINT = "/responses"
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__BASE_DELAY = 1  # Base delay in seconds for API request retries
__PAGE_LIMIT = 100  # Page size for pagination


def parse_user_date_to_epoch(date_input):
    """
    Parse user-provided date input in YYYY-MM-DD format and convert to epoch milliseconds.

    Args:
        date_input: Date string in YYYY-MM-DD format (e.g., "2023-01-01")
    Returns:
        Unix timestamp in milliseconds
    Raises:
        ValueError: if the date format is not YYYY-MM-DD or invalid
    """
    if not date_input:
        return None

    try:
        # Parse date in YYYY-MM-DD format and assume UTC timezone
        parsed_date = datetime.strptime(date_input, "%Y-%m-%d")
        return int(parsed_date.timestamp() * 1000)

    except ValueError as e:
        raise ValueError(
            f"Invalid date format '{date_input}'. Please use YYYY-MM-DD format (e.g., '2023-01-01'). Error: {e}"
        )


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """

    # Validate required configuration parameters
    if "api_token" not in configuration:
        raise ValueError("Missing required configuration value: api_token")

    # Validate start_date format if provided
    if "start_date" in configuration:
        try:
            parse_user_date_to_epoch(configuration["start_date"])
        except ValueError as e:
            raise ValueError(f"Invalid start_date: {e}")


def make_api_request(url: str, headers: dict, params: Optional[dict] = None):
    """
    Make an API request with retry logic and proper error handling.
    This function handles retries with exponential backoff for transient errors and rate limiting.
    Args:
        url: The API endpoint URL to make the request to
        headers: HTTP headers for the request including authorization
        params: Optional query parameters for the request
    Returns:
        JSON response data from the API
    Raises:
        Exception: if the request fails after all retry attempts or for authentication errors
    """
    for attempt in range(__MAX_RETRIES):
        try:
            log.info(f"Making API request to {url} (attempt {attempt + 1})")
            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                delay = __BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                log.warning(f"Rate limited. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            elif response.status_code in [401, 403]:
                raise PermissionError(f"Authentication failed: {response.status_code}")
            else:
                error_detail = f"Status: {response.status_code}, Response: {response.text[:200]}"
                raise ValueError(f"API request failed: {error_detail}")

        except requests.RequestException as e:
            if attempt == __MAX_RETRIES - 1:
                raise ConnectionError(f"Request failed after {__MAX_RETRIES} attempts: {e}")

            delay = __BASE_DELAY * (2**attempt) + random.uniform(0, 1)
            log.warning(f"Request failed: {e}. Retrying in {delay:.2f} seconds...")
            time.sleep(delay)

    raise ConnectionError("Max retries exceeded")


def flatten_metadata(record: dict):
    """
    Flatten the metadata dictionary into separate columns with metadata_ prefix.
    This function processes response records to extract nested metadata into flat columns for better database compatibility.
    Args:
        record: The record containing metadata to flatten
    Returns:
        Updated record with flattened metadata fields as separate columns
    """
    if "metadata" in record and isinstance(record["metadata"], dict):
        metadata = record.pop("metadata")
        for key, value in metadata.items():
            # Replace hyphens with underscores for valid column names
            column_name = f"metadata_{key.replace('-', '_')}"
            record[column_name] = value
    return record


def parse_iso_timestamp(iso_string: str):
    """
    Parse an ISO format timestamp string into a Unix timestamp in milliseconds.
    Handles various ISO format variations including timezone suffixes.
    Args:
        iso_string: ISO format datetime string (e.g., "2023-12-01T10:30:00Z", "2023-12-01T10:30:00+01:00")
    Returns:
        Unix timestamp in milliseconds, or None if parsing fails
    """
    if not iso_string:
        return None

    try:
        # Handle various ISO format strings more robustly
        if iso_string.endswith("Z"):
            # Replace 'Z' with '+00:00' for UTC timezone
            normalized_string = iso_string.replace("Z", "+00:00")
        elif "+" in iso_string or (len(iso_string) >= 6 and "-" in iso_string[-6:]):
            # Already has timezone info (e.g., +01:00 or -05:00), use as-is
            normalized_string = iso_string
        else:
            # No timezone info, assume UTC
            normalized_string = iso_string + "+00:00"

        return int(datetime.fromisoformat(normalized_string).timestamp() * 1000)

    except (ValueError, AttributeError) as e:
        log.warning(f"Failed to parse ISO timestamp '{iso_string}': {e}")
        return None


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
            "table": "response",  # Name of the table in the destination, required.
            "primary_key": ["_id"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "_id": "STRING",  # Contains a dictionary of column names and data types
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        },
    ]


def get_account_ids(headers: dict):
    """
    Fetch all account IDs from Zigpoll accounts endpoint.
    This function retrieves the list of accounts that the API token has access to.
    Args:
        headers: HTTP headers for the request including authorization
    Returns:
        List of account IDs that can be used to fetch responses
    """
    url = f"{__ZIGPOLL_BASE_URL}{__ACCOUNTS_ENDPOINT}"
    accounts_data = make_api_request(url, headers)

    account_ids = []
    if isinstance(accounts_data, list):
        for account in accounts_data:
            if "_id" in account:
                account_ids.append(account["_id"])

    return account_ids


def process_responses_page(
    headers: dict,
    account_id: str,
    start_cursor: Optional[str],
    last_sync_timestamp: Optional[int],
    state: dict,
):
    """
    Process a single page of responses for an account.
    This function fetches one page of responses and processes them with client-side filtering.
    Args:
        headers: HTTP headers for the request including authorization
        account_id: The account ID to fetch responses for
        start_cursor: Cursor for pagination, None for first page
        last_sync_timestamp: Timestamp to filter old responses
        state: State dictionary to checkpoint progress
    Returns:
        Tuple of (processed_count, has_next_page, end_cursor, should_continue)
    """
    # Prepare API parameters
    params = {"accountId": account_id, "limit": str(__PAGE_LIMIT)}
    if start_cursor:
        params["startCursor"] = start_cursor

    # Make API request
    url = f"{__ZIGPOLL_BASE_URL}{__RESPONSES_ENDPOINT}"
    response_data = make_api_request(url, headers, params)

    responses = response_data.get("data", [])
    has_next_page = response_data.get("hasNextPage", False)
    end_cursor = response_data.get("endCursor")

    # Process and filter responses
    processed_count = 0
    should_continue = True

    for response in responses:
        # Check if response is too old (client-side filtering)
        created_at = response.get("createdAt")
        if created_at and last_sync_timestamp is not None:
            response_timestamp = parse_iso_timestamp(created_at)

            if response_timestamp is not None and response_timestamp < last_sync_timestamp:
                should_continue = False
                break

        flattened_response = flatten_metadata(response)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted.
        op.upsert(table="response", data=flattened_response)
        processed_count += 1

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state=state)

    return processed_count, has_next_page, end_cursor, should_continue


def sync_account_responses(
    headers: dict, account_id: str, last_sync_timestamp: Optional[int], state: dict
):
    """
    Sync all responses for a single account with pagination.
    This function handles the pagination loop for fetching all responses from one account.
    Args:
        headers: HTTP headers for the request including authorization
        account_id: The account ID to fetch responses for
        last_sync_timestamp: Timestamp to filter old responses
        state: State dictionary to checkpoint progress
    Returns:
        Total number of responses processed for this account
    """
    log.info(f"Fetching responses for account: {account_id}")
    start_cursor = None
    total_processed = 0
    previous_cursor = None

    while True:
        processed_count, has_next_page, end_cursor, should_continue = process_responses_page(
            headers, account_id, start_cursor, last_sync_timestamp, state
        )

        total_processed += processed_count
        log.info(
            f"Retrieved {processed_count} responses for account {account_id}, total so far: {total_processed}"
        )

        # Check stopping conditions
        if not should_continue:
            log.info(f"Reached old data threshold for account {account_id}, stopping pagination")
            break
        if not has_next_page:
            log.info(f"No more pages for account {account_id} (hasNextPage: false)")
            break
        if end_cursor is not None and end_cursor == previous_cursor:
            log.warning(
                f"API bug detected: same cursor returned ({end_cursor}), stopping to prevent infinite loop"
            )
            break

        previous_cursor = end_cursor
        start_cursor = end_cursor
        log.info(f"Fetching next page with cursor: {start_cursor}")

    return total_processed


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

    log.warning("Example: Source Connector: Zigpoll")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    api_token = configuration.get("api_token")
    start_date_input = configuration.get("start_date")

    # Convert start_date to epoch milliseconds if provided
    start_date_epoch = None
    if start_date_input:
        start_date_epoch = parse_user_date_to_epoch(start_date_input)

    # Get the state variable for the sync, if needed
    last_sync_timestamp = state.get("last_sync_timestamp", start_date_epoch)

    log.info(f"Starting sync with timestamp: {last_sync_timestamp}")

    # Prepare headers for API requests
    headers = {"Authorization": api_token, "Accept": "application/json"}

    try:
        # Get all account IDs
        account_ids = get_account_ids(headers)
        log.info(f"Found {len(account_ids)} accounts: {account_ids}")

        total_responses = 0

        # Fetch responses for each account
        for account_id in account_ids:
            account_responses = sync_account_responses(
                headers, account_id, last_sync_timestamp, state
            )
            total_responses += account_responses

        # Update state with the current sync time for the next run
        current_timestamp = int(time.time() * 1000)
        new_state = {"last_sync_timestamp": current_timestamp}
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(new_state)
        log.info(
            f"Sync completed. Total responses: {total_responses}. Updated state timestamp: {current_timestamp}"
        )

    except PermissionError as e:
        # Handle authentication errors specifically
        raise RuntimeError(f"Authentication failed: {str(e)}")
    except ValueError as e:
        # Handle API errors specifically
        raise RuntimeError(f"API error occurred: {str(e)}")
    except ConnectionError as e:
        # Handle connection errors specifically
        raise RuntimeError(f"Connection error occurred: {str(e)}")
    except Exception as e:
        # Handle any other unexpected errors
        raise RuntimeError(f"Unexpected error during sync: {str(e)}")


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
