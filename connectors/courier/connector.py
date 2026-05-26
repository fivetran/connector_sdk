"""Courier API Connector for Fivetran Connector SDK.
This connector fetches data from Courier API endpoints including messages,
audiences, brands, audit events, lists, and notifications.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for details
"""

# For reading configuration from a JSON file
import json

# For implementing retry logic with exponential backoff
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete()
# and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP API requests to Courier API
import requests

# Maximum number of retry attempts for API requests
__MAX_RETRIES = 3

# Base delay in seconds for exponential backoff retry strategy
__BASE_DELAY_SECONDS = 1

# Base URL for Courier API
__BASE_URL = "https://api.courier.com"

# Number of records to process before checkpointing state
__CHECKPOINT_INTERVAL = 100


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required
    parameters.
    This function is called at the start of the update method to ensure that
    the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for
            the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def get_headers(api_key: str):
    """
    Construct HTTP headers for Courier API requests.
    Args:
        api_key: The API key for authentication.
    Returns:
        Dictionary containing HTTP headers with authorization token.
    """
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def make_api_request(url: str, headers: dict):
    """
    Make an API request with retry logic and exponential backoff.
    Args:
        url: The full URL to make the request to.
        headers: Dictionary containing HTTP headers.
    Returns:
        Parsed JSON response from the API.
    Raises:
        RuntimeError: If the API request fails after all retry attempts.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 500, 502, 503, 504]:
                if attempt < __MAX_RETRIES - 1:
                    delay = __BASE_DELAY_SECONDS * (2**attempt)
                    log.warning(
                        f"Request failed with status {response.status_code}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    log.error(
                        f"Failed to fetch data after {__MAX_RETRIES} attempts. Last status: {response.status_code} - {response.text}"
                    )
                    raise RuntimeError(
                        f"API returned {response.status_code} after {__MAX_RETRIES} attempts: {response.text}"
                    )
            else:
                log.error(
                    f"API request failed with status {response.status_code}: {response.text}"
                )
                raise RuntimeError(f"API returned {response.status_code}: {response.text}")

        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Network error occurred, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}"
                )
                time.sleep(delay)
                continue
            else:
                log.error(f"Network error after {__MAX_RETRIES} attempts", e)
                raise RuntimeError(f"Network error after {__MAX_RETRIES} attempts: {str(e)}")
    return None


def flatten_nested_object(obj: dict, parent_key: str = "", separator: str = "_"):
    """
    Flatten a nested dictionary into a single level dictionary.
    Arrays and complex nested structures are converted to JSON strings.
    Args:
        obj: The dictionary to flatten.
        parent_key: The parent key for nested objects.
        separator: The separator to use between nested keys.
    Returns:
        Flattened dictionary.
    """
    items = []
    for key, value in obj.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_nested_object(value, new_key, separator=separator).items())
        elif isinstance(value, list):
            # Convert lists/arrays to JSON string since Fivetran doesn't support list type
            items.append((new_key, json.dumps(value)))
        else:
            items.append((new_key, value))
    return dict(items)


def fetch_brands(api_key: str, state: dict):
    """
    Fetch brands from Courier API and upsert them into the destination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state with latest sync timestamp for brands.
    """
    url = f"{__BASE_URL}/brands"
    headers = get_headers(api_key)

    log.info("Fetching brands from Courier API")
    response_data = make_api_request(url, headers)

    results = response_data.get("results", [])
    log.info(f"Retrieved {len(results)} brands from API")

    latest_timestamp = state.get("brands_last_updated")
    record_count = 0
    skipped_count = 0

    for brand in results:
        brand_updated = brand.get("updated")

        # Skip records that haven't been updated since last sync (incremental sync logic)
        if latest_timestamp and brand_updated and brand_updated <= latest_timestamp:
            skipped_count += 1
            continue

        flattened_brand = flatten_nested_object(brand)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="brand", data=flattened_brand)

        record_count += 1
        if brand_updated and (latest_timestamp is None or brand_updated > latest_timestamp):
            latest_timestamp = brand_updated

        if record_count % __CHECKPOINT_INTERVAL == 0:
            state["brands_last_updated"] = latest_timestamp
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

    log.info(f"Upserted {record_count} brands, skipped {skipped_count} unchanged brands")

    # Always update and checkpoint after processing all records
    state["brands_last_updated"] = latest_timestamp
    if record_count % __CHECKPOINT_INTERVAL != 0:
        op.checkpoint(state)
    return state


def fetch_audiences(api_key: str, state: dict):
    """
    Fetch audiences from Courier API with cursor-based pagination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state with cursor position for audiences.
    """
    headers = get_headers(api_key)
    cursor = state.get("audiences_cursor")
    has_more = True
    record_count = 0

    log.info("Fetching audiences from Courier API")

    while has_more:
        url = f"{__BASE_URL}/audiences"
        if cursor:
            url = f"{url}?cursor={cursor}"

        response_data = make_api_request(url, headers)

        items = response_data.get("items", [])
        paging = response_data.get("paging", {})

        log.info(f"Retrieved {len(items)} audiences in current page")

        for audience in items:
            flattened_audience = flatten_nested_object(audience)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="audience", data=flattened_audience)

            record_count += 1

        cursor = paging.get("cursor")
        has_more = paging.get("more", False)

        state["audiences_cursor"] = cursor
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if not has_more:
            break

    log.info(f"Completed fetching {record_count} total audiences")
    state["audiences_cursor"] = None
    return state


def fetch_audit_events(api_key: str, state: dict):
    """
    Fetch audit events from Courier API with pagination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state with latest sync timestamp for audit events.
    """
    url = f"{__BASE_URL}/audit-events"
    headers = get_headers(api_key)

    log.info("Fetching audit events from Courier API")
    response_data = make_api_request(url, headers)

    results = response_data.get("results", [])
    log.info(f"Retrieved {len(results)} audit events from API")

    latest_timestamp = state.get("audit_events_last_timestamp")
    record_count = 0
    skipped_count = 0

    for event in results:
        event_timestamp = event.get("timestamp")

        # Skip records that haven't been updated since last sync (incremental sync logic)
        if latest_timestamp and event_timestamp and event_timestamp <= latest_timestamp:
            skipped_count += 1
            continue

        flattened_event = flatten_nested_object(event)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="audit_event", data=flattened_event)

        record_count += 1
        if event_timestamp and (latest_timestamp is None or event_timestamp > latest_timestamp):
            latest_timestamp = event_timestamp

        if record_count % __CHECKPOINT_INTERVAL == 0:
            state["audit_events_last_timestamp"] = latest_timestamp
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

    log.info(f"Upserted {record_count} audit events, skipped {skipped_count} unchanged events")

    # Always update and checkpoint after processing all records
    state["audit_events_last_timestamp"] = latest_timestamp
    if record_count % __CHECKPOINT_INTERVAL != 0:
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
    return state


def fetch_lists(api_key: str, state: dict):
    """
    Fetch lists from Courier API with cursor-based pagination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state with cursor position for lists.
    """
    headers = get_headers(api_key)
    cursor = state.get("lists_cursor")
    has_more = True
    record_count = 0

    log.info("Fetching lists from Courier API")

    while has_more:
        url = f"{__BASE_URL}/lists"
        if cursor:
            url = f"{url}?cursor={cursor}"

        response_data = make_api_request(url, headers)

        items = response_data.get("items", [])
        paging = response_data.get("paging", {})

        log.info(f"Retrieved {len(items)} lists in current page")

        for list_item in items:
            flattened_list = flatten_nested_object(list_item)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="list", data=flattened_list)

            record_count += 1

        cursor = paging.get("cursor")
        has_more = paging.get("more", False)

        state["lists_cursor"] = cursor
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if not has_more:
            break

    log.info(f"Completed fetching {record_count} total lists")
    state["lists_cursor"] = None
    return state


def fetch_messages(api_key: str, state: dict):
    """
    Fetch messages from Courier API with cursor-based pagination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state.
    """
    headers = get_headers(api_key)
    cursor = state.get("messages_cursor")
    has_more = True
    record_count = 0

    log.info("Fetching messages from Courier API")

    while has_more:
        url = f"{__BASE_URL}/messages"
        if cursor:
            url = f"{url}?cursor={cursor}"

        response_data = make_api_request(url, headers)

        results = response_data.get("results", [])
        paging = response_data.get("paging", {})

        log.info(f"Retrieved {len(results)} messages in current page")

        for message in results:
            flattened_message = flatten_nested_object(message)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="message", data=flattened_message)

            record_count += 1

        cursor = paging.get("cursor")
        has_more = paging.get("more", False)

        state["messages_cursor"] = cursor
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if not has_more:
            break

    log.info(f"Completed fetching {record_count} total messages")
    state["messages_cursor"] = None
    return state


def fetch_notifications(api_key: str, state: dict):
    """
    Fetch notifications from Courier API with cursor-based pagination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state.
    """
    headers = get_headers(api_key)
    cursor = state.get("notifications_cursor")
    has_more = True
    record_count = 0

    log.info("Fetching notifications from Courier API")

    while has_more:
        url = f"{__BASE_URL}/notifications"
        if cursor:
            url = f"{url}?cursor={cursor}"

        response_data = make_api_request(url, headers)

        results = response_data.get("results", [])
        paging = response_data.get("paging", {})

        log.info(f"Retrieved {len(results)} notifications in current page")

        for notification in results:
            flattened_notification = flatten_nested_object(notification)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="notification", data=flattened_notification)

            record_count += 1

        cursor = paging.get("cursor")
        has_more = paging.get("more", False)

        state["notifications_cursor"] = cursor
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if not has_more:
            break

    log.info(f"Completed fetching {record_count} total notifications")
    state["notifications_cursor"] = None
    return state


def fetch_tenants(api_key: str, state: dict):
    """
    Fetch tenants from Courier API with pagination.
    Args:
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    Returns:
        Updated state.
    """
    headers = get_headers(api_key)
    next_url = state.get("tenants_next_url")
    has_more = True
    record_count = 0

    log.info("Fetching tenants from Courier API")

    while has_more:
        if next_url:
            url = f"{__BASE_URL}{next_url}"
        else:
            url = f"{__BASE_URL}/tenants"

        response_data = make_api_request(url, headers)

        items = response_data.get("items", [])
        has_more = response_data.get("has_more", False)
        next_url = response_data.get("next_url")

        log.info(f"Retrieved {len(items)} tenants in current page")

        for tenant in items:
            flattened_tenant = flatten_nested_object(tenant)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="tenant", data=flattened_tenant)

            record_count += 1

        state["tenants_next_url"] = next_url
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if not has_more:
            break

    log.info(f"Completed fetching {record_count} total tenants")
    state["tenants_next_url"] = None
    return state


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "brand", "primary_key": ["id"]},
        {"table": "audience", "primary_key": ["id"]},
        {"table": "audit_event", "primary_key": ["auditEventId"]},
        {"table": "list", "primary_key": ["id"]},
        {"table": "message", "primary_key": ["id"]},
        {"table": "notification", "primary_key": ["id"]},
        {"table": "tenant", "primary_key": ["id"]},
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
    log.warning("Example: Source Connector: Courier API Connector")

    validate_configuration(configuration)

    api_key = configuration.get("api_key")

    state = fetch_brands(api_key, state)
    state = fetch_audiences(api_key, state)
    state = fetch_audit_events(api_key, state)
    state = fetch_lists(api_key, state)
    state = fetch_messages(api_key, state)
    state = fetch_notifications(api_key, state)
    state = fetch_tenants(api_key, state)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info("Completed sync for all Courier API endpoints")


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
