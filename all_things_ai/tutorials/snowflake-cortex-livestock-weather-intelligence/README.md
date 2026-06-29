# Snowflake Cortex Livestock Weather Intelligence Connector Example

## Connector overview

This connector chains weather forecast APIs with Snowflake Cortex Agent to provide actionable livestock health intelligence based on predicted weather conditions. It demonstrates real-time AI enrichment during data ingestion using the Fivetran Connector SDK.

The connector retrieves 7-day weather forecasts for farm ZIP codes and enriches each forecast period with AI-generated livestock health risk assessments. This enables proactive farm management by correlating weather predictions with current livestock health status.

Use cases:
- Proactive health management - Receive 24-48 hour advance warning of dangerous weather conditions affecting specific animals, enabling preventive measures that reduce veterinary costs
- Emergency preparedness - Automated alerts for extreme weather with species-specific action plans based on current herd health status
- Historical analysis - Track correlations between weather patterns and livestock health outcomes to improve future decision-making
- Insurance documentation - Detailed weather and health risk documentation for insurance claims related to weather-related livestock losses

APIs used:
- [Zippopotam.us](https://api.zippopotam.us/) - ZIP code to geographic coordinates conversion
- [National Weather Service](https://www.weather.gov/documentation/services-web-api) - Weather forecast retrieval
- [Snowflake Cortex Agent](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-llm-rest-api) - Livestock health risk analysis via REST API

Key capabilities:
- Weather forecast sync for multiple farm ZIP codes
- Real-time AI enrichment during ingestion using Snowflake Cortex Agent
- Farm-specific livestock health risk assessment based on weather conditions
- Species-specific risk matrices and recommended preventive actions
- Historical weather-health correlation analysis
- Cost control with configurable enrichment limits


## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- Snowflake account with Cortex enabled (for AI enrichment)
- Snowflake Personal Access Token (PAT)
- Existing livestock health data table with semantic view for Cortex Analyst access


## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.


## Features

- Multi-ZIP code weather sync - Fetches 7-day forecasts (14 periods) for multiple farm locations
- Real-time AI enrichment - Adds livestock health intelligence via Snowflake Cortex Agent REST API during ingestion
- Farm-to-ZIP mapping - Associates specific farms with ZIP codes for targeted analysis
- Configurable enrichment limits - Control costs by limiting AI enrichments per sync
- Exponential backoff retry - Handles rate limits and transient API failures automatically
- Comprehensive error handling - Graceful handling of API errors with detailed logging


## Configuration file

The connector requires the following configuration parameters in `configuration.json`:

```json
{
  "zip_codes": "77429,77856,81611",
  "user_agent": "your_user_agent_name",
  "farm_zip_mapping": "77429:FARM_000000,FARM_000001|77856:FARM_000002,FARM_000003|81611:FARM_000004",
  "enable_cortex_enrichment": "true",
  "snowflake_account": "your_snowflake_account.snowflakecomputing.com",
  "snowflake_pat_token": "your_snowflake_pat",
  "cortex_timeout": "60",
  "max_enrichments": "5"
}
```

Configuration parameters:
- `zip_codes` (required) - Comma-separated US ZIP codes for weather forecast retrieval
- `user_agent` (required) - User-Agent string for NWS API requests, should include contact info per NWS terms of service
- `farm_zip_mapping` (optional) - Maps ZIP codes to farm IDs in format "ZIP:FARM1,FARM2|ZIP:FARM3", enables farm-specific analysis
- `enable_cortex_enrichment` (optional) - Enable AI enrichment via Snowflake Cortex Agent, defaults to "false"
- `snowflake_account` (conditional) - Snowflake account URL, required if Cortex enrichment is enabled
- `snowflake_pat_token` (conditional) - Snowflake Personal Access Token, required if Cortex enrichment is enabled
- `cortex_timeout` (optional) - Timeout in seconds for Cortex Agent calls, defaults to "60"
- `max_enrichments` (optional) - Maximum number of AI enrichments per sync for cost control, defaults to "10"

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Authentication

This connector uses multiple authentication mechanisms:

National Weather Service API:
- No API key required
- Requires User-Agent header with contact information per NWS terms of service
- Example: "LivestockWeatherIntelligence/1.0 (your-email@example.com)"

Zippopotam.us API:
- No authentication required
- Free geocoding service for US ZIP codes

Snowflake Cortex Agent:
- Uses [Personal Access Token (PAT) authentication](https://docs.snowflake.com/en/en/user-guide/programmatic-access-tokens#label-pat-generate)
- Generate PAT via Snowflake UI: Profile > Account Settings > Security > Personal Access Tokens
- Token format: "ver:1-hint:abc123..."
- Required permissions: SELECT on livestock data tables and semantic views


## Pagination

Weather data pagination:
- The National Weather Service API returns all 14 forecast periods (7 days) in a single response
- No pagination required for weather data retrieval

ZIP code processing:
- The connector processes ZIP codes sequentially with rate limiting delays
- NWS rate limit: 1 second delay between requests
- Zippopotam.us rate limit: 0.5 second delay between requests


## Data handling

The connector processes data through the following sequential pipeline steps, implemented in `def update(configuration, state)`:

1. ZIP code geocoding - Converts ZIP codes to latitude/longitude coordinates via Zippopotam.us API
2. Weather forecast retrieval - Fetches 7-day forecasts from NWS API using grid coordinates
3. AI enrichment (optional) - Calls Snowflake Cortex Agent for livestock health risk analysis
4. Data flattening - Converts nested JSON structures to flat records for warehouse compatibility
5. Upsert operations - Inserts or updates records in the destination table

Data transformations:
- Nested dictionaries are flattened using underscore separators (e.g., `user_name`)
- Arrays are serialized to JSON strings for warehouse storage
- Farm IDs are stored as JSON arrays in the `farm_ids` column

Refer to `def flatten_dict(d, parent_key, sep)` for the flattening implementation.


## Error handling

The connector implements comprehensive error handling - refer to `def fetch_data_with_retry(session, url, params, headers)`:

Retry logic:
- Exponential backoff for transient failures (429, 500, 502, 503, 504 status codes)
- Maximum 3 retry attempts with delays of 1s, 2s, 4s
- Non-retryable errors are logged and raised immediately

API-specific handling:
- ZIP code 404 errors are logged as warnings and skipped (invalid ZIP codes)
- Missing grid data for coordinates is logged and skipped
- Cortex Agent timeouts are logged and the record is stored without enrichment

Validation:
- Configuration validation occurs before sync starts - refer to `def validate_configuration(configuration)`
- Records without primary keys are logged and skipped
- Empty agent responses result in null enrichment fields


## Additional files

This example includes supplementary files to help you set up and test the connector:

### CORTEX_AGENT_SETUP.md
- Complete setup guide for configuring Snowflake Cortex Agent
- Step-by-step instructions for creating the AGR_RECORDS table and semantic view
- Agent configuration via Snowflake UI
- Troubleshooting common issues
- Testing and validation procedures

### agr_records.csv
- Sample livestock health data for testing the connector
- Contains 42 animal records across 4 farms (FARM_000000 through FARM_000003)
- Includes realistic species data: Beef Cattle, Chickens, Pigs, and Goats
- Provides health status, vaccination history, and environmental conditions
- Load this data into your Snowflake AGR_RECORDS table to enable AI enrichment

### accounts.json.example
- Example configuration file for Fivetran account settings
- Shows the structure for configuring Python version and API keys
- Reference this when setting up local testing with the Fivetran CLI


## Tables created

The connector creates a single table with weather forecasts enriched with livestock health intelligence.

Table: `livestock_weather_intelligence`

Primary key: `zip_code`, `period_number`

Location columns:
- `zip_code` (STRING) - US ZIP code
- `place_name` (STRING) - City/town name
- `state` (STRING) - Full state name
- `state_abbr` (STRING) - Two-letter state code
- `latitude` (FLOAT) - Location latitude
- `longitude` (FLOAT) - Location longitude

Farm columns:
- `farm_ids` (STRING) - JSON array of farm IDs mapped to this ZIP code
- `farm_count` (INTEGER) - Number of farms in this ZIP code

Weather grid columns:
- `nws_office` (STRING) - NWS forecast office code
- `grid_x` (INTEGER) - NWS grid X coordinate
- `grid_y` (INTEGER) - NWS grid Y coordinate

Forecast columns:
- `period_number` (INTEGER) - Forecast period number (1-14)
- `period_name` (STRING) - Period name (e.g., "Tonight", "Friday")
- `start_time` (TIMESTAMP) - Period start time (ISO 8601)
- `end_time` (TIMESTAMP) - Period end time (ISO 8601)
- `is_daytime` (BOOLEAN) - Daytime period indicator
- `temperature` (INTEGER) - Temperature value
- `temperature_unit` (STRING) - Temperature unit ("F" or "C")
- `temperature_trend` (STRING) - Trend (rising/falling/null)
- `wind_speed` (STRING) - Wind speed (e.g., "5 to 10 mph")
- `wind_direction` (STRING) - Wind direction (e.g., "N", "SW")
- `icon` (STRING) - URL to weather icon
- `short_forecast` (STRING) - Brief forecast summary
- `detailed_forecast` (STRING) - Detailed forecast description

AI-enriched columns (populated when Cortex enrichment is enabled):
- `agent_livestock_risk_assessment` (STRING) - Overall livestock health risk analysis
- `agent_affected_farms` (STRING) - JSON array of farm IDs identified as at-risk
- `agent_species_risk_matrix` (STRING) - JSON object mapping species to risk levels
- `agent_recommended_actions` (STRING) - Numbered list of specific preventive actions
- `agent_historical_correlation` (STRING) - Past weather-health pattern analysis


## Cost considerations

Cortex Agent enrichment costs scale with the number of enrichments per sync:

Example cost projections (using llama3.3-70b model):
- 5 enrichments (POC/testing): approximately $0.006 per sync
- 18 enrichments (3 ZIPs x 6 periods, next 48 hours): approximately $0.023 per sync
- 42 enrichments (3 ZIPs x 14 periods, full 7-day forecast): approximately $0.054 per sync

Use the `max_enrichments` configuration parameter to control costs during testing and production.


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

Cortex Agent requirements:
- The connector dynamically constructs the Cortex Agent configuration in each API request
- Update the semantic view path in `connector.py` to match your database/schema
- The agent uses the llama3.3-70b model for livestock health analysis

Sync behavior:
- This connector performs full refresh on each sync
- Weather forecasts are time-sensitive and constantly updated by NWS
- Recommended sync frequency: every 6-12 hours depending on enrichment settings