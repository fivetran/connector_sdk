"""This connector consumes one queue of an AMQP 1.0 broker, such as Solace PubSub+, Azure Service Bus or RabbitMQ,
and writes every message to a destination table named after the queue.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For pausing between acknowledgment retries and generating event ids
import time

# For recording when the sync started
from datetime import datetime, timezone

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For building the setup form shown to users when configuring the connector in Fivetran
from fivetran_connector_sdk import ConfigurationForm

# For defining the fields of the setup form
from fivetran_connector_sdk import form_field

# For returning success or failure from the setup form's connection test
from fivetran_connector_sdk import Test

# For detecting the end of the queue and failures to settle deliveries
from proton import ProtonException, Timeout

# For connecting to the broker, validating the host and classifying failures
import amqp_client

# For turning AMQP messages into destination rows
import amqp_message

__RECEIVE_TIMEOUT_SECONDS = 10
__CONNECTION_TIMEOUT_SECONDS = 60
__CONNECTION_TEST_RECEIVE_TIMEOUT_SECONDS = 2
__CHECKPOINT_INTERVAL = 10_000
__MAX_EVENTS_WITHOUT_CREATION_TIME = 1_000_000
__MAX_ACKNOWLEDGMENT_ATTEMPTS = 3
__ACKNOWLEDGMENT_INITIAL_BACKOFF_SECONDS = 0.3
__ACKNOWLEDGMENT_MAX_BACKOFF_SECONDS = 3.0
__MILLIS_PER_SECOND = 1000
__MESSAGE_TYPE_TEXT = "Text"
__MESSAGE_TYPE_JSON = "JSON"
__JSON_DELIVERY_PACKED = "Packed"
__JSON_DELIVERY_UNPACKED = "Unpacked"
__REQUIRED_CONFIGURATION_KEYS = ["host", "port", "queue_name"]
__STATE_CREATION_TIME_KEY = "last_message_creation_time"


def configuration_form():
    """
    Define the setup form shown to users when configuring this connector in Fivetran.
    Fivetran calls this method when rendering the connector setup UI.
    Returns:
        ConfigurationForm: the completed form with fields and the connection test.
    """
    config_form = ConfigurationForm()
    config_form.add_field(form_field.TextField(name="host", label="Host", required=True))
    config_form.add_field(
        form_field.TextField(name="port", label="Port", required=True, placeholder="5671")
    )
    config_form.add_field(
        form_field.TextField(
            name="namespace",
            label="Namespace",
            placeholder="/",
            description="Identifies the broker scope of your queue: RabbitMQ vhost or Solace Message VPN for"
            " example. Only the broker's default scope is supported, so leave it as /.",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="queue_name",
            label="Queue name",
            required=True,
            description="Exact queue name to consume from without prefixes.",
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="auth_type",
            label="Authentication method",
            required=True,
            fields=[
                form_field.DropdownFieldParam(
                    value=amqp_client.AUTH_TYPE_BASIC, label="Username and Password"
                ),
                form_field.DropdownFieldParam(
                    value=amqp_client.AUTH_TYPE_MUTUAL_TLS, label="Mutual TLS"
                ),
            ],
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="username", label="Username", description="Required for Username and Password."
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="password",
            label="Password",
            field_type=form_field.TextField.password,
            description="Required for Username and Password.",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="client_certificate",
            label="Client certificate",
            field_type=form_field.TextField.password,
            description="Required for Mutual TLS: the PEM client certificate chain, base64-encoded.",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="client_private_key",
            label="Client private key",
            field_type=form_field.TextField.password,
            description="Required for Mutual TLS: the PEM private key, base64-encoded.",
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="message_type",
            label="Message type",
            required=True,
            fields=[
                form_field.DropdownFieldParam(value=__MESSAGE_TYPE_TEXT, label="Text"),
                form_field.DropdownFieldParam(value=__MESSAGE_TYPE_JSON, label="JSON"),
            ],
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="json_delivery_mode",
            label="JSON delivery mode",
            description="Used when the message type is JSON.",
            fields=[
                form_field.DropdownFieldParam(value=__JSON_DELIVERY_PACKED, label="Packed"),
                form_field.DropdownFieldParam(value=__JSON_DELIVERY_UNPACKED, label="Unpacked"),
            ],
        )
    )
    config_form.add_test(label="Connecting to AMQP 1.0-compatible broker", func=connection_test)
    return config_form


def connection_test(configuration: dict):
    """
    Connect to the broker and open a receiver on the queue. A message that arrives during the test is not accepted,
    so the broker keeps it for the next sync.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
    test = Test()
    try:
        validate_configuration(configuration=configuration)
        connection = amqp_client.open_connection(configuration, __CONNECTION_TIMEOUT_SECONDS)
    except (ValueError, ConnectionError) as error:
        return test.failure(str(error))
    except ProtonException as error:
        return test.failure(f"Connection error: {error}")
    try:
        receiver = amqp_client.open_receiver(connection, configuration["queue_name"])
        try:
            receiver.receive(timeout=__CONNECTION_TEST_RECEIVE_TIMEOUT_SECONDS)
            log.info("Successfully connected to broker")
        except Timeout:
            log.info("Successfully connected to broker (no messages currently in queue)")
    except ProtonException as error:
        return test.failure(f"Unable to open queue '{configuration['queue_name']}': {error}")
    finally:
        connection.close()
    return test.success()


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    for key in __REQUIRED_CONFIGURATION_KEYS:
        if not str(configuration.get(key) or "").strip():
            raise ValueError(f"Missing required configuration value: {key}")
    if not amqp_client.is_valid_host(configuration["host"]):
        raise ValueError(amqp_client.INVALID_HOST_ERROR)
    if not str(configuration["port"]).strip().isdigit():
        raise ValueError(f"Port must be a number, got: {configuration['port']}")
    auth_type = configuration.get("auth_type") or amqp_client.AUTH_TYPE_BASIC
    if auth_type not in (amqp_client.AUTH_TYPE_BASIC, amqp_client.AUTH_TYPE_MUTUAL_TLS):
        raise ValueError(f"Unsupported auth_type: {auth_type}")
    required_credentials = (
        ["username", "password"]
        if auth_type == amqp_client.AUTH_TYPE_BASIC
        else ["client_certificate", "client_private_key"]
    )
    for key in required_credentials:
        if not str(configuration.get(key) or "").strip():
            raise ValueError(f"Missing required configuration value for {auth_type}: {key}")
    if message_type(configuration) not in (__MESSAGE_TYPE_TEXT, __MESSAGE_TYPE_JSON):
        raise ValueError(f"Unsupported message_type: {configuration.get('message_type')}")
    if json_delivery_mode(configuration) not in (__JSON_DELIVERY_PACKED, __JSON_DELIVERY_UNPACKED):
        raise ValueError(
            f"Unsupported json_delivery_mode: {configuration.get('json_delivery_mode')}"
        )


