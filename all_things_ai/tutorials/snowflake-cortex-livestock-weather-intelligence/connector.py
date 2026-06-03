"""
Livestock Weather Intelligence - Fivetran Custom Connector with Snowflake Cortex AI

Chains weather forecast APIs with Snowflake Cortex Agent to provide actionable
livestock health intelligence based on predicted weather conditions.

APIs Used:
1. Zippopotam.us - ZIP code to coordinates
2. National Weather Service - Weather forecasts
3. Snowflake Cortex Agent - Livestock health risk analysis

Features:
- Weather forecast sync for farm ZIP codes
- Real-time AI enrichment during ingestion
- Livestock health risk assessment based on weather
- Farm-specific recommendations
- Historical weather-health correlations
- Cost control with max_enrichments limit

See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For regular expression operations in parsing agent responses function
import re

# API Configuration Constants
__BASE_URL_ZIPPOPOTAM = "http://api.zippopotam.us/us"
__BASE_URL_NWS = "https://api.weather.gov"
__API_TIMEOUT_SECONDS = 10

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__NWS_RATE_LIMIT_DELAY = 1.0
__ZIP_API_RATE_LIMIT_DELAY = 0.5

# Default Configuration Values
__DEFAULT_MAX_ENRICHMENTS = 10
__DEFAULT_CORTEX_TIMEOUT = 60
__DEFAULT_USER_AGENT = "LivestockWeatherIntelligence/1.0"

# Cortex Agent Configuration
__CORTEX_AGENT_ENDPOINT = "/api/v2/cortex/agent:run"
__SEMANTIC_VIEW_PATH = "HOL_DATABASE.AGR_0729_CLAUDE.AGR_LIVESTOCK_OVERALL_PERFORMANCE_SV"


def flatten_dict(d, parent_key="", sep="_"):
    """
    Flatten nested dictionaries and serialize lists to JSON strings.

    This is REQUIRED for Fivetran compatibility as nested structures
    cannot be directly inserted into warehouse tables.

    Args:
        d: Dictionary to flatten
        parent_key: Prefix for nested keys (used in recursion)
        sep: Separator between nested key levels

    Returns:
        Flattened dictionary with all nested structures resolved
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, (list, tuple)):
            items.append((new_key, json.dumps(v) if v else None))
        else:
            items.append((new_key, v))
    return dict(items)


