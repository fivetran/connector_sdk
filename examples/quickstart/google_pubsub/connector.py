"""This connector consumes messages from a Google Cloud Pub/Sub subscription and writes them to the destination.
Messages are acknowledged only after the rows that hold them have been checkpointed, and a Pub/Sub snapshot taken at
the end of each sync lets the next sync replay messages acknowledged by a sync that failed afterwards.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For measuring how long the subscription has been quiet
from datetime import datetime, timedelta, timezone

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

# For returning success or failure from the setup form's tests
from fivetran_connector_sdk import Test

# For the errors the Pub/Sub API raises
from google.api_core import exceptions as google_exceptions

# For pulling, acknowledging and snapshotting the subscription
import pubsub_client

# For turning messages into destination rows
import message_parser

__REQUIRED_CONFIGURATION_KEYS = ["project_id", "subscription_id", "key_content", "sync_format"]
__SYNC_FORMATS = [message_parser.SYNC_FORMAT_PACKED, message_parser.SYNC_FORMAT_UNPACKED]
__UNPACKING_LEVELS = [message_parser.UNPACKING_LEVEL_ONE, message_parser.UNPACKING_LEVEL_TWO]

# The sync stops once no message has arrived for this long.
__SECONDS_WITHOUT_UPDATE = 60
# The sync also stops once no message published before the sync started has arrived for this long, so a
# subscription that keeps receiving new messages cannot keep one sync running forever.
__FORWARD_WINDOW_SECONDS = 180
# How long one Pull call waits for messages.
__PULL_TIMEOUT_SECONDS = 30
__PULL_MAX_MESSAGES = 1000
# Pulled messages stay leased for this long while their rows are written and checkpointed.
__ACK_DEADLINE_SECONDS = 600
# The connector alternates between this many snapshots, so the previous one survives until the new one is saved.
__MAX_SNAPSHOTS = 2


def configuration_form():
    """
    Define the setup form shown to users when configuring this connector in Fivetran.
    Fivetran calls this method when rendering the connector setup UI.
    Returns:
        ConfigurationForm: the completed form with fields and setup tests.
    """
    config_form = ConfigurationForm()
    config_form.add_field(
        form_field.TextField(
            name="project_id",
            label="Project ID",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="my-google-pubsub-project",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="subscription_id",
            label="Subscription ID",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="my-google-pubsub-subscription",
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="sync_format",
            label="Sync format",
            fields=[form_field.DropdownFieldParam(value=value) for value in __SYNC_FORMATS],
            required=True,
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="unpacking_level",
            label="Unpacking level",
            description="Only used with the UNPACKED sync format.",
            fields=[form_field.DropdownFieldParam(value=value) for value in __UNPACKING_LEVELS],
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="key_content",
            label="Service Account Key",
            description="The content of the service account key file, in JSON format.",
            required=True,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_test(label="Validating subscriber permissions", func=subscriber_test)
    config_form.add_test(label="Validating snapshot permissions", func=snapshot_permissions_test)
    return config_form


def subscriber_test(configuration: dict):
    """
    Confirm that the key is a service account key and that it can consume the subscription.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
    test = Test()
    try:
        validate_configuration(configuration=configuration)
        client = create_client(configuration)
        granted = pubsub_client.granted_subscription_permissions(
            client, [pubsub_client.CONSUME_PERMISSION]
        )
    except (ValueError, google_exceptions.GoogleAPICallError) as error:
        return test.failure(f"Unable to create subscriber: {error}")
    if pubsub_client.CONSUME_PERMISSION not in granted:
        return test.failure(
            f"No {pubsub_client.CONSUME_PERMISSION} permission for {client.subscription_path}"
        )
    return test.success()


