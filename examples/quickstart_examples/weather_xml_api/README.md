# Weather Station XML Connector Example

## Connector overview

This connector fetches current weather observations from NOAA's National Weather Service XML API for specified weather station codes. It demonstrates how to work with XML API responses in the Fivetran Connector SDK.

The connector maintains two tables:
- `WEATHER_OBSERVATIONS`: Current weather data including temperature, humidity, wind, pressure, and visibility.
- `WEATHER_STATIONS`: Station metadata including location, coordinates, and data source information.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating System:
  - Windows 10 or later
  - macOS 13 (Ventura) or later
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart_examples/weather_xml_api
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Parses XML responses using Python's built-in XML parser
- Fetches current weather observations for multiple weather stations
- Maintains historical observation data with incremental updates
- Uses NOAA's public API with no authentication required
- Provides comprehensive weather data including temperature, humidity, wind, and atmospheric pressure
- Includes station metadata for better data analysis

## Configuration file

The connector requires a simple configuration with a list of weather station codes:

```json
{
  "station_codes": "KOAK,KJFK,KLAX,KORD,KDFW"
}
```

Common weather station codes:
- `KOAK` - Oakland International Airport, CA
- `KJFK` - John F. Kennedy International Airport, NY
- `KLAX` - Los Angeles International Airport, CA
- `KORD` - Chicago O'Hare International Airport, IL
- `KDFW` - Dallas/Fort Worth International Airport, TX

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector uses minimal external dependencies. The `requirements.txt` file should be empty as all required packages are pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This custom connector uses NOAA's public XML API that does not require authentication. The API endpoint follows the pattern:
`https://forecast.weather.gov/xml/current_obs/{station_code}.xml`

The connector includes appropriate User-Agent headers as recommended by NOAA's usage guidelines.

## Data handling

The connector processes data in the following way:
- Fetches XML weather observations from NOAA's API for each configured station.
- Parses XML responses using Python's `xml.etree.ElementTree` library.
- Converts string values to appropriate data types (FLOAT, INT) where applicable.
- Transforms the data into two tables:
   - `WEATHER_OBSERVATIONS`: Contains current weather observation data.
   - `WEATHER_STATIONS`: Contains station metadata including location and coordinates.

The connector uses incremental sync based on the `observation_time_rfc822` field to avoid duplicate data.

## Error handling

The connector implements error handling for:
- Invalid weather station codes
- XML parsing errors
- API request failures
- Data type conversion errors

All errors are logged using the Fivetran logging system for debugging and monitoring.

## Tables created

The connector creates two tables:

### WEATHER_OBSERVATIONS
Primary key: `station_id`, `observation_time_rfc822`
Contains weather observation data including:
- Temperature (Fahrenheit and Celsius)
- Weather conditions
- Humidity and atmospheric pressure
- Wind speed and direction
- Visibility and dewpoint

### WEATHER_STATIONS
Primary key: `station_id`
Contains station metadata including:
- Location name
- Latitude and longitude
- Data source credit information

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
