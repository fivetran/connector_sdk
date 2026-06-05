# Oura Ring Connector Example

## Connector overview

This connector syncs health and wellness data from the Oura Ring API v2 into your Fivetran destination. It retrieves daily activity scores, sleep metrics, readiness assessments, stress levels, and continuous heart rate measurements. The connector supports incremental syncing using date-based cursors and handles cursor-based pagination via the Oura API's `next_token` mechanism. Nested contributor objects (activity, sleep, and readiness scores) are automatically flattened for warehouse compatibility, and time-series arrays are serialized to JSON strings.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- An Oura Ring account with a Personal Access Token

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/oura_ring
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental syncing using date-based state tracking to avoid re-fetching historical data
- Cursor-based pagination via `next_token` for reliable large dataset retrieval
- Automatic flattening of nested contributor objects into top-level columns
- Configurable lookback window for initial sync (default 90 days)
- Graceful handling of restricted endpoints when stress data requires a higher subscription tier
- Exponential backoff retry logic for transient API failures and rate limiting

## Configuration file

The `configuration.json` file contains the parameters needed to connect to the Oura API:

```json
{
    "personal_access_token": "<YOUR_PERSONAL_ACCESS_TOKEN>",
    "lookback_days": "<LOOKBACK_DAYS>"
}
```

- `personal_access_token` (required): Your Oura Personal Access Token generated from the Oura developer portal
- `lookback_days` (optional): Number of days to look back on the initial sync, defaults to 90

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

This connector uses Bearer token authentication with a Personal Access Token. To generate your token:

1. Log in to the Oura developer portal at https://cloud.ouraring.com/personal-access-tokens
2. Click **Create New Personal Access Token**
3. Copy the generated token and add it to your `configuration.json` file as the `personal_access_token` value

The token is sent in the `Authorization` header as `Bearer <token>` on every API request via a persistent `requests.Session`.

## Pagination

The Oura API v2 uses cursor-based pagination via a `next_token` field in each response. The connector fetches pages in a loop, passing the `next_token` from the previous response as a query parameter to retrieve the next page. Pagination continues until the API returns no `next_token`. State is checkpointed after each page to support resumable syncs in case of interruptions.

## Data handling

The `def update(configuration, state)` function orchestrates the sync across all five tables. For each table, the `def sync_table(session, table_name, table_config, start_date_str, end_date_str, state)` function handles pagination, record processing, and checkpointing.

Records with nested contributor objects (daily activity, sleep, and readiness) are flattened using the `def flatten_dict(d, parent_key, sep)` function. For example, `{"contributors": {"deep_sleep": 99}}` becomes `{"contributors_deep_sleep": 99}`. Lists and arrays are serialized to JSON strings.

Daily endpoints use `start_date` and `end_date` query parameters in YYYY-MM-DD format. The heart rate endpoint uses `start_datetime` and `end_datetime` in ISO 8601 format, handled by the `def build_date_params(table_name, table_config, start_date_str, end_date_str)` function.

## Error handling

The `def fetch_data_with_retry(session, url, params)` function implements exponential backoff retry logic for transient failures. Retryable HTTP status codes (429, 500, 502, 503, 504) trigger up to 3 retry attempts with increasing delays. Connection errors and timeouts are also retried.

The daily_stress endpoint may return HTTP 403 (forbidden) or 426 (upgrade required) for accounts without the appropriate Oura subscription tier. The connector gracefully skips the stress table in these cases and continues syncing the remaining tables.

Authentication and authorization failures (HTTP 401/403) surface immediately with a descriptive error message directing users to check their `personal_access_token` and API scopes.

## Tables created

### DAILY_ACTIVITY

The `DAILY_ACTIVITY` table consists of the following columns:

