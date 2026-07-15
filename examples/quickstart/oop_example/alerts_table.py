from nps_client import NPS


class ALERTS(NPS):
    """
    A subclass of NPS to handle data related to alerts.
    Fetches and processes alert data from the NPS API, maps it to a schema,
    and returns the processed data.
    """

    # For more info, see https://www.nps.gov/subjects/developer/index.htm

    @staticmethod
    def path():
        """
        Specifies the API endpoint for alerts data.

        Returns:
            str: The API path for fetching alerts data.
        """
        return "alerts"

    @staticmethod
    def primary_key():
        """
        Defines the primary key(s) for the alerts data.

        Returns:
            list: A list containing the primary key(s) for the alerts table.
        """
        return ["alert_id"]

    @staticmethod
    def assign_schema():
        """
        Assigns the schema for the alerts table, including the table name,
        primary key, and column definitions with data types.

        Returns:
            dict: A dictionary representing the schema for the alerts table.
        """
        return {
            "table": ALERTS.path(),
            "primary_key": ALERTS.primary_key(),
            "columns": {
                "alert_id": "STRING",  # Unique identifier for the alert
                "park_code": "STRING",  # Park code related to the alert
                "title": "STRING",  # Title of the alert
                "description": "STRING",  # Description of the alert
                "category": "STRING",  # Category of the alert
                "url": "STRING",  # URL with more information about the alert
            },
        }

    def process_data(self):
        """
        Fetches and processes alerts data from the NPS API. Maps raw API data
        to the defined schema and returns a processed list of alert information.

        Returns:
            list: A list of dictionaries where each dictionary represents an alert
                  and its associated details mapped to the schema.
        """
        # Fetch raw data for alerts using the NPS parent class method
        alerts_response = NPS.fetch_data(self, ALERTS.path())
        processed_alerts = []  # List to store processed alerts data

        # Process each alert's data retrieved from the API
        for alert in alerts_response[ALERTS.path()]:
            # Extract and map fields from the API response
            alert_id = alert.get("id", "Unknown ID")  # Get alert ID or default to "Unknown ID"
            park_code = alert.get("parkCode", "")  # Get park ID or default to an empty string
            title = alert.get("title", "No Title")  # Get alert title or default to "No Title"
            description = alert.get("description", "No Description")  # Get description or default
            category = alert.get(
                "category", "No Category"
            )  # Get category or default to "No Category"
            url = alert.get("url", "")  # Get URL or default to an empty string

            # Map fields to schema-defined column names
            col_mapping = {
                "alert_id": alert_id,
                "park_code": park_code,
                "title": title,
                "description": description,
                "category": category,
                "url": url,
            }
            processed_alerts.append(col_mapping)  # Add the processed alert data to the list

        # Return the final processed list of alerts
        return processed_alerts