def fetch_data_with_retry(session, url, params=None, headers=None):
    """
    Fetch data from API with exponential backoff retry logic.

    Implements industry-standard retry pattern for transient failures
    including rate limits (429) and server errors (5xx).

    Args:
        session: requests.Session object for connection pooling
        url: Full URL to fetch
        params: Optional query parameters
        headers: Optional request headers

    Returns:
        JSON response as dictionary

    Raises:
        RuntimeError: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(
                url, params=params, headers=headers, timeout=__API_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.error(f"Connection failed after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}")

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.error(f"Timeout after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}")

        except requests.exceptions.RequestException as e:
            should_retry = (
                hasattr(e, "response")  # noqa: W504
                and e.response is not None  # noqa: W503
                and hasattr(e.response, "status_code")  # noqa: W503
                and e.response.status_code in __RETRYABLE_STATUS_CODES  # noqa: W503
            )

            if should_retry and attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Request failed with status {e.response.status_code}, "
                    f"retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                status_code = (
                    e.response.status_code
                    if hasattr(e, "response") and e.response is not None
                    else "N/A"
                )
                log.error(
                    f"Failed after {__MAX_RETRIES} attempts. "
                    f"URL: {url}, Status: {status_code}, Error: {str(e)}"
                )
                raise RuntimeError(f"API request failed after {__MAX_RETRIES} attempts: {e}")


def parse_farm_zip_mapping(mapping_str):
    """
    Parse farm-to-ZIP mapping string into dictionary.

    Mapping format allows multiple farms per ZIP code, supporting
    complex farm network configurations.

    Args:
        mapping_str: String in format "ZIP:FARM1,FARM2|ZIP:FARM3"

    Returns:
        Dictionary mapping ZIP codes to lists of farm IDs
    """
    if not mapping_str:
        return {}

    mapping = {}
    for zip_farms in mapping_str.split("|"):
        if ":" not in zip_farms:
            continue
        zip_code, farms_str = zip_farms.split(":", 1)
        mapping[zip_code.strip()] = [f.strip() for f in farms_str.split(",")]

    return mapping


def get_coordinates_from_zip(session, zip_code):
    """
    Get geographic coordinates for a ZIP code using Zippopotam.us API.

    Args:
        session: requests.Session object for connection pooling
        zip_code: 5-digit US ZIP code as string

    Returns:
        Dictionary containing latitude, longitude, place_name, state,
        and state_abbr, or None if ZIP code not found
    """
    url = f"{__BASE_URL_ZIPPOPOTAM}/{zip_code}"

    try:
        data = fetch_data_with_retry(session, url)

        if "places" in data and len(data["places"]) > 0:
            place = data["places"][0]
            return {
                "zip_code": zip_code,
                "latitude": float(place["latitude"]),
                "longitude": float(place["longitude"]),
                "place_name": place["place name"],
                "state": place["state"],
                "state_abbr": place["state abbreviation"],
            }
        else:
            log.warning(f"No location data found for ZIP code {zip_code}")
            return None

    except RuntimeError as e:
        if "404" in str(e):
            log.warning(f"ZIP code {zip_code} not found (404)")
            return None
        raise
    except Exception as e:
        log.warning(f"Error fetching coordinates for ZIP {zip_code}: {str(e)}")
        return None


def get_weather_forecast(session, latitude, longitude, user_agent):
    """
    Get weather forecast from National Weather Service API.

    NWS API requires a two-step process:
    1. Convert lat/long to grid coordinates
    2. Fetch forecast for grid location

    Args:
        session: requests.Session object for connection pooling
        latitude: Latitude as float
        longitude: Longitude as float
        user_agent: User-Agent header required by NWS

    Returns:
        Dictionary containing office, grid coordinates, and forecast data,
        or None if API request fails
    """
    headers = {"User-Agent": user_agent}

    try:
        # Step 1: Get grid coordinates
        points_url = f"{__BASE_URL_NWS}/points/{latitude},{longitude}"
        log.info(f"Fetching grid coordinates for {latitude},{longitude}")

        points_data = fetch_data_with_retry(session, points_url, headers=headers)

        properties = points_data.get("properties", {})
        office = properties.get("gridId")
        grid_x = properties.get("gridX")
        grid_y = properties.get("gridY")

        if not all([office, grid_x, grid_y]):
            log.warning(f"Missing grid data for {latitude},{longitude}")
            return None

        # Rate limiting - NWS requests 1 second between calls
        time.sleep(__NWS_RATE_LIMIT_DELAY)

        # Step 2: Get forecast
        forecast_url = f"{__BASE_URL_NWS}/gridpoints/{office}/{grid_x},{grid_y}/forecast"
        log.info(f"Fetching forecast from {office} office, grid {grid_x},{grid_y}")

        forecast_data = fetch_data_with_retry(session, forecast_url, headers=headers)

        return {"office": office, "grid_x": grid_x, "grid_y": grid_y, "forecast": forecast_data}

    except Exception as e:
        log.warning(f"Error fetching weather forecast: {str(e)}")
        return None


def parse_agent_response(response_text):
    """
    Parse the Cortex Agent's structured response into enriched fields.

    Extracts structured sections from agent response with robust parsing
    and fallback default values.

    Args:
        response_text: Full text response from Cortex Agent

    Returns:
        Dictionary with enriched fields ready for record update
    """

    enriched = {}

    # Default values
    enriched["agent_livestock_risk_assessment"] = "No assessment available"
    enriched["agent_affected_farms"] = json.dumps([])
    enriched["agent_species_risk_matrix"] = json.dumps({})
    enriched["agent_recommended_actions"] = "Monitor livestock regularly"
    enriched["agent_historical_correlation"] = "No historical data available"

    response_upper = response_text.upper()

    # Extract RISK ASSESSMENT section
    if "RISK ASSESSMENT:" in response_upper:
        start = response_upper.find("RISK ASSESSMENT:") + len("RISK ASSESSMENT:")
        end = response_upper.find("AFFECTED FARMS:", start)
        if end == -1:
            end = start + 500
        section = response_text[start:end].strip()
        if section and len(section) > 10:
            enriched["agent_livestock_risk_assessment"] = section[:1000]

    # Extract AFFECTED FARMS section
    if "AFFECTED FARMS:" in response_upper:
        start = response_upper.find("AFFECTED FARMS:") + len("AFFECTED FARMS:")
        end = response_upper.find("SPECIES RISK MATRIX:", start)
        if end == -1:
            end = start + 200
        section = response_text[start:end].strip()

        farm_ids = []
        if section and "no high-risk" not in section.lower():
            farm_pattern = r"FARM_\d{6}"
            farm_ids = re.findall(farm_pattern, section)
            if not farm_ids:
                farm_ids = [f.strip() for f in section.split(",") if "FARM" in f.upper()]

        enriched["agent_affected_farms"] = json.dumps(list(set(farm_ids)))

    # Extract SPECIES RISK MATRIX section
    if "SPECIES RISK MATRIX:" in response_upper:
        start = response_upper.find("SPECIES RISK MATRIX:") + len("SPECIES RISK MATRIX:")
        end = response_upper.find("RECOMMENDED ACTIONS:", start)
        if end == -1:
            end = start + 300
        section = response_text[start:end].strip()

        species_risks = {}
        for line in section.split("\n"):
            if ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    species = parts[0].strip().lstrip("-*• ")
                    risk = parts[1].strip().split()[0] if parts[1].strip() else ""
                    if species and risk:
                        species_risks[species] = risk

        enriched["agent_species_risk_matrix"] = json.dumps(species_risks)

    # Extract RECOMMENDED ACTIONS section
    if "RECOMMENDED ACTIONS:" in response_upper:
        start = response_upper.find("RECOMMENDED ACTIONS:") + len("RECOMMENDED ACTIONS:")
        end = response_upper.find("HISTORICAL CORRELATION:", start)
        if end == -1:
            end = start + 800
        section = response_text[start:end].strip()
        if section and len(section) > 10:
            enriched["agent_recommended_actions"] = section[:1500]

    # Extract HISTORICAL CORRELATION section
    if "HISTORICAL CORRELATION:" in response_upper:
        start = response_upper.find("HISTORICAL CORRELATION:") + len("HISTORICAL CORRELATION:")
        section = response_text[start : start + 800].strip()
        if section and len(section) > 10:
            enriched["agent_historical_correlation"] = section[:1000]

    return enriched


def call_cortex_livestock_agent(session, config, weather_record):
    """
    Call Snowflake Cortex Agent via REST API for livestock health analysis.

    Args:
        session: requests.Session object with proper authentication
        config: Configuration dictionary containing Snowflake credentials
        weather_record: Weather forecast record to analyze

    Returns:
        Dictionary with enriched fields, or None if agent call fails
    """
    snowflake_account = config.get("snowflake_account")
    pat_token = config.get("snowflake_pat_token")
    timeout = int(config.get("cortex_timeout", str(__DEFAULT_CORTEX_TIMEOUT)))

    farm_ids = weather_record.get("farm_ids", [])
    if not farm_ids:
        return None

    farm_ids_str = ", ".join(farm_ids)
    url = f"https://{snowflake_account}{__CORTEX_AGENT_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {pat_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    prompt = f"""Analyze weather impact on livestock health for farms: {farm_ids_str}

