"""DragonflyDB connector for Fivetran - syncs high-performance in-memory data from DragonflyDB.
This connector demonstrates how to fetch caching data, session stores, real-time analytics, and high-throughput key-value data from DragonflyDB and sync it to Fivetran using the Fivetran Connector SDK.
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

# Import Redis client for connecting to DragonflyDB (Redis-compatible)
import redis

# For handling time operations and timestamps
from datetime import datetime, timezone

# For type hints
from typing import Dict, List, Tuple

# For deterministic hashing
import hashlib

# For implementing retry logic with exponential backoff
import time

# Checkpoint after processing every 1000 keys
__CHECKPOINT_INTERVAL = 1000

# Batch size for key scanning
__BATCH_SIZE = 100

# DragonflyDB SCAN count parameter for pagination
__SCAN_COUNT = 100

# Default DragonflyDB port
__DEFAULT_DRAGONFLY_PORT = 6379

# Default DragonflyDB database number
__DEFAULT_DRAGONFLY_DB = 0

# Socket timeout in seconds
__SOCKET_TIMEOUT_SEC = 30

# Socket connection timeout in seconds
__SOCKET_CONNECT_TIMEOUT_SEC = 30

# Retry configuration for transient failures
__MAX_RETRIES = 3
__INITIAL_BACKOFF_SEC = 1
__MAX_BACKOFF_SEC = 16


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["host", "port"]
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
    table_name = configuration.get("table_name", "dragonfly_data")

    return [
        {
            "table": table_name,
            "primary_key": ["key"],
        },
    ]


def build_connection_params(configuration: dict) -> dict:
    """
    Build DragonflyDB connection parameters from configuration.
    Args:
        configuration: Configuration dictionary.
    Returns:
        Dictionary of connection parameters for DragonflyDB client.
    """
    host = configuration.get("host", "localhost")
    port = int(configuration.get("port", __DEFAULT_DRAGONFLY_PORT))
    username = configuration.get("username")
    password = configuration.get("password")
    database = int(configuration.get("database", __DEFAULT_DRAGONFLY_DB))
    ssl_config = configuration.get("ssl", "false")
    ssl = ssl_config.lower() == "true" if isinstance(ssl_config, str) else ssl_config

    connection_params = {
        "host": host,
        "port": port,
        "db": database,
        "decode_responses": True,
        "socket_timeout": __SOCKET_TIMEOUT_SEC,
        "socket_connect_timeout": __SOCKET_CONNECT_TIMEOUT_SEC,
    }

    if username and username.strip():
        connection_params["username"] = username

    if password and password.strip():
        connection_params["password"] = password

    if ssl:
        connection_params["ssl"] = True
        connection_params["ssl_cert_reqs"] = "required"
        connection_params["ssl_check_hostname"] = False

    return connection_params


def create_dragonfly_client(configuration: dict):
    """
    Create a DragonflyDB client using the provided configuration with retry logic.
    Implements exponential backoff for transient connection failures.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        redis.Redis: A DragonflyDB client instance.
    """
    connection_params = build_connection_params(configuration)
    host = connection_params["host"]
    port = connection_params["port"]
    database = connection_params["db"]

    last_exception = None
    backoff_time = __INITIAL_BACKOFF_SEC

    for attempt in range(__MAX_RETRIES):
        try:
            dragonfly_client = redis.Redis(**connection_params)
            dragonfly_client.ping()
            log.info(
                f"Successfully connected to DragonflyDB at {host}:{port}, database: {database}"
            )
            return dragonfly_client
        except (redis.ConnectionError, redis.TimeoutError) as e:
            last_exception = e
            if attempt < __MAX_RETRIES - 1:
                log.warning(
                    f"Connection attempt {attempt + 1} failed: {e}. Retrying in {backoff_time}s..."
                )
                time.sleep(backoff_time)
                backoff_time = min(backoff_time * 2, __MAX_BACKOFF_SEC)
            else:
                log.error(
                    f"Failed to create DragonflyDB client after {__MAX_RETRIES} attempts: {e}"
                )
        except redis.AuthenticationError as e:
            log.error(f"Authentication failed: {e}")
            raise RuntimeError(f"Failed to create DragonflyDB client: {str(e)}")
        except redis.RedisError as e:
            log.error(f"Redis error during client creation: {e}")
            raise RuntimeError(f"Redis error during client creation: {str(e)}")

    raise RuntimeError(
        f"Failed to create DragonflyDB client after {__MAX_RETRIES} attempts: {str(last_exception)}"
    )


def close_dragonfly_client(dragonfly_client):
    """
    Close the DragonflyDB client connection.
    Args:
        dragonfly_client: The DragonflyDB client instance to close.
    """
    try:
        dragonfly_client.close()
    except redis.RedisError as e:
        log.warning(f"Error closing DragonflyDB connection: {e}")
    except (OSError, AttributeError) as e:
        log.warning(f"Unexpected error closing connection: {e}")


def is_timeseries_key(dragonfly_client, key: str) -> bool:
    """
    Check if a key is a TimeSeries key.
    Args:
        dragonfly_client: DragonflyDB client instance.
        key: Key to check.
    Returns:
        True if the key is a TimeSeries, False otherwise.
    """
    try:
        key_type = dragonfly_client.type(key)
        return key_type.lower() in ["tsdb-type", "timeseries"]
    except redis.ConnectionError as e:
        log.warning(f"The supplied key is not a timeseries key '{key}': {e}")
        return False


def get_timeseries_range(
    dragonfly_client, key: str, from_timestamp: int, to_timestamp: str = "+"
) -> List[Tuple[int, float]]:
    """
    Get TimeSeries data points within a timestamp range.
    Args:
        dragonfly_client: DragonflyDB client instance.
        key: TimeSeries key name.
        from_timestamp: Starting timestamp in milliseconds (Unix epoch).
        to_timestamp: Ending timestamp in milliseconds or "+" for latest.
    Returns:
        List of (timestamp, value) tuples.
    """
    try:
        result = dragonfly_client.execute_command("TS.RANGE", key, from_timestamp, to_timestamp)
        return result if result else []
    except redis.RedisError as e:
        log.warning(f"Failed to get TimeSeries range for key '{key}': {e}")
        return []


def sync_timeseries_key(
    dragonfly_client, key: str, table_name: str, last_timestamp: int
) -> Tuple[int, int]:
    """
    Sync a single TimeSeries key incrementally from last_timestamp to now.
    Args:
        dragonfly_client: DragonflyDB client instance.
        key: TimeSeries key name.
        table_name: Destination table name.
        last_timestamp: Last synced timestamp in milliseconds.
    Returns:
        Tuple of (number of data points synced, latest timestamp).
    """
    from_ts = last_timestamp + 1 if last_timestamp > 0 else 0
    data_points = get_timeseries_range(dragonfly_client, key, from_ts, "+")

    if not data_points:
        return 0, last_timestamp

    max_timestamp = last_timestamp
    count = 0

    for timestamp, value in data_points:
        record = {
            "key": key,
            "value": str(value),
            "data_type": "timeseries",
            "ttl": -1,
            "last_modified": datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(),
            "size": 1,
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table_name, data=record)
        count += 1
        max_timestamp = max(max_timestamp, timestamp)

    return count, max_timestamp


def extract_value_by_type(dragonfly_client, key: str, key_type: str) -> Tuple[str, int]:
    """
    Extract value and size based on data type.
    Args:
        dragonfly_client: DragonflyDB client instance.
        key: Key name.
        key_type: Data type (string, hash, list, set, zset).
    Returns:
        Tuple of (value, size).
    """
    if key_type == "string":
        value = dragonfly_client.get(key)
        size = len(value) if value else 0
        return value, size

    elif key_type == "hash":
        data = dragonfly_client.hgetall(key)
        return json.dumps(data), len(data)

    elif key_type == "list":
        data = dragonfly_client.lrange(key, 0, -1)
        return json.dumps(data), len(data)

    elif key_type == "set":
        data = list(dragonfly_client.smembers(key))
        return json.dumps(data), len(data)

    elif key_type == "zset":
        zset_data = dragonfly_client.zrange(key, 0, -1, withscores=True)
        zset_list = [[member, score] for member, score in zset_data]
        return json.dumps(zset_list), len(zset_data)

    else:
        return f"Unsupported type: {key_type}", 0


def compute_key_hash(dragonfly_client, key: str) -> str:
    """
    Compute a deterministic hash for a key's value to detect changes for incremental sync.
    Uses MD5 for deterministic hashing across runs.
    Args:
        dragonfly_client: The DragonflyDB client instance.
        key: The key to compute hash for.
    Returns:
        Hash string representing the key's current value state.
    """
    try:
        key_type = dragonfly_client.type(key)
        value, _ = extract_value_by_type(dragonfly_client, key, key_type)
        hash_input = f"{key_type}:{value}"
        return hashlib.md5(hash_input.encode("utf-8")).hexdigest()
    except redis.RedisError as e:
        log.warning(f"Failed to compute hash for key '{key}': {e}")
        return ""


def get_key_info(dragonfly_client, key: str) -> dict:
    """
    Get comprehensive information about a key including value, type, TTL, and size.
    Args:
        dragonfly_client: The DragonflyDB client instance.
        key: The key to get information for.
    Returns:
        Dictionary containing key information.
    """
    try:
        key_type = dragonfly_client.type(key)
        ttl = dragonfly_client.ttl(key)
        value, size = extract_value_by_type(dragonfly_client, key, key_type)

        return {
            "key": key,
            "value": value,
            "data_type": key_type,
            "ttl": ttl,
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "size": size,
        }

    except redis.RedisError as e:
        log.warning(f"Failed to get info for key '{key}': {e}")
        return {
            "key": key,
            "value": f"Error: {str(e)}",
            "data_type": "error",
            "ttl": -2,
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "size": 0,
        }


def scan_keys(
    dragonfly_client, pattern: str = "*", cursor: int = 0, count: int = __SCAN_COUNT
) -> Tuple[int, List[str]]:
    """
    Scan keys using SCAN command for efficient pagination.
    Args:
        dragonfly_client: The DragonflyDB client instance.
        pattern: Pattern to match keys (default: "*" for all keys).
        cursor: Cursor position for pagination (0 to start).
        count: Number of keys to scan in this iteration.
    Returns:
        Tuple of (next_cursor, list_of_keys).
    """
    try:
        cursor, keys = dragonfly_client.scan(cursor=cursor, match=pattern, count=count)
        log.info(f"Scanned {len(keys)} keys, next cursor: {cursor}")
        return cursor, keys
    except redis.RedisError as e:
        log.error(f"Failed to scan keys: {e}")
        raise RuntimeError(f"Failed to scan keys: {str(e)}")


def process_batch(
    dragonfly_client,
    keys: List[str],
    table_name: str,
    previous_key_hashes: Dict[str, str],
    timeseries_state: Dict[str, int],
) -> Tuple[int, Dict[str, str], Dict[str, int]]:
    """
    Process a batch of keys and upsert them to the destination.
    Detects TimeSeries keys and syncs them incrementally.
    Only processes regular keys that are new or have changed since last sync.
    Args:
        dragonfly_client: DragonflyDB client instance.
        keys: List of keys to process.
        table_name: Destination table name.
        previous_key_hashes: Dictionary of key -> hash from previous sync.
        timeseries_state: Dictionary mapping TimeSeries keys to their last synced timestamp.
    Returns:
        Tuple of (number of records processed, updated key hashes, updated timeseries state).
    """
    batch_row_count = 0
    current_key_hashes = {}

    for key in keys:
        if is_timeseries_key(dragonfly_client, key):
            last_ts = timeseries_state.get(key, 0)
            count, max_ts = sync_timeseries_key(dragonfly_client, key, table_name, last_ts)
            batch_row_count += count

            if max_ts > last_ts:
                timeseries_state[key] = max_ts

            log.info(
                f"Synced {count} data points from TimeSeries key '{key}' (timestamp: {max_ts})"
            )
        else:
            current_hash = compute_key_hash(dragonfly_client, key)
            current_key_hashes[key] = current_hash
            previous_hash = previous_key_hashes.get(key)

            if current_hash != previous_hash:
                key_info = get_key_info(dragonfly_client, key)

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table=table_name, data=key_info)
                batch_row_count += 1

                if previous_hash:
                    log.info(f"Key modified: {key}")
                else:
                    log.info(f"New key detected: {key}")

    return batch_row_count, current_key_hashes, timeseries_state


def handle_deleted_keys(
    previous_key_hashes: Dict[str, str], current_key_hashes: Dict[str, str], table_name: str
) -> int:
    """
    Detect and handle keys that have been deleted from DragonflyDB.
    Args:
        previous_key_hashes: Dictionary of key -> hash from previous sync.
        current_key_hashes: Dictionary of key -> hash from current sync.
        table_name: Destination table name.
    Returns:
        Number of deleted keys processed.
    """
    deleted_count = 0
    deleted_keys = set(previous_key_hashes.keys()) - set(current_key_hashes.keys())

    if deleted_keys:
        log.info(f"Detected {len(deleted_keys)} deleted keys: {deleted_keys}")

    for key in deleted_keys:
        # The 'delete' operation removes a record from the destination table.
        # It uses the primary key value to identify which record to delete.
        op.delete(table=table_name, key=key)
        log.info(f"Key deleted: {key}")
        deleted_count += 1

    return deleted_count


def sync_dragonfly_data(
    dragonfly_client,
    table_name: str,
    key_pattern: str,
    batch_size: int,
    cursor: int,
    current_sync_time: str,
    previous_key_hashes: Dict[str, str],
    timeseries_state: Dict[str, int],
) -> Tuple[int, Dict[str, str], Dict[str, int]]:
    """
    Sync DragonflyDB data by scanning and processing keys in batches.
    Supports both regular keys and TimeSeries keys with incremental sync.
    Args:
        dragonfly_client: DragonflyDB client instance.
        table_name: Destination table name.
        key_pattern: Pattern to match keys.
        batch_size: Number of keys to process per batch.
        cursor: Starting cursor position.
        current_sync_time: Current sync timestamp.
        previous_key_hashes: Dictionary of key -> hash from previous sync.
        timeseries_state: Dictionary mapping TimeSeries keys to their last synced timestamp.
    Returns:
        Tuple of (total records processed, updated key hashes, updated timeseries state).
    """
    row_count = 0
    batch_count = 0
    total_keys_processed = 0
    all_current_key_hashes = {}

    log.info(f"Starting key scan with pattern: {key_pattern}, batch size: {batch_size}")

    while True:
        batch_count += 1
        log.info(f"Processing batch {batch_count}, cursor: {cursor}")

        cursor, keys = scan_keys(dragonfly_client, key_pattern, cursor, batch_size)

        if not keys:
            log.info("No more keys to process")
            if cursor == 0:
                break
            continue

        batch_row_count, batch_key_hashes, timeseries_state = process_batch(
            dragonfly_client, keys, table_name, previous_key_hashes, timeseries_state
        )
        row_count += batch_row_count
        total_keys_processed += batch_row_count
        all_current_key_hashes.update(batch_key_hashes)

        # Save the progress by checkpointing the state after every batch. This ensures that the sync process can resume
        # from the correct position in case of next sync or interruptions, even if no new/modified keys are found.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        save_state(cursor, current_sync_time, all_current_key_hashes, timeseries_state)

        log.info(
            f"Completed batch {batch_count}: processed {batch_row_count} records, "
            f"total processed: {total_keys_processed}, cursor: {cursor}"
        )

        if cursor == 0:
            break

    deleted_count = handle_deleted_keys(previous_key_hashes, all_current_key_hashes, table_name)
    if deleted_count > 0:
        log.info(f"Processed {deleted_count} deleted keys")

    return total_keys_processed, all_current_key_hashes, timeseries_state


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: SOURCE_EXAMPLES : DRAGONFLY_DB_CONNECTOR")

    validate_configuration(configuration=configuration)

    dragonfly_client = create_dragonfly_client(configuration)

    table_name = configuration.get("table_name", "dragonfly_data")
    key_pattern = configuration.get("key_pattern", "*")
    batch_size = int(configuration.get("batch_size", __BATCH_SIZE))

    cursor = state.get("cursor", 0)
    previous_key_hashes = state.get("key_hashes", {})
    timeseries_state = state.get("timeseries_state", {})
    current_sync_time = datetime.now(timezone.utc).isoformat()

    try:
        total_records_processed, current_key_hashes, timeseries_state = sync_dragonfly_data(
            dragonfly_client,
            table_name,
            key_pattern,
            batch_size,
            cursor,
            current_sync_time,
            previous_key_hashes,
            timeseries_state,
        )

        save_state(0, current_sync_time, current_key_hashes, timeseries_state)

        log.info(f"Successfully synced {total_records_processed} records from DragonflyDB")

    except redis.RedisError as e:
        log.error(f"Redis error during sync: {e}")
        raise RuntimeError(f"Failed to sync data due to Redis error: {str(e)}")
    except (ValueError, KeyError, TypeError) as e:
        log.error(f"Data processing error during sync: {e}")
        raise RuntimeError(f"Failed to sync data due to processing error: {str(e)}")
    finally:
        close_dragonfly_client(dragonfly_client)


def save_state(
    cursor: int, sync_time: str, key_hashes: Dict[str, str], timeseries_state: Dict[str, int]
):
    """
    Save the current state including cursor position, sync time, key hashes, and TimeSeries timestamps.
    Args:
        cursor: Current cursor position for SCAN.
        sync_time: Current sync timestamp.
        key_hashes: Dictionary mapping keys to their value hashes for change detection.
        timeseries_state: Dictionary mapping TimeSeries keys to their last synced timestamp.
    """
    new_state = {
        "cursor": cursor,
        "last_sync_time": sync_time,
        "key_hashes": key_hashes,
        "timeseries_state": timeseries_state,
    }
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