def message_type(configuration: dict):
    """
    Return the configured message type, which defaults to JSON.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        "Text" or "JSON".
    """
    return configuration.get("message_type") or __MESSAGE_TYPE_JSON


def json_delivery_mode(configuration: dict):
    """
    Return the configured JSON delivery mode, which defaults to Packed.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        "Packed" or "Unpacked".
    """
    return configuration.get("json_delivery_mode") or __JSON_DELIVERY_PACKED


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    data_type = "JSON" if message_type(configuration) == __MESSAGE_TYPE_JSON else "STRING"
    return [
        {
            "table": configuration["queue_name"],
            "primary_key": ["event_id"],
            "columns": {
                "event_id": "STRING",
                "data": data_type,
                "absolute_expiry_time": "LONG",
                "created_time": "UTC_DATETIME",
                "group_sequence": "LONG",
            },
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: QuickStart Examples - AMQP")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    sync_start = datetime.now(timezone.utc)
    log.info(
        f"Starting message consumption from queue: {configuration['queue_name']} and recorded sync start"
        f" time is: {sync_start.isoformat()}"
    )
    try:
        consumed = consume_queue(configuration, state, sync_start)
    except Exception as error:
        customer_error = amqp_client.classify_failure(error)
        if customer_error is None:
            raise
        # A failure the customer must fix, such as rejected credentials, ends the sync with an error on the dashboard.
        op.error(message=str(customer_error))
        return
    log.info(
        f"Finished consuming messages from queue: {configuration['queue_name']}. Total messages consumed:"
        f" {consumed}"
    )


def consume_queue(configuration: dict, state: dict, sync_start):
    """
    Receive messages until the queue is drained, a message created after the sync started arrives, or a million
    messages without a creation time have been read. Rows are checkpointed before their messages are accepted, so a
    message only leaves the queue after its row is safe in the destination; anything not yet accepted when a sync
    fails is redelivered on the next sync.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: the connector state, holding the creation time of the last synced message.
        sync_start: the UTC time the sync started.
    Returns:
        The number of messages consumed.
    """
    progress = {
        "consumed": 0,
        "pending_acknowledgments": 0,
        "without_creation_time": 0,
        "event_counter": 0,
        "warned_types": set(),
        "warned_null_body": False,
    }
    connection = amqp_client.open_connection(configuration, __CONNECTION_TIMEOUT_SECONDS)
    try:
        receiver = amqp_client.open_receiver(connection, configuration["queue_name"])
        while True:
            try:
                message = receiver.receive(timeout=__RECEIVE_TIMEOUT_SECONDS)
            except Timeout:
                break
            creation_time = amqp_message.created_time(message)
            if should_terminate_sync(creation_time, sync_start, progress):
                # The message is not accepted, so the broker redelivers it on the next sync.
                break
            process_message(configuration, state, message, creation_time, progress)
            progress["consumed"] += 1
            progress["pending_acknowledgments"] += 1
            if progress["consumed"] % __CHECKPOINT_INTERVAL == 0:
                checkpoint_and_acknowledge(state, receiver, progress)
        checkpoint_and_acknowledge(state, receiver, progress)
    finally:
        connection.close()
    if state.get(__STATE_CREATION_TIME_KEY):
        log.info(f"Last message synced with creation_time: {state[__STATE_CREATION_TIME_KEY]}")
    return progress["consumed"]


def should_terminate_sync(creation_time, sync_start, progress: dict):
    """
    Decide whether to stop before processing a message. A message created at or after the sync start belongs to the
    next sync. Messages without a creation time cannot close the window that way, so a million of them end the sync.
    Args:
        creation_time: the message creation time, or None.
        sync_start: the UTC time the sync started.
        progress: the sync progress counters.
    Returns:
        True when the sync should stop without accepting the message.
    """
    if creation_time is not None and creation_time >= sync_start:
        log.info(
            f"Message creation_time ({amqp_message.iso_text(creation_time)}) is after sync start time"
            f" ({sync_start.isoformat()}). Not acknowledging message, terminating sync."
        )
        return True
    if creation_time is None:
        progress["without_creation_time"] += 1
        if progress["without_creation_time"] > __MAX_EVENTS_WITHOUT_CREATION_TIME:
            log.info(
                f"Processed {progress['without_creation_time']} events without creation_time (limit:"
                f" {__MAX_EVENTS_WITHOUT_CREATION_TIME}), terminating sync."
            )
            return True
    return False


def process_message(configuration: dict, state: dict, message, creation_time, progress: dict):
    """
    Write one message as a row. Messages that are not text, and messages that cannot be processed, are skipped with
    a warning; they are still accepted with the batch, so they do not block the queue.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: the connector state.
        message: the received proton message.
        creation_time: the message creation time, or None.
        progress: the sync progress counters.
    """
    queue_name = configuration["queue_name"]
    kind, detail = amqp_message.body_kind(message)
    if kind != "text":
        log.warning(f"Skipped non-text message type: {detail} for queue: {queue_name}")
        if detail not in progress["warned_types"]:
            progress["warned_types"].add(detail)
            op.warning(
                message=f"Some messages encountered in queue {queue_name} were of type {detail} and were"
                " skipped, as this connector only supports text messages."
            )
        return
    try:
        payload = amqp_message.message_text(message, detail)
        values = message_values(configuration, payload, progress)
        if values is not None:
            upsert_row(queue_name, message, values, creation_time, progress)
    except amqp_message.MessageProcessingError as error:
        log.warning(f"Skipped message due to processing error: {error}")
        return
    if creation_time is not None:
        state[__STATE_CREATION_TIME_KEY] = amqp_message.iso_text(creation_time)


def message_values(configuration: dict, payload, progress: dict):
    """
    Turn the payload into the value columns of the row for the configured message type.
    Text puts the payload in a data column, JSON Packed puts the parsed JSON there, and JSON Unpacked writes one
    value_<field> column per first-level field, falling back to Packed when the payload is not a JSON object.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        payload: the message text, or None.
        progress: the sync progress counters.
    Returns:
        A dictionary of column name to value, or None when the message is skipped.
    Raises:
        MessageProcessingError: if a JSON payload cannot be parsed.
    """
    if message_type(configuration) == __MESSAGE_TYPE_TEXT:
        return {"data": payload}
    if json_delivery_mode(configuration) == __JSON_DELIVERY_PACKED:
        return {"data": amqp_message.packed_json(payload)}
    queue_name = configuration["queue_name"]
    if payload is None:
        log.warning(f"Skipped null-body message in JSON Unpacked mode for queue: {queue_name}")
        if not progress["warned_null_body"]:
            progress["warned_null_body"] = True
            op.warning(
                message=f"Some messages encountered in queue {queue_name} had a null body and were skipped,"
                " as this connector requires a message body to process."
            )
        return None
    values = amqp_message.unpacked_json(payload)
    if values is None:
        log.warning("Unable to unpack message, falling back to packed mode")
        return {"data": amqp_message.packed_json(payload)}
    return values


def upsert_row(queue_name: str, message, values: dict, creation_time, progress: dict):
    """
    Upsert one row. The event id is the receive time in milliseconds plus a per-sync counter, so every delivery is
    its own row, including a message the broker redelivers.
    Args:
        queue_name: the queue, which is also the destination table.
        message: the received proton message.
        values: the value columns of the row.
        creation_time: the message creation time, or None.
        progress: the sync progress counters.
    """
    progress["event_counter"] += 1
    event_id = f"{int(time.time() * __MILLIS_PER_SECOND)}_{progress['event_counter']}"
    row = amqp_message.metadata_columns(message, event_id, creation_time)
    row.update(values)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=queue_name, data=row)


def checkpoint_and_acknowledge(state: dict, receiver, progress: dict):
    """
    Checkpoint, then accept every message processed since the last checkpoint.
    Args:
        state: the connector state.
        receiver: the open proton receiver.
        progress: the sync progress counters.
    """
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)
    acknowledge_pending(receiver, progress)


