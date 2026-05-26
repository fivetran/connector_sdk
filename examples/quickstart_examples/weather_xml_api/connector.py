"""
This is an example for how to work with the fivetran_connector_sdk module with XML APIs.
This connector fetches current weather observations from NOAA's National Weather Service XML API
for specified weather station codes (like KOAK for Oakland, KJFK for JFK Airport, etc.).
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
import xml.etree.ElementTree as ET  # For parsing XML responses
from typing import Dict, Any  # For type hinting
import requests as rq  # For making HTTP requests


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
            "table": "weather_observations",
            "primary_key": ["station_id", "observation_time_rfc822"],
        },
        {
            "table": "weather_stations",
            "primary_key": ["station_id"],
        },
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    if "station_codes" not in configuration:
        raise ValueError("Missing required configuration value: 'station_codes'")


def parse_xml_weather_data(xml_content: str) -> Dict[str, Any]:
    """
    Parse XML weather data from NOAA API response.
    Args:
        xml_content (str): Raw XML content from the API
    Returns:
        Dict[str, Any]: Parsed weather data as a dictionary
    """
    root = ET.fromstring(xml_content)

    # Extract all weather data from XML
    weather_data = {}

    # Direct text elements
    text_elements = [
        "credit",
        "credit_URL",
        "image",
        "suggested_pickup",
        "suggested_pickup_period",
        "location",
        "station_id",
        "latitude",
        "longitude",
        "observation_time",
        "observation_time_rfc822",
        "weather",
        "temperature_string",
        "temp_f",
        "temp_c",
        "relative_humidity",
        "wind_string",
        "wind_dir",
        "wind_degrees",
        "wind_mph",
        "wind_kt",
        "pressure_string",
        "pressure_mb",
        "pressure_in",
        "dewpoint_string",
        "dewpoint_f",
        "dewpoint_c",
        "visibility_mi",
        "icon_url_base",
        "two_day_history_url",
        "icon_url_name",
        "ob_url",
        "disclaimer_url",
        "copyright_url",
        "privacy_policy_url",
    ]

    for element_name in text_elements:
        element = root.find(element_name)
        if element is not None and element.text:
            weather_data[element_name] = element.text.strip()

    # Convert numeric fields to appropriate types
    numeric_fields = {
        "latitude": float,
        "longitude": float,
        "temp_f": float,
        "temp_c": float,
        "relative_humidity": int,
        "wind_degrees": int,
        "wind_mph": float,
        "wind_kt": float,
        "pressure_mb": float,
        "pressure_in": float,
        "dewpoint_f": float,
        "dewpoint_c": float,
        "visibility_mi": float,
    }

    for field, field_type in numeric_fields.items():
        if field in weather_data:
            try:
                weather_data[field] = field_type(weather_data[field])
            except (ValueError, TypeError):
                log.warning(
                    f"Could not convert {field} to {field_type.__name__}: {weather_data[field]}"
                )

    return weather_data


def get_weather_data(station_code: str) -> Dict[str, Any]:
    """
    Fetch current weather observations from NOAA XML API for a given station.
    Args:
        station_code (str): Weather station code (e.g., 'KOAK', 'KJFK')
    Returns:
        Dict[str, Any]: Parsed weather observation data
    Raises:
        requests.exceptions.HTTPError: If the API request fails
    """
    url = f"https://forecast.weather.gov/xml/current_obs/{station_code}.xml"
    log.info(f"Requesting weather data for station {station_code}")

    headers = {"User-Agent": "Fivetran NOAA Weather Connector (contact: developers@fivetran.com)"}

    response = rq.get(url, headers=headers)
    response.raise_for_status()

    log.debug(f"Received XML response for {station_code}: {len(response.text)} characters")

    # Parse the XML response
    weather_data = parse_xml_weather_data(response.text)

    log.info(
        f"Parsed weather data for {station_code}: {weather_data.get('weather', 'Unknown')}, "
        f"Temp: {weather_data.get('temp_f', 'N/A')}°F"
    )

    return weather_data


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
    """
    log.warning("Example: QuickStart Examples - NOAA Weather XML API")

    # Validate the configuration
    validate_configuration(configuration)

    # Get station codes from configuration
    station_codes_str = configuration.get("station_codes", "KOAK")
    station_codes = [code.strip().upper() for code in station_codes_str.split(",")]

    log.info(f"Processing {len(station_codes)} weather stations: {', '.join(station_codes)}")

    # Get cursor from state (last observation time)
    cursor = state.get("last_observation_time", "1900-01-01T00:00:00Z")
    log.info(f"Starting from cursor: {cursor}")

    latest_observation_time = cursor

    for station_code in station_codes:
        try:
            # Get current weather data from XML API
            weather_data = get_weather_data(station_code)

            # Create station metadata record
            station_data = {
                "station_id": weather_data.get("station_id", station_code),
                "location": weather_data.get("location", "Unknown"),
                "latitude": weather_data.get("latitude"),
                "longitude": weather_data.get("longitude"),
                "credit": weather_data.get("credit", "NOAA's National Weather Service"),
            }

            # Remove None values
            station_data = {k: v for k, v in station_data.items() if v is not None}

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table="weather_stations", data=station_data)
            log.debug(f"Upserted station data for {station_code}")

            # Check if this observation is newer than our cursor
            observation_time = weather_data.get("observation_time_rfc822", "")
            if observation_time and observation_time > cursor:
                # Upsert weather observation data
                op.upsert(table="weather_observations", data=weather_data)
                log.debug(f"Upserted weather observation for {station_code}: {observation_time}")

                # Track the latest observation time
                if observation_time > latest_observation_time:
                    latest_observation_time = observation_time
            else:
                log.info(f"Skipping observation for {station_code} - not newer than cursor")

        except Exception as e:
            log.error(f"Error processing station {station_code}", e)
            raise

    # Update state with the latest observation time
    new_state = {"last_observation_time": latest_observation_time}
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=new_state)

    log.info(f"Completed sync. New cursor: {latest_observation_time}")


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
        # Fallback to default configuration if the file is not found
        configuration = {"station_codes": "KOAK,KJFK,KLAX"}

    # Allows testing the connector directly
    connector.debug(configuration=configuration)
