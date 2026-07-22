from nps_client import NPS


class PEOPLE(NPS):
    """
    A subclass of NPS to handle data related to people.
    Fetches and processes people-related data from the NPS API, maps it to a schema,
    and returns the processed data.
    """

    # For more info, see https://www.nps.gov/subjects/developer/index.htm

    @staticmethod
    def path():
        """
        Specifies the API endpoint for people data.

        Returns:
            str: The API path for fetching people data.
        """
        return "people"

    @staticmethod
    def primary_key():
        """
        Defines the primary key(s) for the people data.

        Returns:
            list: A list containing the primary key(s) for the people table.
        """
        return ["person_id"]

    @staticmethod
    def assign_schema():
        """
        Assigns the schema for the people table, including the table name,
        primary key, and column definitions with data types.

        Returns:
            dict: A dictionary representing the schema for the people table.
        """
        return {
            "table": PEOPLE.path(),
            "primary_key": PEOPLE.primary_key(),
            "columns": {
                "person_id": "STRING",  # Unique identifier for the person
                "name": "STRING",  # Name of the person
                "title": "STRING",  # Title of the person
                "description": "STRING",  # Description of the person
                "url": "STRING",  # URL for more information about the person
                "related_parks": "STRING",  # Parks related to the person
            },
        }

    def process_data(self):
        """
        Fetches and processes people data from the NPS API. Maps raw API data
        to the defined schema and returns a processed list of people information.

        Returns:
            list: A list of dictionaries where each dictionary represents a person
                  and their associated details mapped to the schema.
        """
        # Fetch raw data for people using the NPS parent class method
        people_response = NPS.fetch_data(self, PEOPLE.path())
        processed_people = []  # List to store processed people data

        # Process each person's data retrieved from the API
        for p in people_response[PEOPLE.path()]:
            # Extract and map fields from the API response
            person_id = p.get("id", "Unknown ID")  # Get person ID or default to "Unknown ID"
            name = p.get("title", "No Name")  # Get person's name or default to "No Name"
            title = p.get("listingDescription", "No Title")  # Get title or default to "No Title"
            description = p.get(
                "listingDescription", "No Description"
            )  # Get description or default
            url = p.get("url", "")  # Get URL or default to an empty string
            related_parks = ", ".join(p["parkCode"] for p in p.get("relatedParks", []))
            # Concatenate related park codes into a single string

            # Map fields to schema-defined column names
            col_mapping = {
                "person_id": person_id,
                "name": name,
                "title": title,
                "description": description,
                "url": url,
                "related_parks": related_parks,
            }
            processed_people.append(col_mapping)  # Add the processed person data to the list

        # Return the final processed list of people
        return processed_people