**WEATHER FORECAST:**
- Location: {weather_record.get('place_name')}, {weather_record.get('state')} (ZIP: {weather_record.get('zip_code')})
- Period: {weather_record.get('period_name')}
- Time: {weather_record.get('start_time')} to {weather_record.get('end_time')}
- Temperature: {weather_record.get('temperature')}°{weather_record.get('temperature_unit')}
- Temperature Trend: {weather_record.get('temperature_trend') or 'Stable'}
- Conditions: {weather_record.get('short_forecast')}
- Detailed: {weather_record.get('detailed_forecast')}
- Wind: {weather_record.get('wind_speed')}, {weather_record.get('wind_direction')}

**YOUR TASK:**
Query the AGR_RECORDS table using your Cortex Analyst tool to analyze current livestock health for these farms and assess weather-related risks.

Provide your response in these exact sections:

RISK ASSESSMENT:
[Overall risk level and 2-3 sentence summary]

AFFECTED FARMS:
[Comma-separated farm IDs with concerns, or "No high-risk farms identified"]

SPECIES RISK MATRIX:
[Format: Species: RiskLevel (one per line)]

RECOMMENDED ACTIONS:
1. [Specific action with timeframe]
2. [Specific action with timeframe]
3. [Specific action with timeframe]

HISTORICAL CORRELATION:
[Past weather-health patterns or "No similar historical events found"]

