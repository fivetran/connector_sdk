"""RavenDB Documents Connector for Fivetran - fetches document data from RavenDB collections.
This connector demonstrates how to fetch document data from RavenDB NoSQL database and sync it to Fivetran using the RavenDB Python client.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import the RavenDB Python SDK for connecting to RavenDB database
from ravendb import DocumentStore
from ravendb.exceptions.raven_exceptions import RavenException

# For handling type hints
from typing import Optional, List, Dict, Any, Tuple

# For handling the deployment-safe base64-encoded certificate
import base64
import tempfile
import os

# For exponential backoff delays during retry logic
import time

__DEFAULT_BATCH_SIZE = 100
__DEFAULT_COLLECTION_NAME = "Orders"
__EARLIEST_TIMESTAMP = "1990-01-01T00:00:00.0000000Z"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function validates both the presence and format of configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """

    # Validate required configuration parameters are present
    required_configs = ["ravendb_urls", "database_name", "certificate_base64"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")
        if not configuration[key] or not str(configuration[key]).strip():
            raise ValueError(f"Configuration value for {key} cannot be empty")

    # Validate that ravendb_urls contains at least one valid URL
    ravendb_urls = configuration.get("ravendb_urls", "")
    urls = [u.strip() for u in ravendb_urls.split(",") if u.strip()]
    if not urls:
        raise ValueError("No valid RavenDB URLs provided")

    # Validate URL format (should start with http:// or https://)
    for url in urls:
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid URL format: {url}. URLs must start with http:// or https://"
            )

    # Validate database_name is not empty and contains valid characters
    database_name = configuration.get("database_name", "").strip()
    if not database_name:
        raise ValueError("database_name cannot be empty")

    # Validate certificate_base64 is valid base64-encoded string
    certificate_base64 = configuration.get("certificate_base64", "")
    try:
        decoded = base64.b64decode(certificate_base64, validate=True)
        if not decoded:
            raise ValueError("certificate_base64 decodes to empty content")
    except Exception as e:
        raise ValueError(f"certificate_base64 must be a valid base64-encoded string: {e}")


def flatten_dict(data: dict, prefix: str = "", separator: str = "_") -> dict:
    """
    Flatten a nested dictionary by concatenating keys with a separator.
    This is used to convert nested JSON documents into flat table structures.

    Args:
        data: The dictionary to flatten
        prefix: Prefix to add to keys (used for recursion)
        separator: Separator to use between nested keys

    Returns:
        A flattened dictionary
    """
    flattened = {}

    for key, value in data.items():
        # Skip RavenDB metadata fields that start with @
        if key.startswith("@"):
            continue

        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            flattened.update(flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            # Convert lists to JSON strings for storage
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # Get collection name from configuration or use default
    collection_name = configuration.get("collection_name", __DEFAULT_COLLECTION_NAME)

    return [
        {
            "table": collection_name.lower(),  # Name of the table in the destination, required.
            "primary_key": ["Id"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "Id": "STRING",  # RavenDB document ID is a string
            },  # For any columns whose names are not provided here, their data types will be inferred
        },
    ]


def create_document_store(configuration: dict) -> Tuple[DocumentStore, str]:
    """Create and initialize a RavenDB DocumentStore using a base64-encoded PEM certificate.

    Deployment note:
    In the Fivetran runtime you cannot rely on local file paths being present. The
    certificate is therefore supplied as a base64 string in configuration, decoded
    at runtime, written to a transient temp PEM file, and referenced by the RavenDB
    client. The caller is responsible for cleaning up the certificate file.
    Args:
        configuration: Connector configuration dict containing: ravendb_urls, database_name, certificate_base64.
    Returns:
        A tuple of (initialized DocumentStore instance, temporary certificate file path).
    """
    ravendb_urls = configuration.get("ravendb_urls")
    database_name = configuration.get("database_name")
    certificate_base64 = configuration.get("certificate_base64")

    # Initialize temp_cert_path so it is available in the except block below,
    # even if an exception occurs before it is assigned.
    temp_cert_path: Optional[str] = None

    try:
        # Support comma-separated URLs for cluster compatibility
        urls = [u.strip() for u in ravendb_urls.split(",") if u.strip()]

        log.info("Decoding base64 certificate")
        try:
            cert_bytes = base64.b64decode(certificate_base64)
        except ValueError as decode_err:
            raise ValueError(f"Failed to decode base64 certificate: {decode_err}")

        # Write certificate bytes directly to temp PEM file
        temp_file = tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False)
        temp_file.write(cert_bytes)
        temp_file.flush()
        temp_file.close()
        temp_cert_path = temp_file.name
        log.info(f"Temporary PEM certificate written to {temp_cert_path}")

        store = DocumentStore(urls=urls, database=database_name)
        store.certificate_pem_path = temp_cert_path
        store.initialize()
        log.info(f"DocumentStore initialized for database '{database_name}'")
        return store, temp_cert_path

    except (ValueError, RavenException, OSError) as e:
        if temp_cert_path and os.path.exists(temp_cert_path):
            try:
                os.unlink(temp_cert_path)
                log.info("Cleaned up temporary certificate after failure")
            except OSError as cleanup_err:
                log.warning(f"Failed to remove temporary certificate file: {cleanup_err}")
        log.error(f"Failed to create RavenDB DocumentStore: {e}")
        raise RuntimeError(f"Failed to create RavenDB DocumentStore: {e}")


