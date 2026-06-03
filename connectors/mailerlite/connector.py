"""MailerLite Connector for Fivetran - fetches subscriber, group, campaign, and field data from MailerLite API.
This connector demonstrates how to fetch data from MailerLite REST API and upsert it into destination using the Fivetran Connector SDK.
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

# For making HTTP requests to MailerLite API
import requests

# For handling time operations and timestamps
import time
from datetime import datetime

# For type hints to support optional function parameters
from typing import Optional

__BASE_URL = "https://connect.mailerlite.com/api"
__PAGINATION_LIMIT = 100
__REQUEST_TIMEOUT_IN_SECONDS = 30
__MAX_RETRIES = 5
__BACKOFF_BASE = 1
__CHECKPOINT_INTERVAL = 50


def iso_to_timestamp(iso_string: str) -> int:
    """
    Convert ISO 8601 timestamp string to milliseconds since epoch.
    Args:
        iso_string: ISO 8601 formatted timestamp string (e.g., '2025-10-27 18:16:07')
    Returns:
        Milliseconds since epoch as integer
    """
    try:
        dt = datetime.strptime(iso_string, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp() * 1000)
    except (ValueError, AttributeError):
        return 0


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def flatten_dict(data: dict, prefix: str = "", separator: str = "_") -> dict:
    """
    Flatten a nested dictionary by concatenating keys with a separator.
    This is used to convert nested JSON responses into flat table structures.
    Args:
        data: The dictionary to flatten
        prefix: Prefix to add to keys (used for recursion)
        separator: Separator to use between nested keys
    Returns:
        A flattened dictionary
    """
    flattened = {}

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            flattened.update(flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


def make_api_request(url: str, headers: dict, params: Optional[dict] = None) -> dict:
    """
    Make an HTTP GET request to the MailerLite API with error handling and exponential backoff retry logic.
    Args:
        url: The API endpoint URL
        headers: HTTP headers for the request
        params: Optional query parameters
    Returns:
        The JSON response from the API
    Raises:
        requests.exceptions.RequestException: For HTTP errors
        ValueError: For invalid JSON responses
    """
    params = params or {}

    for attempt in range(__MAX_RETRIES):
        response = None
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_IN_SECONDS
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if attempt < __MAX_RETRIES - 1:
                delay = __BACKOFF_BASE * (2**attempt)
                log.warning(f"Request timeout for URL: {url}. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            log.error(f"Request timeout for URL: {url}")
            raise
        except requests.exceptions.HTTPError as e:
            is_retryable_error = response and (
                response.status_code == 429 or response.status_code >= 500
            )
            should_retry = is_retryable_error and attempt < __MAX_RETRIES - 1
            if should_retry:
                delay = __BACKOFF_BASE * (2**attempt)
                log.warning(
                    f"Rate limit or server error for URL: {url}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
                continue
            log.error(f"HTTP error for URL: {url}: {e}")
            raise
        except (requests.exceptions.RequestException, ValueError) as e:
            log.error(f"Request failed for URL: {url}: {e}")
            raise

    raise requests.exceptions.RequestException(
        f"Request failed for URL: {url} after {__MAX_RETRIES} attempts"
    )


def should_sync_record(record: dict, last_sync_timestamp: Optional[int]) -> bool:
    """
    Determine if a record should be synced based on its updated_at timestamp.
    Args:
        record: The record to check
        last_sync_timestamp: The timestamp of the last sync (None if first sync)
    Returns:
        True if the record should be synced, False otherwise
    """
    if not last_sync_timestamp:
        return True

    updated_at_str = record.get("updated_at")
    if not updated_at_str:
        return True

    updated_at_ts = iso_to_timestamp(updated_at_str)
    return updated_at_ts > last_sync_timestamp


def update_max_timestamp(record: dict, current_max: Optional[int]) -> Optional[int]:
    """
    Update the maximum updated_at timestamp from a record.
    Args:
        record: The record to check
        current_max: The current maximum timestamp (None if no max yet)
    Returns:
        The updated maximum timestamp
    """
    updated_at_str = record.get("updated_at")
    if not updated_at_str:
        return current_max

    updated_at_ts = iso_to_timestamp(updated_at_str)
    if not current_max or updated_at_ts > current_max:
        return updated_at_ts

    return current_max


def update_pagination_params(params: dict, pagination_type: str, page: int, cursor: Optional[str]):
    """
    Update pagination parameters based on pagination type.
    Args:
        params: The request parameters dictionary to update
        pagination_type: Type of pagination ('page' or 'cursor')
        page: Current page number (for page-based pagination)
        cursor: Current cursor value (for cursor-based pagination)
    """
    if pagination_type == "page":
        params["page"] = page
    elif pagination_type == "cursor" and cursor:
        params["cursor"] = cursor


def has_more_pages(response_data: dict, pagination_type: str) -> tuple[bool, Optional[str]]:
    """
    Check if there are more pages to fetch and return the next cursor if applicable.
    Args:
        response_data: The API response data
        pagination_type: Type of pagination ('page' or 'cursor')
    Returns:
        Tuple of (has_more_pages, next_cursor)
    """
    if pagination_type == "page":
        links = response_data.get("links", {})
        return bool(links.get("next")), None
    elif pagination_type == "cursor":
        meta = response_data.get("meta", {})
        next_cursor = meta.get("next_cursor")
        return bool(next_cursor), next_cursor

    return False, None


def process_and_upsert_record(
    record: dict,
    table_name: str,
    last_sync_timestamp: Optional[int],
    enable_incremental: bool,
    max_updated_at: Optional[int],
) -> tuple[bool, Optional[int]]:
    """
    Process a single record and upsert it if it should be synced.
    Args:
        record: The record to process
        table_name: The destination table name
        last_sync_timestamp: The timestamp of the last sync
        enable_incremental: Whether incremental sync is enabled
        max_updated_at: The current maximum updated_at timestamp
    Returns:
        Tuple of (should_count_as_synced, updated_max_timestamp)
    """
    # Handle incremental sync filtering if enabled
    if enable_incremental and not should_sync_record(record, last_sync_timestamp):
        return False, max_updated_at

    # Update max timestamp for incremental sync
    if enable_incremental:
        max_updated_at = update_max_timestamp(record, max_updated_at)

    flattened_record = flatten_dict(record)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table_name, data=flattened_record)
    return True, max_updated_at


def checkpoint_if_needed(
    records_synced: int,
    table_name: str,
    state: dict,
    enable_incremental: bool,
    max_updated_at: Optional[int],
):
    """
    Checkpoint state at regular intervals.
    Args:
        records_synced: Number of records synced so far
        table_name: The destination table name
        state: Current state dictionary
        enable_incremental: Whether incremental sync is enabled
        max_updated_at: The current maximum updated_at timestamp
    """
    if records_synced % __CHECKPOINT_INTERVAL == 0 and records_synced > 0:
        state[f"{table_name}_synced"] = records_synced
        if enable_incremental and max_updated_at:
            state[f"max_{table_name}_updated_at"] = max_updated_at

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)


def update_pagination_state(
    pagination_type: str, page: int, cursor: Optional[str], next_cursor: Optional[str]
) -> tuple[int, Optional[str]]:
    """
    Update pagination state for the next iteration.
    Args:
        pagination_type: Type of pagination ('page' or 'cursor')
        page: Current page number
        cursor: Current cursor value
        next_cursor: Next cursor value from response
    Returns:
        Tuple of (updated_page, updated_cursor)
    """
    if pagination_type == "page":
        return page + 1, cursor
    elif pagination_type == "cursor":
        return page, next_cursor
    return page, cursor


def sync_paginated_data(
    url: str,
    headers: dict,
    table_name: str,
    state: dict,
    pagination_type: str = "page",
    enable_incremental: bool = False,
) -> int:
    """
    Generic function to sync paginated data from MailerLite API with optional incremental sync.
    Args:
        url: The API endpoint URL
        headers: HTTP headers for the request
        table_name: The destination table name
        state: Current state dictionary for tracking sync progress
        pagination_type: Type of pagination ('page' or 'cursor')
        enable_incremental: Whether to enable incremental sync filtering
    Returns:
        Number of records synced
    """
    log.info(f"Starting {table_name} sync")

    params = {"limit": __PAGINATION_LIMIT}
    records_synced = 0
    records_skipped = 0
    page = 1
    cursor = None

    last_sync_timestamp = state.get("last_sync_timestamp") if enable_incremental else None
    max_updated_at = state.get(f"max_{table_name}_updated_at")

    if last_sync_timestamp and enable_incremental:
        log.info(f"Incremental sync - fetching {table_name} updated after {last_sync_timestamp}")

    while True:
        update_pagination_params(params, pagination_type, page, cursor)

        try:
            response_data = make_api_request(url, headers, params)
            records = response_data.get("data", [])

            if not records:
                break

            for record in records:
                was_synced, max_updated_at = process_and_upsert_record(
                    record, table_name, last_sync_timestamp, enable_incremental, max_updated_at
                )
                if was_synced:
                    records_synced += 1
                else:
                    records_skipped += 1

            checkpoint_if_needed(
                records_synced, table_name, state, enable_incremental, max_updated_at
            )

            # Handle pagination continuation
            has_more, next_cursor = has_more_pages(response_data, pagination_type)
            if not has_more:
                break

            page, cursor = update_pagination_state(pagination_type, page, cursor, next_cursor)

        except requests.RequestException as e:
            log.error(f"API request error syncing {table_name}: {e}")
            raise

    if enable_incremental:
        log.info(
            f"Synced {records_synced} {table_name}, skipped {records_skipped} unchanged records"
        )
    else:
        log.info(f"Synced {records_synced} {table_name}")

    return records_synced


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
            "table": "subscriber",
            "primary_key": ["id"],
        },
        {
            "table": "group",
            "primary_key": ["id"],
        },
        {
            "table": "group_subscriber",
            "primary_key": ["group_id", "subscriber_id"],
        },
        {
            "table": "field",
            "primary_key": ["id"],
        },
        {
            "table": "campaign",
            "primary_key": ["id"],
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
    log.warning("Example: API Connector : MailerLite Connector")

    validate_configuration(configuration=configuration)

    api_key = configuration.get("api_key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    current_sync_timestamp = int(time.time() * 1000)

    try:
        # Sync custom fields
        sync_paginated_data(
            url=f"{__BASE_URL}/fields",
            headers=headers,
            table_name="field",
            state=state,
            pagination_type="page",
            enable_incremental=False,
        )

        # Sync groups
        sync_groups(headers, state)

        # Sync subscribers with incremental sync
        sync_paginated_data(
            url=f"{__BASE_URL}/subscribers",
            headers=headers,
            table_name="subscriber",
            state=state,
            pagination_type="cursor",
            enable_incremental=True,
        )

        # Sync campaigns with incremental sync
        sync_paginated_data(
            url=f"{__BASE_URL}/campaigns",
            headers=headers,
            table_name="campaign",
            state=state,
            pagination_type="page",
            enable_incremental=True,
        )

        # Save final state with updated timestamps
        new_state = {
            "last_sync_timestamp": current_sync_timestamp,
            "max_subscriber_updated_at": state.get("max_subscriber_updated_at"),
            "max_campaign_updated_at": state.get("max_campaign_updated_at"),
        }

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(new_state)

    except requests.exceptions.RequestException as e:
        log.error(f"Network/API error during sync: {e}")
        raise
    except ValueError as e:
        log.error(f"Value error during sync: {e}")
        raise
    except Exception as e:
        log.error(f"Unexpected error during sync: {e}")
        raise


def sync_groups(headers: dict, state: dict):
    """
    Fetch and sync groups data from MailerLite API.
    Args:
        headers: HTTP headers including authorization
        state: Current state dictionary for tracking sync progress
    """
    log.info("Starting groups sync")

    url = f"{__BASE_URL}/groups"
    params = {"limit": __PAGINATION_LIMIT}

    groups_synced = 0
    page = 1

    while True:
        params["page"] = page

        try:
            response_data = make_api_request(url, headers, params)
            groups = response_data.get("data", [])

            if not groups:
                break

            for group in groups:
                flattened_group = flatten_dict(group)

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="group", data=flattened_group)
                groups_synced += 1

                sync_group_subscribers(headers, group["id"])

            if groups_synced % __CHECKPOINT_INTERVAL == 0:
                state["groups_synced"] = groups_synced

                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)

            links = response_data.get("links", {})
            if not links.get("next"):
                break

            page += 1

        except requests.exceptions.RequestException as e:
            log.error(f"Error syncing groups: {e}")
            raise

    log.info(f"Synced {groups_synced} groups")


def sync_group_subscribers(headers: dict, group_id: str):
    """
    Fetch and sync group subscribers relationship data from MailerLite API.
    Args:
        headers: HTTP headers including authorization
        group_id: The group ID to fetch subscribers for
    """
    url = f"{__BASE_URL}/groups/{group_id}/subscribers"
    params = {"limit": __PAGINATION_LIMIT}

    cursor = None
    group_subscribers_synced = 0

    while True:
        if cursor:
            params["cursor"] = cursor

        try:
            response_data = make_api_request(url, headers, params)
            subscribers = response_data.get("data", [])

            if not subscribers:
                break

            for subscriber in subscribers:
                group_subscriber_data = {
                    "group_id": group_id,
                    "subscriber_id": subscriber.get("id"),
                }

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="group_subscriber", data=group_subscriber_data)
                group_subscribers_synced += 1

            meta = response_data.get("meta", {})
            cursor = meta.get("next_cursor")

            if not cursor:
                break

        except requests.exceptions.RequestException as e:
            log.error(f"Network/API error syncing group subscribers for group {group_id}: {e}")
            raise
        except (ValueError, TypeError) as e:
            log.error(f"Data parsing error syncing group subscribers for group {group_id}: {e}")
            raise

    log.info(f"Synced {group_subscribers_synced} subscribers for group {group_id}")


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
