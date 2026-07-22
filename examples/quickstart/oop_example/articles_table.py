from nps_client import NPS


class ARTICLES(NPS):
    """
    A subclass of NPS to handle data related to articles.
    Fetches and processes articles data from the NPS API, maps it to a schema,
    and returns the processed data.
    """

    # For more info, see https://www.nps.gov/subjects/developer/index.htm

    @staticmethod
    def path() -> str:
        """
        Specifies the API endpoint for articles data.

        Returns:
            str: The API path for fetching articles data.
        """
        return "articles"

    @staticmethod
    def primary_key():
        """
        Defines the primary key(s) for the articles data.

        Returns:
            list: A list containing the primary key(s) for the articles table.
        """
        return ["article_id"]

    @staticmethod
    def assign_schema():
        """
        Assigns the schema for the articles table, including the table name,
        primary key, and column definitions with data types.

        Returns:
            dict: A dictionary representing the schema for the articles table.
        """
        return {
            "table": ARTICLES.path(),
            "primary_key": ARTICLES.primary_key(),
            "columns": {
                "article_id": "STRING",  # Unique identifier for the article
                "title": "STRING",  # Title of the article
                "url": "STRING",  # URL to the article
                "park_code": "STRING",  # Park codes related to the article
                "park_names": "STRING",  # Names of parks related to the article
                "states": "STRING",  # States related to the parks in the article
                "listing_description": "STRING",  # Description of the article
                "date": "STRING",  # Date the article was published
            },
        }

    def process_data(self):
        """
        Fetches and processes articles data from the NPS API. Maps raw API data
        to the defined schema and returns a processed list of article information.

        Returns:
            list: A list of dictionaries where each dictionary represents an article
                  and its associated details mapped to the schema.
        """
        # Fetch raw data for articles using the NPS parent class method
        articles_response = NPS.fetch_data(self, ARTICLES.path())
        processed_articles = []  # List to store processed articles data

        # Process each article's data retrieved from the API
        for article in articles_response[ARTICLES.path()]:
            # Extract and map fields from the API response
            article_id = article.get(
                "id", "Unknown ID"
            )  # Get article ID or default to "Unknown ID"
            title = article.get("title", "No Title")  # Get article title or default to "No Title"
            url = article.get("url", "")  # Get article URL or default to an empty string

            # Extract related parks data as lists of codes, names, and states
            park_code = [
                related_park.get("parkCode", "")
                for related_park in article.get("relatedParks", [])
            ]
            park_names = [
                related_park.get("fullName", "")
                for related_park in article.get("relatedParks", [])
            ]
            states = [
                related_park.get("states", "") for related_park in article.get("relatedParks", [])
            ]

            listing_description = article.get(
                "listingDescription", ""
            )  # Get description or default to an empty string
            date = article.get("date", "")  # Get publication date or default to an empty string

            # Map fields to schema-defined column names
            col_mapping = {
                "article_id": article_id,
                "title": title,
                "url": url,
                "park_code": park_code,
                "park_names": park_names,
                "states": states,
                "listing_description": listing_description,
                "date": date,
            }

            processed_articles.append(col_mapping)  # Add the processed article data to the list

        # Return the final processed list of articles
        return processed_articles
