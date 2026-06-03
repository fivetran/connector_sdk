"""Redis connector for Fivetran - fetches key-value data from Redis database.
This connector demonstrates how to fetch gaming leaderboards, player statistics, and real-time engagement data from Redis and sync it to Fivetran using the Fivetran Connector SDK.
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

# Import Redis client for connecting to Redis database
import redis

# For handling time operations and timestamps
from datetime import datetime, timezone

# For type hints
from typing import Dict, List, Any, Tuple

# Constants for the connector
__CHECKPOINT_INTERVAL = 1000  # Checkpoint after processing every 1000 keys
__BATCH_SIZE = 100  # Batch size for key scanning
__SCAN_COUNT = 100  # Redis SCAN count parameter for pagination
__TIMESERIES_BATCH_SIZE = 1000  # Number of data points to process per batch for TimeSeries
__DEFAULT_REDIS_PORT = 6379  # Default Redis port
__DEFAULT_REDIS_DB = 0  # Default Redis database number
__SOCKET_TIMEOUT_SEC = 30  # Socket timeout in seconds
__SOCKET_CONNECT_TIMEOUT_SEC = 30  # Socket connection timeout in seconds


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
    # Get table name from configuration or use default
    table_name = configuration.get("table_name", "redis_data")

    return [
        {
            "table": table_name,  # Name of the table in the destination, required.
            "primary_key": ["key"],  # Primary key column(s) for the table, required.
            "columns": {  # Definition of columns and their types, optional.
                "key": "STRING",  # Redis key name
                "value": "STRING",  # Redis value (converted to string)
                "data_type": "STRING",  # Redis data type (string, hash, list, set, etc.)
                "ttl": "INT",  # Time to live in seconds (-1 for no expiry, -2 for expired)
                "last_modified": "UTC_DATETIME",  # When the key was last modified
                "size": "INT",  # Size of the value (length for strings, count for collections)
            },
        },
    ]


def build_connection_params(configuration: dict) -> dict:
    """
    Build Redis connection parameters from configuration.
    Args:
        configuration: Configuration dictionary.
    Returns:
        Dictionary of connection parameters for Redis client.
    """
    host = configuration.get("host", "localhost")
    port = int(configuration.get("port", __DEFAULT_REDIS_PORT))
    username = configuration.get("username")
    password = configuration.get("password")
    database = int(configuration.get("database", __DEFAULT_REDIS_DB))
    ssl_config = configuration.get("ssl", "false")
    ssl = ssl_config.lower() == "true" if isinstance(ssl_config, str) else ssl_config

    connection_params = {
        "host": host,
        "port": port,
        "db": database,
        "decode_responses": True,  # Decode responses to strings
        "socket_timeout": __SOCKET_TIMEOUT_SEC,
        "socket_connect_timeout": __SOCKET_CONNECT_TIMEOUT_SEC,
    }

    if username and username.strip():  # Add username if provided (for Redis ACL)
        connection_params["username"] = username

    if password and password.strip():  # Only add password if it's not empty
        connection_params["password"] = password

    if ssl:
        connection_params["ssl"] = True
        connection_params["ssl_cert_reqs"] = "required"
        connection_params["ssl_check_hostname"] = False

    return connection_params


def create_redis_client(configuration: dict):
    """
    Create a Redis client using the provided configuration.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        redis.Redis: A Redis client instance.
    """
    connection_params = build_connection_params(configuration)
    host = connection_params["host"]
    port = connection_params["port"]
    database = connection_params["db"]

    try:
        # Create Redis client
        redis_client = redis.Redis(**connection_params)

        # Test the connection
        redis_client.ping()
        log.info(f"Successfully connected to Redis at {host}:{port}, database: {database}")
        return redis_client
    except Exception as e:
        log.error("Failed to create Redis client", e)
        raise RuntimeError(f"Failed to create Redis client: {str(e)}")


def close_redis_client(redis_client: redis.Redis):
    """
    Close the Redis client connection.
    Args:
        redis_client: The Redis client instance to close.
    """
    try:
        redis_client.close()
    except Exception as e:
        log.warning(f"Error closing Redis connection: {e}")


def is_timeseries_key(redis_client: redis.Redis, key: str) -> bool:
    """
    Check if a Redis key is a TimeSeries key.
    Args:
        redis_client: Redis client instance.
        key: Redis key to check.
    Returns:
        True if the key is a TimeSeries, False otherwise.
    """
    try:
        key_type = redis_client.type(key)
        # TimeSeries keys have type "TSDB-TYPE" or "timeseries"
        return key_type.lower() in ["tsdb-type", "timeseries"]
    except Exception as e:
        log.warning(f"The supplied key is not a timeseries key '{key}': {e}")
        return False


def get_timeseries_range(
    redis_client: redis.Redis,
    key: str,
    from_timestamp: int,
    to_timestamp: str = "+",
) -> List[Tuple[int, float]]:
    """
    Get TimeSeries data points within a timestamp range.
    Args:
        redis_client: Redis client instance.
        key: TimeSeries key name.
        from_timestamp: Starting timestamp in milliseconds (Unix epoch).
        to_timestamp: Ending timestamp in milliseconds or "+" for latest.
    Returns:
        List of (timestamp, value) tuples.
    """
    try:
        # TS.RANGE returns list of [timestamp, value] pairs
        result = redis_client.execute_command("TS.RANGE", key, from_timestamp, to_timestamp)
        return result if result else []
    except Exception as e:
        log.warning(f"Failed to get TimeSeries range for key '{key}': {e}")
        return []


def sync_timeseries_key(
    redis_client: redis.Redis, key: str, table_name: str, last_timestamp: int
) -> Tuple[int, int]:
    """
    Sync a single TimeSeries key incrementally from last_timestamp to now.
    Args:
        redis_client: Redis client instance.
        key: TimeSeries key name.
        table_name: Destination table name.
        last_timestamp: Last synced timestamp in milliseconds.
    Returns:
        Tuple of (number of data points synced, latest timestamp).
    """
    # Query from last_timestamp + 1 to latest
    from_ts = last_timestamp + 1 if last_timestamp > 0 else 0
    data_points = get_timeseries_range(redis_client, key, from_ts, "+")

    if not data_points:
        return 0, last_timestamp

    max_timestamp = last_timestamp
    count = 0

    # Process each data point
    for timestamp, value in data_points:
        # Create record for each data point
        record = {
            "key": key,
            "value": str(value),
            "data_type": "timeseries",
            "ttl": -1,  # TimeSeries don't typically use TTL
            "last_modified": datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(),
            "size": 1,  # Each data point is a single value
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table=table_name, data=record)
        count += 1
        max_timestamp = max(max_timestamp, timestamp)

    return count, max_timestamp


def extract_value_by_type(redis_client: redis.Redis, key: str, key_type: str) -> Tuple[str, int]:
    """
    Extract value and size based on Redis data type.
    Args:
        redis_client: Redis client instance.
        key: Redis key.
        key_type: Redis data type (string, hash, list, set, zset).
    Returns:
        Tuple of (value, size).
    """
    if key_type == "string":
        value = redis_client.get(key)
        size = len(value) if value else 0
        return value, size

    elif key_type == "hash":
        data = redis_client.hgetall(key)
        return json.dumps(data), len(data)

    elif key_type == "list":
        data = redis_client.lrange(key, 0, -1)
        return json.dumps(data), len(data)

    elif key_type == "set":
        data = list(redis_client.smembers(key))
        return json.dumps(data), len(data)

    elif key_type == "zset":
        zset_data = redis_client.zrange(key, 0, -1, withscores=True)
        # Convert to list of [member, score] pairs for JSON serialization
        zset_list = [[member, score] for member, score in zset_data]
        return json.dumps(zset_list), len(zset_data)

    else:
        return f"Unsupported type: {key_type}", 0


def get_redis_value_info(redis_client: redis.Redis, key: str) -> Dict[str, Any]:
    """
    Get comprehensive information about a Redis key including value, type, TTL, and size.
    Args:
        redis_client: The Redis client instance.
        key: The Redis key to get information for.
    Returns:
        Dictionary containing key information.
    """
    try:
        # Get key type and TTL
        key_type = redis_client.type(key)
        ttl = redis_client.ttl(key)  # -1 = no expiry, -2 = expired/doesn't exist

        # Extract value and size based on type
        value, size = extract_value_by_type(redis_client, key, key_type)

        return {
            "key": key,
            "value": value,
            "data_type": key_type,
            "ttl": ttl,
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "size": size,
        }

    except Exception as e:
        log.warning(f"Failed to get info for key '{key}': {e}")
        return {
            "key": key,
            "value": f"Error: {str(e)}",
            "data_type": "error",
            "ttl": -2,
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "size": 0,
        }


def scan_redis_keys(
    redis_client: redis.Redis,
    pattern: str = "*",
    cursor: int = 0,
    count: int = __SCAN_COUNT,
) -> Tuple[int, List[str]]:
    """
    Scan Redis keys using SCAN command for efficient pagination.
    Args:
        redis_client: The Redis client instance.
        pattern: Pattern to match keys (default: "*" for all keys).
        cursor: Cursor position for pagination (0 to start).
        count: Number of keys to scan in this iteration.
    Returns:
        Tuple of (next_cursor, list_of_keys).
    """
    try:
        cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=count)
        log.info(f"Scanned {len(keys)} keys, next cursor: {cursor}")
        return cursor, keys
    except Exception as e:
        log.error("Failed to scan Redis keys", e)
        raise RuntimeError(f"Failed to scan Redis keys: {str(e)}")


def process_batch(
    redis_client: redis.Redis,
    keys: List[str],
    table_name: str,
    timeseries_state: Dict[str, int],
) -> Tuple[int, Dict[str, int]]:
    """
    Process a batch of Redis keys and upsert them to the destination.
    Detects TimeSeries keys and syncs them incrementally.
    Args:
        redis_client: Redis client instance.
        keys: List of keys to process.
        table_name: Destination table name.
        timeseries_state: Dictionary mapping TimeSeries keys to their last synced timestamp.
    Returns:
        Tuple of (number of records processed, updated timeseries_state).
    """
    batch_row_count = 0

    for key in keys:
        # Check if this is a TimeSeries key
        if is_timeseries_key(redis_client, key):
            # Sync incrementally from last known timestamp
            last_ts = timeseries_state.get(key, 0)
            count, max_ts = sync_timeseries_key(redis_client, key, table_name, last_ts)
            batch_row_count += count

            # Update the state with the latest timestamp for this key
            if max_ts > last_ts:
                timeseries_state[key] = max_ts

            log.info(
                f"Synced {count} data points from TimeSeries key '{key}' (timestamp: {max_ts})"
            )
        else:
            # Handle regular Redis key-value data
            key_info = get_redis_value_info(redis_client, key)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table_name, data=key_info)
            batch_row_count += 1

    return batch_row_count, timeseries_state


def sync_redis_data(
    redis_client: redis.Redis,
    table_name: str,
    key_pattern: str,
    batch_size: int,
    cursor: int,
    current_sync_time: str,
    timeseries_state: Dict[str, int],
) -> Tuple[int, Dict[str, int]]:
    """
    Sync Redis data by scanning and processing keys in batches.
    Supports both regular Redis keys and TimeSeries keys with incremental sync.
    Args:
        redis_client: Redis client instance.
        table_name: Destination table name.
        key_pattern: Pattern to match keys.
        batch_size: Number of keys to process per batch.
        cursor: Starting cursor position.
        current_sync_time: Current sync timestamp.
        timeseries_state: Dictionary mapping TimeSeries keys to their last synced timestamp.
    Returns:
        Tuple of (total records processed, updated timeseries_state).
    """
    row_count = 0
    batch_count = 0
    total_keys_processed = 0

    log.info(f"Starting Redis key scan with pattern: {key_pattern}, batch size: {batch_size}")

    # Scan all keys matching the pattern
    while True:
        batch_count += 1
        log.info(f"Processing batch {batch_count}, cursor: {cursor}")

        # Scan keys from Redis
        cursor, keys = scan_redis_keys(redis_client, key_pattern, cursor, batch_size)

        if not keys:
            log.info("No more keys to process")
            if cursor == 0:  # Scan completed
                break
            continue

        # Process each key in the current batch
        batch_row_count, timeseries_state = process_batch(
            redis_client, keys, table_name, timeseries_state
        )
        row_count += batch_row_count
        total_keys_processed += batch_row_count

        # Checkpoint periodically and at cursor reset
        if row_count % __CHECKPOINT_INTERVAL == 0 or cursor == 0:
            save_state(cursor, current_sync_time, timeseries_state)

        log.info(
            f"Completed batch {batch_count}: processed {batch_row_count} records, "
            f"total processed: {total_keys_processed}, cursor: {cursor}"
        )

        # If cursor is 0, we've completed the full scan
        if cursor == 0:
            break

    return total_keys_processed, timeseries_state


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
    log.warning("Example: Source Examples - Redis")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Create Redis client
    redis_client = create_redis_client(configuration)

    # Get configuration parameters
    table_name = configuration.get("table_name", "redis_data")
    key_pattern = configuration.get("key_pattern", "*")
    batch_size = int(configuration.get("batch_size", __BATCH_SIZE))

    # Get the state variables for the sync
    # For regular Redis keys: track cursor for resumption using SCAN
    # For TimeSeries keys: track last synced timestamp for incremental sync
    cursor = state.get("cursor", 0)
    timeseries_state = state.get("timeseries_state", {})
    current_sync_time = datetime.now(timezone.utc).isoformat()

    try:
        # Sync all Redis data (both regular keys and TimeSeries)
        total_records_processed, timeseries_state = sync_redis_data(
            redis_client,
            table_name,
            key_pattern,
            batch_size,
            cursor,
            current_sync_time,
            timeseries_state,
        )

        # Final checkpoint - reset cursor to 0 for next scan, but preserve TimeSeries timestamps
        save_state(0, current_sync_time, timeseries_state)

        log.info(f"Successfully synced {total_records_processed} records from Redis")

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")
    finally:
        # Close Redis connection
        close_redis_client(redis_client)


def save_state(cursor: int, sync_time: str, timeseries_state: Dict[str, int]):
    """
    Save the current state including cursor position, sync time, and TimeSeries timestamps.
    Args:
        cursor: Current cursor position for Redis SCAN.
        sync_time: Current sync timestamp.
        timeseries_state: Dictionary mapping TimeSeries keys to their last synced timestamp.
    """
    new_state = {
        "cursor": cursor,
        "last_sync_time": sync_time,
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
