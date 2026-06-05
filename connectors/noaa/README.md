# NOAA Weather API Connector Example

## Connector overview
This connector retrieves weather observation data and active alerts from the [National Weather Service (NOAA) API](https://www.weather.gov/documentation/services-web-api) and syncs it to Fivetran destinations. The connector fetches current observations from specified weather stations and weather alerts for designated areas, supporting incremental syncing to efficiently process weather data over time.
## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/noaa
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Automatically discovers and syncs weather stations by state code
- Supports manual specification of individual weather stations
- Fetches weather observations from multiple NOAA weather stations
- Retrieves active weather alerts filtered by US state or area
- Supports incremental sync using timestamp-based checkpointing
- Automatic retry logic with exponential backoff for API requests
- Comprehensive weather metrics, including temperature, wind, pressure, and precipitation
- Detailed alert information, including severity, urgency, and affected zones
- No authentication required (public API)
- Modular architecture with dedicated functions for observations and alerts

## Configuration file
The connector requires only a User-Agent identifier. All other parameters are optional and can be omitted.

Minimal Configuration (fetches all available data):
```json
{
  "user_agent": "<YOUR_APPLICATION_NAME_AND_CONTACT_EMAIL>"
}
```

Full Configuration (with all optional parameters):
```json
{
  "user_agent": "<YOUR_APPLICATION_NAME_AND_CONTACT_EMAIL>",
  "state_code": "<OPTIONAL_US_STATE_CODE_FOR_OBSERVATIONS>",
  "station_ids": "<OPTIONAL_COMMA_SEPARATED_STATION_IDS>",
  "alert_area": "<OPTIONAL_US_STATE_CODE_FOR_ALERTS>",
  "start_date": "<OPTIONAL_YYYY-MM-DD_START_DATE>"
}
```

### Configuration parameters

- `user_agent` (required): Your application name and contact information (e.g., "MyWeatherApp (contact@example.com)"). The National Weather Service requires this to identify your application.
- `state_code` (optional): Two-letter US state code to automatically fetch all weather stations in that state (e.g., "IL", "CA"). Default behavior if omitted: fetches all stations from all states using pagination (500 stations per page).
- `station_ids` (optional): Comma-separated list of specific weather station identifiers (e.g., "KORD, KMDW, KPWK"). This takes precedence over state_code if both are provided. Default behavior if omitted: uses state_code logic or fetches from all states.
- `alert_area` (optional): Two-letter US state code for filtering weather alerts (e.g., "IL", "CA"). Default behavior if omitted: fetches all active weather alerts across the United States.
- `start_date` (optional): Date in YYYY-MM-DD format to start syncing observations from (e.g., "2025-01-01"). Default behavior if omitted: starts syncing from the current time (no historical backfill).

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector uses only the pre-installed packages in the Fivetran environment and does not require any additional dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector accesses the NOAA Weather API, which is a public API that does not require authentication. However, the API requires a User-Agent header to identify your application. This is a best practice implemented by the National Weather Service to track API usage and contact users if necessary. The User-Agent should include your application name and contact information (refer to the `make_api_request` function).

## Data handling
The connector processes two types of data from the NOAA API:

Observations - Weather station observations are fetched using the `/stations/{station_id}/observations` endpoint. The connector:
- Implements pagination to fetch ALL observations (500 observations per page)
- Continues fetching pages until all observations are retrieved
- Extracts comprehensive weather metrics from the GeoJSON response
- Normalizes nested data structures into flat columns
- Uses the observation ID as the primary key for upserts
- Checkpoints every 100 records to ensure resumability

Alerts - Active weather alerts are fetched using the `/alerts/active` endpoint. The connector:
- Filters alerts by state/area if configured
- Extracts alert metadata, including severity, urgency, and affected zones
- Converts complex arrays and objects to string representations
- Uses the alert ID as the primary key for upserts
- Captures active alerts at the time of sync

State management uses ISO 8601 timestamps to track the last sync time, enabling incremental syncing for observations (see the `update` function).

## Error handling
The connector implements comprehensive error handling through multiple layers:
- Configuration validation ensures the required User-Agent parameter is present
- API requests include retry logic with exponential backoff for transient errors (refer to the `make_api_request` function)
- Specific exception catching for HTTP timeouts, rate limiting (429), and service unavailable (503) errors
- Client errors (400, 404) fail fast without retry
- Individual station failures are logged and skipped without stopping the entire sync (refer to the `fetch_observations_for_station` function)
- Detailed error logging with context information for debugging
- Runtime error wrapping for sync failures to provide clear error messages

## Tables created

OBSERVATION - Contains weather observations from NOAA weather stations

| Column | Type | Description |
|--------|------|-------------|
| id | STRING (Primary Key) | Unique identifier for the observation |
| station | STRING | Weather station identifier URI |
| timestamp | STRING | Observation timestamp in ISO 8601 format |
| raw_message | STRING | Raw METAR message |
| text_description | STRING | Human-readable weather description |
| temperature_c | FLOAT | Temperature in Celsius |
| dewpoint_c | FLOAT | Dewpoint in Celsius |
| wind_direction_degrees | FLOAT | Wind direction in degrees |
| wind_speed_kmh | FLOAT | Wind speed in kilometers per hour |
| wind_gust_kmh | FLOAT | Wind gust speed in kilometers per hour |
| barometric_pressure_pa | FLOAT | Barometric pressure in Pascals |
| sea_level_pressure_pa | FLOAT | Sea level pressure in Pascals |
| visibility_m | FLOAT | Visibility in meters |
| max_temperature_last_24_hours_c | FLOAT | Maximum temperature in last 24 hours (Celsius) |
| min_temperature_last_24_hours_c | FLOAT | Minimum temperature in last 24 hours (Celsius) |
| precipitation_last_hour_mm | FLOAT | Precipitation in last hour (millimeters) |
| precipitation_last_3_hours_mm | FLOAT | Precipitation in last 3 hours (millimeters) |
| precipitation_last_6_hours_mm | FLOAT | Precipitation in last 6 hours (millimeters) |
| relative_humidity_percent | FLOAT | Relative humidity percentage |
| wind_chill_c | FLOAT | Wind chill in Celsius |
| heat_index_c | FLOAT | Heat index in Celsius |
| cloud_layers | STRING | Cloud layer information as string |
| elevation_m | FLOAT | Station elevation in meters |
| latitude | FLOAT | Station latitude |
| longitude | FLOAT | Station longitude |

ALERT - Contains active weather alerts from NOAA

| Column | Type | Description |
|--------|------|-------------|
| id | STRING (Primary Key) | Unique identifier for the alert |
| area_desc | STRING | Description of affected area |
| geocode_same | STRING | SAME geocode array as string |
| geocode_ugc | STRING | UGC geocode array as string |
| affected_zones | STRING | Array of affected zone URIs as string |
| sent | STRING | Time alert was sent |
| effective | STRING | Time alert becomes effective |
| onset | STRING | Time event begins |
| expires | STRING | Time alert expires |
| ends | STRING | Time event ends |
| status | STRING | Alert status (e.g., Actual, Test) |
| message_type | STRING | Message type (e.g., Alert, Update) |
| category | STRING | Event category (e.g., Met, Health) |
| severity | STRING | Event severity (e.g., Severe, Moderate) |
| certainty | STRING | Event certainty (e.g., Likely, Possible) |
| urgency | STRING | Event urgency (e.g., Immediate, Expected) |
| event | STRING | Event type (e.g., Winter Storm Warning) |
| sender | STRING | Sender email address |
| sender_name | STRING | Sender organization name |
| headline | STRING | Alert headline |
| description | STRING | Detailed alert description |
| instruction | STRING | Recommended actions |
| response | STRING | Response type (e.g., Prepare, Evacuate) |
| parameters | STRING | Additional parameters as string |
| geometry_type | STRING | Geometry type for affected area |

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.