"""DTN Weather Connector — Syncs weather data from DTN's Observations, Conditions, and Lightning APIs.
See PLAN.md for full design documentation.
"""

import json
import time
from datetime import datetime, timedelta, timezone

import requests
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
__OBS_BASE_URL = "https://api.dtn.com"
__CONDITIONS_BASE_URL = "https://weather.api.dtn.com"
__LIGHTNING_BASE_URL = "https://lightning.api.dtn.com"
__AUTH_TOKEN_URL = "https://api.auth.dtn.com/v1/tokens/authorize"

__REQUEST_TIMEOUT = 30
__MAX_RETRIES = 3
__LIGHTNING_WINDOW_MINUTES = 15
__LIGHTNING_CHECKPOINT_INTERVAL = 10  # checkpoint every N windows


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class _TokenCache:
    """Caches OAuth2 tokens per audience with proactive refresh."""

    def __init__(self):
        self._tokens = {}  # audience -> (token, expiry_epoch)

    def get_token(self, client_id: str, client_secret: str, audience: str) -> str:
        cached = self._tokens.get(audience)
        if cached and time.time() < cached[1] - 10:  # refresh 10s before expiry
            return cached[0]

        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
        }
        resp = requests.post(__AUTH_TOKEN_URL, json=payload, timeout=__REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        token = data["access_token"]
        expires_in = data.get("expires_in", 90)
        self._tokens[audience] = (token, time.time() + expires_in)
        log.fine(f"OAuth token obtained for {audience}, expires in {expires_in}s")
        return token


_token_cache = _TokenCache()


def _obs_headers(configuration: dict) -> dict:
    return {"apikey": configuration["api_key"], "Accept": "application/json"}


def _oauth_headers(configuration: dict, audience: str) -> dict:
    token = _token_cache.get_token(
        configuration["client_id"], configuration["client_secret"], audience
    )
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# HTTP helper with retry
# ---------------------------------------------------------------------------
def _request(
    method: str, url: str, headers: dict, params: dict = None, json_body: dict = None
) -> dict:
    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=__REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning(f"Rate limited, waiting {wait}s (attempt {attempt})")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = 2 ** (attempt - 1)
                log.warning(f"Server error {resp.status_code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt < __MAX_RETRIES:
                log.warning(f"Request timeout, retrying (attempt {attempt})")
                time.sleep(2 ** (attempt - 1))
            else:
                raise
    raise RuntimeError(f"Request failed after {__MAX_RETRIES} retries: {method} {url}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _parse_enabled_apis(configuration: dict) -> set:
    raw = configuration.get("enabled_apis", "observations,conditions,lightning")
    return {a.strip().lower() for a in raw.split(",")}


def _parse_station_ids(configuration: dict) -> list:
    raw = configuration.get("station_ids", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_locations(configuration: dict) -> list:
    raw = configuration.get("locations", "[]")
    try:
        locations = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "locations must be a valid JSON array of {lat, lon} objects, "
            'e.g. \'[{"lat":35.46,"lon":-97.51}]\''
        ) from exc
    return locations


def validate_configuration(configuration: dict):
    enabled = _parse_enabled_apis(configuration)

    if "observations" in enabled and not configuration.get("api_key"):
        raise ValueError("Missing required configuration: api_key (needed for observations API)")

    if enabled & {"conditions", "lightning"}:
        if not configuration.get("client_id") or not configuration.get("client_secret"):
            raise ValueError(
                "Missing required configuration: client_id and client_secret (needed for conditions/lightning APIs)"
            )

    if "observations" in enabled and not _parse_station_ids(configuration):
        raise ValueError(
            "Missing required configuration: station_ids (comma-separated station IDs for observations API)"
        )

    if "conditions" in enabled and not _parse_locations(configuration):
        raise ValueError(
            "Missing required configuration: locations (JSON array of lat/lon for conditions API)"
        )

    if "lightning" in enabled:
        if not configuration.get("lightning_lat") or not configuration.get("lightning_lon"):
            raise ValueError("Missing required configuration: lightning_lat and lightning_lon")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def schema(configuration: dict):
    enabled = _parse_enabled_apis(configuration)
    tables = []

    if "observations" in enabled:
        tables.extend(
            [
                {"table": "stations", "primary_key": ["station_id"]},
                {"table": "daily_forecasts", "primary_key": ["station_id", "date"]},
                {"table": "daily_observations", "primary_key": ["station_id", "date"]},
                {"table": "hourly_forecasts", "primary_key": ["station_id", "utc_time"]},
                {"table": "hourly_observations", "primary_key": ["station_id", "utc_time"]},
            ]
        )
    if "conditions" in enabled:
        tables.append(
            {"table": "conditions", "primary_key": ["latitude", "longitude", "utc_time"]}
        )
    if "lightning" in enabled:
        tables.append(
            {"table": "lightning_strikes", "primary_key": ["latitude", "longitude", "utc_time"]}
        )

    return tables


# ---------------------------------------------------------------------------
# Observations & Forecasts API — Data Fetching
# ---------------------------------------------------------------------------
def _sync_stations(configuration: dict):
    """Full refresh of station metadata for all configured stations."""
    headers = _obs_headers(configuration)
    station_ids = _parse_station_ids(configuration)
    count = 0

    for sid in station_ids:
        url = f"{__OBS_BASE_URL}/weather/stations/{sid}"
        try:
            data = _request("GET", url, headers)
            row = {
                "station_id": data.get("stationId", sid),
                "display_name": data.get("displayName"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "elevation": data.get("elevation"),
                "elevation_units": data.get("elevationUnits"),
                "is_forecast_station": data.get("isForecastStation"),
                "has_soil_sensor": data.get("hasSoilSensor"),
                "last_observation_datetime": data.get("lastObservationDateTime"),
            }
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert("stations", row)
            count += 1
        except Exception as e:
            log.warning(f"Failed to fetch station {sid}: {e}")

    log.info(f"Synced {count} station(s)")


def _parse_daily_record(record: dict, station_id: str) -> dict:
    """Flatten a daily forecast/observation record into a row."""
    precip = record.get("precipitation", [{}])
    precip_first = precip[0] if precip else {}
    temps = record.get("temperatures", {})

    return {
        "station_id": station_id,
        "date": record.get("date"),
        "weather_code": record.get("weatherCode"),
        "weather_description": record.get("weatherDescription"),
        "temp_avg": temps.get("avg"),
        "temp_max": temps.get("max"),
        "temp_min": temps.get("min"),
        "dew_point_avg": (
            record.get("dewPoint", {}).get("avg")
            if isinstance(record.get("dewPoint"), dict)
            else record.get("dewPoint")
        ),
        "humidity_avg": (
            record.get("humidity", {}).get("avg")
            if isinstance(record.get("humidity"), dict)
            else record.get("humidity")
        ),
        "pressure_avg": (
            record.get("pressure", {}).get("avg")
            if isinstance(record.get("pressure"), dict)
            else record.get("pressure")
        ),
        "wind_speed_avg": (
            record.get("wind", {}).get("speed", {}).get("avg")
            if isinstance(record.get("wind"), dict)
            else None
        ),
        "wind_direction_avg": (
            record.get("wind", {}).get("direction", {}).get("avg")
            if isinstance(record.get("wind"), dict)
            else None
        ),
        "wind_gust_max": (
            record.get("wind", {}).get("gust", {}).get("max")
            if isinstance(record.get("wind"), dict)
            else None
        ),
        "precipitation_amount": precip_first.get("amount"),
        "precipitation_type": precip_first.get("type"),
        "feels_like_avg": (
            record.get("feelsLike", {}).get("avg")
            if isinstance(record.get("feelsLike"), dict)
            else record.get("feelsLike")
        ),
        "sunrise": record.get("sunrise"),
        "sunset": record.get("sunset"),
        "minutes_of_sunshine": record.get("minutesOfSunshine"),
    }


def _parse_hourly_record(record: dict, station_id: str) -> dict:
    """Flatten an hourly forecast/observation record into a row."""
    precip = record.get("precipitation", [{}])
    precip_first = precip[0] if precip else {}

    return {
        "station_id": station_id,
        "utc_time": record.get("utcTime"),
        "weather_code": record.get("weatherCode"),
        "weather_description": record.get("weatherDescription"),
        "temperature": record.get("temperature"),
        "dew_point": record.get("dewPoint"),
        "feels_like": record.get("feelsLike"),
        "humidity": record.get("humidity"),
        "pressure": record.get("pressure"),
        "wind_speed": record.get("windSpeed"),
        "wind_direction": record.get("windDirection"),
        "wind_gust": record.get("windGust"),
        "visibility": record.get("visibility"),
        "cloud_cover_percent": record.get("cloudCoverPercent"),
        "precipitation_amount": precip_first.get("amount"),
        "precipitation_type": precip_first.get("type"),
    }


def _sync_daily_forecasts(configuration: dict, state: dict) -> dict:
    headers = _obs_headers(configuration)
    station_ids = _parse_station_ids(configuration)
    units = configuration.get("units", "us")
    count = 0

    # Always fetch full 15-day forecast window (forecasts are mutable)
    for sid in station_ids:
        params = {"stationId": sid, "days": "15", "units": units}
        try:
            data = _request("GET", f"{__OBS_BASE_URL}/weather/daily-forecasts", headers, params)
            records = (
                data if isinstance(data, list) else data.get("forecasts", data.get("data", []))
            )
            for rec in records:
                row = _parse_daily_record(rec, sid)
                if row["date"]:
                    op.upsert("daily_forecasts", row)
                    count += 1
        except Exception as e:
            log.warning(f"Failed to fetch daily forecasts for {sid}: {e}")

    cursor = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"Synced {count} daily forecast row(s)")
    return {**state, "daily_forecasts_cursor": cursor}


def _sync_daily_observations(configuration: dict, state: dict) -> dict:
    headers = _obs_headers(configuration)
    station_ids = _parse_station_ids(configuration)
    units = configuration.get("units", "us")
    cursor = state.get("daily_observations_cursor")
    count = 0

    # Calculate days to look back
    if cursor:
        cursor_date = datetime.strptime(cursor, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_back = max(1, (datetime.now(timezone.utc) - cursor_date).days + 1)
    else:
        days_back = 30  # initial sync: 30 days of history

    for sid in station_ids:
        params = {"stationId": sid, "days": str(min(days_back, 30)), "units": units}
        try:
            data = _request("GET", f"{__OBS_BASE_URL}/weather/daily-observations", headers, params)
            records = (
                data if isinstance(data, list) else data.get("observations", data.get("data", []))
            )
            for rec in records:
                row = _parse_daily_record(rec, sid)
                if row["date"]:
                    op.upsert("daily_observations", row)
                    count += 1
        except Exception as e:
            log.warning(f"Failed to fetch daily observations for {sid}: {e}")

    new_cursor = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"Synced {count} daily observation row(s)")
    return {**state, "daily_observations_cursor": new_cursor}


def _sync_hourly_forecasts(configuration: dict, state: dict) -> dict:
    headers = _obs_headers(configuration)
    station_ids = _parse_station_ids(configuration)
    units = configuration.get("units", "us")
    count = 0

    # Always fetch full forecast window (mutable data)
    for sid in station_ids:
        params = {"stationId": sid, "units": units}
        try:
            data = _request("GET", f"{__OBS_BASE_URL}/weather/hourly-forecasts", headers, params)
            records = (
                data if isinstance(data, list) else data.get("forecasts", data.get("data", []))
            )
            for rec in records:
                row = _parse_hourly_record(rec, sid)
                if row["utc_time"]:
                    op.upsert("hourly_forecasts", row)
                    count += 1
        except Exception as e:
            log.warning(f"Failed to fetch hourly forecasts for {sid}: {e}")

    cursor = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(f"Synced {count} hourly forecast row(s)")
    return {**state, "hourly_forecasts_cursor": cursor}


def _sync_hourly_observations(configuration: dict, state: dict) -> dict:
    headers = _obs_headers(configuration)
    station_ids = _parse_station_ids(configuration)
    units = configuration.get("units", "us")
    cursor = state.get("hourly_observations_cursor")
    count = 0

    if cursor:
        cursor_dt = datetime.strptime(cursor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        hours_back = max(
            1, int((datetime.now(timezone.utc) - cursor_dt).total_seconds() / 3600) + 1
        )
    else:
        hours_back = 168  # initial sync: 7 days

    for sid in station_ids:
        params = {"stationId": sid, "hours": str(min(hours_back, 168)), "units": units}
        try:
            data = _request(
                "GET", f"{__OBS_BASE_URL}/weather/hourly-observations", headers, params
            )
            records = (
                data if isinstance(data, list) else data.get("observations", data.get("data", []))
            )
            for rec in records:
                row = _parse_hourly_record(rec, sid)
                if row["utc_time"]:
                    op.upsert("hourly_observations", row)
                    count += 1
        except Exception as e:
            log.warning(f"Failed to fetch hourly observations for {sid}: {e}")

    new_cursor = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(f"Synced {count} hourly observation row(s)")
    return {**state, "hourly_observations_cursor": new_cursor}


# ---------------------------------------------------------------------------
# Weather Conditions API — Data Fetching
# ---------------------------------------------------------------------------
def _sync_conditions(configuration: dict, state: dict) -> dict:
    headers = _oauth_headers(configuration, __CONDITIONS_BASE_URL)
    locations = _parse_locations(configuration)
    units = configuration.get("units", "us")
    units_mapped = "us-std" if units == "us" else "si-std"
    cursor = state.get("conditions_cursor")
    count = 0

    now = datetime.now(timezone.utc)
    if cursor:
        start_time = cursor
    else:
        # Initial sync: 7 days of history
        start_time = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Use batch endpoint for multiple locations
    if len(locations) > 1:
        body = {
            "locations": locations,
            "startTime": start_time,
            "endTime": end_time,
            "units": units_mapped,
        }
        try:
            # Refresh headers in case token expired during prior syncs
            headers = _oauth_headers(configuration, __CONDITIONS_BASE_URL)
            data = _request(
                "POST", f"{__CONDITIONS_BASE_URL}/v2/conditions/batch", headers, json_body=body
            )
            count += _parse_and_upsert_conditions(data)
        except Exception as e:
            log.warning(f"Batch conditions request failed: {e}")
    else:
        for loc in locations:
            params = {
                "lat": str(loc["lat"]),
                "lon": str(loc["lon"]),
                "startTime": start_time,
                "endTime": end_time,
                "units": units_mapped,
            }
            try:
                headers = _oauth_headers(configuration, __CONDITIONS_BASE_URL)
                data = _request("GET", f"{__CONDITIONS_BASE_URL}/v2/conditions", headers, params)
                count += _parse_and_upsert_conditions(data)
            except Exception as e:
                log.warning(f"Conditions request failed for {loc}: {e}")

    log.info(f"Synced {count} conditions row(s)")
    return {**state, "conditions_cursor": end_time}


def _parse_and_upsert_conditions(geojson: dict) -> int:
    """Parse GeoJSON FeatureCollection and upsert flattened rows."""
    count = 0
    features = geojson.get("features", [])

    for feature in features:
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        properties = feature.get("properties", {})

        for timestamp, values in properties.items():
            if not isinstance(values, dict):
                continue
            row = {
                "latitude": lat,
                "longitude": lon,
                "utc_time": timestamp,
            }
            # Map camelCase API keys to snake_case columns
            key_map = {
                "airTemp": "air_temp",
                "dewPoint": "dew_point",
                "feelsLikeTemp": "feels_like_temp",
                "heatIndex": "heat_index",
                "windChill": "wind_chill",
                "relativeHumidity": "relative_humidity",
                "windSpeed": "wind_speed",
                "windDirection": "wind_direction",
                "windGust": "wind_gust",
                "mslPressure": "msl_pressure",
                "surfacePressure": "surface_pressure",
                "visibility": "visibility",
                "totalCloudCover": "total_cloud_cover",
                "precipAmount": "precip_amount",
                "precipProb": "precip_prob",
                "precipType": "precip_type",
                "snowfallAmount": "snowfall_amount",
                "weatherCode": "weather_code",
                "globalRadiation": "global_radiation",
                "sunshineDuration": "sunshine_duration",
            }
            for api_key, col_name in key_map.items():
                if api_key in values:
                    row[col_name] = values[api_key]

            op.upsert("conditions", row)
            count += 1

    return count


# ---------------------------------------------------------------------------
# Lightning API — Data Fetching
# ---------------------------------------------------------------------------
def _sync_lightning(configuration: dict, state: dict) -> dict:
    lat = configuration["lightning_lat"]
    lon = configuration["lightning_lon"]
    radius = configuration.get("lightning_radius_km", "50")
    cursor = state.get("lightning_cursor")
    count = 0
    window_count = 0

    now = datetime.now(timezone.utc)
    if cursor:
        start = datetime.strptime(cursor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    else:
        # Initial sync: 24 hours of history
        start = now - timedelta(hours=24)

    current = start
    new_state = dict(state)

    while current < now:
        window_end = min(current + timedelta(minutes=__LIGHTNING_WINDOW_MINUTES), now)

        params = {
            "by": "radius",
            "lat": lat,
            "lon": lon,
            "radius": radius,
            "startTime": current.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            headers = _oauth_headers(configuration, __LIGHTNING_BASE_URL)
            data = _request("GET", f"{__LIGHTNING_BASE_URL}/v2/strikes", headers, params)
            count += _parse_and_upsert_lightning(data)
        except Exception as e:
            log.warning(f"Lightning request failed for window {current}: {e}")

        current = window_end
        window_count += 1

        # Periodic checkpoint for long-running lightning syncs
        if window_count % __LIGHTNING_CHECKPOINT_INTERVAL == 0:
            new_state["lightning_cursor"] = current.strftime("%Y-%m-%dT%H:%M:%SZ")
            op.checkpoint(new_state)
            log.fine(
                f"Lightning checkpoint at {current} ({window_count} windows, {count} strikes)"
            )

    new_state["lightning_cursor"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(f"Synced {count} lightning strike(s) across {window_count} window(s)")
    return new_state


def _parse_and_upsert_lightning(geojson: dict) -> int:
    """Parse GeoJSON lightning response and upsert flattened rows."""
    count = 0
    features = geojson.get("features", [])

    for feature in features:
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        properties = feature.get("properties", {})

        for timestamp, values in properties.items():
            if not isinstance(values, dict):
                continue
            row = {
                "latitude": lat,
                "longitude": lon,
                "utc_time": timestamp,
                "lightning_type": values.get("lightningType"),
                "peak_current": values.get("peakCurrent"),
                "cloud_to_cloud_height": values.get("cloudToCloudHeight"),
                "sensor_count": values.get("sensorCount"),
                "error_ellipse_bearing": values.get("errorEllipseBearing"),
                "error_ellipse_semi_major": values.get("errorEllipseSemiMajor"),
                "error_ellipse_semi_minor": values.get("errorEllipseSemiMinor"),
            }
            op.upsert("lightning_strikes", row)
            count += 1

    return count


# ---------------------------------------------------------------------------
# Update Orchestrator
# ---------------------------------------------------------------------------
def update(configuration: dict, state: dict):
    validate_configuration(configuration)
    enabled = _parse_enabled_apis(configuration)
    new_state = dict(state)

    log.info(f"Starting sync — enabled APIs: {', '.join(sorted(enabled))}")

    # --- Observations & Forecasts API ---
    if "observations" in enabled:
        log.info("Syncing stations...")
        _sync_stations(configuration)

        log.info("Syncing daily forecasts...")
        new_state = _sync_daily_forecasts(configuration, new_state)

        log.info("Syncing daily observations...")
        new_state = _sync_daily_observations(configuration, new_state)
        op.checkpoint(new_state)

        log.info("Syncing hourly forecasts...")
        new_state = _sync_hourly_forecasts(configuration, new_state)

        log.info("Syncing hourly observations...")
        new_state = _sync_hourly_observations(configuration, new_state)
        op.checkpoint(new_state)

    # --- Weather Conditions API ---
    if "conditions" in enabled:
        log.info("Syncing weather conditions...")
        new_state = _sync_conditions(configuration, new_state)
        op.checkpoint(new_state)

    # --- Lightning API ---
    if "lightning" in enabled:
        log.info("Syncing lightning strikes...")
        new_state = _sync_lightning(configuration, new_state)

    # Final checkpoint
    op.checkpoint(new_state)
    log.info(f"Sync complete. State: {json.dumps(new_state)}")


# ---------------------------------------------------------------------------
# Connector entry point
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
