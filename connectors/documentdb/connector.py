"""
This is an example for how to work with the fivetran_connector_sdk module.
This example demonstrates how to connect to AWS DocumentDB and upsert data queried from DocumentDB collections.
NOTE: Fivetran already provides a native Java-based DocumentDB connector that supports SaaS deployment models.
This Python-based connector is specifically intended for Hybrid Deployment (HD) scenarios, as the native connector
does not support Hybrid Deployment. For SaaS deployments, we recommend using the native DocumentDB connector
available at https://fivetran.com/docs/connectors/databases/documentdb.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

import datetime

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Required for data transformations before upsert
from datetime import timezone
from dateutil import parser

# Import the MongoDB driver for DocumentDB (DocumentDB is MongoDB-compatible)
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# Checkpoint every 1000 records. You can modify this number based on your requirements
__CHECKPOINT_INTERVAL = 1000
__DEFAULT_START_DATE = "1990-01-01T00:00:00Z"


def create_documentdb_connection(configuration: dict):
    """
    Create a connection to AWS DocumentDB
    This function creates a MongoDB client connection to DocumentDB using the pymongo library.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        client: a MongoDB client object connected to DocumentDB
    """
    host = configuration.get("hostname")
    port = int(configuration.get("port", 27017))
    username = configuration.get("username")
    password = configuration.get("password")

    # DocumentDB connection string
    connection_string = f"mongodb://{username}:{password}@{host}:{port}/?tls=true&retryWrites=false&DirectConnection=true"

    try:
        # Create MongoDB client without SSL configuration
        client = MongoClient(
            connection_string,
            tls=True,
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True,
        )

        # Test the connection
        client.admin.command("ping")
        log.info("Connection to DocumentDB successful")
        return client

    except ConnectionFailure as e:
        raise RuntimeError(f"Failed to connect to DocumentDB: {e}")
    except ServerSelectionTimeoutError as e:
        raise RuntimeError(f"DocumentDB server selection timeout: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error connecting to DocumentDB: {e}")


def fetch_documents_with_pagination(collection, last_updated_at: str, batch_size: int = 100):
    """
    Fetches documents from DocumentDB collection using pagination.
    Args:
        collection: MongoDB collection object
        last_updated_at: ISO timestamp string for incremental sync
        batch_size: Number of documents to fetch per batch
    Returns:
        Generator of fetched documents
    """
    try:
        # Convert timestamp string to datetime object
        timestamp_obj = parser.parse(last_updated_at)
        if timestamp_obj.tzinfo is None:
            # Add UTC timezone if missing
            timestamp_obj = timestamp_obj.replace(tzinfo=timezone.utc)

        # Query to fetch documents updated after the last sync time
        # You can modify this query to suit your specific needs
        query = {"updated_at": {"$gt": timestamp_obj}}

        # Sort by updated_at to ensure consistent ordering
        sort_criteria = [("updated_at", 1)]

        # Use find with cursor for efficient pagination
        cursor = collection.find(query).sort(sort_criteria).batch_size(batch_size)

        # Iterate through the cursor and yield each document
        # This approach is memory-efficient for large datasets
        for document in cursor:
            yield document

    except Exception as e:
        raise RuntimeError(f"Error fetching documents from DocumentDB: {e}")


def upsert_documents_from_orders(client, database_name: str, state: dict):
    """
    Fetches documents from DocumentDB orders collection, upserts them, and updates state.
    Args:
        client: MongoDB client object
        database_name: Name of the DocumentDB database
        state: A dictionary containing state information from previous runs
    """
    collection_name = "orders"
    # Get the database and collection
    db = client[database_name]
    collection = db[collection_name]

    # Get the last sync time from the state for orders
    state_key = f"{collection_name}_last_updated_at"
    last_sync = state.get(state_key, __DEFAULT_START_DATE)
    max_updated_at = parser.parse(last_sync)
    if max_updated_at.tzinfo is None:
        max_updated_at = max_updated_at.replace(tzinfo=timezone.utc)

    record_count = 0

    # Fetch documents from DocumentDB orders collection
    for document in fetch_documents_with_pagination(collection, last_sync):
        # Ensure updated_at has timezone info before comparison
        doc_updated_at = add_timezone_helper(document.get("updated_at"))

        # Prepare the record for upsert - Orders specific fields
        document["_id"] = str(document.get("_id"))
        document["created_at"] = add_timezone_helper(document.get("created_at"))
        document["updated_at"] = doc_updated_at
        document["metadata"] = document.get("items", [])

        # The 'upsert' operation is used to insert or update data in the destination table.
        op.upsert(table=collection_name, data=document)
        record_count += 1

        # Update the max_updated_at with doc_updated_at
        max_updated_at = doc_updated_at

        # Checkpoint every 1000 records
        if record_count % __CHECKPOINT_INTERVAL == 0:
            state[state_key] = max_updated_at.isoformat()
            op.checkpoint(state)
            log.info(f"{record_count} orders processed")

    log.info(f"Total orders processed: {record_count}")

    # Checkpoint the last updated_at timestamp for orders
    state[state_key] = max_updated_at.isoformat()
    op.checkpoint(state)


def upsert_documents_from_users(client, database_name: str, state: dict):
    """
    Fetches documents from DocumentDB users collection, upserts them, and updates state.
    Args:
        client: MongoDB client object
        database_name: Name of the DocumentDB database
        state: A dictionary containing state information from previous runs
    """
    collection_name = "users"
    # Get the database and collection
    db = client[database_name]
    collection = db[collection_name]

    # Get the last sync time from the state for users
    state_key = f"{collection_name}_last_updated_at"
    last_sync = state.get(state_key, __DEFAULT_START_DATE)
    max_updated_at = parser.parse(last_sync)
    if max_updated_at.tzinfo is None:
        max_updated_at = max_updated_at.replace(tzinfo=timezone.utc)

    record_count = 0

    # Fetch documents from DocumentDB users collection
    for document in fetch_documents_with_pagination(collection, last_sync):
        # Ensure updated_at has timezone info before comparison
        doc_updated_at = add_timezone_helper(document.get("updated_at"))

        # Prepare the record for upsert - Users specific fields
        document["_id"] = str(document.get("_id"))
        document["created_at"] = add_timezone_helper(document.get("created_at"))
        document["updated_at"] = doc_updated_at
        document["metadata"] = document.get("metadata", {})

        # The 'upsert' operation is used to insert or update data in the destination table.
        op.upsert(table=collection_name, data=document)
        record_count += 1

        # Update the max_updated_at with doc_updated_at
        max_updated_at = doc_updated_at

        # Checkpoint every 1000 records
        if record_count % __CHECKPOINT_INTERVAL == 0:
            state[state_key] = max_updated_at.isoformat()
            op.checkpoint(state)
            log.info(f"{record_count} users processed")

    log.info(f"Total users processed: {record_count}")

    # Checkpoint the last updated_at timestamp for users
    state[state_key] = max_updated_at.isoformat()
    op.checkpoint(state)


def add_timezone_helper(doc_updated_at: datetime.datetime):
    """
    Converts datetime object to utc timezone if timezone is not present.
    Args:
        doc_updated_at a datetime object with or without timezone info
    """
    if doc_updated_at and doc_updated_at.tzinfo is None:
        doc_updated_at = doc_updated_at.replace(tzinfo=timezone.utc)
    return doc_updated_at


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
            "table": "users",
            "primary_key": ["_id"],
            "columns": {
                "_id": "STRING",
                "created_at": "UTC_DATETIME",
                "updated_at": "UTC_DATETIME",
                "metadata": "JSON",
            },
        },
        {
            "table": "orders",
            "primary_key": ["_id"],
            "columns": {
                "_id": "STRING",
                "created_at": "UTC_DATETIME",
                "updated_at": "UTC_DATETIME",
                "items": "JSON",
            },
        },
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
    # Create a DocumentDB connection
    client = create_documentdb_connection(configuration)
    database_name = configuration.get("database")
    validate_configuration(configuration)

    # IMPORTANT: This connector requires that the following prerequisites exist in your DocumentDB instance:
    # 1. A database named as specified in your configuration
    # 2. Collections named 'users' and 'orders' with documents containing the following fields:
    #    For users collection:
    #    - _id (ObjectId): Primary key
    #    - name (string): User name
    #    - email (string): User email
    #    - status (string): User status
    #    - created_at (datetime): Document creation timestamp
    #    - updated_at (datetime): Document update timestamp
    #    - metadata (object): Additional user metadata
    #
    #    For orders collection:
    #    - _id (ObjectId): Primary key
    #    - user_id (string): Reference to user
    #    - order_number (string): Order identifier
    #    - total_amount (number): Order total
    #    - status (string): Order status
    #    - created_at (datetime): Order creation timestamp
    #    - updated_at (datetime): Order update timestamp
    #    - items (array): Order items
    #
    # Example documents:
    # Users: {"_id": ObjectId(), "name": "John Doe", "email": "john@example.com", "status": "active", "created_at": ISODate(), "updated_at": ISODate(), "metadata": {"source": "web"}}
    # Orders: {"_id": ObjectId(), "user_id": "user123", "order_number": "ORD-001", "total_amount": 99.99, "status": "completed", "created_at": ISODate(), "updated_at": ISODate(), "items": [{"product": "Widget", "quantity": 2}]}
    #
    # If these prerequisites are not met, the connector will not function correctly.
    log.warning("Example: Source Examples - DocumentDB")
    try:
        # Sync users collection
        log.info("Starting sync of users collection")
        upsert_documents_from_users(client=client, database_name=database_name, state=state)

        # Sync orders collection
        log.info("Starting sync of orders collection")
        upsert_documents_from_orders(client=client, database_name=database_name, state=state)
    finally:
        # Close the client connection
        client.close()


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary for required fields.
    Args:
        configuration (dict): A dictionary containing the connection parameters.
    Raises:
        ValueError: If any required field is missing or invalid.
    """
    required_fields = ["hostname", "port", "username", "password", "database"]
    for field in required_fields:
        if field not in configuration or not configuration[field]:
            raise ValueError(f"Missing required configuration field: {field}")
    log.info("Configuration validation passed.")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Test the connector locally
    connector.debug(configuration=configuration)
