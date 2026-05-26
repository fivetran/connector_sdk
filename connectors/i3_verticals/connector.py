"""Fivetran connector for I3 Verticals Burton Platform REST API (v2).

Syncs payment charges, refunds, customers, distributions, merchants, and accounts
from the Burton Platform into a Fivetran-managed warehouse.
"""

import json  # For loading local configuration during connector debugging.
import time  # For retry backoff delays and token expiry calculations.
from datetime import datetime, timezone  # For parsing and comparing UTC timestamps.

import requests  # For making HTTP requests to the Burton Platform API and OAuth token endpoint.
from fivetran_connector_sdk import Connector  # For initializing the Fivetran connector.
from fivetran_connector_sdk import (
    Logging as log,
)  # For writing logs using the Connector SDK logger.
from fivetran_connector_sdk import (
    Operations as op,
)  # For performing upsert and checkpoint operations.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

__TOKEN_ENDPOINT = "/services/oauth2/token"
__TOKEN_REFRESH_BUFFER_SECONDS = 300  # Refresh 5 min before expiry
__DEFAULT_PAGE_SIZE = 100
__DEFAULT_RATE_LIMIT_RPS = 2
__MAX_RETRIES = 5
__RETRY_BASE_SECONDS = 2
__RETRY_MAX_SECONDS = 60
__CHECKPOINT_INTERVAL = 1000  # Checkpoint every N records per table

# OAuth scopes needed (read-only where available)
__OAUTH_SCOPES = (
    "urn:v2:charges:all "
    "urn:v2:refunds:all "
    "urn:v2:customers:all "
    "urn:v2:distributions:all "
    "urn:v2:merchants:read "
    "urn:v2:accounts:read"
)

# PCI-sensitive fields to exclude from synced data
__PCI_EXCLUDED_FIELDS = {
    "card_number",
    "account_number",
    "routing_number",
    "cvv",
    "pin",
    "security_code",
    "expiration_date",
}

# Table definitions: (table_name, endpoint, primary_key, timestamp_field)
__TABLES = [
    ("charges", "/v2/charges", "charge_id", "charge_timestamp"),
    ("refunds", "/v2/refunds", "refund_id", "refund_timestamp"),
    ("customers", "/v2/customers", "customer_id", "created_at"),
    ("distributions", "/v2/distributions", "distribution_id", "distribution_date"),
    ("merchants", "/v2/merchants", "merchant_id", "created_at"),
    ("accounts", "/v2/accounts", "account_id", "created_at"),
]

# ---------------------------------------------------------------------------
# Module-level token cache
# ---------------------------------------------------------------------------

_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def validate_configuration(configuration: dict):
    """Validate required configuration fields are present."""
    required = ["client_id", "client_secret", "base_url"]
    for key in required:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")


def _get_base_url(configuration: dict) -> str:
    """Return the base URL with trailing slash stripped."""
    return configuration["base_url"].rstrip("/")


def _get_page_size(configuration: dict) -> int:
    return int(configuration.get("page_size", str(__DEFAULT_PAGE_SIZE)))


