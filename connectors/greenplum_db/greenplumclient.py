import psycopg2
import psycopg2.extras
from datetime import datetime, timezone  # This is used for handling timestamps

# Import required classes from fivetran_connector_sdk.
# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


# Define the Greenplum client class to handle database operations.
class GreenplumClient:
    def __init__(self, configuration):
        # Check if the credentials for connecting to database is present in the configuration.
        cred = ["HOST", "DATABASE", "USERNAME", "PASSWORD", "PORT"]
        for key in cred:
            if key not in configuration:
                raise ValueError(f"Missing required configuration: {key}")

        self.connection = GreenplumClient.connect(configuration)
        # Create a cursor object to execute SQL queries.
        # The cursor is created with RealDictCursor factory to return results as dictionaries.
        # The cursor is name "my_cursor" to allow server-side cursors. This enables streaming of results.
        # This is useful for large result sets as it does not load entire data in memory and prevents memory overflow errors.
        self.cursor = self.connection.cursor(
            name="my_cursor", cursor_factory=psycopg2.extras.RealDictCursor
        )

    @staticmethod
    def connect(configuration):
        """
        This method establishes a connection to the Greenplum database using psycopg2.
        It uses the connection parameters provided in the configuration.
        If the connection fails, it raises a ConnectionError with a message.
        """
        host = configuration.get("HOST")
        port = int(configuration.get("PORT"))
        database = configuration.get("DATABASE")
        user = configuration.get("USERNAME")
        password = configuration.get("PASSWORD")

        try:
            return psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
        except Exception as e:
            raise ConnectionError(f"Error connecting to Greenplum database: {e}")

    def disconnect(self):
        # This method closes the connection to the Greenplum database.
        # It checks if the connection is open before attempting to close it.
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        log.info("Database connection closed.")

    @staticmethod
    def parse_state_timestamp(state):
        """
        Parse the last_timestamp from the state dictionary.
        If the timestamp is not present or invalid, return a default datetime.
        Args:
            state: a dictionary containing state information from previous runs
        Returns:
            A datetime object representing the last processed timestamp.
        """
        timestamp_str = state.get("last_query_timestamp")
        if not timestamp_str:
            return datetime(1990, 1, 1, tzinfo=timezone.utc)
        try:
            # Handle possible 'Z'
            timestamp_str = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str.tzinfo is None:
                timestamp_str = timestamp_str.replace(tzinfo=timezone.utc)
            return timestamp_str
        except ValueError:
            return datetime(1990, 1, 1, tzinfo=timezone.utc)

    def upsert_data(self, query, table_name, state):
        """
        This method executes a SQL query to fetch data from the Greenplum database and upserts it into the destination table.
        Args:
            query: Query to fetch data from the Greenplum database.
            table_name: name of the destination table.
            state: a dictionary containing the state checkpointed during the prior sync.
        """

        # Get the last query from the state dictionary.
        last_query_timestamp = GreenplumClient.parse_state_timestamp(state=state)

        # Execute the SQL query using the cursor.
        self.cursor.execute(query)

        # Iterate through the cursor to fetch and upsert data.
        # The cursor is a named cursor, which allows for server-side cursors.
        # This means that the cursor will fetch rows from the database server in streaming fashion, rather than loading all rows into memory at once.
        for row in self.cursor:
            # Converting the row to a dictionary
            upsert_row = dict(row)
            # The 'upsert' operation is used to insert or update the data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=upsert_row)

            # update the last_query_timestamp variable if the current row's query_start is greater than the last_query_timestamp
            if upsert_row["query_start"] > last_query_timestamp:
                last_query_timestamp = upsert_row["query_start"]

        state["last_query_timestamp"] = last_query_timestamp.isoformat()
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)