def build_rql_query(
    collection_name: str,
    last_modified: Optional[str] = None,
    last_document_id: Optional[str] = None,
    skip: int = 0,
    take: int = __DEFAULT_BATCH_SIZE,
) -> str:
    """
    Build an RQL query string for fetching documents from a RavenDB collection.

    Args:
        collection_name: The name of the collection to query.
        last_modified: The last modified timestamp for incremental sync filtering.
        last_document_id: The last document ID for cursor-based pagination.
        skip: Number of records to skip (for pagination).
        take: Number of records to fetch in this batch.
    Returns:
        An RQL query string ready for execution.
    """
    # Start with base collection query
    # RavenDB groups documents into collections based on ID prefix (e.g., "Orders/1-A")
    rql = f"from '{collection_name}'"

    # Add filter for incremental sync with compound cursor (timestamp + document ID)
    if last_modified and last_document_id:
        # Use >= for timestamp and > for document ID to handle same-timestamp documents
        # This ensures we don't skip documents with the same timestamp as the last processed one
        rql += f" where (@metadata.'@last-modified' > '{last_modified}' or (@metadata.'@last-modified' = '{last_modified}' and @metadata.'@id' > '{last_document_id}'))"
    elif last_modified:
        # First sync after initial state, use >= to be inclusive
        rql += f" where @metadata.'@last-modified' >= '{last_modified}'"

    # Add ordering for consistent results - order by timestamp, then by ID as tiebreaker
    rql += " order by @metadata.'@last-modified', @metadata.'@id'"

    # Add pagination
    rql += f" limit {skip}, {take}"

    return rql


def enrich_document_with_metadata(document, metadata):
    """
    Enrich a document with metadata fields (Id and LastModified).

    Args:
        document (dict): The document to enrich.
        metadata (dict): The metadata dictionary from RavenDB.

    Returns:
        dict: The enriched document with Id and LastModified fields.
    """
    if metadata:
        document["Id"] = metadata.get("@id", "")
        document["LastModified"] = metadata.get("@last-modified", "")
    return document


