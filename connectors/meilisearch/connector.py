"""MeiliSearch Connector for Fivetran - syncs indexes and documents from MeiliSearch API.
This connector demonstrates how to fetch index and document data from MeiliSearch REST API and upsert it into destination using the Fivetran Connector SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For generating stable hashes for document IDs
import hashlib

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to MeiliSearch API
import requests

# For handling time operations and timestamps
import time

# For type hints in function signatures
from typing import Optional, Dict, List

__DOCUMENTS_ENDPOINT = "/indexes/{index_uid}/documents/fetch"
__INDEXES_ENDPOINT = "/indexes"
__PAGINATION_LIMIT = 100
__REQUEST_TIMEOUT_IN_SECONDS = 30
__MAX_RETRIES = 5
__BACKOFF_BASE = 1
__CHECKPOINT_INTERVAL = 500


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
            "table": "index",
            "primary_key": ["uid"],
        },
        {
            "table": "document",
            "primary_key": ["_index_uid", "_document_id"],
        },
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    # Validate required configuration parameters
    required_configs = ["api_url", "api_key"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: '{key}'")

    # Validate api_url format
    api_url = configuration.get("api_url")
    if not api_url.startswith(("http://", "https://")):
        raise ValueError(
            f"Invalid api_url format: {api_url}. Must start with 'http://' or 'https://'"
        )


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: Source Examples - MeiliSearch")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    api_url = configuration.get("api_url")
    api_key = configuration.get("api_key")

    headers = build_request_headers(api_key)

    last_sync_timestamp = state.get("last_sync_timestamp")
    synced_indexes = state.get("synced_indexes", [])
    indexes_synced = state.get("indexes_synced", False)

    # Use existing current_sync_timestamp if this is a resumed sync, otherwise create a new one
    # This ensures we don't lose data between the original sync start and a restart
    current_sync_timestamp = state.get("current_sync_timestamp")
    if current_sync_timestamp is None:
        current_sync_timestamp = int(time.time() * 1000)

    # Sync indexes first only if not already synced in this sync run
    if not indexes_synced:
        sync_indexes(api_url, headers)

        # Checkpoint after completing the index table sync
        # This ensures we don't lose index sync progress if the sync fails during document processing
        new_state = {
            "last_sync_timestamp": last_sync_timestamp,
            "synced_indexes": synced_indexes,
            "indexes_synced": True,
            "current_sync_timestamp": current_sync_timestamp,
        }
        op.checkpoint(new_state)
        log.info("Checkpointed after completing index sync")
    else:
        log.info("Skipping index sync - already completed in this sync run")

    # Sync documents from all indexes
    sync_documents_from_all_indexes(
        api_url, headers, last_sync_timestamp, synced_indexes, current_sync_timestamp
    )

    # Final checkpoint after all syncs are complete
    final_state = {
        "last_sync_timestamp": current_sync_timestamp,
        "synced_indexes": [],
        "indexes_synced": False,
        "current_sync_timestamp": None,
    }
    op.checkpoint(final_state)
    log.info("Checkpointed after completing all syncs")


def build_request_headers(api_key: str) -> Dict[str, str]:
    """
    Build HTTP headers for MeiliSearch API requests.
    Args:
        api_key: The API key for authentication
    Returns:
        Dictionary containing HTTP headers
    """
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def make_api_request(
    url: str,
    headers: Dict[str, str],
    method: str = "GET",
    params: Optional[Dict] = None,
    json_payload: Optional[Dict] = None,
) -> Dict:
    """
    Make an HTTP request to the MeiliSearch API with error handling and exponential backoff retry logic.
    Args:
        url: The API endpoint URL
        headers: HTTP headers for the request
        method: HTTP method (GET or POST)
        params: Optional query parameters
        json_payload: Optional JSON payload for POST requests
    Returns:
        The JSON response from the API
    Raises:
        requests.exceptions.RequestException: For HTTP errors
        ValueError: For invalid JSON responses
    """
    params = params or {}
    json_payload = json_payload or {}

    for attempt in range(__MAX_RETRIES):
        response = None
        try:
            if method == "POST":
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=json_payload,
                    timeout=__REQUEST_TIMEOUT_IN_SECONDS,
                )
            else:
                response = requests.get(
                    url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_IN_SECONDS
                )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if attempt < __MAX_RETRIES - 1:
                delay = __BACKOFF_BASE * (2**attempt)
                log.warning(f"Request timeout for URL: {url}. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            log.error(f"Request timeout for URL: {url}")
            raise
        except requests.exceptions.HTTPError as e:
            is_retryable_error = response and (
                response.status_code == 429 or response.status_code >= 500
            )
            should_retry = is_retryable_error and attempt < __MAX_RETRIES - 1
            if should_retry:
                delay = __BACKOFF_BASE * (2**attempt)
                log.warning(
                    f"Rate limit or server error for URL: {url}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
                continue
            log.error(f"HTTP error for URL: {url}", e)
            raise
        except (requests.exceptions.RequestException, ValueError) as e:
            log.error(f"Request failed for URL: {url}", e)
            raise

    raise requests.exceptions.RequestException(
        f"Request failed for URL: {url} after {__MAX_RETRIES} attempts"
    )


def sync_indexes(api_url: str, headers: Dict[str, str]):
    """
    Fetch and sync index metadata from MeiliSearch API.
    Args:
        api_url: The base URL of the MeiliSearch instance
        headers: HTTP headers including authorization
    """
    log.info("Starting indexes sync")

    url = f"{api_url}{__INDEXES_ENDPOINT}"
    params = {"limit": __PAGINATION_LIMIT, "offset": 0}

    indexes_synced = 0

    while True:
        response_data = make_api_request(url, headers, params=params)
        indexes = response_data.get("results", [])

        for index in indexes:
            index_data = {
                "uid": index.get("uid"),
                "created_at": index.get("createdAt"),
                "updated_at": index.get("updatedAt"),
                "primary_key": index.get("primaryKey"),
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="index", data=index_data)
            indexes_synced += 1

        total = response_data.get("total", 0)
        current_offset = params["offset"]
        fetched_count = len(indexes)

        if current_offset + fetched_count >= total:
            break

        params["offset"] += __PAGINATION_LIMIT

    log.info(f"Synced {indexes_synced} indexes")


def sync_documents_from_all_indexes(
    api_url: str,
    headers: Dict[str, str],
    last_sync_timestamp: Optional[int] = None,
    synced_indexes: List[str] = None,
    current_sync_timestamp: Optional[int] = None,
):
    """
    Fetch documents from all indexes in MeiliSearch and sync them to the destination.
    Supports incremental sync when documents have a last_updated field configured as filterable.
    Args:
        api_url: The base URL of the MeiliSearch instance
        headers: HTTP headers including authorization
        last_sync_timestamp: Timestamp in milliseconds for incremental sync filtering
        synced_indexes: List of index UIDs that have already been synced
        current_sync_timestamp: Timestamp for the current sync run (preserved across restarts)
    """
    log.info("Starting documents sync from all indexes")

    if synced_indexes is None:
        synced_indexes = []

    indexes = fetch_all_indexes(api_url, headers)

    for index in indexes:
        index_uid = index.get("uid")
        if index_uid:
            # Skip indexes that have already been synced (for resumption after failure)
            if index_uid in synced_indexes:
                log.info(f"Skipping already synced index: {index_uid}")
                continue

            sync_documents_for_index(api_url, headers, index_uid, last_sync_timestamp)

            # Checkpoint after each index is fully synced
            # This ensures we can resume from the next index if the sync fails
            synced_indexes.append(index_uid)
            checkpoint_state = {
                "last_sync_timestamp": last_sync_timestamp,
                "synced_indexes": synced_indexes,
                "indexes_synced": True,
                "current_sync_timestamp": current_sync_timestamp,
            }
            op.checkpoint(checkpoint_state)
            log.info(f"Checkpointed after syncing index: {index_uid}")


def fetch_all_indexes(api_url: str, headers: Dict[str, str]) -> List[Dict]:
    """
    Fetch all indexes from MeiliSearch API.
    Args:
        api_url: The base URL of the MeiliSearch instance
        headers: HTTP headers including authorization
    Returns:
        List of index dictionaries
    """
    url = f"{api_url}{__INDEXES_ENDPOINT}"
    params = {"limit": __PAGINATION_LIMIT, "offset": 0}
    all_indexes = []

    while True:
        response_data = make_api_request(url, headers, params=params)
        indexes = response_data.get("results", [])
        all_indexes.extend(indexes)

        total = response_data.get("total", 0)
        current_offset = params["offset"]
        fetched_count = len(indexes)

        if current_offset + fetched_count >= total:
            break

        params["offset"] += __PAGINATION_LIMIT

    return all_indexes


def sync_documents_for_index(
    api_url: str,
    headers: Dict[str, str],
    index_uid: str,
    last_sync_timestamp: Optional[int] = None,
):
    """
    Fetch and sync documents from a specific MeiliSearch index.
    Args:
        api_url: The base URL of the MeiliSearch instance
        headers: HTTP headers including authorization
        index_uid: The unique identifier of the index
        last_sync_timestamp: Timestamp in milliseconds for incremental sync filtering
    """
    log.info(f"Syncing documents from index: {index_uid}")

    url = f"{api_url}{__DOCUMENTS_ENDPOINT.format(index_uid=index_uid)}"
    offset = 0
    documents_synced = 0

    while True:
        payload = {"offset": offset, "limit": __PAGINATION_LIMIT}

        if last_sync_timestamp:
            last_updated_seconds = last_sync_timestamp // 1000
            payload["filter"] = f"last_updated >= {last_updated_seconds}"

        response_data = make_api_request(url, headers, method="POST", json_payload=payload)
        documents = response_data.get("results", [])

        for document in documents:
            document_id = extract_document_id(document, index_uid)

            flattened_document = flatten_document(document)
            flattened_document["_index_uid"] = index_uid
            flattened_document["_document_id"] = document_id

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="document", data=flattened_document)
            documents_synced += 1

            if documents_synced % __CHECKPOINT_INTERVAL == 0:
                log.info(f"Processed {documents_synced} documents from index {index_uid}")

        total = response_data.get("total", 0)
        fetched_count = len(documents)

        if offset + fetched_count >= total:
            break

        offset += __PAGINATION_LIMIT

    log.info(f"Synced {documents_synced} documents from index: {index_uid}")


def extract_document_id(document: Dict, index_uid: str) -> str:
    """
    Extract document ID from document data.
    Uses SHA256 hash as a fallback for documents without an ID field to ensure stable, deterministic IDs.
    Args:
        document: The document dictionary
        index_uid: The index UID for logging context
    Returns:
        The document ID as a string
    """
    if "id" in document:
        return str(document["id"])
    elif "_id" in document:
        return str(document["_id"])
    else:
        # Use SHA256 for stable, deterministic hash across runs
        # Sort keys to ensure consistent serialization
        document_json = json.dumps(document, sort_keys=True, ensure_ascii=True)
        generated_id = hashlib.sha256(document_json.encode("utf-8")).hexdigest()
        log.warning(
            f"Document in index '{index_uid}' has no 'id' or '_id' field. Generated SHA256-based ID: {generated_id}"
        )
        return generated_id


def flatten_document(document: Dict, prefix: str = "", separator: str = "_") -> Dict:
    """
    Flatten nested document structure for table storage.
    Args:
        document: The document dictionary to flatten
        prefix: Prefix to add to keys
        separator: Separator to use between nested keys
    Returns:
        Flattened dictionary
    """
    flattened = {}

    for key, value in document.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            flattened.update(flatten_document(value, new_key, separator))
        elif isinstance(value, list):
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


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
