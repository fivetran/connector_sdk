"""Rillet Connector for Fivetran Connector SDK.

This connector fetches frequently used resources from the Rillet API and upserts
records into destination tables. It uses keyset pagination, incremental sync,
and checkpointing to handle large datasets safely.

See https://docs.api.rillet.com/docs/getting-started
and https://docs.api.rillet.com/docs/webhooks
"""

import json  # For loading connector configuration when running locally in the __main__ block
import time  # For implementing sleep-based exponential backoff between retry attempts
from typing import (
    Dict,
)  # For type annotations on configuration, state, and helper function arguments/returns

import requests  # For making HTTP requests to the Rillet API endpoints
from fivetran_connector_sdk import (
    Connector,
)  # For initializing the connector entry point used by Fivetran
from fivetran_connector_sdk import (
    Logging as log,
)  # For emitting structured logs within the Fivetran Connector SDK runtime
from fivetran_connector_sdk import (
    Operations as op,
)  # For performing data operations such as upsert and checkpoint
from sync_collections import (
    SYNC_COLLECTIONS,
)  # For the list of collections to sync, including endpoint and table metadata

__DEFAULT_BASE_URL = "https://api.rillet.com"
__DEFAULT_API_VERSION = "3"
__MAX_RETRIES = 8
__BACKOFF_BASE = 2
__PAGE_LIMIT = 100
__CHECKPOINT_INTERVAL = 200
__REQUEST_TIMEOUT_SECONDS = 60


def validate_configuration(configuration: Dict):
    """
    Validates the connector configuration for required and optional fields.

    Required Keys:
        - api_key (str): The API key for authenticating with the Rillet API. Must be a non-empty string.

    Optional Keys:
        - base_url (str): The base URL for the Rillet API. Defaults to 'https://api.rillet.com' if not provided.
        - api_version (str|int): The Rillet API version. Defaults to '3' if not provided.

    Validation Logic:
        - Ensures all required keys are present and non-empty.
        - Validates that 'base_url' is a non-empty string if provided.
        - Validates that 'api_version' is a non-empty string or integer if provided.

    Raises:
        ValueError: If any required key is missing or empty, or if optional keys are of incorrect type or empty.
    """
    required_keys = ["api_key"]
    for key in required_keys:
        if key not in configuration or not configuration.get(key):
            raise ValueError(f"Missing required configuration value: {key}")

    base_url = configuration.get("base_url", __DEFAULT_BASE_URL)
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url must be a non-empty string")

    api_version = configuration.get("api_version", __DEFAULT_API_VERSION)
    if not isinstance(api_version, (str, int)) or not str(api_version).strip():
        raise ValueError("api_version must be a non-empty string or number")


def schema(configuration: Dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": collection["table"], "primary_key": ["id"]} for collection in SYNC_COLLECTIONS
    ]


def _make_headers(configuration: Dict) -> Dict:
    """
    Build the HTTP headers required for Rillet API requests.
    Args:
        configuration: A dictionary containing connector configuration values, including the API key and optional API version.
    Returns:
        A dictionary of HTTP headers to include with each Rillet API request.
    Behavior:
        - Constructs the 'Authorization' header using the provided API key.
        - Sets the 'accept' header to 'application/json' to specify the expected response format
        - Includes the 'X-Rillet-API-Version' header based on the provided API version in the configuration, or defaults to a predefined version if not specified.
    """
    return {
        "Authorization": f"Bearer {configuration['api_key']}",
        "accept": "application/json",
        "X-Rillet-API-Version": str(configuration.get("api_version", __DEFAULT_API_VERSION)),
    }


