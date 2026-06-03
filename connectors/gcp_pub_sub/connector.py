# This is an example for how to work with the fivetran_connector_sdk module.
# It defines a simple 'update' method, which upserts some data to a table from gcp PubSub.
# It creates a test topic, publishes some test messages, creates a test subscription, pulls messages from the subscription, and upserts them to the destination.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required classes from google cloud pubsub
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from google.api_core.exceptions import AlreadyExists, NotFound
import json
import time


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):

    # check if required configuration values are present in configuration
    for key in ["service_key", "topic_name", "subscription_name"]:
        if key not in configuration:
            raise RuntimeError(f"Missing required configuration value : {key}")

    return [
        {
            "table": "sample_table",  # Name of the table in the destination.
            "primary_key": ["key"],  # Primary key column(s) for the table.
            "columns": {  # Define the columns and their data types.
                "key": "STRING",
                "timestamp": "UTC_DATETIME",
            },  # For any columns whose names are not provided here, their data types will be inferred
        }
    ]


def create_sample_topic(credentials, project_id: str, topic_name: str):
    """
    Creates a sample Pub/Sub topic if it doesn't already exist.
    This method is used only for TESTING purposes.
    In actual connectors, topics are already present from which messages are consumed.
    :param credentials: service account credentials
    :param project_id: GCP project ID
    :param topic_name: name of the topic
    :return: Publisher client instance for further use
    :raises RuntimeError: If there's an error creating the topic
    """
    # Create a publisher client and topic path
    publisher = pubsub_v1.PublisherClient(credentials=credentials)

    # Format the topic path using project ID and topic name
    # Topic paths follow the format: projects/{project_id}/topics/{topic_name}
    topic_path = publisher.topic_path(project_id, topic_name)

    try:
        # Attempt to create the topic using the formatted path
        publisher.create_topic(request={"name": topic_path})
        log.info(f"Topic created: {topic_path}")
    # If the topic already exists, an AlreadyExists exception is thrown
    except AlreadyExists:
        # If the topic already exists, log a warning but continue execution
        log.warning(f"Topic path already exists : {topic_path}")
    except Exception as e:
        # If any other error occurs, raise a RuntimeError with details
        raise RuntimeError(f"Error creating topic: {e}")

    # Return the publisher client
    return publisher


def publish_test_messages(publisher, topic_path: str) -> None:
    """
    Publishes 5 messages to the specified Pub/Sub topic.
    Each message contains sample data and a timestamp, formatted as JSON string.
    This method is used only for TESTING purposes.
    In actual connectors, messages would already be published by your application.
    :param publisher: publisher client instance
    :param topic_path: path of the topic
    :raises RuntimeError: If there's an error publishing any message
    """
    # Define the maximum number of test messages to publish
    max_test_messages = 5

    for count in range(max_test_messages):
        # Create a message with incremental data and a fixed timestamp
        # Note: In a real connector, you might use dynamic timestamps and actual data
        message = {"data": f"Message {count + 1}", "timestamp": "2021-09-01T00:00:00Z"}

        # Convert the message dictionary to JSON and encode as UTF-8 bytes
        # Pub/Sub requires message data to be in bytes format
        message_data = json.dumps(message).encode("utf-8")

        try:
            # Publish the message to the topic and get a future
            # The future.result() call waits for the publish operation to complete
            future = publisher.publish(topic_path, message_data)
            log.debug(f"Published message ID: {future.result()}")
        except Exception as e:
            # If publishing fails, raise a RuntimeError with details
            raise RuntimeError(f"Error publishing message: {e}")


def check_subscription(subscriber, subscription_path: str, topic_path: str) -> None:
    """
    Verifies if a subscription exists and creates it if it doesn't.
    :param subscriber: subscriber client instance
    :param subscription_path: path of the subscription
    :param topic_path: path of the topic
    """
    try:
        # Check if the subscription exists by attempting to get it
        subscriber.get_subscription(request={"subscription": subscription_path})
        log.info(f"Subscription {subscription_path} already exists.")
        # If we reach here, the subscription exists (no exception was thrown)
    except NotFound:
        # Create subscription if it doesn't exist
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
        log.info(f"Subscription {subscription_path} created.")
    except Exception as e:
        # If any other error occurs, raise a RuntimeError with details
        raise RuntimeError(f"Error checking subscription: {e}")


def clean_up_resources(publisher, subscriber, subscription_path, topic_path) -> None:
    """
    Cleans up the resources created during the test connector execution
    This method is used only for TESTING purposes.
    In real deployments, topics and subscriptions are meant to persist.
    :param publisher: publisher client instance
    :param subscriber: subscriber client instance
    :param subscription_path: path of the subscription
    :param topic_path: path of the topic
    :raises RuntimeError: If any deletion operations fail
    """
    try:
        # Delete subscription first - topics with active subscriptions cannot be deleted
        subscriber.delete_subscription(request={"subscription": subscription_path})
        log.info(f"Subscription deleted: {subscription_path}")

        # After subscription is deleted, it's safe to delete the topic
        publisher.delete_topic(request={"topic": topic_path})
        log.info(f"Topic deleted: {topic_path}")
    except Exception as e:
        # Any failure in cleanup is raised as a RuntimeError with details
        raise RuntimeError(f"Error deleting resources: {e}")


