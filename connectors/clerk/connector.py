"""Clerk API Connector for Fivetran Connector SDK.
This connector fetches user data from Clerk API and syncs it to the destination with flattened nested structures.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For adding delay between retries
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to the Clerk API
import requests

# Constants for API configuration
__API_BASE_URL = "https://api.clerk.com/v1"
__USERS_ENDPOINT = "/users"
__PAGE_LIMIT = 100  # Number of records to fetch per API request
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__CHECKPOINT_INTERVAL = 1000  # Checkpoint state after every 1000 records processed
__DEFAULT_START_CREATED_AT = (
    631152000000  # Epoch milliseconds for 1990-01-01 (default start date for incremental sync)
)
__REQUEST_TIMEOUT_SEC = 30  # Timeout for API requests in seconds
__RATE_LIMIT_STATUS_CODE = 429  # HTTP status code for rate limiting
__SERVER_ERROR_MIN_STATUS = 500  # Minimum HTTP status code for server errors
__SERVER_ERROR_MAX_STATUS = 600  # Maximum HTTP status code for server errors

# Child table configuration: maps array field names to their destination table names
__CHILD_TABLES = {
    "email_addresses": "user_email_address",
    "phone_numbers": "user_phone_number",
    "web3_wallets": "user_web3_wallet",
    "passkeys": "user_passkey",
    "external_accounts": "user_external_account",
    "saml_accounts": "user_saml_account",
    "enterprise_accounts": "user_enterprise_account",
}


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.

    Args:
        configuration: A dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: If any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    if "api_key" not in configuration:
        raise ValueError("Missing required configuration value: api_key")


def schema(configuration: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
    """

    return [
        {
            "table": "user",
            "primary_key": ["id"],
        },
        {
            "table": "user_email_address",
            "primary_key": ["id"],
        },
        {
            "table": "user_phone_number",
            "primary_key": ["id"],
        },
        {
            "table": "user_web3_wallet",
            "primary_key": ["id"],
        },
        {
            "table": "user_passkey",
            "primary_key": ["id"],
        },
        {
            "table": "user_external_account",
            "primary_key": ["id"],
        },
        {
            "table": "user_saml_account",
            "primary_key": ["id"],
        },
        {
            "table": "user_enterprise_account",
            "primary_key": ["id"],
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update

    Args:
        configuration: A dictionary containing connection details.
        state: A dictionary containing state information from previous runs.
               The state dictionary is empty for the first sync or for any full re-sync.

    Raises:
        RuntimeError: If API request fails or data sync encounters an error.
    """

    log.warning("Example: Source Examples - Clerk API")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    api_key = configuration.get("api_key")

    # Get the state variable for the sync - last_created_at tracks incremental sync using created_at_after
    # Default to January 1, 1990 if no previous state exists
    last_created_at = state.get("last_created_at", __DEFAULT_START_CREATED_AT)
    new_created_at = None  # Only update if we actually process records

    # Counter for tracking records processed for checkpointing
    records_processed = 0

    try:
        # Fetch users using pagination with incremental sync support
        for user in fetch_users_paginated(api_key, last_created_at):

            # Process and upsert user and child table records
            process_user_record(user)

            # Track the latest created_at timestamp for incremental sync
            new_created_at = update_sync_cursor(user, new_created_at)

            records_processed += 1

            # Checkpoint state periodically to enable resumption on interruption
            if records_processed % __CHECKPOINT_INTERVAL == 0:
                checkpoint_sync_state(new_created_at, records_processed)

        # Final checkpoint with the latest state only if we processed any records
        if new_created_at is not None:
            checkpoint_sync_state(new_created_at, records_processed, is_final=True)
        else:
            log.info("No new records to process. Sync completed without state update.")

    except requests.exceptions.RequestException as e:
        # Handle HTTP/network related errors
        raise RuntimeError(f"API request failed: {str(e)}")
    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def process_user_record(user):
    """
    Process and upsert a single user record along with its child table data.

    Args:
        user: The user dictionary from the API.
    """
    # Process and upsert the main user record
    user_record = flatten_user_record(user)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The op.upsert method is called with two arguments:
    # - The first argument is the name of the table to upsert the data into.
    # - The second argument is a dictionary containing the data to be upserted.
    op.upsert(table="user", data=user_record)

    # Process nested arrays and upsert into separate child tables
    process_child_tables(user)


def update_sync_cursor(user, current_cursor):
    """
    Update the sync cursor with the latest created_at timestamp.

    Args:
        user: The user dictionary from the API.
        current_cursor: The current sync cursor value.

    Returns:
        Updated cursor value.
    """
    user_created_at = user.get("created_at")
    if user_created_at and (current_cursor is None or user_created_at > current_cursor):
        return user_created_at
    return current_cursor


def checkpoint_sync_state(cursor_value, records_processed, is_final=False):
    """
    Checkpoint the current sync state.

    Args:
        cursor_value: The current cursor value to save.
        records_processed: Number of records processed so far.
        is_final: Whether this is the final checkpoint (default: False).
    """
    checkpoint_state = {"last_created_at": cursor_value}
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(checkpoint_state)

    if is_final:
        log.info(f"Sync completed. Total records processed: {records_processed}")
    else:
        log.info(f"Checkpointed after processing {records_processed} records")


def fetch_users_paginated(api_key, last_created_at=None):
    """
    Fetch users from Clerk API using offset-based pagination with incremental sync support.
    This generator function yields user records one at a time to avoid loading all data into memory.
    Pagination is handled using offset and limit parameters as per Clerk API documentation.

    Args:
        api_key: The API key for authentication.
        last_created_at: Timestamp in milliseconds for incremental sync (fetches users created after this time).

    Yields:
        User dictionaries from the API response.
    """
    offset = 0
    has_more_data = True

    while has_more_data:
        # Build API URL with pagination parameters
        url = f"{__API_BASE_URL}{__USERS_ENDPOINT}"
        params = {"limit": __PAGE_LIMIT, "offset": offset, "order_by": "created_at"}

        # Add incremental sync parameter if last_created_at is provided
        if last_created_at is not None:
            params["created_at_after"] = last_created_at

        # Make API request with retry logic
        users = make_api_request(url, api_key, params)

        # If no users returned, we've reached the end
        if not users:
            break

        # Yield each user individually to avoid memory issues
        for user in users:
            yield user

        # If we received fewer records than the limit, we've reached the end
        if len(users) < __PAGE_LIMIT:
            has_more_data = False
        else:
            # Move to the next page
            offset += __PAGE_LIMIT


def should_retry_http_error(status_code):
    """
    Determine if an HTTP error should be retried based on status code.

    Args:
        status_code (int): HTTP status code from the response.

    Returns:
        bool: True if the error is retryable (429 or 5xx), False otherwise.
    """
    is_rate_limit = status_code == __RATE_LIMIT_STATUS_CODE
    is_server_error = __SERVER_ERROR_MIN_STATUS <= status_code < __SERVER_ERROR_MAX_STATUS
    return is_rate_limit or is_server_error


def retry_with_backoff(attempt_number, error_message):
    """
    Sleep for exponential backoff duration and log a warning.

    Implements exponential backoff strategy: wait time = 2^attempt_number seconds.
    For example: attempt 0 = 1s, attempt 1 = 2s, attempt 2 = 4s.

    Args:
        attempt_number (int): Current retry attempt number (0-indexed).
        error_message (str): Message to log before waiting.
    """
    wait_time_sec = 2**attempt_number
    log.warning(f"{error_message} Retrying in {wait_time_sec} seconds...")
    time.sleep(wait_time_sec)


def handle_http_error_with_retry(response, attempt_number):
    """
    Handle HTTP errors with appropriate retry logic based on status code.

    Retryable errors (429 rate limit, 5xx server errors) will sleep with exponential backoff.
    Non-retryable errors (4xx client errors except 429) will raise immediately.

    Args:
        response: HTTP response object containing status code.
        attempt_number (int): Current retry attempt number (0-indexed).

    Raises:
        requests.exceptions.RequestException: For non-retryable errors or when retries exhausted.
    """
    if not response:
        raise requests.exceptions.RequestException("No response received from API")

    status_code = response.status_code

    # Don't retry client errors (4xx) except rate limiting (429)
    if not should_retry_http_error(status_code):
        raise requests.exceptions.HTTPError(
            f"HTTP {status_code} error: {response.reason}", response=response
        )

    # For rate limiting errors
    if status_code == __RATE_LIMIT_STATUS_CODE:
        retry_with_backoff(attempt_number, "Rate limited.")
        return

    # For server errors (5xx)
    if attempt_number < __MAX_RETRIES - 1:
        retry_with_backoff(attempt_number, f"Server error {status_code}.")
    else:
        raise requests.exceptions.HTTPError(
            f"Server error {status_code} after {__MAX_RETRIES} attempts: {response.reason}",
            response=response,
        )


def make_api_request(url: str, api_key: str, params: dict) -> dict:
    """
    Make an API request to Clerk API with retry logic and exponential backoff.

    This function implements a robust retry mechanism for handling transient errors:
    - Rate limiting (429): Retries with exponential backoff
    - Server errors (5xx): Retries with exponential backoff
    - Network errors: Retries with exponential backoff
    - Client errors (4xx except 429): No retry, raises immediately

    Args:
        url (str): The API endpoint URL.
        api_key (str): The API key for authentication.
        params (dict): Query parameters for the request.

    Returns:
        dict: JSON response from the API.

    Raises:
        requests.exceptions.RequestException: If all retry attempts fail or for non-retryable errors.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(__MAX_RETRIES):
        response = None
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SEC
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError:
            handle_http_error_with_retry(response, attempt)

        except requests.exceptions.RequestException as e:
            # Retry network errors with exponential backoff
            if attempt < __MAX_RETRIES - 1:
                retry_with_backoff(attempt, f"Request failed: {str(e)}.")
            else:
                raise

    # If all retries exhausted without returning
    raise requests.exceptions.RequestException(f"Failed after {__MAX_RETRIES} attempts")


def serialize_complex_value(value):
    """
    Serialize complex data types (dict, list) to JSON string.

    Args:
        value: The value to serialize (can be dict, list, or any JSON-serializable type).

    Returns:
        str or None: JSON string representation if value is non-empty, None otherwise.
    """
    if not value:
        return None
    return json.dumps(value)


def flatten_deeply_nested_value(parent_key, nested_key, deep_key, deep_value):
    """
    Flatten a deeply nested (3-level) dictionary value.

    Args:
        parent_key: The top-level key name.
        nested_key: The second-level key name.
        deep_key: The third-level key name.
        deep_value: The value at the third level.

    Returns:
        tuple: (flattened_key, processed_value) where flattened_key is underscore-separated
               and processed_value is either serialized JSON or the raw value.
    """
    flattened_key = f"{parent_key}_{nested_key}_{deep_key}"

    if isinstance(deep_value, (dict, list)):
        return flattened_key, serialize_complex_value(deep_value)

    return flattened_key, deep_value


def flatten_nested_value(parent_key, nested_key, nested_value):
    """
    Flatten a nested (2-level) dictionary value.

    Args:
        parent_key: The top-level key name.
        nested_key: The second-level key name.
        nested_value: The value at the second level.

    Returns:
        dict: Dictionary containing flattened key-value pairs. May contain multiple entries
              if nested_value is itself a dictionary.
    """
    flattened = {}
    flattened_key = f"{parent_key}_{nested_key}"

    if isinstance(nested_value, dict):
        # Handle deeply nested objects (3 levels)
        for deep_key, deep_value in nested_value.items():
            key, value = flatten_deeply_nested_value(parent_key, nested_key, deep_key, deep_value)
            flattened[key] = value
    elif isinstance(nested_value, list):
        flattened[flattened_key] = json.dumps(nested_value)
    else:
        flattened[flattened_key] = nested_value

    return flattened


def flatten_dict_value(key, value):
    """
    Flatten a dictionary value by converting nested structures to underscore-separated keys.

    Args:
        key: The parent key name.
        value: The dictionary value to flatten.

    Returns:
        dict: Dictionary with flattened key-value pairs.
    """
    flattened = {}

    for nested_key, nested_value in value.items():
        nested_flattened = flatten_nested_value(key, nested_key, nested_value)
        flattened.update(nested_flattened)

    return flattened


def flatten_record(record, excluded_fields=None):
    """
    Flatten a record by converting nested dictionaries into underscore-separated column names.

    This function processes a nested dictionary structure and converts it into a flat dictionary
    suitable for database storage. Nested dictionaries are flattened using underscore notation
    (e.g., {"user": {"name": "John"}} becomes {"user_name": "John"}). Lists and deeply nested
    structures are serialized to JSON strings.

    Args:
        record (dict): The record to flatten. Can contain nested dicts, lists, and scalar values.
        excluded_fields (list, optional): List of field names to exclude from flattening
                                         (e.g., array fields that need separate processing).
                                         Defaults to None.

    Returns:
        Flattened dictionary.
    """
    flattened = {}
    excluded_fields = excluded_fields or []

    for key, value in record.items():
        # Skip excluded fields early to reduce nesting
        if key in excluded_fields:
            continue

        # Process based on value type
        if isinstance(value, dict):
            dict_flattened = flatten_dict_value(key, value)
            flattened.update(dict_flattened)
        elif isinstance(value, list):
            flattened[key] = json.dumps(value)
        else:
            flattened[key] = value

    return flattened


def flatten_user_record(user):
    """
    Flatten the main user record by extracting nested JSON objects into the same table.
    Arrays are excluded and processed separately into child tables.

    Args:
        user: The user dictionary from the API.

    Returns:
        Flattened user dictionary with nested objects converted to column names.
    """
    # Exclude array fields that will be processed separately as child tables
    array_fields = list(__CHILD_TABLES.keys())
    return flatten_record(user, excluded_fields=array_fields)


def process_child_tables(user):
    """
    Process all child table arrays and upsert records into their respective tables.

    Args:
        user: The user dictionary containing array fields.
    """
    user_id = user.get("id")

    # Process each configured child table
    for array_field, table_name in __CHILD_TABLES.items():
        array_data = user.get(array_field, [])
        for item in array_data:
            # Add user_id as foreign key and flatten the record
            item_record = flatten_record(item)
            item_record["user_id"] = user_id

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=item_record)


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
