"""Resend Emails Connector for Fivetran - fetches email data from Resend API.
This connector demonstrates how to fetch email data from Resend REST API and upsert it into destination using the Fivetran Connector SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP API requests (provided by SDK runtime)
import requests

# For handling time operations and timestamps
import time

# For type hints
from typing import Optional

__BASE_URL = "https://api.resend.com"  # Base URL for Resend API
__EMAILS_ENDPOINT = "/emails"  # Endpoint path for emails API
__REQUEST_TIMEOUT_SECONDS = 30  # Timeout for API requests in seconds
__CHECKPOINT_INTERVAL = 50  # Checkpoint after every 50 emails
__RATE_LIMIT_DELAY_SECONDS = 0.6  # Delay between requests to respect 2 req/sec limit

# Retry configuration constants
__MAX_RETRIES = 5  # Maximum number of retry attempts for API requests
__BACKOFF_BASE_SECONDS = 1  # Base delay in seconds for API request retries


def flatten_dict(data: dict, prefix: str = "", separator: str = "_") -> dict:
    """
    Flatten a nested dictionary by concatenating keys with a separator.
    This is used to convert nested JSON responses into flat table structures.

    Args:
        data: The dictionary to flatten
        prefix: Prefix to add to keys (used for recursion)
        separator: Separator to use between nested keys

    Returns:
        A flattened dictionary with nested objects flattened and arrays converted to JSON strings
    """
    flattened = {}

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            flattened.update(flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            # Convert lists to JSON strings for storage
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


def is_retryable_http_error(response) -> bool:
    """
    Check if an HTTP error is retryable (rate limit or server error).
    Args:
        response: The HTTP response object
    Returns:
        True if the error is retryable, False otherwise
    """
    return response and (response.status_code == 429 or response.status_code >= 500)


def retry_with_backoff(attempt: int) -> None:
    """
    Sleep with exponential backoff and log retry attempt.
    Args:
        attempt: Current retry attempt number (0-indexed)
    """
    delay_seconds = __BACKOFF_BASE_SECONDS * (2**attempt)
    log.warning(f"Retrying in {delay_seconds} seconds (attempt {attempt + 1}/{__MAX_RETRIES})")
    time.sleep(delay_seconds)


def fetch_emails_from_api(url: str, headers: dict, params: Optional[dict] = None) -> dict:
    """
    Fetch emails from Resend API with error handling and exponential backoff retry logic.

    Args:
        url: The API endpoint URL
        headers: HTTP headers including authorization
        params: Optional query parameters for pagination

    Returns:
        The JSON response containing email data

    Raises:
        requests.exceptions.RequestException: For HTTP errors
        ValueError: For invalid JSON responses
    """
    params = params or {}

    for attempt in range(__MAX_RETRIES):
        response = None
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if attempt < __MAX_RETRIES - 1:
                log.warning("Request timeout.")
                retry_with_backoff(attempt)
                continue
            log.error(f"Request timeout after {__MAX_RETRIES} attempts")
            raise
        except requests.exceptions.HTTPError as e:
            if is_retryable_http_error(response) and attempt < __MAX_RETRIES - 1:
                log.warning(f"HTTP {response.status_code} error.")
                retry_with_backoff(attempt)
                continue
            log.error(f"HTTP error {response.status_code}: {e}")
            raise
        except (requests.exceptions.RequestException, ValueError) as e:
            log.error(f"Request failed: {e}")
            raise

    raise requests.exceptions.RequestException(f"Request failed after {__MAX_RETRIES} attempts")


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    api_token = configuration.get("api_token")

    if not api_token:
        raise ValueError("Missing required configuration parameter: 'api_token'")

    if not isinstance(api_token, str) or not api_token.strip():
        raise ValueError("Configuration parameter 'api_token' must be a non-empty string")


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
            "table": "email",  # Table for Resend emails
            "primary_key": ["id"],  # Email ID as primary key
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """

    log.warning("Example: API Connector : Resend Emails Connector")

    # Validate configuration before proceeding
    validate_configuration(configuration)

    # Extract configuration parameters
    api_token = configuration.get("api_token")

    # Set up authentication headers
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

    # Get the state variable from previous sync
    last_synced_email_id = state.get("last_synced_email_id")

    try:
        # Sync emails data from /emails endpoint
        new_last_synced_email_id = sync_emails(headers, last_synced_email_id)

        # Update state with the last synced email ID for incremental sync
        new_state = {"last_synced_email_id": new_last_synced_email_id}

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(new_state)

    except (requests.exceptions.RequestException, ValueError) as e:
        log.error(f"Failed to sync data: {str(e)}")
        raise


def track_newest_email_id(
    idx: int, email_id: str, newest_email_id: Optional[str]
) -> Optional[str]:
    """
    Track the first (newest) email ID from the current sync.
    Args:
        idx: Current email index in the page
        email_id: Current email ID
        newest_email_id: Previously tracked newest email ID
    Returns:
        The newest email ID
    """
    if idx == 0 and newest_email_id is None:
        log.info(f"Newest email ID in this sync: {email_id}")
        return email_id
    return newest_email_id


