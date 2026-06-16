# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with a self-managed Couchbase Server using Magma storage engine.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import the required libraries
from datetime import timedelta, datetime, timezone
import json
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions, QueryOptions


def create_couchbase_client(configuration: dict):
    """
    Create a Couchbase client for on-prem or cloud-hosted Couchbase Server.
    Supports both TLS and non-TLS endpoints based on configuration.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        cluster_bucket: a couchbase bucket reference object
    """
    username = configuration.get("username")
    password = configuration.get("password")
    endpoint = configuration.get("endpoint")
    bucket_name = configuration.get("bucket_name")
    use_tls_str = configuration.get("use_tls", "false").strip().lower()  # Optional flag to use TLS
    use_tls = use_tls_str == "true"
    cert_path = configuration.get("cert_path")  # Optional path to cert

    try:
        # Authenticate using the provided username and password
        auth = PasswordAuthenticator(username, password)
        options = ClusterOptions(auth)

        # Use secure connection if use_tls is true
        if use_tls:
            connection_string = f"couchbases://{endpoint}"
            if not cert_path:
                raise ValueError("TLS is enabled but cert_path is not provided.")
            cluster = Cluster(connection_string, options, tested_cert_path=cert_path)
        else:
            connection_string = f"couchbase://{endpoint}"
            cluster = Cluster(connection_string, options)

        # Wait until the cluster is ready for use.
        cluster.wait_until_ready(timedelta(seconds=5))

        # get a reference to couchbase magma bucket
        cluster_bucket = cluster.bucket(bucket_name)
        log.info(f"Connected to bucket '{bucket_name}' at '{connection_string}' successfully.")
        return cluster_bucket

    except Exception as e:
        raise RuntimeError(f"Failed to connect to Couchbase: {e}")


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
            created_at_str = row_data["created_at"]
            row_data["created_at"] = to_utc_datetime_str(created_at_str)
            # Perform an upsert operation to the Fivetran connector.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(table=table_name, data=row_data)
            # Update state based on the latest "created_at"
            state["last_created_at"] = row_data["created_at"]
            count += 1

            if count % checkpoint_interval == 0:
                # Checkpoint the state every CHECKPOINT_INTERVAL records to avoid losing progress
                # With regular checkpointing, the next sync will start from the last checkpoint of the previous failed sync, thus saving time.
                op.checkpoint(state)

        op.checkpoint(state)

    except Exception as e:
        # In case of exception, raise a RuntimeError
        raise RuntimeError(f"Failed to fetch and upsert data: {e}")

    log.info(f"Upserted {count} records into {table_name} successfully.")


def to_utc_datetime_str(timestamp_str: str) -> datetime:
    """
    Convert an ISO-8601 timestamp string to a UTC datetime object without microseconds.

    Returns:
        A timezone-aware datetime object in UTC (tzinfo=timezone.utc) with no microseconds.
    """
    # Normalize 'Z' to '+00:00' to make it ISO-8601 compliant
    if timestamp_str.endswith("Z"):
        timestamp_str = timestamp_str[:-1] + "+00:00"

    # Parse the ISO string
    dt = datetime.fromisoformat(timestamp_str)

    # If tz-naive, assume UTC; else convert to UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    # Remove microseconds and ensure UTC tzinfo is preserved
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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
            raise ValueError(f"Missing required configuration value: {key}")

    return [
        {
            "table": "airline_table",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
                "created_at": "UTC_DATETIME",  # Ensure created_at is in UTC format
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
    last_created = state.get("last_created_at", "1970-01-01T00:00:00Z")

    # name of the table to upsert data into
    table_name = "airline_table"

    # SQL query to fetch data from the collection
    # You can modify this query to fetch data as per your requirements.
    sql_query = (
        f"SELECT * FROM `{collection}` "
        f"WHERE created_at > '{last_created}' "
        f"ORDER BY created_at ASC"
    )

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
