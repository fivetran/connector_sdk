# ZIP Code Weather Connector

## Connector overview

This connector fetches weather forecast data for specified US ZIP codes using two public APIs:
1. Zippopotam.us API - Converts ZIP codes to geographic coordinates
2. National Weather Service (NWS) API - Provides detailed weather forecasts

The connector maintains two tables:
- `forecast`: Contains weather forecast data for each ZIP code
- `zip_code`: Contains metadata about each ZIP code including city, state, and coordinates

## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating System:  
  * Windows 10 or later  
  * macOS 13 (Ventura) or later
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/weather_with_configuration
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory. 
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

* Fetches weather forecasts for multiple ZIP codes in a single sync
* Maintains historical forecast data with incremental updates
* Uses public APIs with no authentication required
* Provides detailed weather information including temperature, conditions, and wind data
* Includes ZIP code metadata for better data analysis

## Configuration file

The connector requires a simple configuration with a list of ZIP codes to monitor:

```json
{
  "zip_codes": "94612,90210,10001"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector uses minimal external dependencies. The `requirements.txt` file should be empty as all required packages are pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses public APIs that do not require authentication:
- Zippopotam.us API is completely public
- NWS API requires only a User-Agent header for identification

## Data handling

The connector processes data in the following way:
1. Converts ZIP codes to coordinates using Zippopotam.us API
2. Fetches forecast data from NWS API using the coordinates
3. Transforms the data into two tables:
   - `forecast`: Contains weather forecast periods with detailed weather information
   - `zip_code`: Contains ZIP code metadata including city, state, and coordinates

The connector uses incremental sync based on the `startTime` field to avoid duplicate data.

## Error handling

The connector implements error handling for:
- Invalid ZIP codes
- API request failures
- Data parsing errors

All errors are logged using the Fivetran logging system for debugging and monitoring.

## Tables Created

The connector creates two tables:

### forecast
Primary key: `startTime`, `zip_code`
Contains weather forecast data including:
- Temperature
- Weather conditions
- Wind information
- Forecast period details

### zip_code
Primary key: `zip_code`
Contains ZIP code metadata including:
- City name
- State
- Latitude
- Longitude
- Additional location details

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 
