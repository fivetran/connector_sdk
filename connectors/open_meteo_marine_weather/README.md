# Open-Meteo Marine Weather Connector Example

## Connector overview

This connector syncs marine weather data from the [Open-Meteo Marine Weather API](https://open-meteo.com/en/docs/marine-weather-api) for a configured coastal location. It delivers hourly and daily marine conditions including wave height, wave period, wave direction, swell data, and wind wave metrics.

No authentication is required — Open-Meteo is a free, open-source weather API with no API key needed.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs hourly marine weather data (wave height, direction, period, swell, wind waves)
- Syncs daily aggregated marine data (max wave height, dominant direction, max period)
- Incremental sync with date-based cursor and 1-day overlap for deduplication
- No authentication required (free, open API)
- Configurable forecast window (1-16 days ahead)
- Configurable historical window (0-92 days back)
- Exponential backoff retry logic for transient API errors

## Configuration file

Create a `configuration.json` file with the following parameters:

```json
{
    "latitude": "<YOUR_LATITUDE>",
    "longitude": "<YOUR_LONGITUDE>",
    "timezone": "<TIMEZONE>",
    "forecast_days": "<FORECAST_DAYS>",
    "past_days": "<PAST_DAYS>"
}
```

Configuration parameters:

- `latitude` (required) - The latitude of the coastal location to monitor (e.g., `37.75` for San Francisco coast)
- `longitude` (required) - The longitude of the coastal location to monitor (e.g., `-122.52` for San Francisco coast)
- `timezone` (optional) - The timezone for timestamps in the response; defaults to `America/Los_Angeles`
- `forecast_days` (optional) - The number of forecast days to fetch (1-16); defaults to `7`
- `past_days` (optional) - The number of past days to include in each sync (0-92); defaults to `7`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

No authentication is required. The Open-Meteo Marine Weather API is free and open — no API key, token, or signup needed.

## Pagination

The Open-Meteo API does not use pagination. All requested data for the configured date range is returned in a single response. The connector manages incremental sync by tracking the last synced date and requesting data from that point forward with a 1-day overlap to handle inclusive date boundaries.

## Data handling

- Hourly data is returned as parallel arrays (one array per metric, indexed by timestamp). The connector normalizes these into one row per timestamp.
- Daily data follows the same parallel-array structure, normalized to one row per date.
- The composite primary key (`location_id` + `timestamp`/`date`) ensures upserts correctly deduplicate records when date ranges overlap between syncs.
- The `location_id` is derived from the configured latitude and longitude (e.g., `37.75_-122.52`).

## Error handling

- Connection errors and timeouts: retried with exponential backoff up to 3 attempts.
- Retryable HTTP status codes (429, 500, 502, 503, 504): retried with exponential backoff.
- Non-retryable HTTP errors (4xx): fail immediately with descriptive error message.
- Records missing primary key fields are skipped with an informational log message.

Refer to the `fetch_data_with_retry` function in `connector.py`.

## Tables created

The connector creates the `MARINE_HOURLY` and `MARINE_DAILY` tables.

### MARINE_HOURLY

The `MARINE_HOURLY` table consists of the following columns:
- `location_id` (STRING, primary key): Composite location identifier from latitude and longitude
- `timestamp` (UTC_DATETIME, primary key): The hourly timestamp for this observation
- `wave_height` (FLOAT): Significant wave height in meters
- `wave_direction` (FLOAT): Mean wave direction in degrees
- `wave_period` (FLOAT): Mean wave period in seconds
- `wind_wave_height` (FLOAT): Wind wave height in meters
- `wind_wave_direction` (FLOAT): Wind wave direction in degrees
- `wind_wave_period` (FLOAT): Wind wave period in seconds
- `swell_wave_height` (FLOAT): Swell wave height in meters
- `swell_wave_direction` (FLOAT): Swell wave direction in degrees
- `swell_wave_period` (FLOAT): Swell wave period in seconds
- `ocean_current_velocity` (FLOAT): Ocean surface current speed in km/h
- `ocean_current_direction` (FLOAT): Ocean surface current direction in degrees
- `elevation` (FLOAT): Location elevation in meters as reported by the API (typically 0 for marine locations)
- `timezone` (STRING): Timezone of the location as reported by the API

### MARINE_DAILY

The `MARINE_DAILY` table consists of the following columns:
- `location_id` (STRING, primary key): Composite location identifier from latitude and longitude
- `date` (STRING, primary key): The date for this daily aggregation
- `wave_height_max` (FLOAT): Maximum wave height for the day in meters
- `wave_direction_dominant` (FLOAT): Dominant wave direction for the day in degrees
- `wave_period_max` (FLOAT): Maximum wave period for the day in seconds
- `wind_wave_height_max` (FLOAT): Maximum wind wave height for the day in meters
- `wind_wave_direction_dominant` (FLOAT): Dominant wind wave direction for the day in degrees
- `wind_wave_period_max` (FLOAT): Maximum wind wave period for the day in seconds
- `swell_wave_height_max` (FLOAT): Maximum swell wave height for the day in meters
- `swell_wave_direction_dominant` (FLOAT): Dominant swell wave direction for the day in degrees
- `elevation` (FLOAT): Location elevation in meters as reported by the API (typically 0 for marine locations)
- `timezone` (STRING): Timezone of the location as reported by the API

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
