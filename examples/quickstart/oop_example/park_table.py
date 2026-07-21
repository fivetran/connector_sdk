from nps_client import NPS


class PARKS(NPS):
    """
    A subclass of NPS to handle data related to parks.
    Fetches and processes park data from the NPS API, maps it to a schema,
    and returns the processed data.
    """

    # For more info, see https://www.nps.gov/subjects/developer/index.htm

    @staticmethod
    def path() -> str:
        """
        Specifies the API endpoint for parks data.

        Returns:
            str: The API path for fetching park data.
        """
        return "parks"

    @staticmethod
    def primary_key():
        """
        Defines the primary key(s) for the parks data.

        Returns:
            list: A list containing the primary key(s) for the parks table.
        """
        return ["park_id"]

    @staticmethod
    def assign_schema():
        """
        Assigns the schema for the parks table, including the table name,
        primary key, and column definitions with data types.

        Returns:
            dict: A dictionary representing the schema for the parks table.
        """
        return {
            "table": PARKS.path(),
            "primary_key": PARKS.primary_key(),
            "columns": {
                "park_id": "STRING",  # Unique identifier for the park
                "name": "STRING",  # Name of the park
                "description": "STRING",  # Description of the park
                "state": "STRING",  # State(s) where the park is located
                "latitude": "FLOAT",  # Latitude of the park's location
                "longitude": "FLOAT",  # Longitude of the park's location
                "activities": "STRING",  # Activities available in the park
            },
        }

    def process_data(self):
        """
        Fetches and processes park data from the NPS API. Maps raw API data
        to the defined schema and returns a processed list of park information.

        Returns:
            list: A list of dictionaries where each dictionary represents a park
                  and its associated details mapped to the schema.
        """
        # Fetch raw data for parks using the NPS parent class method
        parks_response = NPS.fetch_data(self, PARKS.path())
        processed_parks = []  # List to store processed park data

        # Process each park's data retrieved from the API
        for park in parks_response[PARKS.path()]:
            # Extract and map fields from the API response
            park_id = park.get("id", "Unknown ID")  # Get park ID or default to "Unknown ID"
            name = park.get("fullName", "No Name")  # Get park name or default to "No Name"
            description = park.get("description", "No Description")  # Get description or default
            state = ", ".join(park.get("states", []))  # Concatenate states into a single string
            latitude = park.get("latitude", None)  # Get latitude or default to None
            longitude = park.get("longitude", None)  # Get longitude or default to None
            activities = ", ".join(activity["name"] for activity in park.get("activities", []))
            # Join activity names into a single string

            # Map fields to schema-defined column names
            col_mapping = {
                "park_id": park_id,
                "name": name,
                "description": description,
                "state": state,
                "latitude": float(latitude) if latitude else None,
                "longitude": float(longitude) if longitude else None,
                "activities": activities,
            }
            processed_parks.append(col_mapping)  # Add the processed park data to the list

        # Return the final processed list of parks
        return processed_parks
