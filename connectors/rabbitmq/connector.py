"""RabbitMQ Connector - syncs messages from RabbitMQ queues to Fivetran using the pika library.
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

# Import the pika library for connecting to RabbitMQ
import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

# For handling type hints
from typing import Optional, Dict, Any, Tuple

# For parsing timestamps and generating unique IDs
import hashlib
from datetime import datetime, timezone

# Checkpoint every 500 records
__CHECKPOINT_INTERVAL = 500
__DEFAULT_BATCH_SIZE = 100


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
    if "connection_url" not in configuration or not configuration["connection_url"]:
        raise ValueError("Missing required configuration value: connection_url")

    # Validate queues list
    if "queues" not in configuration or not configuration["queues"]:
        raise ValueError(
            "Missing required configuration value: queues (must be a non-empty comma-separated string)"
        )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    Each RabbitMQ queue will be synced to a separate table.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # Get queues from configuration (comma-separated string)
    queues_str = configuration.get("queues", "")
    queues = [q.strip() for q in queues_str.split(",") if q.strip()]

    schemas = []
    for queue_name in queues:
        # Create a table for each queue
        # Table name is the queue name in lowercase with special characters replaced
        table_name = queue_name.lower().replace("-", "_").replace(".", "_")

        schemas.append(
            {
                "table": table_name,  # Name of the table in the destination, required.
                "primary_key": ["message_id"],  # Primary key column(s) for the table, required.
                # Note: Column types are automatically inferred by Fivetran.
                # See the README for detailed column descriptions.
            }
        )

    return schemas


def create_rabbitmq_connection(configuration: dict):
    """
    Create a RabbitMQ connection using the provided connection URL.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        pika.BlockingConnection: A RabbitMQ connection instance.
    """

    try:
        connection_url = configuration.get("connection_url")
        log.info("Connecting to RabbitMQ using connection URL")
        parameters = pika.URLParameters(connection_url)

        connection = pika.BlockingConnection(parameters)
        log.info("Successfully created RabbitMQ connection")
        return connection

    except AMQPConnectionError as e:
        log.error("Failed to connect to RabbitMQ", e)
        raise RuntimeError(f"Failed to connect to RabbitMQ: {str(e)}")
    except Exception as e:
        log.error("Unexpected error creating RabbitMQ connection", e)
        raise RuntimeError(f"Unexpected error creating RabbitMQ connection: {str(e)}")


def generate_message_id(queue_name: str, delivery_tag: int, body: bytes) -> str:
    """
    Generate a unique message ID based on queue name, delivery tag, and message body.
    This ensures consistent IDs for the same messages across syncs.
    Args:
        queue_name: The queue name
        delivery_tag: The delivery tag from RabbitMQ
        body: The message body as bytes
    Returns:
        A unique message ID string
    """
    # Create a hash from queue name, delivery tag, and body content
    content = f"{queue_name}:{delivery_tag}:{body.decode('utf-8', errors='ignore')}"
    message_hash = hashlib.sha256(content.encode()).hexdigest()
    return f"{queue_name}_{delivery_tag}_{message_hash[:16]}"


def parse_message_body(body: bytes, content_type: str) -> str:
    """
    Parse message body based on content type with error handling.

    Args:
        body (bytes): Raw message body as bytes.
        content_type (str): Content type from message properties.

    Returns:
        str: Decoded message body as string.
    """
    try:
        if content_type == "application/json":
            return body.decode("utf-8")
        else:
            return body.decode("utf-8", errors="replace")
    except (UnicodeDecodeError, AttributeError):
        # Fallback to string representation if decoding fails
        return str(body)


def format_timestamp_from_properties(properties_timestamp, fallback_timestamp: str) -> str:
    """
    Format timestamp from RabbitMQ properties or use fallback.

    Converts Unix timestamp from RabbitMQ properties to ISO 8601 format.
    If no timestamp is available in properties, uses the provided fallback.

    Args:
        properties_timestamp: Timestamp from RabbitMQ message properties (Unix timestamp or None).
        fallback_timestamp (str): Fallback timestamp to use if properties timestamp is None.

    Returns:
        str: ISO 8601 formatted timestamp string.
    """
    if not properties_timestamp:
        return fallback_timestamp

    return (
        datetime.fromtimestamp(properties_timestamp, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def extract_routing_info(method_frame) -> Dict[str, str]:
    """
    Extract routing information from RabbitMQ method frame.

    Args:
        method_frame: RabbitMQ method frame containing routing information.

    Returns:
        dict: Dictionary containing routing_key, exchange, and redelivered flag.
    """
    return {
        "routing_key": method_frame.routing_key or "",
        "exchange": method_frame.exchange or "",
        "redelivered": method_frame.redelivered,
    }


def extract_message_properties(properties) -> Dict[str, Any]:
    """
    Extract all relevant properties from RabbitMQ message properties.

    Args:
        properties: RabbitMQ message properties object.

    Returns:
        dict: Dictionary containing all extracted properties with safe defaults.
    """
    return {
        "content_type": properties.content_type or "",
        "content_encoding": properties.content_encoding or "",
        "delivery_mode": properties.delivery_mode or 1,
        "priority": properties.priority or 0,
        "correlation_id": properties.correlation_id or "",
        "reply_to": properties.reply_to or "",
        "expiration": properties.expiration or "",
        "message_id_header": properties.message_id or "",
        "type": properties.type or "",
        "user_id": properties.user_id or "",
        "app_id": properties.app_id or "",
        "headers": json.dumps(properties.headers) if properties.headers else "{}",
    }


def build_message_record(
    queue_name: str,
    delivery_tag: int,
    method_frame,
    properties,
    body: bytes,
    synced_at: str,
) -> Dict[str, Any]:
    """
    Build a complete message record from RabbitMQ message components.

    This function orchestrates the parsing and extraction of all message components,
    combining them into a single record ready for database upsert.

    Args:
        queue_name (str): The queue name.
        delivery_tag (int): RabbitMQ delivery tag.
        method_frame: RabbitMQ method frame containing routing info.
        properties: RabbitMQ message properties.
        body (bytes): Raw message body as bytes.
        synced_at (str): Timestamp when message was synced.

    Returns:
        Dict[str, Any]: Dictionary containing all message data ready for upsert with fields:
            - message_id: Unique identifier for the message
            - delivery_tag: RabbitMQ delivery tag
            - queue_name: Source queue name
            - routing_key, exchange: Routing information
            - message_body: Decoded message content
            - Various properties: content_type, delivery_mode, priority, etc.
            - timestamp: Message timestamp or synced_at fallback
            - headers: JSON-serialized headers
    """
    # Generate unique message ID
    message_id = generate_message_id(queue_name, delivery_tag, body)

    # Parse message body based on content type
    message_body = parse_message_body(body, properties.content_type or "")

    # Extract routing information from method frame
    routing_info = extract_routing_info(method_frame)

    # Extract all message properties
    message_props = extract_message_properties(properties)

    # Format timestamp from properties or use synced_at
    timestamp = format_timestamp_from_properties(properties.timestamp, synced_at)

    # Build complete message record by combining all components
    return {
        "message_id": message_id,
        "delivery_tag": delivery_tag,
        "queue_name": queue_name,
        "message_body": message_body,
        "timestamp": timestamp,
        "synced_at": synced_at,
        **routing_info,
        **message_props,
    }


def fetch_and_upsert_messages_batch(
    channel,
    queue_name: str,
    table_name: str,
    last_delivery_tag: Optional[int] = None,
    batch_size: int = __DEFAULT_BATCH_SIZE,
) -> Tuple[int, bool, int]:
    """
    Fetch messages from RabbitMQ queue and upsert them immediately to avoid memory accumulation.
    Messages are consumed (removed) from the queue after successful sync to prevent duplicate reads.

    This function implements incremental sync by tracking delivery tags. Messages with delivery tags
    less than or equal to the last synced tag are skipped and acknowledged to remove them from the queue.

    Args:
        channel: The RabbitMQ channel instance.
        queue_name: The name of the queue to fetch data from.
        table_name: The destination table name.
        last_delivery_tag: The last delivery tag from the previous sync (used for incremental sync).
        batch_size: Number of messages to fetch in this batch.
    Returns:
        A tuple containing (message_count, has_more_data boolean, highest_delivery_tag).
    """
    try:
        highest_delivery_tag = last_delivery_tag or 0
        synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Get queue information to check message count
        queue_declare_result = channel.queue_declare(queue=queue_name, passive=True)
        message_count = queue_declare_result.method.message_count
        log.info(f"Queue '{queue_name}' has {message_count} messages available")

        # Fetch messages using basic_get and process them one by one
        fetched_count = 0
        for _ in range(batch_size):
            # Get message without consuming it immediately (auto_ack=False)
            method_frame, properties, body = channel.basic_get(queue=queue_name, auto_ack=False)

            if method_frame is None:
                # No more messages available in the queue
                break

            delivery_tag = method_frame.delivery_tag

            # Skip already-synced messages based on delivery tag for incremental sync
            # Acknowledge them to remove from queue and prevent infinite re-reading
            if last_delivery_tag and delivery_tag <= last_delivery_tag:
                channel.basic_ack(delivery_tag=delivery_tag)
                continue

            # Build complete message record from RabbitMQ components
            message = build_message_record(
                queue_name=queue_name,
                delivery_tag=delivery_tag,
                method_frame=method_frame,
                properties=properties,
                body=body,
                synced_at=synced_at,
            )

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table_name, data=message)
            fetched_count += 1

            # Track the highest delivery tag seen for state management
            if delivery_tag > highest_delivery_tag:
                highest_delivery_tag = delivery_tag

            # Acknowledge the message to remove it from the queue after syncing
            # This prevents re-reading the same messages infinitely
            # Note: Messages are "consumed" but data is preserved in the warehouse
            channel.basic_ack(delivery_tag=delivery_tag)

        log.info(
            f"Fetched and upserted batch: {fetched_count} messages from queue: {queue_name}, "
            f"highest delivery_tag: {highest_delivery_tag}"
        )

        # Check if there might be more data
        # If we fetched exactly the batch size, there might be more messages
        has_more_data = fetched_count == batch_size

        return fetched_count, has_more_data, highest_delivery_tag

    except AMQPChannelError as e:
        log.error(f"Channel error while fetching from queue {queue_name}", e)
        raise RuntimeError(f"Channel error while fetching from queue {queue_name}: {str(e)}")
    except Exception as e:
        log.error(f"Failed to fetch batch from queue {queue_name}", e)
        raise RuntimeError(f"Failed to fetch batch from queue {queue_name}: {str(e)}")


def process_queue_batches(
    channel,
    queue_name: str,
    table_name: str,
    state: dict,
    batch_size: int,
) -> int:
    """
    Process all message batches from a single queue with incremental sync support.

    This function fetches messages in batches, upserts them to the destination table,
    and checkpoints state periodically. It implements incremental sync by tracking
    the last delivery tag for each queue.

    Args:
        channel: The RabbitMQ channel instance
        queue_name: The queue name to process
        table_name: The destination table name
        state: The state dictionary for tracking sync progress
        batch_size: Number of messages to fetch per batch
    Returns:
        Total number of messages processed from this queue
    """
    # Get the state variable for this queue
    state_key = f"{queue_name}_last_delivery_tag"
    last_delivery_tag = state.get(state_key, 0)
    new_delivery_tag = last_delivery_tag

    row_count = 0
    batch_count = 0
    has_more_data = True

    log.info(f"Starting batch processing for queue '{queue_name}' with batch size: {batch_size}")

    # Process data in batches until no more messages available
    while has_more_data:
        batch_count += 1
        log.info(f"Processing batch {batch_count} for queue '{queue_name}'")

        # Fetch and upsert messages
        batch_row_count, has_more_data, highest_delivery_tag = fetch_and_upsert_messages_batch(
            channel, queue_name, table_name, last_delivery_tag, batch_size
        )

        if batch_row_count == 0:
            log.info(f"No more messages to process from queue '{queue_name}'")
            break

        row_count += batch_row_count

        # Update new_delivery_tag with the highest delivery tag from this batch
        if highest_delivery_tag > new_delivery_tag:
            new_delivery_tag = highest_delivery_tag

        if row_count > 0 and row_count % __CHECKPOINT_INTERVAL == 0:
            save_state(state, queue_name, new_delivery_tag)

        log.info(
            f"Completed batch {batch_count} for queue '{queue_name}': "
            f"processed {batch_row_count} messages, total processed: {row_count}, "
            f"last delivery_tag: {new_delivery_tag}"
        )

        # Update last_delivery_tag for next iteration
        last_delivery_tag = new_delivery_tag

    # Final checkpoint for this queue
    save_state(state, queue_name, new_delivery_tag)

    log.info(
        f"Successfully synced {row_count} messages from queue '{queue_name}' "
        f"across {batch_count} batches"
    )

    return row_count


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

    log.warning("Example: Source Connector: RabbitMQ")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Create RabbitMQ connection
    connection = create_rabbitmq_connection(configuration)

    try:
        # Create a channel
        channel = connection.channel()

        # Extract configuration parameters as required
        queues_str = configuration.get("queues", "")
        queues = [q.strip() for q in queues_str.split(",") if q.strip()]
        batch_size = int(configuration.get("batch_size", __DEFAULT_BATCH_SIZE))

        # Process each queue independently
        for queue_name in queues:
            log.info(f"Processing queue: {queue_name}")

            # Convert queue name to valid table name
            table_name = queue_name.lower().replace("-", "_").replace(".", "_")

            # Process all batches from this queue
            process_queue_batches(
                channel=channel,
                queue_name=queue_name,
                table_name=table_name,
                state=state,
                batch_size=batch_size,
            )

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")
    finally:
        # Always close the connection
        if connection and connection.is_open:
            connection.close()
            log.info("RabbitMQ connection closed")


def save_state(current_state: dict, queue_name: str, new_delivery_tag: int):
    """
    Save the current sync state by checkpointing.
    Args:
        current_state: The current state dictionary
        queue_name: The queue name being processed
        new_delivery_tag: The latest delivery tag processed for this queue.
    """
    # Update state for this specific queue
    state_key = f"{queue_name}_last_delivery_tag"
    current_state[state_key] = new_delivery_tag

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(current_state)


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
