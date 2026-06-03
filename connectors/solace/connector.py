"""
This is a connector for fetching events from Solace using the Fivetran Connector SDK.
It supports incremental sync by tracking the last processed event timestamp.
The connector can work with Solace messaging APIs to fetch events.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For JSON serialization and deserialization of event data and configs
import json

# For handling timestamps and time zones in event processing
from datetime import datetime, timezone

# For type hints to improve code clarity and static checks
from typing import Dict, List, Optional, Generator

# For connecting to Solace messaging service
from solace.messaging.messaging_service import MessagingService

# For handling inbound messages from Solace queues
from solace.messaging.receiver.inbound_message import InboundMessage

# For working with Solace queue resources
from solace.messaging.resources.queue import Queue

# For data manipulation and deduplication using DataFrames
import pandas as pd

# For publishing messages to Solace for testing purposes
from solace_publisher import SolacePublisher

# CONFIGURATION AND CONSTANTS
__DEFAULT_LAST_SYNC_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)
__MAX_BATCH_SIZE = 1000


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    validate_configuration(configuration, "schema")

    return [{"table": "solace_events", "primary_key": ["event_id", "timestamp"]}]


class SolaceAuth:
    """
    Handles authentication and connection to the Solace messaging service.

    This class encapsulates the logic for establishing and managing a connection
    to a Solace broker using the provided host, username, password, and VPN name.
    It provides a method to obtain a connected MessagingService instance, which
    can be reused for sending or receiving messages.
    """

    def __init__(self, host: str, username: str, password: str, vpn_name: str = "default"):
        self.host = host
        self.username = username
        self.password = password
        self.vpn_name = vpn_name
        self.messaging_service = None

    def get_messaging_service(self) -> MessagingService:
        """Get or create a messaging service connection."""
        if self.messaging_service is None:
            try:
                # Create messaging service
                self.messaging_service = (
                    MessagingService.builder()
                    .from_properties(
                        {
                            "solace.messaging.transport.host": self.host,
                            "solace.messaging.authentication.basic.username": self.username,
                            "solace.messaging.authentication.basic.password": self.password,
                            "solace.messaging.service.vpn-name": self.vpn_name,
                            "solace.messaging.service.ssl.trust-store": None,
                            "solace.messaging.service.ssl.validate-certificate": False,
                        }
                    )
                    .build()
                )

                # Connect to the messaging service
                self.messaging_service.connect()
                log.info(f"Successfully connected to Solace at {self.host}")

            except Exception as e:
                log.error("Failed to connect to Solace", e)
                raise RuntimeError(f"Solace connection failed: {e}")

        return self.messaging_service


def fetch_events_messaging(
    config: dict, last_sync_time: datetime, batch_size: int = __MAX_BATCH_SIZE
) -> List[Dict]:
    """
    Fetch events from Solace using messaging API (queue/topic subscription).

    Args:
        config (dict): Configuration dictionary
        last_sync_time (datetime): Last sync timestamp for incremental sync
        batch_size (int): Number of events to fetch per batch

    Returns:
        List[Dict]: List of event records
    """
    method_name = "fetch_events_messaging"

    # Initialize authentication
    auth = SolaceAuth(
        host=config["solace_host"],
        username=config["solace_username"],
        password=config["solace_password"],
        vpn_name=config.get("solace_vpn", "default"),
    )

    messaging_service = auth.get_messaging_service()
    events = []
    receiver = None

    try:
        # Get queue name from config
        queue_name = config.get("solace_queue")
        durable_exclusive_queue = Queue.durable_exclusive_queue(queue_name)

        # Create message receiver
        receiver = messaging_service.create_persistent_message_receiver_builder().build(
            durable_exclusive_queue
        )

        # Start receiving messages
        receiver.start()
        log.info(f"{method_name}: Started receiving messages from queue: {queue_name}")

        # Collect messages
        message_count = 0

        while message_count < batch_size:
            try:
                message = receiver.receive_message(timeout=1000)  # 1 second timeout
                if message:
                    event_record = process_message(message, last_sync_time)
                    if event_record:
                        events.append(event_record)
                        message_count += 1
                    else:
                        # event_record is None if the event was already consumed in a previous sync and loaded into the destination based on the checkpoint.
                        # Acknowledge the message to remove it from the queue.
                        receiver.ack(message)
                else:
                    # No more messages available
                    break

            except Exception as e:
                log.warning(f"{method_name}: Error processing message: {e}")
                continue

        log.info(f"{method_name}: Fetched {len(events)} events from messaging API")

    except Exception as e:
        log.error(f"{method_name}: Error fetching events via messaging API", e)
    finally:
        if receiver is not None:
            receiver.terminate()

    return events


def process_message(message: InboundMessage, last_sync_time: datetime) -> Optional[Dict]:
    """
    Process a Solace message into an event record.

    Args:
        message (InboundMessage): Solace message object
        last_sync_time (datetime): Last sync timestamp for filtering

    Returns:
        Optional[Dict]: Processed event record or None if old message
    """
    try:
        # Extract message properties
        payload = message.get_payload_as_string()
        topic = message.get_destination_name()
        timestamp = datetime.now(timezone.utc)

        # Parse payload as JSON if possible
        try:
            payload_json = json.loads(payload)
            message_type = payload_json.get("type", "unknown")
            event_timestamp = payload_json.get("event_timestamp", timestamp.isoformat())
            message_id = payload_json.get("message_id", "")
            details = payload_json.get("details", "")
        except (json.JSONDecodeError, TypeError):
            event_timestamp = timestamp.isoformat()
            message_type = "raw"
            message_id = ""
            details = ""

        # Check if message is newer than last sync time
        if last_sync_time and datetime.fromisoformat(event_timestamp) <= last_sync_time:
            return None

        event_record = {
            "event_id": f"{topic}_{timestamp.timestamp()}_{hash(payload) % 1000000}",
            "message_id": message_id,
            "timestamp": event_timestamp,
            "topic": topic,
            "message_payload": payload,
            "message_type": message_type,
            "source_system": "solace",
            "details": details,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        return event_record

    except Exception as e:
        log.error("Error processing message", e)
        return None


def clean_and_deduplicate_events(events: List[Dict]) -> List[Dict]:
    """
    Clean and deduplicate event records.

    Args:
        events (List[Dict]): Raw event records

    Returns:
        List[Dict]: Cleaned and deduplicated events
    """
    if not events:
        return []

    # Convert to DataFrame for easier processing
    df = pd.DataFrame(events)

    # Remove duplicates based on event_id
    df = df.drop_duplicates(subset=["event_id"], keep="first")

    # Sort by timestamp
    df = df.sort_values("timestamp")

    # Convert back to list of dictionaries
    return df.to_dict("records")


def sync_events(config: dict, state: dict) -> Generator:
    """
    Main function to sync events from Solace.

    Args:
        config (dict): Configuration dictionary
        state (dict): State for incremental sync

    This function fetches, cleans, deduplicates, and upserts events, then updates and checkpoints the sync state.
    """
    method_name = "sync_events"

    # Get last sync time from state
    last_sync_time_str = state.get("last_sync_time")
    if last_sync_time_str:
        last_sync_time = datetime.fromisoformat(last_sync_time_str)
    else:
        last_sync_time = __DEFAULT_LAST_SYNC_DATE

    log.info(f"{method_name}: Starting sync from {last_sync_time}")

    try:
        events = fetch_events_messaging(config, last_sync_time)

        # Clean and deduplicate events
        events = clean_and_deduplicate_events(events)

        if not events:
            log.info(f"{method_name}: No new events found")
            op.checkpoint(state)
            return

        log.info(f"{method_name}: Processing {len(events)} events")

        # Upsert events
        for event in events:
            try:
                op.upsert(table="solace_events", data=event)
            except Exception as e:
                log.error(f"{method_name}: Error upserting event {event.get('event_id')}", e)

        # Update state with latest timestamp
        latest_timestamp = max(event["timestamp"] for event in events)
        state["last_sync_time"] = latest_timestamp

        log.info(f"{method_name}: Successfully processed {len(events)} events")

    except Exception as e:
        log.error(f"{method_name}: Error during sync", e)
        raise

    # Checkpoint state
    op.checkpoint(state)


def publish_messages_for_testing(config: dict, count: int):
    publisher = SolacePublisher(
        host=config["solace_host"],
        username=config["solace_username"],
        password=config["solace_password"],
        topic_name="demo/topic",
        vpn=config.get("solace_vpn", "default"),
    )

    publisher.connect()
    publisher.publish_messages(count)


def validate_configuration(configuration: dict, method_name: str):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the schema and update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        method_name: the name of the method that is calling this method
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_keys = ["solace_host", "solace_username", "solace_password", "solace_queue"]
    for key in required_keys:
        if key not in configuration:
            log.error(f"{method_name}: Missing required configuration key: {key}")
            raise ValueError(f"Missing configuration key: {key}")


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
    log.warning("Example: Syncing data from Solace queue")

    method_name = "update"
    validate_configuration(configuration, method_name)

    # Load messages for testing purpose
    publish_messages_for_testing(configuration, 10)

    log.info(f"{method_name}: Starting Solace connector sync")

    # Sync events
    sync_events(configuration, state)

    log.info(f"{method_name}: Solace connector sync completed")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
