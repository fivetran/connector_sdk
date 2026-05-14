"""Prometheus Time-Series Database Connector for Fivetran Connector SDK.
This connector demonstrates how to sync metrics and time-series data from Prometheus monitoring system.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from JSON file
import json

# For handling datetime operations and timezone conversions
from datetime import datetime, timezone, timedelta

# For type hints in function signatures
from typing import Any

# For base64 encoding in basic authentication
import base64

# For generating series IDs from metric names and labels
import hashlib

# For retry delays and backoff logic
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling logs in connector code
from fivetran_connector_sdk import Logging as log

# For supporting data operations like upsert and checkpoint
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to Prometheus API (provided by SDK runtime)
import requests

# Batch size for checkpointing during large metric syncs
__CHECKPOINT_BATCH_SIZE = 1000

# Query step duration for range queries (15 seconds)
__QUERY_STEP_SECONDS = 15

# Maximum retries for API requests
__MAX_RETRIES = 3

# Base delay in seconds for exponential backoff
__BASE_DELAY_SECONDS = 1

# Timeout for API requests in seconds
__REQUEST_TIMEOUT_SECONDS = 30

# Default lookback period in hours for initial sync
__DEFAULT_LOOKBACK_HOURS = 24


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_fields = ["prometheus_url"]
    missing_fields = [field for field in required_fields if not configuration.get(field)]

    if missing_fields:
        raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")

    auth_type = configuration.get("auth_type", "none")
    valid_auth_types = ["none", "basic", "bearer"]
    if auth_type not in valid_auth_types:
        raise ValueError(
            f"Invalid auth_type: {auth_type}. Valid values: {', '.join(valid_auth_types)}"
        )

    if "lookback_hours" in configuration:
        lookback_hours_str = configuration["lookback_hours"]
        try:
            lookback_hours = int(lookback_hours_str)
            if lookback_hours <= 0:
                raise ValueError(
                    f"lookback_hours must be a positive integer, got: {lookback_hours}"
                )
        except ValueError:
            raise ValueError(f"lookback_hours must be a valid integer, got: {lookback_hours_str}")


def schema(configuration: dict) -> list[dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "metrics",
            "primary_key": ["metric_name"],
            "columns": {
                "metric_name": "STRING",
                "metric_type": "STRING",
                "help_text": "STRING",
            },
        },
        {
            "table": "time_series",
            "primary_key": ["series_id", "timestamp"],
            "columns": {
                "series_id": "STRING",
                "metric_name": "STRING",
                "labels": "JSON",
                "timestamp": "UTC_DATETIME",
                "value": "DOUBLE",
            },
        },
    ]


def build_prometheus_url(base_url: str, endpoint: str) -> str:
    """
    Build complete Prometheus API URL.
    Args:
        base_url: Base URL of Prometheus server.
        endpoint: API endpoint path.
    Returns:
        Complete URL string.
    """
    base_url = base_url.rstrip("/")
    endpoint = endpoint.lstrip("/")
    return f"{base_url}/{endpoint}"


def get_auth_headers(configuration: dict) -> dict:
    """
    Build authentication headers from configuration.
    Args:
        configuration: Configuration dictionary with optional auth settings.
    Returns:
        Dictionary of HTTP headers for authentication.
    """
    headers = {}

    auth_type = configuration.get("auth_type", "none")

    if auth_type == "basic":
        username = configuration.get("username", "")
        password = configuration.get("password", "")
        if username and password:
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

    elif auth_type == "bearer":
        token = configuration.get("bearer_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    return headers


def handle_retry_with_backoff(attempt: int, error_message: str) -> None:
    """
    Handle retry logic with exponential backoff.
    Args:
        attempt: Current attempt number.
        error_message: Error message to log.
    Raises:
        RuntimeError: If max retries reached.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{error_message}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{error_message} after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{error_message} after {__MAX_RETRIES} attempts")


def handle_response_status(response, attempt: int) -> dict:
    """
    Handle HTTP response status codes.
    Args:
        response: HTTP response object.
        attempt: Current attempt number.
    Returns:
        JSON response as dictionary if successful.
    Raises:
        RuntimeError: If response indicates failure.
    """
    if response.status_code == 200:
        return response.json()

    if response.status_code in [429, 500, 502, 503, 504]:
        error_message = f"Request failed with status {response.status_code}"
        handle_retry_with_backoff(attempt, error_message)
        return None

    log.error(f"API request failed with status {response.status_code}: {response.text}")
    raise RuntimeError(f"API request failed with status {response.status_code}: {response.text}")