def snapshot_permissions_test(configuration: dict):
    """
    Check the project-level permissions that snapshots need. Snapshots only add recovery after a failed sync,
    so a missing permission is reported as a warning in the log and the test still passes.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success.
    """
    test = Test()
    try:
        granted = pubsub_client.granted_project_permissions(
            configuration["project_id"],
            configuration["key_content"],
            pubsub_client.SNAPSHOT_PERMISSIONS,
        )
    except Exception as error:
        # Any failure here only means snapshot recovery cannot be verified; it must not block the setup.
        log.warning(
            "Unable to verify snapshot permissions, data recovery after a sync failure may be unavailable: "
            f"{error}"
        )
        return test.success()
    missing = [
        permission
        for permission in pubsub_client.SNAPSHOT_PERMISSIONS
        if permission not in granted
    ]
    if missing:
        log.warning(
            f"Missing {', '.join(missing)} permissions in project {configuration['project_id']}. "
            "Grant them to enable data recovery after a sync failure"
        )
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
        if not str(configuration.get(key, "")).strip():
            raise ValueError(f"Missing required configuration value: {key}")
    if configuration["sync_format"] not in __SYNC_FORMATS:
        raise ValueError(f"sync_format must be one of {', '.join(__SYNC_FORMATS)}")
    if configuration["sync_format"] == message_parser.SYNC_FORMAT_UNPACKED:
        if configuration.get("unpacking_level") not in __UNPACKING_LEVELS:
            raise ValueError(
                f"unpacking_level must be one of {', '.join(__UNPACKING_LEVELS)} for UNPACKED"
            )
    pubsub_client.parse_service_account_key(configuration["key_content"])