- `id` (STRING, primary key): Unique identifier for the daily activity record
- `day` (STRING): Date in YYYY-MM-DD format
- `timestamp` (STRING): ISO 8601 timestamp
- `score` (INTEGER): Overall activity score (0-100)
- `active_calories` (INTEGER): Calories burned through activity
- `steps` (INTEGER): Total steps for the day
- `equivalent_walking_distance` (FLOAT): Equivalent walking distance in meters
- `high_activity_met_minutes` (FLOAT): Minutes of high activity weighted by MET
- `high_activity_time` (INTEGER): Seconds of high activity
- `medium_activity_met_minutes` (FLOAT): Minutes of medium activity weighted by MET
- `medium_activity_time` (INTEGER): Seconds of medium activity
- `low_activity_met_minutes` (FLOAT): Minutes of low activity weighted by MET
- `low_activity_time` (INTEGER): Seconds of low activity
- `sedentary_met_minutes` (FLOAT): Minutes of sedentary time weighted by MET
- `sedentary_time` (INTEGER): Seconds of sedentary time
- `resting_time` (INTEGER): Seconds of resting time
- `non_wear_time` (INTEGER): Seconds ring was not worn
- `inactivity_alerts` (INTEGER): Number of inactivity alerts
- `average_met_minutes` (FLOAT): Average MET minutes
- `target_calories` (INTEGER): Target calorie goal
- `target_meters` (INTEGER): Target distance goal in meters
- `meters_to_target` (INTEGER): Remaining meters to daily goal
- `met_interval` (FLOAT): Interval between MET samples in seconds
- `met_items` (STRING): JSON-serialized array of MET sample values
- `met_timestamp` (STRING): Timestamp of first MET sample
- `class_5_min` (STRING): JSON-serialized 5-minute activity classification string
- `contributors_meet_daily_targets` (INTEGER): Contributor score for meeting daily targets (1-100)
- `contributors_move_every_hour` (INTEGER): Contributor score for hourly movement (1-100)
- `contributors_recovery_time` (INTEGER): Contributor score for recovery time (1-100)
- `contributors_stay_active` (INTEGER): Contributor score for staying active (1-100)
- `contributors_training_frequency` (INTEGER): Contributor score for training frequency (1-100)
- `contributors_training_volume` (INTEGER): Contributor score for training volume (1-100)

### DAILY_SLEEP

The `DAILY_SLEEP` table consists of the following columns:

- `id` (STRING, primary key): Unique identifier for the daily sleep record
- `day` (STRING): Date in YYYY-MM-DD format
- `timestamp` (STRING): ISO 8601 timestamp
- `score` (INTEGER): Overall sleep score (0-100)
- `contributors_deep_sleep` (INTEGER): Contributor score for deep sleep (1-100)
- `contributors_efficiency` (INTEGER): Contributor score for sleep efficiency (1-100)
- `contributors_latency` (INTEGER): Contributor score for sleep latency (1-100)
- `contributors_rem_sleep` (INTEGER): Contributor score for REM sleep (1-100)
- `contributors_restfulness` (INTEGER): Contributor score for restfulness (1-100)
- `contributors_timing` (INTEGER): Contributor score for sleep timing (1-100)
- `contributors_total_sleep` (INTEGER): Contributor score for total sleep (1-100)

### DAILY_READINESS

The `DAILY_READINESS` table consists of the following columns:

- `id` (STRING, primary key): Unique identifier for the daily readiness record
- `day` (STRING): Date in YYYY-MM-DD format
- `timestamp` (STRING): ISO 8601 timestamp
- `score` (INTEGER): Overall readiness score (0-100)
- `temperature_deviation` (FLOAT): Deviation from baseline body temperature
- `temperature_trend_deviation` (FLOAT): Trend deviation from baseline temperature
- `contributors_activity_balance` (INTEGER): Contributor score for activity balance (1-100)
- `contributors_body_temperature` (INTEGER): Contributor score for body temperature (1-100)
- `contributors_hrv_balance` (INTEGER): Contributor score for HRV balance (1-100)
- `contributors_previous_day_activity` (INTEGER): Contributor score for previous day activity (1-100)
- `contributors_previous_night` (INTEGER): Contributor score for previous night sleep (1-100)
- `contributors_recovery_index` (INTEGER): Contributor score for recovery index (1-100)
- `contributors_resting_heart_rate` (INTEGER): Contributor score for resting heart rate (1-100)
- `contributors_sleep_balance` (INTEGER): Contributor score for sleep balance (1-100)
- `contributors_sleep_regularity` (INTEGER): Contributor score for sleep regularity (1-100)

### DAILY_STRESS

The `DAILY_STRESS` table consists of the following columns:

- `id` (STRING, primary key): Unique identifier for the daily stress record
- `day` (STRING): Date in YYYY-MM-DD format
- `stress_high` (INTEGER): Seconds of high stress during the day
- `recovery_high` (INTEGER): Seconds of high recovery during the day
- `day_summary` (STRING): Overall day classification (restored, normal, or stressful)

### HEART_RATE

The `HEART_RATE` table consists of the following columns:

- `timestamp` (STRING, primary key): ISO 8601 timestamp of the heart rate reading
- `bpm` (INTEGER): Beats per minute
- `source` (STRING): Context of the reading (awake, rest, sleep, session, live, or workout)

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
