# This is an example for how to fetch the schema from a database and use it in your connector.
# It defines a `schema` method, which retrieves the schema from a Snowflake database and returns it in a format that Fivetran can use.
# It defines a simple `update` method, which upserts retrieved data to respective orders and products tables.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import to connect to Snowflake
import snowflake.connector
import json

# Define a constant for the batch size to control how many records are fetched at once for each table.
__BATCH_SIZE = 1000


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
    required_configs = ["user", "password", "account", "database", "schema", "tables"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def get_snowflake_connection(configuration):
    """
    This function connects to the Snowflake database using the provided configuration.
    This method returns a connection object that can be used to interact with the Snowflake database.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        conn: a Snowflake connection object that can be used to interact with the database.
    """
    # Create a connection to Snowflake using the provided configuration
    conn = snowflake.connector.connect(
        user=configuration["user"],
        password=configuration["password"],
        account=configuration["account"],
        database=configuration["database"],
        schema=configuration["schema"],
    )
    log.info("Connected to Snowflake database")

    # return the connection object
    return conn


def get_table_primary_keys(cursor, table_name):
    """
    This function retrieves the primary keys of a specified table from the Snowflake database.
    It executes a SQL command to fetch the primary keys of the table and returns them in lowercase
    Args:
        cursor: a cursor object to execute SQL commands
        table_name: the name of the table for which to fetch primary keys
    Returns:
        A list of primary keys for the specified table, in lowercase.
    """
    cursor.execute(f"SHOW PRIMARY KEYS IN TABLE {table_name}")
    primary_keys = cursor.fetchall()
    # Extract the primary key names from the result set and return them in lowercase
    return [pk[4].lower() for pk in primary_keys]


def get_column_details(configuration, cursor, table_list):
    """
    This function retrieves the column details of the specified tables from the Snowflake database.
    It executes a SQL command to fetch the table name, column name, and data type of each column.
    Args:
        configuration: dictionary contains any secrets or payloads you configure when deploying the connector
        cursor: a cursor object to execute SQL commands
        table_list: a list of table names for which to fetch column details
    Returns:
        A dictionary where the keys are table names and the values are dictionaries of column names and their data types.
    """
    # Execute a SQL command to fetch the table name, column name, and data type of each column
    cursor.execute(
        f"SELECT table_name, column_name, data_type FROM {configuration['database']}.information_schema.columns WHERE table_schema = '{configuration['schema']}';"
    )
    columns = cursor.fetchall()

    table_columns = {}

    # Iterate through the result set and populate the table_columns dictionary
    for column in columns:
        table_name = column[0].lower()
        column_name = column[1].lower()
        # Extract the data type and get the fivetran supported corresponding type
        data_type = get_fivetran_datatype(column[2]).upper()
        if table_name in table_list:
            # If the table name is in the list of selected tables, add it to the dictionary
            if table_name not in table_columns:
                table_columns[table_name] = {}
            table_columns[table_name].update({column_name: data_type})

    return table_columns


def get_fivetran_datatype(snowflake_type):
    """
    This function maps Snowflake data types to Fivetran data types.
    You can modify this function to add more mappings as needed.
    See the technical reference documentation for more details on the supported data types:
    https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes
    Args:
        snowflake_type: the data type from Snowflake that needs to be mapped to Fivetran data type
    Returns:
        The corresponding Fivetran data type as a string, or "STRING" if the type is not found in the mapping.
    """
    type_mapping = {
        "STRING": "STRING",
        "NUMBER": "INT",
        "FLOAT": "FLOAT",
        "INTEGER": "INT",
        "BOOLEAN": "BOOLEAN",
        "VARCHAR": "STRING",
        "CHAR": "STRING",
        "TEXT": "STRING",
        "DATE": "NAIVE_DATE",
        "DECIMAL": "DECIMAL",
        # Add more mappings as needed
    }
    # Return the mapped type or default to STRING if not found
    return type_mapping.get(snowflake_type, "STRING")


def build_schema(configuration, cursor):
    """
    This function builds the schema by fetching the table and column details from the Snowflake database.
    It uses the get_column_details and get_table_primary_keys functions to retrieve the necessary information.
    Args:
        configuration: dictionary contains any secrets or payloads you configure when deploying the connector
        cursor: a cursor object to execute SQL commands
    Returns:
        A list of dictionaries, each representing a table with its name, primary key, and columns as accepted by the schema method.
    """
    # The tables key in configuration should contain a comma-separated string of table names
    # These tables should be present in the Snowflake database
    table_list = get_table_name_from_configuration(configuration=configuration)
    # fetch the column details for the specified tables
    table_columns = get_column_details(configuration, cursor, table_list)
    schema_list = []

    for table_name, columns in table_columns.items():
        # Get the primary key for the table
        primary_key = get_table_primary_keys(cursor, table_name)
        # Add the table schema to the schema_list
        schema_list.append({"table": table_name, "primary_key": primary_key, "columns": columns})

    return schema_list


def close_connection(connection, cursor):
    """
    This function closes the connection and cursor to the Snowflake database.
    Args:
        connection: a Snowflake connection object that was used to interact with the database
        cursor: a cursor object that was used to execute SQL commands
    """
    if cursor:
        cursor.close()
    if connection:
        connection.close()
    log.info("Closed connection to Snowflake database")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # connect to Snowflake using the provided configuration
    connection = get_snowflake_connection(configuration)
    # create a cursor to execute SQL commands
    cursor = connection.cursor()
    # fetch the schema from the Snowflake database in a format that Fivetran can use
    schema_list = build_schema(configuration, cursor)

    # close the cursor and connection
    close_connection(connection=connection, cursor=cursor)

    # return the schema list
    return schema_list


def get_table_name_from_configuration(configuration):
    """
    This function retrieves the list of table names from the configuration dictionary.
    It splits the "tables" key in the configuration into a list of table names.
    Args:
        configuration: A dictionary containing the configuration settings for the connector.
    """
    table_list = configuration["tables"].split(",")
    table_list = [table.strip() for table in table_list]
    return table_list


def fetch_and_upsert_data(cursor, columns, table, state, last_created):
    """
    This function fetches data from the database in batches and yields upsert operations for each row.
    It checkpoints the state after processing each batch
    This ensures that the sync process can resume from the correct position in case of interruptions.
    Args:
        cursor: A cursor object to execute SQL commands and fetch data from the database.
        columns: A list of column names corresponding to the data being fetched.
        table: The name of the table from which data is being fetched.
        state: A dictionary containing state information from previous runs.
        last_created: The last created date from the state dictionary, used to filter new records.
    """
    while True:
        # Fetch data in batches from the database
        data = cursor.fetchmany(__BATCH_SIZE)

        if not data:
            # If no more data is available, break the loop
            break

        for row in data:
            # This is needed to map the column names to the data returned by the query
            # The zip function pairs each column name with its corresponding value in the row tuple
            # The dict function creates a dictionary from these pairs
            upsert_data = dict(zip(columns, row))
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table, data=upsert_data)

            # Update the last created date in the state dictionary
            created_at = upsert_data.get("created_at").isoformat()
            last_created = created_at if created_at > last_created else last_created

        # Update the state dictionary with the last created date after processing the batch
        # This ensures that the next sync will only fetch records created after this date
        state[f"{table}_last_created"] = last_created
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Common Patterns For Connectors - Fetching Schema From Database")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration)

    # connect to Snowflake using the provided configuration to fetch the data
    connection = get_snowflake_connection(configuration)
    cursor = connection.cursor()

    # Fetch the list of table names from the configuration
    table_list = get_table_name_from_configuration(configuration)

    for table in table_list:
        # Fetch the data from each table using a SQL command
        # The last_created date is fetched from the state dictionary, or set to a default value if not present
        last_created = state.get(f"{table}_last_created", "1990-01-01")
        query = f"SELECT * FROM {table} WHERE created_at > '{last_created}'"
        cursor.execute(query)

        # Get the column names from the cursor description
        columns = [col[0].lower() for col in cursor.description]

        # Yield the upsert operations for the fetched data
        fetch_and_upsert_data(
            cursor=cursor,
            columns=columns,
            table=table,
            state=state,
            last_created=last_created,
        )

    # close the cursor and connection
    close_connection(connection=connection, cursor=cursor)