def make_api_request(url: str, headers: dict, params: dict | None = None) -> dict:
    """
    Make HTTP request to Prometheus API with retry logic.
    Args:
        url: Complete API URL.
        headers: HTTP headers including authentication.
        params: Query parameters.
    Returns:
        JSON response as dictionary.
    Raises:
        RuntimeError: If request fails after all retries.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )
            result = handle_response_status(response, attempt)
            if result is not None:
                return result

        except requests.Timeout:
            handle_retry_with_backoff(attempt, "Request timeout")

        except requests.RequestException as e:
            log.error(f"Request failed: {str(e)}")
            raise RuntimeError(f"Request failed: {str(e)}")

    raise RuntimeError("Failed to complete API request")


def fetch_metric_names(prometheus_url: str, headers: dict) -> list[str]:
    """
    Fetch all available metric names from Prometheus.
    Args:
        prometheus_url: Base URL of Prometheus server.
        headers: Authentication headers.
    Returns:
        List of metric names.
    """
    url = build_prometheus_url(prometheus_url, "/api/v1/label/__name__/values")
    response_data = make_api_request(url, headers)

    if response_data.get("status") != "success":
        log.error(f"Failed to fetch metric names: {response_data}")
        raise RuntimeError(f"Failed to fetch metric names: {response_data}")

    metric_names = response_data.get("data", [])
    log.info(f"Fetched {len(metric_names)} metric names from Prometheus")
    return metric_names


def sync_metrics_metadata(prometheus_url: str, headers: dict) -> None:
    """
    Sync metrics metadata to the metrics table.
    Args:
        prometheus_url: Base URL of Prometheus server.
        headers: Authentication headers.
    """
    log.info("Starting sync of metrics metadata")

    metric_names = fetch_metric_names(prometheus_url, headers)

    synced_count = 0
    for metric_name in metric_names:
        # Note: Metadata endpoint (/api/v1/targets/metadata) is not universally supported
        # (e.g., Grafana Cloud doesn't expose it). Since metric type and help text are
        # not critical for data syncing, we skip the metadata fetch to avoid unnecessary
        # API calls and warnings. The actual time-series data is synced separately.
        metric_record = {
            "metric_name": metric_name,
            "metric_type": "unknown",
            "help_text": "",
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="metrics", data=metric_record)

        synced_count += 1

        if synced_count % 50 == 0:
            log.info(f"Synced {synced_count}/{len(metric_names)} metrics metadata")

    log.info(f"Completed sync of {synced_count} metrics metadata")


def generate_series_id(metric_name: str, labels: dict) -> str:
    """
    Generate unique series identifier from metric name and labels.
    Args:
        metric_name: Name of the metric.
        labels: Dictionary of label key-value pairs.
    Returns:
        Unique series identifier string.
    """
    sorted_labels = sorted(labels.items())
    label_str = ",".join([f"{k}={v}" for k, v in sorted_labels])
    series_str = f"{metric_name}{{{label_str}}}"

    return hashlib.md5(series_str.encode()).hexdigest()


def parse_timestamp_to_datetime(timestamp_float: float) -> datetime:
    """
    Convert Prometheus Unix timestamp to datetime object.
    Args:
        timestamp_float: Unix timestamp as float.
    Returns:
        Datetime object in UTC timezone.
    """
    return datetime.fromtimestamp(timestamp_float, tz=timezone.utc)


def fetch_time_series_data(
    prometheus_url: str,
    headers: dict,
    query: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict]:
    """
    Fetch time-series data using range query.
    Args:
        prometheus_url: Base URL of Prometheus server.
        headers: Authentication headers.
        query: PromQL query string.
        start_time: Start datetime for range query.
        end_time: End datetime for range query.
    Returns:
        List of time-series result dictionaries.
    """
    url = build_prometheus_url(prometheus_url, "/api/v1/query_range")

    params = {
        "query": query,
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "step": f"{__QUERY_STEP_SECONDS}s",
    }

    log.info(f"Fetching time-series data for query: {query}")

    response_data = make_api_request(url, headers, params)

    if response_data.get("status") != "success":
        log.error(f"Failed to fetch time-series data: {response_data}")
        raise RuntimeError(f"Failed to fetch time-series data: {response_data}")

    result_data = response_data.get("data", {})
    results = result_data.get("result", [])

    log.info(f"Fetched {len(results)} time-series for query: {query}")
    return results


def process_and_upsert_time_series_result(result: dict) -> int:
    """
    Process a single time-series result and upsert data points directly.
    Args:
        result: Time-series result dictionary from Prometheus.
    Returns:
        Number of data points upserted.
    """
    metric_labels = result.get("metric", {})
    metric_name = metric_labels.pop("__name__", "unknown")
    values = result.get("values", [])

    series_id = generate_series_id(metric_name, metric_labels)

    data_points_count = 0
    for timestamp_float, value_str in values:
        data_point = {
            "series_id": series_id,
            "metric_name": metric_name,
            "labels": metric_labels,
            "timestamp": parse_timestamp_to_datetime(timestamp_float),
            "value": float(value_str),
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="time_series", data=data_point)
        data_points_count += 1

    return data_points_count


def get_sync_time_range(state: dict, configuration: dict) -> tuple[datetime, datetime]:
    """
    Determine the time range for syncing based on state and configuration.
    Args:
        state: State dictionary containing last sync timestamp.
        configuration: Configuration dictionary with optional lookback hours.
    Returns:
        Tuple of (start_time, end_time) as datetime objects.
    """
    end_time = datetime.now(timezone.utc)

    last_sync_timestamp = state.get("last_sync_timestamp")

    if last_sync_timestamp:
        start_time = datetime.fromisoformat(last_sync_timestamp.replace("Z", "+00:00"))
        log.info(f"Resuming incremental sync from {start_time.isoformat()}")
    else:
        lookback_hours = int(configuration.get("lookback_hours", __DEFAULT_LOOKBACK_HOURS))
        start_time = end_time - timedelta(hours=lookback_hours)
        log.info(
            f"Starting initial sync with {lookback_hours} hour lookback from {start_time.isoformat()}"
        )

    return start_time, end_time


def sync_time_series_for_metrics(
    prometheus_url: str,
    headers: dict,
    metric_names: list[str],
    start_time: datetime,
    end_time: datetime,
    state: dict,
) -> None:
    """
    Sync time-series data for specified metrics.
    Args:
        prometheus_url: Base URL of Prometheus server.
        headers: Authentication headers.
        metric_names: List of metric names to sync.
        start_time: Start datetime for range query.
        end_time: End datetime for range query.
        state: State dictionary for checkpointing.
    """
    log.info(f"Starting sync of time-series data for {len(metric_names)} metrics")

    total_data_points = 0
    metrics_synced = 0

    for metric_name in metric_names:
        query = f"{metric_name}"

        results = fetch_time_series_data(prometheus_url, headers, query, start_time, end_time)

        batch_data_points = 0

        for result in results:
            # Process and upsert data points directly without creating intermediate lists
            num_data_points = process_and_upsert_time_series_result(result)
            batch_data_points += num_data_points

            if batch_data_points >= __CHECKPOINT_BATCH_SIZE:
                total_data_points += batch_data_points
                state["last_sync_timestamp"] = end_time.isoformat()
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)

                log.info(f"Checkpointed {total_data_points} data points")
                batch_data_points = 0

        if batch_data_points:
            state["last_sync_timestamp"] = end_time.isoformat()
            op.checkpoint(state)
            total_data_points += batch_data_points
            log.info(f"Completed Checkpointed {total_data_points} data points")
        metrics_synced += 1

        if metrics_synced % 10 == 0:
            log.info(f"Synced {metrics_synced}/{len(metric_names)} metrics")

    state["last_sync_timestamp"] = end_time.isoformat()
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info(
        f"Completed sync of {metrics_synced} metrics with {total_data_points} total data points"
    )


def update(configuration: dict, state: dict) -> None:
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.info("Example: Time-Series Database Connector : Prometheus")

    validate_configuration(configuration)

    prometheus_url = configuration["prometheus_url"]
    headers = get_auth_headers(configuration)

    sync_metrics_metadata(prometheus_url, headers)

    start_time, end_time = get_sync_time_range(state, configuration)

    metric_names = fetch_metric_names(prometheus_url, headers)

    metrics_filter = configuration.get("metrics_filter", [])
    if metrics_filter:
        # Handle both string (comma-separated) and list formats
        if isinstance(metrics_filter, str):
            metrics_filter = [m.strip() for m in metrics_filter.split(",") if m.strip()]
        filtered_metrics = [m for m in metric_names if m in metrics_filter]
        log.info(f"Filtered to {len(filtered_metrics)} metrics based on configuration filter")
        metric_names = filtered_metrics

    sync_time_series_for_metrics(
        prometheus_url, headers, metric_names, start_time, end_time, state
    )

    log.info("Prometheus connector sync completed successfully")


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
