"""Open-Meteo Marine Weather Connector

Syncs marine weather data (hourly and daily) from the Open-Meteo Marine Weather API
for a configured coastal location near San Francisco. Includes wave height, wave period,
wave direction, swell data, and wind wave metrics.

No authentication required — Open-Meteo is a free, open-source weather API.

See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For time-based operations and rate limiting
import time

# For date manipulation and incremental sync cursor
from datetime import datetime, timedelta

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# --- Module-level constants ---
__BASE_URL = "https://marine-api.open-meteo.com/v1/marine"
__API_TIMEOUT_SECONDS = 30
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]
__DEFAULT_FORECAST_DAYS = 7
__MAX_FORECAST_DAYS_CEILING = 16
__DEFAULT_PAST_DAYS = 7
__MAX_PAST_DAYS_CEILING = 92
__CHECKPOINT_INTERVAL = 100
__HOURLY_VARIABLES = (
    "wave_height,wave_direction,wave_period,"
    "wind_wave_height,wind_wave_direction,wind_wave_period,"
    "swell_wave_height,swell_wave_direction,swell_wave_period,"
    "ocean_current_velocity,ocean_current_direction"
)
__DAILY_VARIABLES = (
    "wave_height_max,wave_direction_dominant,wave_period_max,"
    "wind_wave_height_max,wind_wave_direction_dominant,wind_wave_period_max,"
    "swell_wave_height_max,swell_wave_direction_dominant"
)


def _is_placeholder(value):
    """Type-safe check for unset/placeholder values.

    Args:
        value: The configuration value to check.

    Returns:
        True if the value is None or an empty string or an angle-bracket placeholder.
        Non-string values (e.g. numeric 0, False) return False — they are real values.
    """
    if value is None or value == "":
        return True
    if not isinstance(value, str):
        return False
    return value.startswith("<") and value.endswith(">")


def _parse_bool(value, default=False):
    """Parse a config string as bool.

    Args:
        value: The string value to parse.
        default: Default value if placeholder.

    Returns:
        The parsed boolean value.

    Raises:
        ValueError: If the value is not 'true' or 'false'.
    """
    if isinstance(value, bool):
        return value
    if _is_placeholder(value):
        return default
    normalized = str(value).strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    raise ValueError(f"Boolean config must be 'true' or 'false', got: {value!r}")


def _optional_int(configuration, key, default):
    """Read optional int; placeholder/invalid returns default.

    Args:
        configuration: The configuration dictionary.
        key: The key to read.
        default: Default value if placeholder or invalid.

    Returns:
        The parsed integer or default.
    """
    value = configuration.get(key)
    if value is None or _is_placeholder(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _optional_str(configuration, key, default):
    """Read optional string; placeholder/None returns default.

    Args:
        configuration: The configuration dictionary.
        key: The key to read.
        default: Default value if placeholder or None.

    Returns:
        The string value or default.
    """
    value = configuration.get(key)
    if value is None or _is_placeholder(value):
        return default
    return str(value)


def validate_configuration(configuration: dict):
    """Validate config; raise ValueError on missing/invalid required values.

    Args:
        configuration: The configuration dictionary.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    # Latitude is required
    latitude = configuration.get("latitude")
    if latitude is None or _is_placeholder(latitude):
        raise ValueError("Missing required configuration value: latitude")
    try:
        lat_val = float(latitude)
    except (ValueError, TypeError):
        raise ValueError(f"latitude must be a valid number, got: {latitude!r}")
    if lat_val < -90 or lat_val > 90:
        raise ValueError("latitude must be between -90 and 90")

    # Longitude is required
    longitude = configuration.get("longitude")
    if longitude is None or _is_placeholder(longitude):
        raise ValueError("Missing required configuration value: longitude")
    try:
        lon_val = float(longitude)
    except (ValueError, TypeError):
        raise ValueError(f"longitude must be a valid number, got: {longitude!r}")
    if lon_val < -180 or lon_val > 180:
        raise ValueError("longitude must be between -180 and 180")

    # Validate forecast_days if provided — fail fast on non-numeric input
    raw_forecast = configuration.get("forecast_days")
    if raw_forecast is not None and not _is_placeholder(raw_forecast):
        try:
            forecast_days = int(raw_forecast)
        except (ValueError, TypeError):
            raise ValueError(f"forecast_days must be a valid integer, got: {raw_forecast!r}")
    else:
        forecast_days = __DEFAULT_FORECAST_DAYS
    if forecast_days < 1 or forecast_days > __MAX_FORECAST_DAYS_CEILING:
        raise ValueError(
            f"forecast_days must be between 1 and "
            f"{__MAX_FORECAST_DAYS_CEILING}, got: {forecast_days}"
        )

    # Validate past_days if provided — fail fast on non-numeric input
    raw_past = configuration.get("past_days")
    if raw_past is not None and not _is_placeholder(raw_past):
        try:
            past_days = int(raw_past)
        except (ValueError, TypeError):
            raise ValueError(f"past_days must be a valid integer, got: {raw_past!r}")
    else:
        past_days = __DEFAULT_PAST_DAYS
    if past_days < 0 or past_days > __MAX_PAST_DAYS_CEILING:
        raise ValueError(
            f"past_days must be between 0 and {__MAX_PAST_DAYS_CEILING}, got: {past_days}"
        )