def _get_rate_limit_interval(configuration: dict) -> float:
    rps = float(configuration.get("rate_limit_rps", str(__DEFAULT_RATE_LIMIT_RPS)))
    return 1.0 / rps if rps > 0 else 0


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _get_auth_token(configuration: dict) -> str:
    """Acquire or return a cached OAuth 2.0 Bearer token.

    Refreshes proactively when within __TOKEN_REFRESH_BUFFER_SECONDS of expiry.
    """
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    base_url = _get_base_url(configuration)
    token_url = f"{base_url}{__TOKEN_ENDPOINT}"

    log.info("Requesting new OAuth token")
    resp = requests.post(
        token_url,
        auth=(configuration["client_id"], configuration["client_secret"]),
        data={"grant_type": "client_credentials", "scope": __OAUTH_SCOPES},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if resp.status_code != 200:
        log.severe(f"OAuth token request failed: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Failed to obtain OAuth token: HTTP {resp.status_code}")

    token_data = resp.json()
    _token_cache["access_token"] = token_data["access_token"]
    expires_in = int(token_data.get("expires_in", 3599))
    _token_cache["expires_at"] = now + expires_in - __TOKEN_REFRESH_BUFFER_SECONDS

    log.info(f"OAuth token acquired, expires in {expires_in}s")
    return _token_cache["access_token"]


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------


def _api_request(
    configuration: dict, method: str, endpoint: str, params: dict = None
) -> requests.Response:
    """Make an authenticated API request with retry and rate limiting.

    Retries on 429, 503, and 5xx errors with exponential backoff.
    """
    base_url = _get_base_url(configuration)
    url = f"{base_url}{endpoint}"
    rate_interval = _get_rate_limit_interval(configuration)

    for attempt in range(1, __MAX_RETRIES + 1):
        token = _get_auth_token(configuration)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            resp = requests.request(method, url, headers=headers, params=params, timeout=60)
        except requests.exceptions.RequestException as e:
            log.warning(f"Request error (attempt {attempt}/{__MAX_RETRIES}): {e}")
            if attempt == __MAX_RETRIES:
                raise
            _backoff_sleep(attempt)
            continue

        if resp.status_code == 200:
            if rate_interval > 0:
                time.sleep(rate_interval)
            return resp

        if resp.status_code == 401:
            # Token may have expired server-side; force refresh
            log.warning("Received 401, forcing token refresh")
            _token_cache["access_token"] = None
            _token_cache["expires_at"] = 0
            if attempt == __MAX_RETRIES:
                raise RuntimeError(f"API returned 401 after {__MAX_RETRIES} attempts")
            continue

        if resp.status_code in (429, 503) or resp.status_code >= 500:
            wait = _backoff_wait(attempt, resp)
            log.warning(
                f"HTTP {resp.status_code} on {endpoint} (attempt {attempt}/{__MAX_RETRIES}), retrying in {wait:.1f}s"
            )
            if attempt == __MAX_RETRIES:
                raise RuntimeError(
                    f"API returned {resp.status_code} after {__MAX_RETRIES} attempts: {resp.text}"
                )
            time.sleep(wait)
            continue

        # 4xx client errors (not 401/429) are not retryable
        log.severe(f"API error {resp.status_code}: {resp.text}")
        raise RuntimeError(f"API request failed: HTTP {resp.status_code} on {endpoint}")

    raise RuntimeError(f"Exhausted retries for {endpoint}")


def _backoff_wait(attempt: int, resp: requests.Response = None) -> float:
    """Calculate exponential backoff wait time, respecting Retry-After header."""
    if resp is not None and "Retry-After" in resp.headers:
        try:
            return min(float(resp.headers["Retry-After"]), __RETRY_MAX_SECONDS)
        except ValueError:
            pass
    return min(__RETRY_BASE_SECONDS**attempt, __RETRY_MAX_SECONDS)


def _backoff_sleep(attempt: int):
    time.sleep(min(__RETRY_BASE_SECONDS**attempt, __RETRY_MAX_SECONDS))


# ---------------------------------------------------------------------------
# Response Parsing & Record Processing
# ---------------------------------------------------------------------------


def _extract_records(response_json, table_name: str) -> list:
    """Extract the record list from the API response.

    Burton Platform response envelope format is not fully documented.
    This function handles common patterns:
      - Bare list: [record, ...]
      - Envelope with data key: {"data": [record, ...], ...}
      - Envelope with table-named key: {"charges": [record, ...], ...}
      - Single object: {record} (wrap in list)
    """
    if isinstance(response_json, list):
        return response_json

    if isinstance(response_json, dict):
        # Try common envelope keys
        for key in ("data", "results", "items", "records", table_name):
            if key in response_json and isinstance(response_json[key], list):
                return response_json[key]

        # If the dict looks like a single record (has the primary key), wrap it
        if any(k.endswith("_id") for k in response_json):
            return [response_json]

        # Last resort: look for the first list value
        for value in response_json.values():
            if isinstance(value, list):
                return value

    log.warning(f"Could not extract records from response for {table_name}")
    return []


def _get_pagination_info(response_json) -> dict:
    """Extract pagination metadata from response envelope.

    Returns dict with optional keys: total_count, next_offset, has_more.
    """
    info = {}
    if isinstance(response_json, dict):
        # Total count from envelope or header
        for key in ("total_count", "total", "count", "totalCount"):
            if key in response_json:
                try:
                    info["total_count"] = int(response_json[key])
                except (ValueError, TypeError):
                    pass
                break

        # Cursor or next page indicator
        if "next" in response_json:
            info["has_more"] = response_json["next"] is not None
        if "next_cursor" in response_json:
            info["next_cursor"] = response_json["next_cursor"]

    return info


def _flatten_record(record: dict, parent_key: str = "", sep: str = "_") -> dict:
    """Flatten nested dicts into dot-separated keys. Excludes PCI-sensitive fields."""
    items = {}
    for key, value in record.items():
        full_key = f"{parent_key}{sep}{key}" if parent_key else key

        # Skip PCI-sensitive fields at any nesting level
        if key in __PCI_EXCLUDED_FIELDS:
            continue

        if isinstance(value, dict):
            items.update(_flatten_record(value, full_key, sep))
        elif isinstance(value, list):
            # Store lists as JSON strings to avoid schema complexity
            items[full_key] = json.dumps(value)
        else:
            items[full_key] = value

    return items


def _normalize_timestamp(value) -> str | None:
    """Normalize a timestamp value to ISO 8601 string, or return None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value  # Already a string; assume ISO 8601 from the API
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": table_name, "primary_key": [pk]} for table_name, _endpoint, pk, _ts in __TABLES
    ]


# ---------------------------------------------------------------------------
# Sync Logic
# ---------------------------------------------------------------------------


def _sync_table(
    configuration: dict, state: dict, table_name: str, endpoint: str, pk_field: str, ts_field: str
) -> dict:
    """Sync a single table from the Burton Platform API.

    Paginates through all records, upserts them, and returns updated state.
    Uses timestamp-based cursor for incremental syncs when available.
    """
    table_state = state.get(table_name, {})
    last_synced_at = table_state.get("last_synced_at")
    high_water_mark = last_synced_at

    page_size = _get_page_size(configuration)
    offset = 0
    total_records = 0

    log.info(f"Syncing {table_name} (cursor: {last_synced_at or 'initial load'})")

    while True:
        # Build query parameters
        params = {"limit": page_size, "offset": offset}

        # If server-side date filtering is supported, include it
        # NOTE: Burton Platform date filtering is unconfirmed -- these params
        # are included optimistically. If the API ignores them, we filter client-side.
        if last_synced_at:
            params["created_after"] = last_synced_at
            params["modified_since"] = last_synced_at

        resp = _api_request(configuration, "GET", endpoint, params=params)
        response_json = resp.json()
        records = _extract_records(response_json, table_name)

        if not records:
            break

        for record in records:
            flat = _flatten_record(record)

            # Client-side incremental filtering: skip records older than cursor
            record_ts = _normalize_timestamp(flat.get(ts_field))
            if last_synced_at and record_ts and record_ts <= last_synced_at:
                continue

            op.upsert(table_name, flat)
            total_records += 1

            # Track high-water mark
            if record_ts and (high_water_mark is None or record_ts > high_water_mark):
                high_water_mark = record_ts

            # Periodic checkpoint for large tables
            if total_records > 0 and total_records % __CHECKPOINT_INTERVAL == 0:
                new_state = dict(state)
                new_state[table_name] = {"last_synced_at": high_water_mark}
                op.checkpoint(new_state)
                log.info(f"Checkpoint at {total_records} records for {table_name}")

        # Pagination: if we got fewer records than page_size, we've reached the end
        pagination = _get_pagination_info(response_json)
        if len(records) < page_size:
            break
        if "has_more" in pagination and not pagination["has_more"]:
            break

        offset += page_size

    log.info(f"Completed {table_name}: {total_records} record(s) synced")

    # Update state for this table
    if high_water_mark:
        state[table_name] = {"last_synced_at": high_water_mark}

    return state


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that contains whatever state you have chosen to checkpoint during the prior sync.
    """
    log.warning("Example: connector : i3_verticals")
    validate_configuration(configuration)

    log.info(f"Starting sync, state: {json.dumps(state) if state else 'empty (initial load)'}")

    for table_name, endpoint, pk_field, ts_field in __TABLES:
        try:
            state = _sync_table(configuration, state, table_name, endpoint, pk_field, ts_field)
        except (
            RuntimeError,
            requests.exceptions.HTTPError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.TooManyRedirects,
            json.JSONDecodeError,
        ) as e:
            log.severe(f"Error syncing {table_name}: {e}")
            # Checkpoint what we have so far, then re-raise to signal failure
            op.checkpoint(state)
            raise RuntimeError(f"Failed to sync {table_name}: {e}") from e

    # Final checkpoint with all tables' cursors
    op.checkpoint(state)
    log.info(f"Sync complete. Final state: {json.dumps(state)}")


# ---------------------------------------------------------------------------
# Connector Entry Point
# ---------------------------------------------------------------------------

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