# Create the connector object using the schema and update functions.
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

# Resulting tables:
# Table "orders":
# ┌────────────┬──────────────┬────────────────┬──────────┬──────────┬──────────────────────────────┬────────┐──────────────┐
# | product_id | product_code | product_name   | price    | in_stock | description                  | weight |  created_at  |
# |────────────|──────────────|────────────────|──────────|──────────|──────────────────────────────|────────|──────────────|
# | 101        | LP01         | Laptop Pro     | 1299.99  | True     | High-performance laptop      | 2.5    |  2025-08-08  |
# | 102        | SW01         | Smart Watch    | 249.50   | True     | Fitness tracking smart watch | 0.3    |  2025-08-08  |
# | 103        | OC01         | Office Chair   | 189.95   | False    | Ergonomic office chair       | 12.8   |  2025-08-08  |
# └────────────┴──────────────┴────────────────┴──────────┴──────────┴──────────────────────────────┴────────┘──────────────┘
#
# Table "products":
# ┌───────────────┬─────────────┬─────────────┬────────────┬──────────┬────────────┬──────────┬────────────────┬────────────┬─────────────────┬───────────┬───────┬───────┬──────────────────┐──────────────┐
# | order_id      | customer_id | order_date  | product_id | quantity | unit_price | amount   | payment_method | status     | street_address  | city      | state | zip   | discount_applied |  created_at  |
# |───────────────|─────────────|─────────────|────────────|──────────|────────────|──────────|────────────────|────────────|─────────────────|───────────|───────|───────|──────────────────|──────────────|
# | ord-45678-a   | 1           | 2023-08-15  | 101        | 1        | 1299.99    | 1299.99  | Credit Card    | Completed  | 123 Main St     | Austin    | TX    | 78701 | 10.00            |  2025-08-08  |
# | ord-45678-b   | 1           | 2023-08-15  | 103        | 1        | 189.95     | 189.95   | Credit Card    | Completed  | 123 Main St     | Austin    | TX    | 78701 | 0.00             |  2025-08-08  |
# | ord-98765     | 2           | 2023-09-03  | 102        | 1        | 249.50     | 249.50   | PayPal         | Processing | 456 Park Ave    | New York  | NY    | 10022 | 0.00             |  2025-08-08  |
# | ord-12345-a   | 3           | 2023-09-10  | 101        | 1        | 1299.99    | 1299.99  | Debit Card     | Shipped    | 789 Beach Rd    | Miami     | FL    | 33139 | 15.50            |  2025-08-08  |
# | ord-12345-b   | 3           | 2023-09-10  | 102        | 1        | 249.50     | 249.50   | Debit Card     | Shipped    | 789 Beach Rd    | Miami     | FL    | 33139 | 0.00             |  2025-08-08  |
# └───────────────┴─────────────┴─────────────┴────────────┴──────────┴────────────┴──────────┴────────────────┴────────────┴─────────────────┴───────────┴───────┴───────┴──────────────────┘──────────────┘