def should_stop_at_synced_email(email_id: str, last_synced_email_id: Optional[str]) -> bool:
    """
    Check if we've reached the last synced email for incremental sync.
    Args:
        email_id: Current email ID
        last_synced_email_id: Last synced email ID from previous sync
    Returns:
        True if we should stop, False otherwise
    """
    if last_synced_email_id and email_id == last_synced_email_id:
        log.info(f"Reached previously synced email ID: {email_id}. Stopping incremental sync.")
        return True
    return False


def checkpoint_if_needed(emails_synced_count: int, newest_email_id: str) -> None:
    """
    Checkpoint at regular intervals to save progress.
    Args:
        emails_synced_count: Total number of emails synced so far
        newest_email_id: The newest email ID from this sync
    """
    if emails_synced_count % __CHECKPOINT_INTERVAL == 0:
        checkpoint_state = {"last_synced_email_id": newest_email_id}

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(checkpoint_state)
        log.info(f"Checkpointed at {emails_synced_count} emails with newest ID: {newest_email_id}")


def process_email_batch(
    emails: list,
    last_synced_email_id: Optional[str],
    emails_synced_count: int,
    newest_email_id: Optional[str],
) -> tuple:
    """
    Process a batch of emails from the API response.
    Args:
        emails: List of email records from API
        last_synced_email_id: Last synced email ID from previous sync
        emails_synced_count: Running count of synced emails
        newest_email_id: Newest email ID tracked so far
    Returns:
        Tuple of (found_last_synced, emails_synced_count, new_emails_count, newest_email_id, last_page_email_id)
    """
    new_emails_count = 0
    last_page_email_id = None
    found_last_synced = False

    for idx, email in enumerate(emails):
        email_id = email.get("id")
        if not email_id:
            log.warning(f"Skipping email at index {idx} without ID: {email}")
            continue

        # Track the newest email ID
        newest_email_id = track_newest_email_id(idx, email_id, newest_email_id)

        # Check if we've reached the last synced email
        if should_stop_at_synced_email(email_id, last_synced_email_id):
            found_last_synced = True
            break

        # Flatten and upsert the email data
        flattened_email = flatten_dict(email)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="email", data=flattened_email)

        emails_synced_count += 1
        new_emails_count += 1
        last_page_email_id = email_id

        # Checkpoint at regular intervals
        checkpoint_if_needed(emails_synced_count, newest_email_id)

    return (
        found_last_synced,
        emails_synced_count,
        new_emails_count,
        newest_email_id,
        last_page_email_id,
    )


def sync_emails(headers: dict, last_synced_email_id: Optional[str] = None) -> Optional[str]:
    """
    Fetch and sync emails data from Resend API with incremental syncing support.
    This function handles pagination and checkpoints progress at regular intervals.
    For incremental sync, it fetches all emails and stops when reaching previously synced emails.

    Args:
        headers: HTTP headers including authorization token
        last_synced_email_id: Email ID from last sync for incremental updates

    Returns:
        The last synced email ID for the next sync
    """
    if last_synced_email_id:
        log.info(f"Starting incremental sync from last synced email ID: {last_synced_email_id}")
    else:
        log.info("Starting full sync (no previous state)")

    # Build the URL for emails endpoint
    url = f"{__BASE_URL}{__EMAILS_ENDPOINT}"
    params: dict = {}

    emails_synced_count = 0
    total_new_emails_count = 0
    newest_email_id = None
    last_page_email_id = None
    found_last_synced = False

    # Process emails in pages until no more data available or we reach previously synced emails
    while not found_last_synced:
        try:
            response_data = fetch_emails_from_api(url, headers, params)
            emails = response_data.get("data", [])

            log.info(f"Retrieved {len(emails)} emails from API")

            # Process the batch of emails
            (
                found_last_synced,
                emails_synced_count,
                new_emails_count,
                newest_email_id,
                last_page_email_id,
            ) = process_email_batch(
                emails, last_synced_email_id, emails_synced_count, newest_email_id
            )
            total_new_emails_count += new_emails_count

            # Stop if we found the last synced email
            if found_last_synced:
                break

            # Check for more pages
            has_more_pages = response_data.get("has_more", False)
            if not has_more_pages:
                log.info(f"No more emails to sync. Total synced: {emails_synced_count}")
                break

            # Set up pagination for next page
            params["after"] = last_page_email_id
            log.info(f"Fetching next page after email ID: {last_page_email_id}")
            time.sleep(__RATE_LIMIT_DELAY_SECONDS)

        except (requests.exceptions.RequestException, ValueError) as e:
            log.error(f"Error syncing emails: {e}")
            raise

    log.info(f"Email sync completed. Total new emails synced: {total_new_emails_count}")
    # Return the newest email ID (first email from this sync) for next incremental sync
    # Handle edge case: if no emails exist in the account (first sync with empty dataset)
    if newest_email_id is None and last_synced_email_id is None:
        log.warning(
            "No emails were synced and no previous state exists. Returning None as sync cursor."
        )
        return None
    # If no new emails in this sync but we have previous state, keep the previous cursor
    return newest_email_id if newest_email_id else last_synced_email_id


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)
