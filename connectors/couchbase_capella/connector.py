# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with a Couchbase Capella.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
from datetime import timedelta
import json
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions, QueryOptions


def create_couchbase_client(configuration: dict):
    """
    This function creates a couchbase client using the couchbase library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        cluster_bucket: a couchbase bucket reference object
    """
    username = configuration.get("username")
    password = configuration.get("password")
    endpoint = configuration.get("endpoint")
    bucket_name = configuration.get("bucket_name")

    try:
        # Authenticate using the provided username and password
        auth = PasswordAuthenticator(username, password)
        options = ClusterOptions(auth)

        # Sets a pre-configured profile called "wan_development" to help avoid latency issues
        # when accessing Capella from a different Wide Area Network or Availability Zone(e.g. your laptop).
        options.apply_profile("wan_development")
        cluster = Cluster("couchbases://{}".format(endpoint), options)

        # Wait until the cluster is ready for use.
        cluster.wait_until_ready(timedelta(seconds=5))

        # get a reference to couchbase bucket
        cluster_bucket = cluster.bucket(bucket_name)
        log.info(f"Connected to bucket {bucket_name} successfully.")
        return cluster_bucket

    except Exception as e:
        raise RuntimeError(f"Failed to connect to couchbase: {e}")


def execute_query_and_upsert(client, scope, collection, query, table_name, state):
    """
    This function executes a query and upserts the results into destination.
    The data is fetched in a streaming manner to handle large datasets efficiently.
    Args:
        client: a couchbase client object
        scope: the scope of the collection
        collection: the name of the collection to query
        query: the SQL query to execute
        table_name: the name of the table to upsert data into
        state: a dictionary that holds the state of the connector
    """
    # set the scope in the couchbase client
    client_scope = client.scope(scope)
    count = 0
    checkpoint_interval = 1000
    try:
        # Execute the query and fetch the results
        # By default, couchbase does not load the entire data in the memory.
        # Instead, it streams the data when iterated over. This helps to avoid memory overflow issues.
        row_iter = client_scope.query(query, QueryOptions(metrics=False))
        for row in row_iter:
            row_data = row.get(collection)
            # The 'upsert' operation is used to insert or update the data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=row_data)
            count += 1

            if count % checkpoint_interval == 0:
                # Checkpoint the state every CHECKPOINT_INTERVAL records to avoid losing progress
                # With regular checkpointing, the next sync will start from the last checkpoint of the previous failed sync, thus saving time.
                op.checkpoint(state)

    except Exception as e:
        # In case of exception, raise a RuntimeError
        raise RuntimeError(f"Failed to fetch and upsert data : {e}")

    log.info(f"Upserted {count} records into {table_name} successfully.")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # check if required configuration values are present in configuration
    for key in ["endpoint", "username", "password", "bucket_name", "scope", "collection"]:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value : {key}")

    return [
        {
            "table": "airline_table",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
            },
        }
    ]


def update(configuration, state):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    # Create a couchbase client
    client = create_couchbase_client(configuration)
    scope = configuration.get("scope")
    collection = configuration.get("collection")

    # name of the table to upsert data into
    table_name = "airline_table"

    # SQL query to fetch data from the collection
    # You can modify this query to fetch data as per your requirements.
    sql_query = f"SELECT * FROM `{collection}`"

    # execute the query and upsert the data into destination
    execute_query_and_upsert(
        client=client,
        scope=scope,
        collection=collection,
        query=sql_query,
        table_name=table_name,
        state=state,
    )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
