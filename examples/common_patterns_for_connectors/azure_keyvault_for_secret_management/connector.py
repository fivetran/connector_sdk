# This is an example for how to work with the fivetran_connector_sdk module.
# It defines a method, which fetches the Postgres secrets from Azure Key vault and uses it to authenticate with Postgres.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import Azure libraries
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient

# Import other required libraries
import json
import psycopg2


def fetch_secrets_from_vault(configuration: dict):
    """
    This function fetches secrets from Azure Key Vault using the Azure SDK
    It uses the ClientSecretCredential to authenticate and SecretClient to retrieve secrets
    Args:
        configuration: A dictionary containing the Azure Key Vault credentials and URL.
    Returns:
        A dictionary containing the database connection details.
    """
    tenant_id = configuration["tenant_id"]
    client_id = configuration["client_id"]
    client_secret = configuration["client_secret"]
    vault_url = configuration["vault_url"]

    # Set up the client credentials
    credential = ClientSecretCredential(
        tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
    )

    # Create a SecretClient
    secret_client = SecretClient(vault_url=vault_url, credential=credential)

    # Fetch the secrets
    db_config = {}
    try:
        db_config["database"] = secret_client.get_secret("postgresDatabase").value
        db_config["host"] = secret_client.get_secret("postgresHost").value
        db_config["user"] = secret_client.get_secret("postgresUser").value
        db_config["password"] = secret_client.get_secret("postgresPassword").value
        db_config["port"] = secret_client.get_secret("postgresPort").value
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve secrets from Azure Key Vault: {str(e)}")

    log.info("Successfully retrieved all secrets from Azure Key Vault")
    return db_config


def connect_to_database(db_config: dict):
    """
    This function connects to the PostgreSQL database using the credentials fetched from Azure Key Vault
    Args:
        db_config: A dictionary containing the database connection details.
    Returns:
        connection object: A connection object to the PostgreSQL database.
    """
    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config.get("port", 5439),
            dbname=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        log.info("Successfully connected to database")
        return conn
    except Exception as e:
        raise RuntimeError(f"Failed to connect to database: {str(e)}")


def get_data_from_database(conn):
    """
    This function retrieves data from the PostgreSQL database
    Args:
        conn: A connection object to the PostgreSQL database.
    Returns:
        records: A list of records retrieved from the database.
        columns: A list of column names in the result set.
    """
    try:
        # This simple query demonstrates the purpose; in a production connector, you would query all data that you want to sync.
        sql_query = "SELECT * from employee_table"
        with conn.cursor() as cursor:
            cursor.execute(sql_query)
            records = cursor.fetchall()
            # The cursor.description attribute contains metadata about the columns in the result set.
            columns = [col[0].lower() for col in cursor.description]
            log.info(f"Fetched {len(records)} records from the database")

        # Close the connection to database
        conn.close()
        return columns, records
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data from database: {str(e)}")


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
    required_configs = ["tenant_id", "client_id", "client_secret", "vault_url"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


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
            "table": "employees",  # Name of the table
            "primary_key": ["id"],  # Primary key(s) of the table
            "columns": {
                "id": "INT",
                "name": "STRING",
                "department_id": "INT",
                "employee_metadata": "JSON",
            },
            # Columns not defined in schema will be inferred
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: dictionary containing any secrets or payloads you configure when deploying the connector.
        state:  a dictionary containing the state checkpointed during the prior sync.
        The state dictionary is empty for the first sync or for any full re-sync.
    """
    log.warning("Example: Common Patterns For Connectors - Azure Key Vault For Secret Management")

    # Check if the required fields are present in the configuration
    validate_configuration(configuration=configuration)

    # Fetch database credentials from vault
    db_config = fetch_secrets_from_vault(configuration)

    # Connect to database
    conn = connect_to_database(db_config)

    # Get data from the database
    # It is assumed that the table name is "employee_table".
    # The table has the columns "id", "name", "department_id", and "employee_metadata".
    # This table should be present in the database for successfully running this example.
    columns, records = get_data_from_database(conn)

    for record in records:
        # This is required to create a dictionary with the column names as keys and the record values as values.
        upsert_data = dict(zip(columns, record))

        # The 'upsert' operation inserts the data into the destination.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into, in this case, "employees".
        # - The second argument is a dictionary containing the data to be upserted.
        op.upsert("employees", upsert_data)

    log.debug(f"Upserted {len(records)} records to table 'employees'")
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)