def set_up_pub_sub(pubsub_creds, project_id, topic_name, subscription_name):
    """
    Set up Google Cloud Pub/Sub resources for the connector
    Args:
        pubsub_creds: credentials for the service account
        project_id: project ID
        topic_name: name of the topic
        subscription_name: subscription name
    Returns:
        publisher: publisher client instance
        subscriber: subscriber client instance
        subscription_path: path of the subscription
        topic_path: path of the topic
    """
    # Create Google Cloud authentication credentials from the service account info
    # For more information on authentication with service accounts, refer the google-cloud documentation:
    # https://google-auth.readthedocs.io/en/master/reference/google.oauth2.service_account.html
    credentials = service_account.Credentials.from_service_account_info(pubsub_creds)
    log.info("Service Account credentials initialized")

    # Initialize publisher client, create topic if needed, and publish sample messages
    # This is only for testing purposes. In actual scenarios, you will not need a publisher client
    # This is because messages are published by your application and consumed by the connector
    publisher = create_sample_topic(
        credentials=credentials, project_id=project_id, topic_name=topic_name
    )

    # Initialize subscriber client to read messages from the topic
    # subscriber client is used to pull messages from the topic/subscription
    subscriber = pubsub_v1.SubscriberClient(credentials=credentials)

    # Construct the fully-qualified paths for topic and subscription
    topic_path = subscriber.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    # Ensure the subscription exists or create it if missing
    check_subscription(
        subscriber=subscriber, subscription_path=subscription_path, topic_path=topic_path
    )

    # Publish sample messages to the topic
    # This is only for testing purposes to provide sample data for the connector
    publish_test_messages(publisher=publisher, topic_path=topic_path)

    return publisher, subscriber, subscription_path, topic_path


def pull_and_upsert_messages(subscriber, subscription_path, max_messages, state):
    """
    Pull messages from the Pub/Sub subscription and upsert them to the destination
    This method processes the messages pulled, upserts them and acknowledges them to remove from the subscription
    To build a connector for your use case, replace the upsert logic with your own data processing logic
    Args:
        subscriber: subscriber client instance
        subscription_path: path of the subscription
        max_messages: maximum number of messages to pull in each batch
        state: state dictionary to checkpoint the progress
    """
    while True:
        # pull messages from the subscription
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": max_messages}
        )
        received_messages = response.received_messages

        # Exit the loop when no messages are returned
        if not received_messages:
            break

        try:
            ack_ids = []
            # Process each message in the batch
            for msg in received_messages:
                ack_ids.append(msg.ack_id)

                # Parse the message payload from JSON and decode from bytes to string
                data = json.loads(msg.message.data.decode("utf-8"))

                # Use the message ID as a unique key for the record
                # This ensures each message can be uniquely identified in the destination
                data["key"] = msg.message.message_id

                # upsert the data to the destination
                op.upsert(table="sample_table", data=data)

            # Acknowledge processed messages to remove them from the subscription
            # This prevents redelivery of already processed messages
            # Only acknowledge if we have ack_ids to acknowledge
            if ack_ids:
                subscriber.acknowledge(
                    request={"subscription": subscription_path, "ack_ids": ack_ids}
                )
                log.info(f"Upserted {len(ack_ids)} rows.")

        except Exception as e:
            raise RuntimeError(f"Error processing messages: {e}")

        # Exit the loop when fewer messages than requested are returned
        # This indicates we've processed all available messages
        if len(received_messages) < max_messages:
            break

    # checkpoint the state
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    # Retrieve the service account credentials from the configuration dictionary
    # The service account credentials should be provided as a JSON string in the `service_key` field of `configuration.json`.
    # Example:
    # { "service_key": "{ \"type\": \"service_account\", \"project_id\": \"your-project-id\", ... }", ... }
    # Ensure the JSON string is properly formatted and escaped.
    service_key = configuration.get("service_key")
    topic_name = configuration.get("topic_name")
    subscription_name = configuration.get("subscription_name")
    # Set a default of 5 messages per batch if not specified in configuration
    max_messages = int(configuration.get("max_messages", 5))

    # Parse the service account credentials JSON string into a Python dictionary
    pubsub_creds = json.loads(service_key)
    # Extract the project ID from the service account credentials
    project_id = pubsub_creds.get("project_id")

    # Validate the service account credentials contains a project ID
    if not project_id:
        raise RuntimeError("Invalid service key : Project ID is missing in the service key")

    # Set up Pub/Sub resources for the connector
    # Publisher client instance is only used for testing purposes to create a sample topic and publish messages
    publisher, subscriber, subscription_path, topic_path = set_up_pub_sub(
        pubsub_creds, project_id, topic_name, subscription_name
    )

    # Add a small delay to allow messages to be available for pulling
    # This prevents empty results when pulling messages too quickly after publishing
    time.sleep(4)

    # Process messages in batches until no more messages are available and upsert them to the destination
    # This pagination approach handles large volumes of messages efficiently
    # To build you own connector, replace the upsert logic in this method with your own data processing logic
    pull_and_upsert_messages(
        subscriber=subscriber,
        subscription_path=subscription_path,
        max_messages=max_messages,
        state=state,
    )

    # Clean up the topic and subscription created during the test sync
    # This is only for testing purposes. In actual connectors, topics and subscriptions are meant to persist
    clean_up_resources(
        publisher=publisher,
        subscriber=subscriber,
        subscription_path=subscription_path,
        topic_path=topic_path,
    )


# This creates the connector object that will use the update function defined in this connector.py file.
# This example does not use the schema() function. If it did, it would need to be included in the connector object definition.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug(configuration=configuration)
