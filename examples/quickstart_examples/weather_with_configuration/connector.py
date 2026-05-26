# This is an example for how to work with the fivetran_connector_sdk module.
# This connector fetches weather forecast data for specified US ZIP codes using:
# 1. Zippopotam.us API to get coordinates from ZIP codes
# 2. National Weather Service (NWS) API to get weather forecasts
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details


import json  # Import the json module to handle JSON data.
from datetime import datetime  # Import datetime for handling date and time conversions.

import requests as rq  # Import the requests module for making HTTP requests, aliased as rq.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "forecast",  # Name of the table in the destination.
            "primary_key": ["startTime", "zip_code"],  # Primary key column(s) for the table.
        },
        {
            "table": "zip_code",  # Name of the table for zip code metadata
            "primary_key": ["zip_code"],  # Primary key column for the table.
        },
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    if "zip_codes" not in configuration:
        raise ValueError("Missing required configuration value: 'zip_codes'")


def get_coordinates_from_zip(zip_code: str) -> tuple:
    """
    Get latitude and longitude for a zip code using Zippopotam.us API.
    Args:
        zip_code (str): The US ZIP code to look up
    Returns:
        tuple: A tuple containing:
            - tuple: (latitude, longitude) coordinates
            - dict: ZIP code metadata including city, state, etc.
    Raises:
        requests.exceptions.HTTPError: If the API request fails
    """
    url = f"https://api.zippopotam.us/us/{zip_code}"
    log.info(f"Requesting coordinates for ZIP code {zip_code}")
    response = rq.get(url)
    response.raise_for_status()
    data = response.json()

    log.debug(f"API Response: {json.dumps(data, indent=2)}")

    # Extract coordinates from the response
    zip_info = data["places"][0]  # Get the first place in the zip code
    lat = float(zip_info["latitude"])
    lon = float(zip_info["longitude"])
    zip_info["zip_code"] = zip_code

    log.info(f"Found coordinates: ({lat}, {lon})")
    return (lat, lon), zip_info  # Return both coordinates and metadata


def get_forecast_url(lat: float, lon: float) -> str:
    """
    Get the forecast URL for a location using the NWS API's two-step process.
    Args:
        lat (float): Latitude of the location
        lon (float): Longitude of the location
    Returns:
        str: URL to fetch the weather forecast for the location
    Raises:
        requests.exceptions.HTTPError: If the API request fails
    """
    headers = {"User-Agent": "Fivetran Weather Connector (contact: your-email@example.com)"}

    # Step 1: Get the metadata for the location
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    response = rq.get(points_url, headers=headers)
    response.raise_for_status()
    points_data = response.json()

    # Step 2: Get the forecast URL from the metadata
    forecast_url = points_data["properties"]["forecast"]
    return forecast_url


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
    log.warning("Example: QuickStart Examples - Weather with Configuration")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Retrieve the cursor from the state to determine the current position in the data sync.
    # If the cursor is not present in the state, start from the beginning of time ('0001-01-01T00:00:00Z').
    cursor = state["startTime"] if "startTime" in state else "0001-01-01T00:00:00Z"

    # Read zip codes from configuration
    zip_codes_str = configuration.get("zip_codes", "94612")  # Default to Oakland
    zip_codes = [zip_code.strip() for zip_code in zip_codes_str.split(",")]

    for zip_code in zip_codes:
        try:
            # Get coordinates and metadata for the zip code
            (lat, lon), metadata = get_coordinates_from_zip(zip_code)

            # Store the zip code metadata
            op.upsert(table="zip_code", data=metadata)

            # Get the forecast URL using the NWS API's two-step process
            forecast_url = get_forecast_url(lat, lon)
            log.info(f"Got forecast URL for {zip_code}: {forecast_url}")

            # Get the forecast data
            headers = {
                "User-Agent": "Fivetran Weather Connector (contact: developers@fivetran.com)"
            }
            response = rq.get(forecast_url, headers=headers)
            response.raise_for_status()

            # Parse the JSON response to get the forecast periods of the weather forecast.
            data = response.json()
            forecast_periods = data["properties"]["periods"]

            # This message will show both during debugging and in production.
            log.info(f"number of forecast_periods={len(forecast_periods)}")

            for forecast in forecast_periods:
                # Skip data points we already synced by comparing their start time with the cursor.
                if str2dt(forecast["startTime"]) < str2dt(cursor):
                    continue

                # Add zip code to the period data
                forecast["zip_code"] = zip_code
                # This log message will only show while debugging.
                log.debug(f"forecast_period={forecast['name']} for zip code {zip_code}")

                # Upsert operation to insert/update the row in the "forecast" table.
                op.upsert(table="forecast", data=forecast)

        except Exception as e:
            log.error(f"Unexpected error occurred while processing ZIP code {zip_code}", e)
            raise

    # Update the cursor to the end time of the current period.
    cursor = forecast["endTime"]
    op.checkpoint(state={"startTime": cursor})


def str2dt(incoming: str) -> datetime:
    """
    Convert a string timestamp to a datetime object.
    Args:
        incoming (str): ISO 8601 formatted timestamp string
    Returns:
        datetime: Parsed datetime object with timezone information
    """
    return datetime.strptime(incoming, "%Y-%m-%dT%H:%M:%S%z")


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    try:
        # Try loading the configuration from the file
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        # Fallback to an empty configuration if the file is not found
        configuration = {}
    # Allows testing the connector directly
    connector.debug(configuration=configuration)