def _make_request(url: str, headers: Dict, params: Dict, optional: bool = False):
    """
    Makes a GET request to the specified URL with the provided headers and parameters, handling retries, rate limiting, and server errors.

    Args:
        url (str): The endpoint URL to request.
        headers (dict): HTTP headers to include in the request.
        params (dict): Query parameters for the request.
        optional (bool): If True, treat 404 as non-fatal and return None.

    Returns:
        dict or None: The parsed JSON response if successful, or None if the endpoint is optional and returns 404.

    Raises:
        RuntimeError: If the request fails after maximum retries or encounters a non-recoverable error.
    """
    last_exception = None
    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )

            if response.status_code == 429:
                last_exception = RuntimeError(
                    f"Rate limit error {response.status_code}: {response.text}"
                )
                if attempt == __MAX_RETRIES:
                    raise last_exception
                retry_after_header = response.headers.get("Retry-After")
                retry_after_seconds = None
                if retry_after_header is not None:
                    try:
                        retry_after_seconds = int(retry_after_header)
                        if retry_after_seconds < 0:
                            retry_after_seconds = None
                    except ValueError:
                        retry_after_seconds = None
                base_backoff = __BACKOFF_BASE**attempt
                if retry_after_seconds is not None:
                    sleep_seconds = max(retry_after_seconds, base_backoff)
                else:
                    sleep_seconds = base_backoff
                log.warning(f"Rate limit received, sleeping {sleep_seconds}s (attempt {attempt})")
                time.sleep(sleep_seconds)
                continue

            if 500 <= response.status_code < 600:
                sleep_seconds = __BACKOFF_BASE**attempt
                log.warning(
                    f"Server error {response.status_code}. Retry in {sleep_seconds}s (attempt {attempt})"
                )
                last_exception = RuntimeError(
                    f"Server error {response.status_code}: {response.text}"
                )
                time.sleep(sleep_seconds)
                continue

            if 400 <= response.status_code < 500:
                if optional and response.status_code == 404:
                    log.warning(f"Optional endpoint returned 404, skipping: {url}")
                    return None
                # Fail fast for client errors that require config or request changes
                response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            last_exception = e
            if attempt == __MAX_RETRIES:
                raise RuntimeError(f"Failed to request {url}: {e}")
            sleep_seconds = __BACKOFF_BASE**attempt
            log.warning(f"Request exception: {e}. Retry in {sleep_seconds}s (attempt {attempt})")
            time.sleep(sleep_seconds)

    # Ensure last_exception is set before raising to avoid chaining None
    if last_exception is None:
        last_exception = RuntimeError(
            f"Failed to get API response for {url} after {__MAX_RETRIES} attempts"
        )
    raise RuntimeError(f"Failed to get API response for {url}") from last_exception


def _get_collection_items(
    configuration: Dict,
    endpoint: str,
    response_key: str,
    table_name: str,
    cursor_key: str,
    state: Dict,
    last_updated_key: str,
    supports_pagination: bool,
    supports_updated_gt: bool,
    optional: bool = False,
):
    """Fetch records from one endpoint with optional pagination and incremental updates."""
    base_url = configuration.get("base_url", __DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}{endpoint}"
    headers = _make_headers(configuration)

    cursor = state.get(cursor_key) if supports_pagination else None
    last_synced_at = state.get(last_updated_key) if supports_updated_gt else None
    retrieved = 0
    highest_updated = last_synced_at

    while True:
        params = {}
        if supports_pagination:
            params["limit"] = __PAGE_LIMIT
            if cursor:
                params["cursor"] = cursor
        if supports_updated_gt and not cursor and last_synced_at:
            params["updated.gt"] = last_synced_at

        log.info(
            f"Fetching {endpoint} table={table_name} cursor={cursor} updated.gt={last_synced_at}"
        )
        payload = _make_request(url=url, headers=headers, params=params, optional=optional)

        if payload is None:
            log.info(f"Skipping optional endpoint because it is not available: {endpoint}")
            return
        if not payload:
            break

        items = payload.get(response_key) if isinstance(payload, dict) else None
        if items is None:
            raise RuntimeError(
                f"Unexpected response shape for {endpoint}: missing '{response_key}'"
            )

        if not isinstance(items, list) or len(items) == 0:
            break

        for item in items:
            updated_at = item.get("updated_at") or item.get("created_at")
            if last_synced_at and updated_at and updated_at <= last_synced_at:
                continue

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=table_name, data=item)
            retrieved += 1

            if updated_at and (highest_updated is None or updated_at > highest_updated):
                highest_updated = updated_at

            if retrieved % __CHECKPOINT_INTERVAL == 0:
                if supports_pagination:
                    state[cursor_key] = cursor
                if supports_updated_gt and highest_updated:
                    state[last_updated_key] = highest_updated
                op.checkpoint(state)

        if not supports_pagination:
            break

        pagination = payload.get("pagination", {})
        next_cursor = pagination.get("next_cursor")
        if not next_cursor:
            # No further pages; clear the cursor so we do not persist a stale pagination token.
            cursor = None
            break
        cursor = next_cursor
    if supports_pagination:
        if cursor:
            # Persist the cursor only when there is a valid next page token.
            state[cursor_key] = cursor
        else:
            # Remove any previous cursor so that the next run falls back to updated.gt.
            state.pop(cursor_key, None)
    if supports_updated_gt and highest_updated:
        state[last_updated_key] = highest_updated

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)
    log.info(f"Fetched {retrieved} records for {endpoint}")


def update(configuration: Dict, state: Dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Connectors : Rillet API Connector")

    validate_configuration(configuration)

    try:
        for item in SYNC_COLLECTIONS:
            _get_collection_items(
                configuration=configuration,
                endpoint=item["endpoint"],
                response_key=item["response_key"],
                table_name=item["table"],
                cursor_key=item["cursor_key"],
                state=state,
                last_updated_key=item["last_updated_key"],
                supports_pagination=item["supports_pagination"],
                supports_updated_gt=item["supports_updated_gt"],
                optional=item.get("optional", False),
            )

    except Exception as e:
        log.error(f"Failed to sync Rillet data: {e}")
        raise


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