def fetch_documents_batch(
    store: DocumentStore,
    collection_name: str,
    last_modified: Optional[str] = None,
    last_document_id: Optional[str] = None,
    skip: int = 0,
    take: int = __DEFAULT_BATCH_SIZE,
    max_retries: int = 3,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Fetch a batch of documents from RavenDB collection using streaming to minimize memory footprint.

    This function uses RavenDB's query iterator to stream documents one at a time rather than
    loading the entire result set into memory. Documents are processed incrementally and only
    the requested batch size is kept in memory.

    Implements retry logic with exponential backoff for transient failures.

    Args:
        store (DocumentStore): The RavenDB DocumentStore instance.
        collection_name (str): The name of the collection to fetch data from.
        last_modified (str, optional): The last modified timestamp from the previous sync.
        last_document_id (str, optional): The last document ID for cursor-based pagination.
        skip (int): Number of records to skip (for pagination).
        take (int): Number of records to fetch in this batch.
        max_retries (int): Maximum number of retry attempts for transient failures.

    Returns:
        Tuple[List[Dict[str, Any]], bool]: A tuple containing:
            - List of documents (limited to 'take' size) sorted by LastModified and ID
            - Boolean indicating if more data exists

    Raises:
        RuntimeError: If the batch fetch fails after all retries.
    """
    retry_count = 0

    while retry_count < max_retries:
        try:
            with store.open_session() as session:
                # Build RQL query using helper function with compound cursor
                rql = build_rql_query(collection_name, last_modified, last_document_id, skip, take)

                # Execute raw RQL query and get iterator (does not load all results into memory)
                query_result = session.advanced.raw_query(rql, object_type=dict)

                # Process documents one at a time using iterator
                documents = []
                document_count = 0

                for doc in query_result:
                    # Get metadata for this document
                    metadata = session.advanced.get_metadata_for(doc)

                    # Enrich document with metadata
                    enriched_doc = enrich_document_with_metadata(doc, metadata)
                    documents.append(enriched_doc)

                    document_count += 1

                    # Stop if we've reached the batch size
                    if document_count >= take:
                        break

                log.info(
                    f"Fetched batch: {len(documents)} documents from collection: {collection_name}, "
                    f"skip: {skip}, take: {take}"
                )

                # Check if there might be more data
                # If we got exactly 'take' documents, there might be more
                has_more_data = len(documents) == take

                return documents, has_more_data

        except (ConnectionError, TimeoutError, RavenException) as e:
            retry_count += 1
            if retry_count >= max_retries:
                log.error(
                    f"Failed to fetch batch from collection {collection_name} at skip {skip} "
                    f"after {max_retries} retries: {e}"
                )
                raise RuntimeError(
                    f"Failed to fetch batch from collection {collection_name} at skip {skip} "
                    f"after {max_retries} retries: {str(e)}"
                )

            # Exponential backoff: 1s, 2s, 4s, etc.
            # Using retry_count (which starts at 1 after first failure) to calculate backoff
            backoff_seconds = 2 ** (retry_count - 1)
            log.warning(
                f"Transient error fetching batch from collection {collection_name} at skip {skip}: {e}. "
                f"Retrying in {backoff_seconds}s (attempt {retry_count}/{max_retries})"
            )
            time.sleep(backoff_seconds)

        except (ValueError, KeyError, TypeError) as e:
            # Non-retryable errors (data/configuration issues)
            log.error(
                f"Data error while fetching batch from collection {collection_name} at skip {skip}: {e}"
            )
            raise RuntimeError(
                f"Data error while fetching batch from collection {collection_name} at skip {skip}: {str(e)}"
            )

    # This should never be reached, but if max_retries is 0 or invalid, raise an error
    raise RuntimeError(
        f"Failed to fetch batch from collection {collection_name} at skip {skip}: "
        f"max_retries configuration is invalid or no attempts were made"
    )


def process_document_batch(documents, collection_name):
    """
    Process a batch of documents by flattening and upserting them.

    Args:
        documents (list): List of document dictionaries to process.
        collection_name (str): Name of the collection (used as table name).

    Returns:
        int: Number of documents processed in this batch.
    """
    processed_count = 0

    for document in documents:
        # Flatten nested document structure
        flattened_doc = flatten_dict(document)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=collection_name.lower(), data=flattened_doc)
        processed_count += 1

    return processed_count


def extract_cursor_from_last_document(documents):
    """
    Extract the cursor (LastModified timestamp and document ID) from the last document in a batch.

    Args:
        documents (list): List of document dictionaries.

    Returns:
        tuple: (last_modified, last_document_id) where both are strings or None if documents is empty.
    """
    if not documents:
        return None, None

    last_document = documents[-1]
    last_modified = last_document.get("LastModified")
    last_document_id = last_document.get("Id")
    return last_modified, last_document_id


def process_single_batch(
    store, collection_name, last_modified, last_document_id, skip, batch_size
):
    """
    Fetch and process a single batch of documents from RavenDB.

    Args:
        store (DocumentStore): The RavenDB DocumentStore instance.
        collection_name (str): Name of the collection to fetch from.
        last_modified (str): Timestamp for incremental sync filtering.
        last_document_id (str): Document ID for cursor-based pagination.
        skip (int): Number of records to skip for pagination.
        batch_size (int): Number of records to fetch in this batch.

    Returns:
        tuple: (processed_count, new_last_modified, new_last_document_id, has_more_data) where:
            - processed_count (int): Number of documents processed
            - new_last_modified (str): Updated last modified timestamp
            - new_last_document_id (str): Updated last document ID
            - has_more_data (bool): Whether more data exists to fetch
    """
    # Fetch document batch from RavenDB
    documents, has_more_data = fetch_documents_batch(
        store, collection_name, last_modified, last_document_id, skip, batch_size
    )

    if not documents:
        log.info("No more documents to process")
        return 0, last_modified, last_document_id, False

    # Process all documents in the batch
    processed_count = process_document_batch(documents, collection_name)

    # Extract the cursor (timestamp and document ID) from this batch
    new_last_modified, new_last_document_id = extract_cursor_from_last_document(documents)
    if not new_last_modified:
        new_last_modified = last_modified
    if not new_last_document_id:
        new_last_document_id = last_document_id

    return processed_count, new_last_modified, new_last_document_id, has_more_data


def sync_collection_data(
    store, collection_name, batch_size, initial_last_modified, initial_last_document_id
):
    """
    Sync all data from a RavenDB collection using batch processing with cursor-based pagination.

    This function orchestrates the batch-by-batch processing of documents, handling
    pagination with a compound cursor (timestamp + document ID), state updates, and checkpointing.

    Args:
        store (DocumentStore): The RavenDB DocumentStore instance.
        collection_name (str): Name of the collection to sync.
        batch_size (int): Number of documents to process per batch.
        initial_last_modified (str): Starting timestamp for incremental sync.
        initial_last_document_id (str): Starting document ID for cursor-based pagination.

    Returns:
        tuple: (total_row_count, total_batch_count) with sync statistics.
    """
    last_modified = initial_last_modified
    last_document_id = initial_last_document_id
    total_row_count = 0
    batch_count = 0
    skip = 0
    has_more_data = True

    log.info(f"Starting batch processing with batch size: {batch_size}")

    while has_more_data:
        batch_count += 1
        log.info(f"Processing batch {batch_count}, skip: {skip}")

        # Process a single batch with compound cursor
        batch_row_count, new_last_modified, new_last_document_id, has_more_data = (
            process_single_batch(
                store, collection_name, last_modified, last_document_id, skip, batch_size
            )
        )

        # Update state if we processed any documents
        if batch_row_count > 0:
            total_row_count += batch_row_count

            # Check if cursor changed (timestamp or document ID)
            if new_last_modified != last_modified or new_last_document_id != last_document_id:
                # Reset skip to 0 when cursor changes
                # The compound cursor filter handles incrementing through data
                skip = 0
                last_modified = new_last_modified
                last_document_id = new_last_document_id
            else:
                # Only increment skip when cursor hasn't changed
                # (initial sync or multiple batches at same cursor position - shouldn't happen with proper cursor)
                skip += batch_size

            # Checkpoint after each complete batch to ensure consistent state
            save_state(last_modified, last_document_id)

            log.info(
                f"Completed batch {batch_count}: processed {batch_row_count} documents, "
                f"total processed: {total_row_count}, last modified: {last_modified}, last document ID: {last_document_id}"
            )
        else:
            # No documents processed but has_more_data is True
            # This shouldn't normally happen, but increment skip to avoid infinite loop
            skip += batch_size

    return total_row_count, batch_count


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """

    log.warning("Example: Source Examples - RavenDB")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Create RavenDB DocumentStore and get certificate path for cleanup
    store, cert_path = create_document_store(configuration)
    try:
        # Extract configuration parameters
        collection_name = configuration.get("collection_name", __DEFAULT_COLLECTION_NAME)
        batch_size = int(configuration.get("batch_size", __DEFAULT_BATCH_SIZE))
        last_modified = state.get("last_modified", __EARLIEST_TIMESTAMP)
        last_document_id = state.get("last_document_id", None)

        # Sync all collection data using compound cursor (timestamp + document ID)
        total_row_count, total_batch_count = sync_collection_data(
            store, collection_name, batch_size, last_modified, last_document_id
        )

        log.info(
            f"Successfully synced {total_row_count} documents across {total_batch_count} batches"
        )

    except (RuntimeError, ValueError, KeyError, ConnectionError, RavenException) as e:
        # In case of a known exception, raise a runtime error
        log.error(f"Failed to sync data: {e}")
        raise RuntimeError(f"Failed to sync data: {str(e)}")
    finally:
        # Always close the document store
        try:
            store.close()
        except (RavenException, AttributeError) as close_err:
            log.warning(f"Error closing document store: {close_err}")

        # Clean up the temporary certificate file
        if cert_path and os.path.exists(cert_path):
            try:
                os.unlink(cert_path)
                log.info(f"Cleaned up temporary certificate file: {cert_path}")
            except OSError as cleanup_err:
                log.warning(f"Failed to remove temporary certificate file: {cleanup_err}")


def save_state(new_last_modified, new_last_document_id):
    """
    Save the current sync state by checkpointing with compound cursor.
    Args:
        new_last_modified: The latest LastModified timestamp processed.
        new_last_document_id: The latest document ID processed.
    """
    new_state = {"last_modified": new_last_modified, "last_document_id": new_last_document_id}

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(new_state)


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