def acknowledge_pending(receiver, progress: dict):
    """
    Accept the deliveries processed since the last acknowledgment, oldest first, retrying with exponential backoff.
    Args:
        receiver: the open proton receiver.
        progress: the sync progress counters.
    Raises:
        RuntimeError: if the deliveries cannot be accepted, so the sync fails and the messages are redelivered.
    """
    backoff_seconds = __ACKNOWLEDGMENT_INITIAL_BACKOFF_SECONDS
    last_error = None
    for attempt in range(1, __MAX_ACKNOWLEDGMENT_ATTEMPTS + 1):
        try:
            while progress["pending_acknowledgments"] > 0:
                receiver.accept()
                progress["pending_acknowledgments"] -= 1
            return
        except ProtonException as error:
            last_error = error
            log.warning(
                f"Failed to acknowledge batched messages (attempt {attempt}/{__MAX_ACKNOWLEDGMENT_ATTEMPTS}):"
                f" {error}"
            )
            if attempt < __MAX_ACKNOWLEDGMENT_ATTEMPTS:
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, __ACKNOWLEDGMENT_MAX_BACKOFF_SECONDS)
    raise RuntimeError(
        f"Failed to acknowledge messages after {__MAX_ACKNOWLEDGMENT_ATTEMPTS} retry attempts: rescheduling sync."
        f" Error: {last_error}"
    )


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema, configuration_form=configuration_form)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
