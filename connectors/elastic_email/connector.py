"""Elastic Email Connector for Fivetran Connector SDK.
This connector demonstrates how to fetch email marketing data from Elastic Email API and sync it to destination.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For making HTTP requests to the Elastic Email API
import requests

# For retry delays
import time

# For type hints
from typing import Optional

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Constants
__BASE_URL = "https://api.elasticemail.com/v4"
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__PAGE_LIMIT = 100
__CHECKPOINT_INTERVAL = 500

# Endpoint configuration for all tables
__ENDPOINTS = {
    "campaign": {
        "endpoint": "/campaigns",
        "state_key": "",
        "date_field": "",
        "extra_params": None,
    },
    "contact": {"endpoint": "/contacts", "state_key": "", "date_field": "", "extra_params": None},
    "list": {"endpoint": "/lists", "state_key": "", "date_field": "", "extra_params": None},
    "segment": {"endpoint": "/segments", "state_key": "", "date_field": "", "extra_params": None},
    "template": {
        "endpoint": "/templates",
        "state_key": "",
        "date_field": "",
        "extra_params": {"scopeType": "Personal"},
    },
    "event": {
        "endpoint": "/events",
        "state_key": "last_event_date",
        "date_field": "EventDate",
        "extra_params": None,
    },
    "campaign_statistic": {
        "endpoint": "/statistics/campaigns",
        "state_key": "",
        "date_field": "",
        "extra_params": None,
    },
    "file": {"endpoint": "/files", "state_key": "", "date_field": "", "extra_params": None},
    "domain": {"endpoint": "/domains", "state_key": "", "date_field": "", "extra_params": None},
    "suppression": {
        "endpoint": "/suppressions",
        "state_key": "",
        "date_field": "",
        "extra_params": None,
    },
    "bounce": {
        "endpoint": "/suppressions/bounces",
        "state_key": "",
        "date_field": "",
        "extra_params": None,
    },
    "complaint": {
        "endpoint": "/suppressions/complaints",
        "state_key": "",
        "date_field": "",
        "extra_params": None,
    },
    "unsubscribe": {
        "endpoint": "/suppressions/unsubscribes",
        "state_key": "",
        "date_field": "",
        "extra_params": None,
    },
}


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary
    configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def build_headers(api_key: str) -> dict:
    """
    Build HTTP headers for Elastic Email API requests.
    Args:
        api_key: The API key for authentication.
    Returns:
        Dictionary containing required headers including authentication.
    """
    return {"X-ElasticEmail-ApiKey": api_key, "Content-Type": "application/json"}


def make_request_with_retry(url: str, headers: dict, params: dict = None):
    """
    Make an API request with retry logic and exponential backoff.
    Args:
        url: The full URL to make the request to.
        headers: Dictionary of headers including authentication.
        params: Optional query parameters for the request.
    Returns:
        Response data as dictionary or list.
    Raises:
        RuntimeError: If the request fails after all retry attempts.
    """
    if params is None:
        params = {}

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=120)

            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 500, 502, 503, 504]:
                if attempt < __MAX_RETRIES - 1:
                    delay = __BASE_DELAY_SECONDS * (2**attempt)
                    log.warning(
                        f"Request failed with status {response.status_code}, retrying in {delay} seconds"
                    )
                    time.sleep(delay)
                    continue
                else:
                    raise RuntimeError(
                        f"API returned {response.status_code} after {__MAX_RETRIES} attempts"
                    )
            else:
                raise RuntimeError(
                    f"API request failed with status {response.status_code}: {response.text}"
                )

        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Request error, retrying in {delay} seconds")
                time.sleep(delay)
                continue
            else:
                raise RuntimeError(f"Request failed after {__MAX_RETRIES} attempts: {str(e)}")

    # This line should never be reached due to the exception handling above,
    # but is included for type safety and to avoid implicit None returns
    raise RuntimeError(f"Request failed after {__MAX_RETRIES} attempts")


def flatten_dict(record: dict, parent_key: str = "", separator: str = "_") -> dict:
    """
    Flatten a nested dictionary by concatenating keys with a separator.
    Args:
        record: The dictionary to flatten.
        parent_key: The parent key to prepend to child keys.
        separator: The separator to use between parent and child keys.
    Returns:
        Flattened dictionary with concatenated keys.
    """
    flattened = {}
    for key, value in record.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict):
            flattened.update(flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value
    return flattened


def process_paginated_endpoint(
    api_key: str,
    endpoint: str,
    table_name: str,
    state: dict,
    state_key: str = "",
    date_field: str = "",
    extra_params: Optional[dict] = None,
):
    """
    Process a paginated API endpoint and sync data to destination.
    Args:
        api_key: The API key for authentication.
        endpoint: The API endpoint path.
        table_name: The destination table name.
        state: The state dictionary to track sync progress.
        state_key: Optional state key for incremental sync.
        date_field: Optional date field for tracking max date.
        extra_params: Optional extra parameters to add to requests.
    """
    headers = build_headers(api_key)
    offset = 0
    record_count = 0
    max_date_value = state.get(state_key) if state_key else None
    current_max_date = max_date_value

    log.info(f"Starting {table_name} sync")

    try:
        while True:
            url = f"{__BASE_URL}{endpoint}"
            params: dict = {"limit": __PAGE_LIMIT, "offset": offset}

            if state_key and current_max_date and isinstance(current_max_date, str):
                params["from"] = current_max_date

            if extra_params is not None:
                params.update(extra_params)

            data = make_request_with_retry(url, headers, params)

            if not data or len(data) == 0:
                break

            for record in data:
                flattened = flatten_dict(record)

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table=table_name, data=flattened)
                record_count += 1

                if date_field and date_field in record:
                    record_date = record[date_field]
                    if not current_max_date or record_date > current_max_date:
                        current_max_date = record_date

            offset += __PAGE_LIMIT

            if record_count % __CHECKPOINT_INTERVAL == 0:
                if state_key and current_max_date:
                    state[state_key] = current_max_date
                log.info(f"{table_name} sync progress: {record_count} records processed")
                # Save the progress by checkpointing the state. This is important for ensuring that the sync
                # process can resume from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)

            if len(data) < __PAGE_LIMIT:
                break

        if state_key and current_max_date:
            state[state_key] = current_max_date

        log.info(f"Completed {table_name} sync. Total records synced: {record_count}")

    except RuntimeError as e:
        if "Access Denied" in str(e) or "400" in str(e):
            log.warning(f"Skipping {table_name} sync - insufficient permissions: {str(e)}")
        else:
            raise


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "campaign", "primary_key": ["name"]},
        {"table": "contact", "primary_key": ["email"]},
        {"table": "list", "primary_key": ["listName"]},
        {"table": "segment", "primary_key": ["name"]},
        {"table": "template", "primary_key": ["name"]},
        {"table": "event", "primary_key": ["transactionID"]},
        {"table": "campaign_statistic", "primary_key": ["name"]},
        {"table": "file", "primary_key": ["name"]},
        {"table": "domain", "primary_key": ["domain"]},
        {"table": "suppression", "primary_key": ["email"]},
        {"table": "bounce", "primary_key": ["email"]},
        {"table": "complaint", "primary_key": ["email"]},
        {"table": "unsubscribe", "primary_key": ["email"]},
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
    log.warning("Example: Source Connector : Elastic Email Connector")

    validate_configuration(configuration)

    api_key = configuration.get("api_key")

    try:
        # Iterate through all endpoints and sync data
        for table_name, config in __ENDPOINTS.items():
            process_paginated_endpoint(
                api_key=api_key,
                endpoint=config["endpoint"],
                table_name=table_name,
                state=state,
                state_key=config["state_key"],
                date_field=config["date_field"],
                extra_params=config["extra_params"],
            )

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process
        # can resume from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        log.info("Sync completed successfully")

    except Exception as e:
        log.error(f"Sync failed with error: {str(e)}")
        raise RuntimeError(f"Failed to sync data: {str(e)}")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE
# 'run' button. This is useful for debugging while you write your code. Note this method is not called by Fivetran
# when executing your connector in production. Please test using the Fivetran debug command prior to finalizing
# and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
