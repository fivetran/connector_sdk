# Import necessary libraries.
# As TimescaleDB is a PostgreSQL extension, we can use psycopg2 to connect to the database.
import psycopg2
import psycopg2.extras
import ast  # For converting string representation of lists to actual lists

# Import required classes from fivetran_connector_sdk.
# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


# Define the TimescaleDb client class to handle database operations.
class TimescaleClient:
    def __init__(self, configuration):
        self.connection = TimescaleClient.connect(configuration)
        # Create a cursor object to execute SQL queries.
        # The cursor is created with RealDictCursor factory to return results as dictionaries.
        # The cursor is named to allow server-side cursors. This enables streaming of results.
        # This is useful for large result sets as it does not load entire data in memory and prevents memory overflow errors.
        self.cursor = self.connection.cursor(
            name="my_cursor", cursor_factory=psycopg2.extras.RealDictCursor
        )
        self.vector_cursor = self.connection.cursor(
            name="vector_cursor", cursor_factory=psycopg2.extras.RealDictCursor
        )

    @staticmethod
    def connect(configuration):
        """
        This method establishes a connection to the TimescaleDb database using psycopg2.
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
            raise ConnectionError(f"Error connecting to TimescaleDb database: {e}")

    def disconnect(self):
        # This method closes the connection to the TimescaleDb database.
        # It checks if the connection is open before attempting to close it.
        if self.cursor:
            self.cursor.close()
        if self.vector_cursor:
            self.vector_cursor.close()
        if self.connection:
            self.connection.close()
        log.info("Database connection closed.")

    def upsert_data(self, query, table_name, state, batch_size=1000):
        """
        This method executes a SQL query to fetch data from the TimescaleDb database and upserts it into the destination table.
        Args:
            query: Query to fetch data from the TimescaleDb database.
            table_name: name of the destination table.
            state: a dictionary containing the state checkpointed during the prior sync.
            batch_size: number of rows to fetch in each batch. Default is 1000.
        """
        # Get the last query from the state dictionary.
        last_timestamp = state.get("last_timestamp", "1990-01-01T00:00:00Z")

        # Execute the SQL query using the cursor.
        self.cursor.execute(query)

        # Fetch the data in batches to avoid loading all rows into memory at once.
        # The cursor is a named cursor, which allows for server-side cursors.
        # This means that the cursor will fetch rows from the database server in streaming fashion.
        while True:
            rows = self.cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                # Converting the row to a dictionary
                upsert_row = dict(row)
                # Converting datetime objects to ISO format.
                upsert_row = TimescaleClient.serialize_upsert_row(upsert_row)
                # The 'upsert' operation is used to insert or update data in a table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted.
                op.upsert(table=table_name, data=upsert_row)

                # update the last_timestamp variable if the current row's time is greater than the last_timestamp
                if upsert_row["time"] > last_timestamp:
                    last_timestamp = upsert_row["time"]

            state["last_timestamp"] = last_timestamp
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)

        # After fetching all rows, update the state with the last_timestamp and checkpoint it.
        state["last_timestamp"] = last_timestamp
        op.checkpoint(state)

    def upsert_vector_data(self, query, table_name, state, batch_size=1000):
        """
        This method fetches vector data from TimescaleDB and upserts it into the destination table.
        Args:
            query: Query to fetch vector data from the TimescaleDB.
            table_name: Name of the destination table.
            state: A dictionary containing the state checkpointed during the prior sync.
            batch_size: Number of rows to fetch in each batch. Default is 1000.
        """
        # Get the last vector timestamp from the state dictionary
        last_vector_timestamp = state.get("last_vector_timestamp", "1990-01-01T00:00:00Z")

        # Execute the SQL query
        self.vector_cursor.execute(query)

        # Fetch the data in batches to avoid loading all rows into memory at once.
        # The cursor is a named cursor, which allows for server-side cursors.
        # This means that the cursor will fetch rows from the database server in streaming fashion.
        while True:
            rows = self.vector_cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                # Convert the row to a dictionary
                upsert_row = dict(row)
                # Converting vector data to list for JSON serialization.
                upsert_row = TimescaleClient.serialize_upsert_row(upsert_row)
                # The 'upsert' operation is used to insert or update data in a table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted.
                op.upsert(table=table_name, data=upsert_row)

                # Update the last timestamp if needed
                if upsert_row["created_at"].isoformat() > last_vector_timestamp:
                    last_vector_timestamp = upsert_row["created_at"].isoformat()

            # Update state and checkpoint after each batch
            state["last_vector_timestamp"] = last_vector_timestamp
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)

        # Final checkpoint after all data is processed
        state["last_vector_timestamp"] = last_vector_timestamp
        op.checkpoint(state)

    @staticmethod
    def serialize_upsert_row(data):
        # This method converts any iterable objects (like vectors) to lists for JSON serialization.
        # This is a helper method to ensure that values are serialized correctly.
        for key, value in data.items():
            if key == "vector_data" and isinstance(value, str):
                data[key] = ast.literal_eval(value)
        return data
