# SenSource Connector Example

## Connector overview

The SenSource custom connector fetches data from the SenSource API, which provides traffic and occupancy metrics for physical spaces. This connector demonstrates how to implement OAuth2 authentication, incremental syncing with date-based cursors, and efficient processing of large historical datasets.

The connector supports:
- Static reference data: Locations, sites, zones, spaces, and sensors
- Traffic metrics: Entry and exit counts by zone with hourly granularity
- Occupancy metrics: Maximum, minimum, and average occupancy by space with hourly granularity
- Incremental syncing: Date-based cursor tracking for efficient data replication
- OAuth2 authentication: Secure API access using client credentials flow

The connector processes data in 30-day chunks to handle large historical datasets efficiently and uses checkpointing to ensure reliable resumption after interruptions.

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
fivetran init <project-path> --template connectors/sensource
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- OAuth2 Authentication: Secure API access using client credentials flow
- Static Data Sync: Reference data for locations, sites, zones, spaces, and sensors
- Traffic Metrics: Entry and exit counts with hourly granularity
- Occupancy Metrics: Maximum, minimum, and average occupancy with hourly granularity
- Incremental Syncing: Date-based cursor tracking for efficient data replication
- Retry Logic: Automatic retry with exponential backoff for 5xx errors
- Configurable Metrics: Customizable traffic and occupancy metrics via configuration
- Configurable Start Date: Support for specific start dates in YYYY-MM-DD format

## Configuration file
The configuration file contains the following keys for SenSource API access:

```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "traffic_metrics": "ins,outs",
  "occupancy_metrics": "occupancy(max),occupancy(min),occupancy(avg)",
  "static_endpoints": "location,site,zone,space,sensor",
  "start_date": "2022-01-01"
}
```

Configuration paramaters:

- `client_id` (required): OAuth2 client ID from SenSource.
- `client_secret` (required): OAuth2 client secret from SenSource.
- `traffic_metrics` (optional): Comma-separated list of traffic metrics (default: "ins,outs").
- `occupancy_metrics` (optional): Comma-separated list of occupancy metrics (default: "occupancy(max),occupancy(min),occupancy(avg)").
- `static_endpoints` (optional): Comma-separated list of static endpoints to sync (default: "location,site,zone,space").
- `start_date` (optional): Start date for historical data collection in YYYY-MM-DD format (default: "2022-01-01"). 

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The `requirements.txt` file specifies the Python libraries required by the connector. For the SenSource connector, no additional dependencies are needed as it only uses the pre-installed `fivetran_connector_sdk` and `requests` packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses an OAuth2 client credentials flow for authentication with the SenSource API. To obtain credentials:

1. Contact SenSource to get your OAuth2 client ID and client secret.
2. Add these credentials to your `configuration.json` file.
3. The connector automatically obtains and refreshes access tokens as needed.

For detailed authentication examples and API reference, see [SenSource's API documentation](https://vea.sensourceinc.com/api-docs/).

**Authentication Flow** - Refer to `get_access_token()` function

## Pagination
The SenSource API returns all data for a given date range in a single response, so no traditional pagination is required. However, the connector implements date-based chunking to handle large historical datasets efficiently.

**Date Range Processing** - Refer to `generate_date_ranges()` function and the main update loop in `update()` function

## Data handling
The connector processes data in the following way:

1. **Static Data**: Fetches reference data (locations, sites, zones, spaces, sensors) without state tracking
2. **Traffic Data**: Fetches hourly traffic metrics by zone with configurable metrics
3. **Occupancy Data**: Fetches hourly occupancy metrics by space with configurable metrics
4. **State Management**: Tracks the last synced date to enable incremental updates
5. **Data Transformation**: Converts API responses to standardized format for Fivetran

**Data Processing** - Refer to `fetch_data()` function and `fetch_static_data()` function

## Error handling
The connector implements comprehensive error handling:

- **Authentication Errors**: Validates OAuth2 token acquisition and provides clear error messages
- **API Request Errors**: Implements retry logic with exponential backoff for 5xx errors
- **Configuration Validation**: Ensures all required configuration parameters are present
- **Data Processing Errors**: Graceful handling of malformed API responses

**Error Handling** - Refer to `make_request_with_retry()` function and configuration validation in `update()` function

## Tables created

The connector creates the following tables:

| Table | Primary Key | Description |
|-------|-------------|-------------|
| `TRAFFIC` | `zone_id`, `record_date_hour_1` | Hourly traffic metrics by zone |
| `OCCUPANCY` | `space_id`, `record_date_hour_1` | Hourly occupancy metrics by space |
| `LOCATION` | `location_id` | Location reference data |
| `SITE` | `site_id` | Site reference data |
| `ZONE` | `zone_id` | Zone reference data |
| `SPACE` | `space_id` | Space reference data |
| `SENSOR` | `sensor_id` | Sensor reference data |

**Schema Definition** - Refer to `schema()` function

## Additional files
This connector uses the standard file structure with no additional modular files. All functionality is contained within the main `connector.py` file.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 
