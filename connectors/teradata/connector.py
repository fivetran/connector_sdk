# This is a simple example for how to work with the fivetran_connector_sdk module.
# The example demonstrates how to fetch data from Teradata Vantage database using teradatasql and upsert it into a destination table.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries.
import json
from datetime import date
import teradatasql  # Required for connecting to Teradata Vantage database.

__DESTINATION_TABLE = "employee"
__BATCH_SIZE = 100


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters for connecting to the Teradata Vantage database.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Check if the credentials for connecting to database is present in the configuration.
    cred = [
        "teradata_host",
        "teradata_user",
        "teradata_password",
        "teradata_database",
        "teradata_table",
    ]
    for key in cred:
        if key not in configuration:
            raise ValueError(f"Missing required configuration: {key}")


def connect_to_teradata(configuration: dict):
    """
    This method establishes a connection to Teradata Vantage database using teradatasql.
    It uses the connection parameters provided in the configuration.
    If the connection fails, it raises a ConnectionError with a message.
    """
    host = configuration.get("teradata_host")
    user = configuration.get("teradata_user")
    password = configuration.get("teradata_password")

    try:
        connection = teradatasql.connect(host=host, user=user, password=password)
        return connection
    except Exception as e:
        raise ConnectionError(f"Error connecting to Teradata Vantage database: {e}")


def process_row_for_upsert(row, columns):
    """
    This function processes a row fetched from the Teradata Vantage database and prepares it for upsert into the destination table.
    It returns a dictionary with the processed row data.
    You can process row data as needed in this function, such as converting data types or formatting dates
    Args:
        row: a list representing a row fetched from the Teradata Vantage database.
        columns: a list of column names corresponding to the row data.
    """
    # Create a dictionary from the row data and column names.
    # The zip() function pairs each column name with its corresponding value in the row.
    row_dict = dict(zip(columns, row))

    # Format any date object into a YYYY-MM-DD string
    # isinstance() check ensures we only format if it's a date object
    for col, val in row_dict.items():
        if isinstance(val, date):
            row_dict[col] = val.isoformat()

    return row_dict


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    return [
        {
            "table": __DESTINATION_TABLE,  # Name of the table in the destination.
            "primary_key": ["EmployeeID"],  # Primary key column(s) for the table.
            "columns": {
                "EmployeeID": "INT",
                "JoiningDate": "NAIVE_DATE",
            },
            # columns not defined will be inferred.
        },
    ]


def fetch_and_upsert_data(cursor, configuration, state):
    """
    This function fetches data from the Teradata Vantage database based on the last joining date stored in the state.
    Args:
        cursor: a cursor object to execute SQL queries.
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary containing the state checkpointed during the prior sync.
    """
    # Extract the database and table name from the configuration.
    database = configuration.get("teradata_database")
    table_name = configuration.get("teradata_table")
    # Get the last joining date from the state dictionary.
    last_joining_date = state.get("last_joining_date", "1990-01-01")

    # SQL query to select data from the Teradata Vantage database.
    # You can modify the query to suit your needs, such as filtering by date or other criteria.
    select_sql = (
        f"SELECT * FROM {database}.{table_name} WHERE JoiningDate > ? ORDER BY JoiningDate"
    )
    cursor.execute(select_sql, (last_joining_date,))

    # Fetch the column names from the cursor description.
    columns = [desc[0] for desc in cursor.description]

    while True:
        # Fetch data in batches of __BATCH_SIZE rows.
        # This is to avoid loading all rows into memory at once. This prevents memory overflow issues for large datasets.
        data = cursor.fetchmany(__BATCH_SIZE)

        if not data:
            # No more data to fetch, break the loop.
            break

        # Process each row in the fetched data.
        for row in data:
            # process the row and prepare it for upsert.
            upsert_row = process_row_for_upsert(row, columns)
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=__DESTINATION_TABLE, data=upsert_row)

            if upsert_row["JoiningDate"] > last_joining_date:
                # Update the last joining date in the state if the current row's JoiningDate is greater.
                last_joining_date = upsert_row["JoiningDate"]

        # Update the state with the last joining date for the next sync.
        state["last_joining_date"] = last_joining_date
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: dictionary containing any secrets or payloads you configure when deploying the connector.
        state:  a dictionary containing the state checkpointed during the prior sync.
        The state dictionary is empty for the first sync or for any full re-sync.
    """
    log.warning("Example: Source Examples: Teradata Vantage Database")

    # Validate the configuration to ensure all required parameters are present.
    validate_configuration(configuration)

    # Establish a connection to the Teradata Vantage database and create a cursor.
    connection = connect_to_teradata(configuration=configuration)
    cursor = connection.cursor()

    try:
        # Fetch data from the Teradata Vantage database and upsert it into the destination table.
        fetch_and_upsert_data(cursor=cursor, configuration=configuration, state=state)
    except Exception as e:
        raise RuntimeError(f"An error occurred during the update process: {e}")
    finally:
        # Ensure the connection is closed properly after the operation.
        disconnect_from_database(connection=connection, cursor=cursor)


def disconnect_from_database(connection, cursor):
    # This method closes the connection to Teradata Vantage database.
    # It checks if the connection is open before attempting to close it.
    if cursor:
        cursor.close()
    if connection:
        connection.close()
    log.info("Teradata Vantage connection closed.")


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