Use real data from AGR_RECORDS to make specific, actionable recommendations."""

    payload = {
        "model": "llama3.3-70b",
        "response_instruction": "You are a livestock health expert. Use your Cortex Analyst tool to query AGR_RECORDS data and provide data-driven livestock health risk assessments based on weather forecasts.",
        "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "Analyst1"}}],
        "tool_resources": {"Analyst1": {"semantic_view": __SEMANTIC_VIEW_PATH}},
        "tool_choice": {"type": "auto"},
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
        response.raise_for_status()

        agent_response = ""
        for line in response.iter_lines():
            if line:
                line_text = line.decode("utf-8")
                if line_text.startswith("data: "):
                    try:
                        data = json.loads(line_text[6:])
                        if not isinstance(data, dict):
                            continue

                        if data.get("object") == "message.delta":
                            delta = data.get("delta", {})
                            content = delta.get("content", [])

                            if not isinstance(content, list):
                                continue

                            for item in content:
                                if not isinstance(item, dict):
                                    continue

                                if item.get("type") == "text":
                                    agent_response += item.get("text", "")

                                elif item.get("type") == "tool_results":
                                    tool_results = item.get("tool_results")
                                    agent_response += extract_tool_results_text(tool_results)

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        log.warning(f"Error parsing SSE line: {e}")
                        continue

                elif line_text.startswith("event: done"):
                    break

        if not agent_response:
            log.warning(f"Empty response from agent for ZIP {weather_record.get('zip_code')}")
            return None

        enriched = parse_agent_response(agent_response)
        log.info(
            f"Enriched forecast for {weather_record.get('zip_code')} {weather_record.get('period_name')}"
        )
        return enriched

    except requests.exceptions.Timeout:
        log.warning(f"Agent timeout after {timeout}s for ZIP {weather_record.get('zip_code')}")
        return None
    except Exception as e:
        log.warning(f"Agent error for ZIP {weather_record.get('zip_code')}: {e}")
        return None


def extract_tool_results_text(tool_results):
    """
    Extract text content from Cortex Agent tool results.

    Args:
        tool_results: Tool results from Cortex Agent response (dict or list)

    Returns:
        Extracted text content as string
    """
    result_text = ""

    if isinstance(tool_results, dict):
        tool_content = tool_results.get("content", [])
        if isinstance(tool_content, list):
            for result_item in tool_content:
                if not isinstance(result_item, dict):
                    continue
                if result_item.get("type") == "json":
                    json_data = result_item.get("json", {})
                    if isinstance(json_data, dict) and "text" in json_data:
                        result_text += json_data["text"] + "\n"
                elif result_item.get("type") == "text":
                    result_text += result_item.get("text", "")

    elif isinstance(tool_results, list):
        for result_item in tool_results:
            if not isinstance(result_item, dict):
                continue
            if result_item.get("type") == "json":
                json_data = result_item.get("json", {})
                if isinstance(json_data, dict) and "text" in json_data:
                    result_text += json_data["text"] + "\n"
            elif result_item.get("type") == "text":
                result_text += result_item.get("text", "")

    return result_text


def build_weather_record(zip_code, location_data, weather_data, period, farm_ids):
    """
    Build a weather record from location and forecast data.

    Args:
        zip_code: ZIP code string
        location_data: Location data from Zippopotam.us
        weather_data: Weather data from NWS
        period: Forecast period data
        farm_ids: List of farm IDs for this ZIP code

    Returns:
        Dictionary containing the weather record
    """
    return {
        "zip_code": zip_code,
        "place_name": location_data["place_name"],
        "state": location_data["state"],
        "state_abbr": location_data["state_abbr"],
        "latitude": location_data["latitude"],
        "longitude": location_data["longitude"],
        "farm_ids": farm_ids,
        "farm_count": len(farm_ids),
        "nws_office": weather_data["office"],
        "grid_x": weather_data["grid_x"],
        "grid_y": weather_data["grid_y"],
        "period_number": period.get("number"),
        "period_name": period.get("name"),
        "start_time": period.get("startTime"),
        "end_time": period.get("endTime"),
        "is_daytime": period.get("isDaytime"),
        "temperature": period.get("temperature"),
        "temperature_unit": period.get("temperatureUnit"),
        "temperature_trend": period.get("temperatureTrend"),
        "wind_speed": period.get("windSpeed"),
        "wind_direction": period.get("windDirection"),
        "icon": period.get("icon"),
        "short_forecast": period.get("shortForecast"),
        "detailed_forecast": period.get("detailedForecast"),
    }


def add_enrichment_fields(record, enriched_fields, farm_ids):
    """
    Add AI enrichment fields to a weather record.

    Args:
        record: Weather record dictionary
        enriched_fields: Enrichment data from Cortex Agent, or None
        farm_ids: List of farm IDs for this ZIP code

    Returns:
        Updated record with enrichment fields
    """
    if enriched_fields:
        record.update(enriched_fields)
    elif not farm_ids:
        record.update(
            {
                "agent_livestock_risk_assessment": "No farms mapped to this ZIP code",
                "agent_affected_farms": json.dumps([]),
                "agent_species_risk_matrix": json.dumps({}),
                "agent_recommended_actions": "Configure farm_zip_mapping to enable analysis",
                "agent_historical_correlation": "Farm mapping required",
            }
        )
    else:
        record.update(
            {
                "agent_livestock_risk_assessment": None,
                "agent_affected_farms": None,
                "agent_species_risk_matrix": None,
                "agent_recommended_actions": None,
                "agent_historical_correlation": None,
            }
        )
    return record


def process_zip_code(
    zip_code,
    farm_ids,
    weather_session,
    cortex_session,
    configuration,
    enable_cortex,
    enriched_count,
    max_enrichments,
):
    """
    Process a single ZIP code: fetch weather and optionally enrich with AI.

    Args:
        zip_code: ZIP code to process
        farm_ids: List of farm IDs for this ZIP code
        weather_session: requests.Session for weather APIs
        cortex_session: requests.Session for Cortex API (or None)
        configuration: Configuration dictionary
        enable_cortex: Whether Cortex enrichment is enabled
        enriched_count: Current count of enrichments performed
        max_enrichments: Maximum enrichments allowed

    Returns:
        Tuple of (records_list, new_enriched_count)
    """
    user_agent = configuration.get("user_agent", __DEFAULT_USER_AGENT)
    records = []

    location_data = get_coordinates_from_zip(weather_session, zip_code)
    if not location_data:
        log.warning(f"Skipping ZIP code {zip_code} - no location data")
        return records, enriched_count

    time.sleep(__ZIP_API_RATE_LIMIT_DELAY)

    weather_data = get_weather_forecast(
        weather_session, location_data["latitude"], location_data["longitude"], user_agent
    )

    if not weather_data or "forecast" not in weather_data:
        log.warning(f"No forecast data for ZIP code {zip_code}")
        return records, enriched_count

    periods = weather_data["forecast"].get("properties", {}).get("periods", [])
    if not periods:
        log.warning(f"No forecast periods for ZIP code {zip_code}")
        return records, enriched_count

    for period in periods:
        if period.get("number") is None:
            continue

        record = build_weather_record(zip_code, location_data, weather_data, period, farm_ids)

        enriched_fields = None
        if enable_cortex and enriched_count < max_enrichments and farm_ids:
            enriched_fields = call_cortex_livestock_agent(cortex_session, configuration, record)
            if enriched_fields:
                enriched_count += 1

        record = add_enrichment_fields(record, enriched_fields, farm_ids)
        records.append(record)

    log.info(f"Processed {len(periods)} periods for ZIP {zip_code}")
    return records, enriched_count


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = ["zip_codes", "user_agent"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate ZIP codes format (5-digit numbers)
    zip_codes = configuration.get("zip_codes", "")
    zip_list = [z.strip() for z in zip_codes.split(",") if z.strip()]
    if not zip_list:
        raise ValueError("No valid ZIP codes provided")
    for z in zip_list:
        if not z.isdigit() or len(z) != 5:
            raise ValueError(f"Invalid ZIP code format: {z}. ZIP codes must be 5-digit numbers.")

    # Validate numeric values if present
    if "max_enrichments" in configuration:
        try:
            max_enr = int(configuration["max_enrichments"])
            if max_enr < 0:
                raise ValueError("max_enrichments must be non-negative")
        except ValueError as e:
            if "non-negative" in str(e):
                raise
            raise ValueError("Invalid max_enrichments value: must be a number")

    if "cortex_timeout" in configuration:
        try:
            timeout = int(configuration["cortex_timeout"])
            if timeout <= 0:
                raise ValueError("cortex_timeout must be positive")
        except ValueError as e:
            if "positive" in str(e):
                raise
            raise ValueError("Invalid cortex_timeout value: must be a number")

    # Validate Snowflake account format if Cortex is enabled
    enable_cortex = configuration.get("enable_cortex_enrichment", "false").lower() == "true"
    if enable_cortex:
        snowflake_account = configuration.get("snowflake_account", "")
        snowflake_pat_token = configuration.get("snowflake_pat_token", "")

        if not snowflake_account:
            raise ValueError("snowflake_account is required when enable_cortex_enrichment is true")
        if not snowflake_pat_token:
            raise ValueError(
                "snowflake_pat_token is required when enable_cortex_enrichment is true"
            )
        if not snowflake_account.endswith("snowflakecomputing.com"):
            raise ValueError("snowflake_account must end with 'snowflakecomputing.com'")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Returns:
        List of table definitions with primary keys
    """
    return [
        {"table": "livestock_weather_intelligence", "primary_key": ["zip_code", "period_number"]}
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning(
        "Example: all_things_ai/tutorials : snowflake-cortex-livestock-weather-intelligence"
    )

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration)

    # Read state from previous sync
    last_sync = state.get("last_sync", 0)
    previous_forecasts = state.get("forecasts_synced", 0)
    previous_enrichments = state.get("enrichments_completed", 0)
    processed_zip_codes = state.get("processed_zip_codes", [])

    if last_sync:
        log.info(f"Previous sync: {previous_forecasts} forecasts, {previous_enrichments} enriched")
        log.info(f"Previously processed {len(processed_zip_codes)} ZIP codes")

    # Parse configuration
    zip_codes_str = configuration.get("zip_codes", "")
    all_zip_codes = [z.strip() for z in zip_codes_str.split(",") if z.strip()]
    farm_mapping = parse_farm_zip_mapping(configuration.get("farm_zip_mapping", ""))

    # Determine which ZIP codes still need processing
    zip_codes = [z for z in all_zip_codes if z not in processed_zip_codes]

    if not zip_codes:
        log.info(f"All {len(all_zip_codes)} ZIP codes already processed. Sync complete.")
        return

    if processed_zip_codes:
        log.info(
            f"Resuming sync: {len(zip_codes)} ZIP codes remaining (of {len(all_zip_codes)} total)"
        )

    # Cortex enrichment settings
    enable_cortex = configuration.get("enable_cortex_enrichment", "false").lower() == "true"
    max_enrichments = int(configuration.get("max_enrichments", str(__DEFAULT_MAX_ENRICHMENTS)))

    if enable_cortex:
        log.info(f"Cortex enrichment ENABLED: max_enrichments={max_enrichments}")
    else:
        log.info("Cortex enrichment DISABLED")

    log.info(f"Starting weather forecast sync for {len(zip_codes)} ZIP codes")
    if farm_mapping:
        log.info(f"Farm mapping configured for {len(farm_mapping)} ZIP codes")

    # Set up sessions
    weather_session = requests.Session()
    cortex_session = requests.Session() if enable_cortex else None

    # Initialize counters from previous state to maintain cumulative totals
    total_forecasts = previous_forecasts
    enriched_count = previous_enrichments

    try:
        for zip_code in zip_codes:
            log.info(f"Processing ZIP code: {zip_code}")
            farm_ids = farm_mapping.get(zip_code, [])

            try:
                records, enriched_count = process_zip_code(
                    zip_code,
                    farm_ids,
                    weather_session,
                    cortex_session,
                    configuration,
                    enable_cortex,
                    enriched_count,
                    max_enrichments,
                )

                for record in records:
                    flattened_record = flatten_dict(record)

                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The first argument is the name of the destination table.
                    # The second argument is a dictionary containing the record to be upserted.
                    op.upsert(table="livestock_weather_intelligence", data=flattened_record)
                    total_forecasts += 1

                # Mark this ZIP code as processed
                processed_zip_codes.append(zip_code)

                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(
                    state={
                        "last_sync": time.time(),
                        "processed_zip_codes": processed_zip_codes,
                        "forecasts_synced": total_forecasts,
                        "enrichments_completed": enriched_count,
                    }
                )

                log.info(
                    f"Checkpointed after ZIP {zip_code} ({len(processed_zip_codes)}/{len(all_zip_codes)} complete)"
                )

            except requests.exceptions.RequestException as e:
                log.warning(f"Failed to fetch weather for ZIP {zip_code}: {str(e)}")
                # Don't add to processed_zip_codes - will retry on next sync
                continue

        log.info(
            f"Sync complete: {total_forecasts} forecasts from {len(zip_codes)} ZIP codes, {enriched_count} enriched"
        )

    except Exception as e:
        log.error(f"Unexpected error during sync: {str(e)}")
        raise

    finally:
        weather_session.close()
        if cortex_session:
            cortex_session.close()


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
    connector.debug()
