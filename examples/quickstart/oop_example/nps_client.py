import requests as rq
import json

# Import required classes from fivetran_connector_sdk
# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log


class NPS:
    """
    A class to interact with the National Park Service (NPS) API.
    Provides methods to fetch data from the API with an optional limit on the number of results.
    """

    def __init__(self, configuration) -> None:
        """
        Initialize the NPS object with configuration details.

        Args:
            configuration (dict): Configuration dictionary containing the API key.

        Raises:
            ValueError: If the API key is not provided in the configuration.
        """
        with open("configuration.json", "r") as f:
            configuration = json.load(f)

        self.api_key = configuration.get("api_key")
        if not self.api_key:
            raise ValueError("API key is missing from the configuration.")

        # Default limit for the number of results fetched from the API
        self.limit = 3

        # Base URL for the NPS API
        self.base_url = "https://developer.nps.gov/api/v1"

    @staticmethod
    def path() -> str:
        """
        Placeholder method to define the API endpoint path.

        Returns:
            str: The path to the desired endpoint.

        Raises:
            Exception: If not overridden by a subclass or implementation.
        """
        raise Exception("Change me")

    @staticmethod
    def primary_key():
        """
        Placeholder method to specify the primary key for the data being fetched.

        Returns:
            Any: The primary key for the fetched data.

        Raises:
            Exception: If not overridden by a subclass or implementation.
        """
        raise Exception("Change me")

    @staticmethod
    def columns():
        """
        Placeholder method to define the columns/fields of interest for the data.

        Returns:
            list: List of columns or fields to extract.

        Raises:
            Exception: If not overridden by a subclass or implementation.
        """
        raise Exception("Change me")

    def fetch_data(self, endpoint):
        """
        Fetch data from a specific endpoint of the NPS API.

        Args:
            endpoint (str): The endpoint to fetch data from (e.g., 'parks', 'events').

        Returns:
            dict: A dictionary containing the data fetched from the API,
                  organized by endpoint. Returns an empty dictionary in case of an error.
        """
        # Parameters for the API request
        params = {"api_key": self.api_key, "limit": self.limit}

        # Results will store the full response; data will store the extracted 'data' field
        results = {}
        data = {}
        try:
            # Make a GET request to the specified API endpoint
            response = rq.get(f"{self.base_url}/{endpoint}", params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Parse the JSON response and extract data
            results[endpoint] = response.json()
            data[endpoint] = results[endpoint].get("data", [])
            print(f"Number of {endpoint} retrieved: {len(data[endpoint])}")
        except rq.exceptions.RequestException as e:
            # Handle exceptions and log a warning message
            log.warning(f"API request to {endpoint} failed: {e}")
            return {}
        # Return the extracted data
        return data