def create_client(configuration: dict):
    """
    Create the Pub/Sub client for the configured subscription.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        A PubsubClient.
    """
    return pubsub_client.create_client(
        configuration["project_id"], configuration["subscription_id"], configuration["key_content"]
    )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Messages carrying a "table" field go to the table they name, which cannot be declared up front, so only
    # the table named after the subscription is declared here.
    return [
        {
            "table": configuration["subscription_id"],
            "primary_key": ["id"],
            "columns": {
                "id": "STRING",
                "message_hash": "STRING",
                "content": "STRING",
                "timestamp": "UTC_DATETIME",
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
    log.warning("Example: QuickStart Examples - Google Pub/Sub")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    client = create_client(configuration)
    try:
        previous_snapshot = state.get("pubsub_snapshot_name")
        if previous_snapshot is not None:
            log.info("Seeking to latest snapshot...")
            pubsub_client.seek_to_snapshot(client, previous_snapshot)
        else:
            log.info(
                "No previous Pub/Sub snapshot in state; starting from current subscription position."
            )

        log.info(f"Upserting data from subscription: {configuration['subscription_id']}")
        consume_messages(client, configuration, state)
        save_snapshot(client, state, previous_snapshot)
        log.info("Finishing upserting data")
    finally:
        client.subscriber.close()


def consume_messages(client, configuration: dict, state: dict):
    """
    Pull and write messages until the subscription is quiet. Each batch is upserted, checkpointed and only then
    acknowledged, so an acknowledged message is never missing from the destination.
    Args:
        client: the Pub/Sub client.
        configuration: the connector configuration.
        state: the connector state, checkpointed after every batch.
    """
    sync_started_at = datetime.now(timezone.utc)
    last_message_at = sync_started_at
    last_backlog_message_at = sync_started_at
    message_count = 0
    while True:
        received_messages = pubsub_client.pull(client, __PULL_MAX_MESSAGES, __PULL_TIMEOUT_SECONDS)
        now = datetime.now(timezone.utc)
        if received_messages:
            message_count, written_publish_times = process_batch(
                client, received_messages, message_count, configuration, state
            )
            # Only written messages count as activity: a message that cannot be parsed is redelivered at once
            # and must not keep the sync running.
            if written_publish_times:
                last_message_at = now
            if any(publish_time < sync_started_at for publish_time in written_publish_times):
                last_backlog_message_at = now
        if should_stop(now, last_message_at, last_backlog_message_at):
            log.info(f"Stopping after {message_count} message(s): the subscription is quiet")
            return


def should_stop(now, last_message_at, last_backlog_message_at):
    """
    Decide whether the sync is done: no message for 60 seconds, or no message published before the sync started
    for 3 minutes.
    Args:
        now: the current time.
        last_message_at: when the last message arrived.
        last_backlog_message_at: when the last message published before the sync started arrived.
    Returns:
        True when the sync should stop.
    """
    no_new_messages = now - timedelta(seconds=__SECONDS_WITHOUT_UPDATE) > last_message_at
    backlog_drained = now - timedelta(seconds=__FORWARD_WINDOW_SECONDS) > last_backlog_message_at
    return no_new_messages or backlog_drained


def process_batch(client, received_messages, message_count: int, configuration: dict, state: dict):
    """
    Write one pulled batch: upsert each message, checkpoint, then acknowledge the messages that were written.
    A message that cannot be parsed is left unacknowledged with its extended lease, so Pub/Sub redelivers it once the
    lease expires, normally in a later sync, rather than straight back into this one.
    Args:
        client: the Pub/Sub client.
        received_messages: the pulled ReceivedMessage objects.
        message_count: how many messages this sync has processed before this batch.
        configuration: the connector configuration.
        state: the connector state.
    Returns:
        A tuple of the updated message count and the publish times of the messages that were written.
    """
    pubsub_client.extend_ack_deadline(
        client, [received.ack_id for received in received_messages], __ACK_DEADLINE_SECONDS
    )
    written = []
    for received in received_messages:
        message_count += 1
        message = received.message
        try:
            table, row = message_parser.build_row(
                message.data.decode("utf-8"),
                message.message_id,
                message.publish_time,
                message_count,
                configuration,
            )
        except (message_parser.MessageParseError, UnicodeDecodeError) as error:
            log.warning(f"Error processing message {message.message_id}: {error}")
            continue
        row = {key: message_parser.to_destination_value(value) for key, value in row.items()}

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table or configuration["subscription_id"], data=row)
        written.append(received)

    if not written:
        return message_count, []

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)

    # The checkpoint has returned, so the rows are committed and the messages can be acknowledged.
    pubsub_client.acknowledge(client, [received.ack_id for received in written])
    return message_count, [received.message.publish_time for received in written]


def save_snapshot(client, state: dict, previous_snapshot):
    """
    Take a snapshot of the subscription after the last acknowledgement and record it in the state. The next sync
    seeks back to it, replaying any message acknowledged by a sync that fails later. The snapshot alternates between
    two slots, and the previous snapshot is deleted only once the state naming the new one has been checkpointed.
    Args:
        client: the Pub/Sub client.
        state: the connector state.
        previous_snapshot: the snapshot named in the state at the start of this sync, or None.
    """
    slot = next_snapshot_slot(previous_snapshot)
    new_snapshot = create_snapshot_recreating(client, pubsub_client.snapshot_name(client, slot))
    if new_snapshot is not None:
        state["pubsub_snapshot_name"] = new_snapshot
    state["checkpoint_timestamp"] = datetime.now(timezone.utc).isoformat()

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)

    # The checkpoint has returned, so the state naming the new snapshot is persisted and the old one is not needed.
    if new_snapshot is not None and previous_snapshot not in (None, new_snapshot):
        log.info(f"Removing outdated snapshot: {previous_snapshot}")
        try:
            pubsub_client.delete_snapshot(client, previous_snapshot)
        except google_exceptions.GoogleAPICallError as error:
            log.warning(f"Failed to delete Pub/Sub snapshot {previous_snapshot}: {error}")


def next_snapshot_slot(previous_snapshot):
    """
    Return the slot after the one the previous snapshot used, or slot 0 when there is none.
    Args:
        previous_snapshot: the snapshot named in the state, or None.
    Returns:
        The slot number for the new snapshot.
    """
    if previous_snapshot is not None:
        for slot in range(__MAX_SNAPSHOTS):
            if previous_snapshot.endswith(f"snapshot-{slot}"):
                return (slot + 1) % __MAX_SNAPSHOTS
    return 0


def create_snapshot_recreating(client, name: str):
    """
    Create a snapshot, replacing a leftover snapshot of the same name.
    Args:
        client: the Pub/Sub client.
        name: the snapshot resource name.
    Returns:
        The snapshot name, or None when it could not be created.
    """
    try:
        return pubsub_client.create_snapshot(client, name)
    except google_exceptions.AlreadyExists:
        log.info(f"Snapshot {name} already exists, recreating it")
        try:
            pubsub_client.delete_snapshot(client, name)
            return pubsub_client.create_snapshot(client, name)
        except google_exceptions.GoogleAPICallError as error:
            log.warning(f"Failed to recreate Pub/Sub snapshot {name}: {error}")
            return None


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
