# This example demonstrates how to connect to a Database server over SSH tunnels via a Bastion Server using `sshtunnel` and `paramiko`.
# This example uses key-based authentication for the SSH tunnel.
# It establishes a secure SSH tunnel from a local port to a remote Bastion server port, which has access to a private database server .
# The connector uses Postgres credentials to fetch the data over the SSH tunnel.
# For this example, an EC2 instance is running PostgreSQL database server and is only accessible via a Bastion server over SSH.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

import io  # For handling in-memory streams for SSH keys
from sshtunnel import SSHTunnelForwarder  # For creating SSH tunnels
import paramiko  # For handling SSH keys and connections
import psycopg2  # For interacting with PostgreSQL
import psycopg2.extras  # For using RealDictCursor to get dict-like cursor results
import base64  # For decoding base64 encoded SSH keys

__CHECKPOINT_INTERVAL = 1000  # Number of records to process before checkpointing state
__LOCAL_BIND_ADDRESS = "127.0.0.1"  # Local address for SSH tunnel
__LOCAL_BIND_PORT = 6543  # Local port for SSH tunnel; ensure this port is free
__SSH_PORT = 22  # Default SSH port


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
    required_configs = [
        "bastion_host",
        "bastion_port",
        "bastion_user",
        "bastion_private_key",
        "private_host",
        "private_port",
        "db_user",
        "db_password",
        "db_name",
    ]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def upsert_data(database_cursor, state, last_modified):
    """
    This function iterates over the data fetched from the source and performs upsert operations to the destination.
    It also checkpoints the state to ensure that the sync process can resume from the correct position in case of interruptions.
    Args:
        database_cursor: A cursor object containing the results of the executed query.
        state: A dictionary containing state information from previous runs
        last_modified: The last modified timestamp from the state, defaulting to a very old date if not present
    """
    # Initialize a counter to keep track of the number of processed records
    count = 0
    # Iterate over each user in the 'items' list and perform an upsert operation.
    # The 'upsert' operation inserts the data into the destination.
    for row in database_cursor:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="sample_users", data=row)
        # Increment the counter after processing each record
        count += 1

        # Update the last_modified to the modified_at of the current row.
        # This ensures that the next sync will only fetch records modified after this timestamp.
        row_modified = row["modified_at"].isoformat()
        if "modified_at" in row and row_modified > last_modified:
            last_modified = row_modified

        if count % __CHECKPOINT_INTERVAL == 0:
            state["last_modified"] = last_modified
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

    state["last_modified"] = last_modified
    # Save the progress by checkpointing the state after processing all records
    # This is important for ensuring that the sync process can resume from the correct position
    # in case of next sync or interruptions.
    op.checkpoint(state)


def upsert_data_from_database(
    bastion_host,
    bastion_port,
    bastion_user,
    bastion_key,
    bastion_passphrase,
    private_host,
    private_port,
    database_credentials,
    state,
):
    """
    Connect to the database over an SSH tunnel via a bastion server and execute the provided SQL query.
    Fetch data from the database and perform upsert operations to the destination.
    Args:
        bastion_host: The hostname or IP address of the bastion server.
        bastion_port: The port number of the bastion server (default is 22).
        bastion_user: The SSH username for the bastion server.
        bastion_key: The private SSH key for the bastion server (as a base64 encoded string).
        bastion_passphrase: The passphrase for the private SSH key, if applicable.
        private_host: The hostname or IP address of the private database server.
        private_port: The port number of the private database server.
        database_credentials: A dictionary containing database connection details:
            - database_user: The database username.
            - database_password: The database password.
            - database_name: The name of the database to connect to.
        state: A dictionary containing state information from previous runs
    Returns:
        A cursor object containing the results of the executed query.
    """
    # Load the private key from the provided string and create an RSAKey object
    bastion_key = base64.b64decode(bastion_key).decode("utf-8")
    key_stream = io.StringIO(bastion_key)
    bastion_passphrase = bastion_passphrase or None

    try:
        private_key = paramiko.RSAKey.from_private_key(key_stream, password=bastion_passphrase)
    except Exception as e:
        log.error("Failed to load SSH private key", e)
        raise

    try:
        # Establish the SSH tunnel to the bastion server and connect to the private database server
        with SSHTunnelForwarder(
            (bastion_host, bastion_port),
            ssh_username=bastion_user,
            ssh_pkey=private_key,
            remote_bind_address=(private_host, private_port),
            local_bind_address=(__LOCAL_BIND_ADDRESS, __LOCAL_BIND_PORT),
        ) as tunnel:
            log.info(f"Tunnel established on local port {tunnel.local_bind_port}")
            # Connect to the PostgreSQL database using the SSH tunnel
            connection = psycopg2.connect(
                host=__LOCAL_BIND_ADDRESS,
                port=tunnel.local_bind_port,
                user=database_credentials["database_user"],
                password=database_credentials["database_password"],
                dbname=database_credentials["database_name"],
            )
            # Fetch data and upsert into destination
            fetch_and_upsert_data(database_connection=connection, state=state)
    except Exception as e:
        log.error("Failed to connect to the database or execute query", e)
        raise


def fetch_and_upsert_data(database_connection, state):
    """
    Fetch data from the database and perform upsert operations to the destination.
    Args:
        database_connection: A connection object to the PostgreSQL database.
        state: A dictionary containing state information from previous runs
    """
    # Get the last modified timestamp from the state, defaulting to a very old date if not present
    # This can be used to fetch only new or updated records since the last sync.
    last_modified = state.get("last_modified", "1970-01-01T00:00:00Z")

    # Define the SQL query to fetch data from the source.
    # You can modify this query based on your requirements.
    sql_query = f"SELECT * FROM sample_users WHERE modified_at > '{last_modified}' ORDER BY modified_at ASC;"
    # Use RealDictCursor to get results as dictionaries instead of tuples
    database_cursor = database_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    database_cursor.execute(sql_query)

    # Upsert data and checkpoint state
    upsert_data(database_cursor=database_cursor, state=state, last_modified=last_modified)

    # Close the database cursor and connection
    database_cursor.close()
    database_connection.close()


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
            "table": "sample_users",  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "id": "STRING",  # Contains a dictionary of column names and data types
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example : Common Pattern For Connectors - Bastion Server : Key based replication")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Fetch configuration parameters from the configuration
    bastion_host = configuration.get("bastion_host")
    bastion_port = int(configuration.get("bastion_port", __SSH_PORT))
    bastion_user = configuration.get("bastion_user")
    bastion_key = configuration.get("bastion_private_key")
    bastion_passphrase = configuration.get("bastion_passphrase")
    private_host = configuration.get("private_host")
    private_port = int(configuration.get("private_port"))

    # Prepare database connection details as a dictionary
    database_credentials = {
        "database_user": configuration.get("db_user"),
        "database_password": configuration.get("db_password"),
        "database_name": configuration.get("db_name"),
    }

    # Fetch data from the database over the SSH tunnel
    upsert_data_from_database(
        bastion_host=bastion_host,
        bastion_port=bastion_port,
        bastion_user=bastion_user,
        bastion_key=bastion_key,
        bastion_passphrase=bastion_passphrase,
        private_host=private_host,
        private_port=private_port,
        database_credentials=database_credentials,
        state=state,
    )


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    try:
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        # Fallback to an empty configuration if the file is not found
        configuration = {}
    # Allows testing the connector directly
    connector.debug(configuration=configuration)
