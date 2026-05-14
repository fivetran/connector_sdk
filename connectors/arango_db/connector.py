"""ArangoDB Connector for Fivetran Connector SDK.
This connector demonstrates how to sync data from ArangoDB multi-model database.
It syncs document collections (airports, points-of-interest) and edge collections (flights)
showcasing ArangoDB's native support for documents and graphs.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For type hints
from typing import Any

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For connecting to ArangoDB database
from arango import ArangoClient
from arango.exceptions import ArangoServerError, ServerConnectionError

# Batch size for checkpointing during large collection syncs
__CHECKPOINT_BATCH_SIZE = 1000


def schema(configuration: dict) -> list[dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        List of table definitions with primary keys.
    """
    return [
        {"table": "airports", "primary_key": ["_key"]},
        {"table": "flights", "primary_key": ["_key"]},
        {"table": "points_of_interest", "primary_key": ["_key"]},
    ]


def connect_to_arangodb(configuration: dict) -> Any:
    """
    Establish connection to ArangoDB database.
    Args:
        configuration: Configuration dictionary with host, database, username, password.
    Returns:
        Database object for executing queries.
    Raises:
        RuntimeError: If connection fails or configuration is missing.
    """
    required_fields = ["host", "database", "username", "password"]
    missing_fields = [field for field in required_fields if not configuration.get(field)]

    if missing_fields:
        error_msg = f"Missing required configuration fields: {', '.join(missing_fields)}"
        log.error(error_msg)
        raise RuntimeError(error_msg)

    try:
        host = configuration["host"]
        database_name = configuration["database"]
        username = configuration["username"]
        password = configuration["password"]

        client = ArangoClient(hosts=host)
        database = client.db(database_name, username=username, password=password)

        log.info(f"Successfully connected to ArangoDB database '{database_name}'")
        return database
    except ServerConnectionError as e:
        log.error("Failed to connect to ArangoDB server", e)
        raise RuntimeError(f"Failed to connect to ArangoDB server: {str(e)}")
    except ArangoServerError as e:
        log.error("ArangoDB server error during connection", e)
        raise RuntimeError(f"ArangoDB server error during connection: {str(e)}")
    except Exception as e:
        log.error("Unexpected error connecting to ArangoDB", e)
        raise RuntimeError(f"Unexpected error connecting to ArangoDB: {str(e)}")


def get_collection_offset(state: dict, collection_name: str) -> int:
    """
    Get the sync offset for a collection from state.
    Args:
        state: State dictionary tracking sync progress.
        collection_name: Name of the collection to get offset for.
    Returns:
        Current offset for the collection (0 if not found in state).
    """
    state_key = f"{collection_name}_offset"
    return state.get(state_key, 0)


def checkpoint_progress(
    state: dict,
    collection_name: str,
    offset: int,
    batch_count: int,
    batch_size: int,
    total_synced: int,
) -> None:
    """
    Save sync progress to state.
    Args:
        state: State dictionary to update with sync progress.
        collection_name: Name of the collection being synced.
        offset: Current offset position in the collection.
        batch_count: Sequential number of this batch.
        batch_size: Number of documents in the current batch.
        total_synced: Total number of documents synced so far.
    """
    state_key = f"{collection_name}_offset"
    state[state_key] = offset
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)
    log.info(
        f"Synced batch {batch_count} for '{collection_name}': {batch_size} documents (total: {total_synced})"
    )


def sync_collection_batches(
    collection: Any, table_name: str, state: dict, collection_name: str, offset: int
) -> int:
    """
    Sync collection in batches, returns total documents synced.
    Args:
        collection: ArangoDB collection object to sync from.
        table_name: Name of the destination table to sync to.
        state: State dictionary to track and update sync progress.
        collection_name: Name of the collection being synced.
        offset: Starting offset position for syncing.
    Returns:
        Total number of documents synced from the collection.
    """
    total_synced = 0
    batch_count = 0

    while True:
        # Fetch cursor for current batch without materializing to list
        cursor = collection.all(skip=offset, limit=__CHECKPOINT_BATCH_SIZE)

        batch_size = 0
        # Process documents directly from cursor to avoid loading entire batch into memory
        for document in cursor:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=table_name, data=document)
            batch_size += 1

        if batch_size == 0:
            break

        total_synced += batch_size
        offset += batch_size
        batch_count += 1

        checkpoint_progress(state, collection_name, offset, batch_count, batch_size, total_synced)

        if batch_size < __CHECKPOINT_BATCH_SIZE:
            break

    return total_synced


def sync_collection(database: Any, collection_name: str, table_name: str, state: dict) -> int:
    """
    Sync a single ArangoDB collection to destination table with pagination.
    Args:
        database: ArangoDB database connection object.
        collection_name: Name of the ArangoDB collection to sync.
        table_name: Name of the destination table.
        state: State dictionary to track sync progress.
    Returns:
        Updated offset for this collection.
    Raises:
        RuntimeError: If collection access or sync fails.
    """
    try:
        collection = database.collection(collection_name)
        offset = get_collection_offset(state, collection_name)

        log.info(f"Starting sync for collection '{collection_name}' from offset {offset}")

        total_synced = sync_collection_batches(
            collection, table_name, state, collection_name, offset
        )

        log.info(
            f"Completed sync for collection '{collection_name}': {total_synced} documents total"
        )
        return state[f"{collection_name}_offset"]
    except ArangoServerError as e:
        log.error(f"ArangoDB server error while syncing collection '{collection_name}'", e)
        raise RuntimeError(
            f"ArangoDB server error while syncing collection '{collection_name}': {str(e)}"
        )
    except Exception as e:
        log.error(f"Unexpected error syncing collection '{collection_name}'", e)
        raise RuntimeError(f"Unexpected error syncing collection '{collection_name}': {str(e)}")


def update(configuration: dict, state: dict) -> None:
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.info("Example: Database Connector : ArangoDB Multi-Model Database")

    database = connect_to_arangodb(configuration)

    sync_collection(database, "airports", "airports", state)
    sync_collection(database, "flights", "flights", state)
    sync_collection(database, "points-of-interest", "points_of_interest", state)

    log.info("ArangoDB connector sync completed successfully")


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