def fetch_data_with_retry(session, url, params=None):
    """Fetch data from the API with exponential backoff retry logic.

    Args:
        session: The requests.Session to use.
        url: The URL to fetch.
        params: Optional query parameters.

    Returns:
        The parsed JSON response.

    Raises:
        RuntimeError: If all retry attempts fail.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=__API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.info(
                    f"Connection error on attempt {attempt + 1}/{__MAX_RETRIES}, retrying in {delay}s: {e}"
                )
                time.sleep(delay)
            else:
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}") from e
        except requests.exceptions.Timeout as e:
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.info(
                    f"Timeout on attempt {attempt + 1}/{__MAX_RETRIES}, retrying in {delay}s: {e}"
                )
                time.sleep(delay)
            else:
                raise RuntimeError(f"Request timed out after {__MAX_RETRIES} attempts: {e}") from e
        except requests.exceptions.RequestException as e:
            status = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )
            if status in __RETRYABLE_STATUS_CODES and attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.info(
                    f"HTTP {status} on attempt {attempt + 1}/{__MAX_RETRIES}, retrying in {delay}s"
                )
                time.sleep(delay)
            else:
                raise RuntimeError(f"API request failed after {attempt + 1} attempts: {e}") from e
    raise RuntimeError("Unexpected: exhausted retries without returning or raising")


def _normalize_timestamp(ts):
    """Normalize Open-Meteo timestamp to full ISO 8601 format with UTC timezone.

    Open-Meteo returns timestamps like '2026-05-24T00:00' (no seconds, no tz offset).
    The Fivetran SDK UTC_DATETIME type requires '%Y-%m-%dT%H:%M:%S%z' format.

    Args:
        ts: The timestamp string from Open-Meteo API.

    Returns:
        A normalized timestamp string with seconds and +00:00 timezone.
    """
    if not ts:
        return ts
    # Add seconds if missing (format: 2026-05-24T00:00 -> 2026-05-24T00:00:00)
    if len(ts) == 16:  # YYYY-MM-DDTHH:MM
        ts = ts + ":00"
    # Add UTC timezone offset if missing
    if "+" not in ts and "Z" not in ts and len(ts) == 19:
        ts = ts + "+00:00"
    return ts


def build_hourly_record(location_id, timestamp, hourly_data, index, elevation, timezone):
    """Build a single hourly marine weather record from API response arrays.

    Args:
        location_id: The location identifier string.
        timestamp: The ISO timestamp for this record.
        hourly_data: The hourly data dict from API response.
        index: The array index for this time step.
        elevation: The elevation in meters from the API response metadata.
        timezone: The timezone string from the API response metadata.

    Returns:
        A dictionary representing one hourly record.
    """
    return {
        "location_id": location_id,
        "timestamp": _normalize_timestamp(timestamp),
        "wave_height": hourly_data.get("wave_height", [None])[index],
        "wave_direction": hourly_data.get("wave_direction", [None])[index],
        "wave_period": hourly_data.get("wave_period", [None])[index],
        "wind_wave_height": hourly_data.get("wind_wave_height", [None])[index],
        "wind_wave_direction": hourly_data.get("wind_wave_direction", [None])[index],
        "wind_wave_period": hourly_data.get("wind_wave_period", [None])[index],
        "swell_wave_height": hourly_data.get("swell_wave_height", [None])[index],
        "swell_wave_direction": hourly_data.get("swell_wave_direction", [None])[index],
        "swell_wave_period": hourly_data.get("swell_wave_period", [None])[index],
        "ocean_current_velocity": hourly_data.get("ocean_current_velocity", [None])[index],
        "ocean_current_direction": hourly_data.get("ocean_current_direction", [None])[index],
        "elevation": elevation,
        "timezone": timezone,
    }


def build_daily_record(location_id, date_str, daily_data, index, elevation, timezone):
    """Build a single daily marine weather record from API response arrays.

    Args:
        location_id: The location identifier string.
        date_str: The date string for this record.
        daily_data: The daily data dict from API response.
        index: The array index for this day.
        elevation: The elevation in meters from the API response metadata.
        timezone: The timezone string from the API response metadata.

    Returns:
        A dictionary representing one daily record.
    """
    return {
        "location_id": location_id,
        "date": date_str,
        "wave_height_max": daily_data.get("wave_height_max", [None])[index],
        "wave_direction_dominant": daily_data.get("wave_direction_dominant", [None])[index],
        "wave_period_max": daily_data.get("wave_period_max", [None])[index],
        "wind_wave_height_max": daily_data.get("wind_wave_height_max", [None])[index],
        "wind_wave_direction_dominant": daily_data.get("wind_wave_direction_dominant", [None])[
            index
        ],
        "wind_wave_period_max": daily_data.get("wind_wave_period_max", [None])[index],
        "swell_wave_height_max": daily_data.get("swell_wave_height_max", [None])[index],
        "swell_wave_direction_dominant": daily_data.get("swell_wave_direction_dominant", [None])[
            index
        ],
        "elevation": elevation,
        "timezone": timezone,
    }


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
            "table": "marine_hourly",
            "primary_key": ["location_id", "timestamp"],
            "columns": {
                "location_id": "STRING",
                "timestamp": "UTC_DATETIME",
                "wave_height": "FLOAT",
                "wave_direction": "FLOAT",
                "wave_period": "FLOAT",
                "wind_wave_height": "FLOAT",
                "wind_wave_direction": "FLOAT",
                "wind_wave_period": "FLOAT",
                "swell_wave_height": "FLOAT",
                "swell_wave_direction": "FLOAT",
                "swell_wave_period": "FLOAT",
                "ocean_current_velocity": "FLOAT",
                "ocean_current_direction": "FLOAT",
                "elevation": "FLOAT",
                "timezone": "STRING",
            },
        },
        {
            "table": "marine_daily",
            "primary_key": ["location_id", "date"],
            "columns": {
                "location_id": "STRING",
                "date": "STRING",
                "wave_height_max": "FLOAT",
                "wave_direction_dominant": "FLOAT",
                "wave_period_max": "FLOAT",
                "wind_wave_height_max": "FLOAT",
                "wind_wave_direction_dominant": "FLOAT",
                "wind_wave_period_max": "FLOAT",
                "swell_wave_height_max": "FLOAT",
                "swell_wave_direction_dominant": "FLOAT",
                "elevation": "FLOAT",
                "timezone": "STRING",
            },
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
    log.warning("Example: connectors : open_meteo_marine_weather")
    validate_configuration(configuration)

    latitude = configuration.get("latitude")
    longitude = configuration.get("longitude")
    timezone = _optional_str(configuration, "timezone", "America/Los_Angeles")
    forecast_days = _optional_int(configuration, "forecast_days", __DEFAULT_FORECAST_DAYS)
    past_days = _optional_int(configuration, "past_days", __DEFAULT_PAST_DAYS)

    # Build a location_id from lat/lon for the composite primary key
    location_id = f"{latitude}_{longitude}"

    # Determine the date range for incremental sync
    # Use state to track last synced date; overlap by 1 day to handle inclusive boundaries
    last_synced_date = state.get("last_synced_date")
    today = datetime.utcnow().date()

    if last_synced_date:
        # Overlap by 1 day to handle inclusive date boundary dedup
        start_date = datetime.strptime(last_synced_date, "%Y-%m-%d").date() - timedelta(days=1)
    else:
        # First sync: go back past_days from today
        start_date = today - timedelta(days=past_days)

    end_date = today + timedelta(days=forecast_days)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": __HOURLY_VARIABLES,
        "daily": __DAILY_VARIABLES,
        "timezone": timezone,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }

    session = requests.Session()
    try:
        log.info(
            f"Fetching marine weather data for ({latitude}, {longitude}) "
            f"from {start_date} to {end_date}"
        )
        data = fetch_data_with_retry(session, __BASE_URL, params=params)

        # Extract location metadata returned at the top level of each API response
        elevation = data.get("elevation")
        resp_timezone = data.get("timezone", "UTC")

        # Process hourly data
        hourly_data = data.get("hourly", {})
        hourly_times = hourly_data.get("time", [])
        hourly_count = 0

        log.info(f"Processing {len(hourly_times)} hourly records")
        for index, timestamp in enumerate(hourly_times):
            record = build_hourly_record(
                location_id, timestamp, hourly_data, index, elevation, resp_timezone
            )
            if not record.get("location_id") or not record.get("timestamp"):
                log.info("Skipping hourly record without primary key fields")
                continue
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="marine_hourly", data=record)
            hourly_count += 1
            if hourly_count % __CHECKPOINT_INTERVAL == 0:
                op.checkpoint(state={"last_synced_date": today.strftime("%Y-%m-%d")})

        log.info(f"Successfully processed {hourly_count} hourly records")

        # Process daily data
        daily_data = data.get("daily", {})
        daily_times = daily_data.get("time", [])
        daily_count = 0

        log.info(f"Processing {len(daily_times)} daily records")
        for index, date_str in enumerate(daily_times):
            record = build_daily_record(
                location_id, date_str, daily_data, index, elevation, resp_timezone
            )
            if not record.get("location_id") or not record.get("date"):
                log.info("Skipping daily record without primary key fields")
                continue
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="marine_daily", data=record)
            daily_count += 1
            if daily_count % __CHECKPOINT_INTERVAL == 0:
                op.checkpoint(state={"last_synced_date": today.strftime("%Y-%m-%d")})

        log.info(f"Successfully processed {daily_count} daily records")

        # Update state with the latest date we synced
        state["last_synced_date"] = today.strftime("%Y-%m-%d")

        # Save the progress by checkpointing the state. This is important for ensuring that
        # the sync process can resume from the correct position in case of next sync or
        # interruptions. You should checkpoint even if you are not using incremental sync,
        # as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development.
if __name__ == "__main__":
    # Test the connector locally
    connector.debug()
