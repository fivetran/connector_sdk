# DTN Weather API Connector Example

> Note: This connector is a draft that has not been validated through direct testing against a live API. It is intended as a starting point and example implementation that should be confirmed and tested before production use.

## Connector overview
This connector integrates with the DTN Weather platform to synchronize weather observations, forecasts, conditions, and lightning strike data into your destination. It supports three DTN API families (Observations, Conditions, and Lightning), each independently configurable, and handles both time-series station data and geospatial GeoJSON responses.

DTN is a weather data provider that offers station-based observations and forecasts, gridded weather conditions by geographic coordinates, and real-time lightning strike detection via REST APIs.

## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/dtn_weather
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Supports three independent DTN API families: Observations, Conditions, and Lightning
- Configurable API selection via `enabled_apis` parameter
- Incremental sync using timestamp-based cursors for observations and conditions
- Full forecast window re-fetch on each sync (forecasts are mutable)
- GeoJSON response parsing for conditions and lightning data
- Batch location support for the conditions API
- Sliding 15-minute time windows for lightning data retrieval
- Periodic checkpointing during long-running lightning syncs
- Retry logic with exponential backoff for transient errors and rate limiting

## Configuration file
The configuration file contains credentials and parameters for the DTN APIs you want to sync.

```json
{
  "api_key": "<YOUR_DTN_API_KEY>",
  "client_id": "<YOUR_DTN_CLIENT_ID>",
  "client_secret": "<YOUR_DTN_CLIENT_SECRET>",
  "station_ids": "<COMMA_SEPARATED_STATION_IDS>",
  "locations": "<JSON_ARRAY_OF_LAT_LON_OBJECTS>",
  "lightning_lat": "<LIGHTNING_LATITUDE>",
  "lightning_lon": "<LIGHTNING_LONGITUDE>",
  "lightning_radius_km": "<LIGHTNING_RADIUS_KM>",
  "enabled_apis": "<ENABLED_APIS>",
  "units": "<UNITS>"
}
```

Configuration parameters:
- `api_key` (required for observations): API key for the DTN Observations API.
- `client_id` (required for conditions/lightning): OAuth2 client ID for the Conditions and Lightning APIs.
- `client_secret` (required for conditions/lightning): OAuth2 client secret for the Conditions and Lightning APIs.
- `station_ids` (required for observations): Comma-separated list of weather station IDs (e.g., `KMSP,KOKC`).
- `locations` (required for conditions): JSON array of latitude/longitude objects for weather conditions queries.
- `lightning_lat` (required for lightning): Latitude of the center point for lightning strike searches.
- `lightning_lon` (required for lightning): Longitude of the center point for lightning strike searches.
- `lightning_radius_km` (optional): Search radius in kilometers for lightning strikes. Defaults to `50`.
- `enabled_apis` (optional): Comma-separated list of APIs to enable. Options: `observations`, `conditions`, `lightning`. Defaults to all three.
- `units` (optional): Unit system for weather data. Options: `us` or `si`. Defaults to `us`.

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication
This connector uses two authentication mechanisms depending on the API:

- Observations API: API key passed in the `apikey` request header. Obtain this key from your DTN account dashboard.
- Conditions and Lightning APIs: OAuth 2.0 client credentials flow. The connector posts `client_id` and `client_secret` to DTN's token endpoint and caches tokens per API audience with proactive refresh 10 seconds before expiry.

Refer to `_obs_headers` for the API key authentication and `_TokenCache.get_token` for the OAuth2 token management.

## Data handling
- Station observations and forecasts are returned as JSON arrays and flattened into tabular rows with explicit field mapping. Refer to `_parse_daily_record` and `_parse_hourly_record`.
- Conditions and lightning data are returned as GeoJSON FeatureCollections. The connector extracts coordinates from geometry and iterates over timestamped property entries. Refer to `_parse_and_upsert_conditions` and `_parse_and_upsert_lightning`.
- CamelCase API field names are mapped to snake_case column names via explicit key mappings.
- Nested structures (precipitation arrays, wind objects) are flattened to top-level columns.
- Forecasts are always fully re-synced because forecast values are mutable and change with each model run.

## Error handling
- Automatic retry with exponential backoff (up to 3 retries) for server errors (5xx) and timeouts. Refer to `_request`.
- Rate limit handling: respects `Retry-After` headers on 429 responses.
- Per-station and per-location errors are logged as warnings and do not halt the overall sync.
- OAuth tokens are refreshed proactively before expiry to avoid mid-sync authentication failures.

## Tables created

The connector creates up to 7 tables depending on which APIs are enabled:

Observations API tables:
- `stations` – Station metadata (primary key: `station_id`). Full refresh each sync.
- `daily_forecasts` – Daily forecast data per station (primary key: `station_id`, `date`). Full window re-fetch.
- `daily_observations` – Daily observation data per station (primary key: `station_id`, `date`). Incremental.
- `hourly_forecasts` – Hourly forecast data per station (primary key: `station_id`, `utc_time`). Full window re-fetch.
- `hourly_observations` – Hourly observation data per station (primary key: `station_id`, `utc_time`). Incremental.

Conditions API tables:
- `conditions` – Gridded weather conditions by location and time (primary key: `latitude`, `longitude`, `utc_time`). Incremental.

Lightning API tables:
- `lightning_strikes` – Lightning strike events within a geographic radius (primary key: `latitude`, `longitude`, `utc_time`). Incremental with 15-minute sliding windows.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
