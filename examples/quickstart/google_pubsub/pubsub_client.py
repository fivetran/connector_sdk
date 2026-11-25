"""Google Cloud Pub/Sub calls used by connector.py: pulling, acknowledging and snapshot management.

Messages are pulled with the synchronous Pull RPC rather than streaming pull, so that an acknowledge
call has reached Pub/Sub when it returns. The connector relies on that ordering: rows are checkpointed
first, then the messages are acknowledged, then a snapshot of the subscription is taken.
"""

# For parsing the service account key from the configuration
import json

# For holding the Pub/Sub client together with the resource names it works on
from dataclasses import dataclass

# For the errors the Pub/Sub API raises
from google.api_core import exceptions as google_exceptions

# For authenticating with the service account key
from google.oauth2 import service_account

# For calling the Resource Manager API to test project-level IAM permissions
from google.auth.transport.requests import AuthorizedSession

# For the Pub/Sub subscriber client
from google.cloud import pubsub_v1

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

__PUBSUB_SCOPE = "https://www.googleapis.com/auth/pubsub"
__CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
__RESOURCE_MANAGER_URL = (
    "https://cloudresourcemanager.googleapis.com/v3/projects/{}:testIamPermissions"
)
__SERVICE_ACCOUNT_TYPE = "service_account"
__HTTP_TIMEOUT_SECONDS = 30

CONSUME_PERMISSION = "pubsub.subscriptions.consume"
SNAPSHOT_PERMISSIONS = [
    "pubsub.snapshots.create",
    "pubsub.snapshots.delete",
    "pubsub.snapshots.seek",
]


@dataclass
class PubsubClient:
    """A Pub/Sub subscriber client bound to one project and subscription."""

    subscriber: pubsub_v1.SubscriberClient
    project_id: str
    subscription_id: str
    subscription_path: str


def parse_service_account_key(key_content: str):
    """
    Parse and validate a service account key. Only keys of type service_account are accepted, which
    rules out external account credentials that would read a local file.
    Args:
        key_content: the JSON content of the service account key.
    Returns:
        The parsed key as a dictionary.
    Raises:
        ValueError: if the key is not valid JSON or is not a service account key.
    """
    try:
        key = json.loads(key_content)
    except ValueError as error:
        raise ValueError("Provided service account key is not valid JSON.") from error
    if not isinstance(key, dict) or key.get("type") != __SERVICE_ACCOUNT_TYPE:
        raise ValueError("Provided service account key must have type 'service_account'.")
    return key


def create_client(project_id: str, subscription_id: str, key_content: str):
    """
    Create a Pub/Sub subscriber client authenticated with the service account key.
    Args:
        project_id: the Google Cloud project that owns the subscription.
        subscription_id: the subscription to consume.
        key_content: the JSON content of the service account key.
    Returns:
        A PubsubClient.
    """
    credentials = service_account.Credentials.from_service_account_info(
        parse_service_account_key(key_content), scopes=[__PUBSUB_SCOPE]
    )
    subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
    return PubsubClient(
        subscriber=subscriber,
        project_id=project_id,
        subscription_id=subscription_id,
        subscription_path=subscriber.subscription_path(project_id, subscription_id),
    )


def pull(client: PubsubClient, max_messages: int, timeout_seconds: int):
    """
    Pull up to max_messages messages. An empty subscription can make the RPC run out its deadline,
    which is treated as an empty batch.
    Args:
        client: the Pub/Sub client.
        max_messages: the largest batch to return.
        timeout_seconds: how long to wait for messages.
    Returns:
        A list of ReceivedMessage objects.
    """
    try:
        response = client.subscriber.pull(
            request={"subscription": client.subscription_path, "max_messages": max_messages},
            timeout=timeout_seconds,
        )
    except google_exceptions.DeadlineExceeded:
        return []
    return list(response.received_messages)


def extend_ack_deadline(client: PubsubClient, ack_ids: list, seconds: int):
    """
    Extend the ack deadline of pulled messages so they are not redelivered while their rows are
    written and checkpointed.
    Args:
        client: the Pub/Sub client.
        ack_ids: the ack ids of the messages.
        seconds: the new deadline, counted from now.
    """
    if ack_ids:
        client.subscriber.modify_ack_deadline(
            request={
                "subscription": client.subscription_path,
                "ack_ids": ack_ids,
                "ack_deadline_seconds": seconds,
            }
        )


def acknowledge(client: PubsubClient, ack_ids: list):
    """
    Acknowledge messages, so Pub/Sub does not deliver them again. The call returns once Pub/Sub has
    accepted the acknowledgement.
    Args:
        client: the Pub/Sub client.
        ack_ids: the ack ids of the messages.
    """
    if ack_ids:
        client.subscriber.acknowledge(
            request={"subscription": client.subscription_path, "ack_ids": ack_ids}
        )


def snapshot_name(client: PubsubClient, slot: int):
    """
    Return the resource name of one of the connector's snapshot slots.
    Args:
        client: the Pub/Sub client.
        slot: the snapshot slot number.
    Returns:
        The snapshot resource name, e.g. projects/p/snapshots/sub_snapshot-0.
    """
    return f"projects/{client.project_id}/snapshots/{client.subscription_id}_snapshot-{slot}"


def create_snapshot(client: PubsubClient, name: str):
    """
    Create a snapshot of the subscription's acknowledgement state.
    Args:
        client: the Pub/Sub client.
        name: the snapshot resource name.
    Returns:
        The snapshot name, or None when Pub/Sub refused for a reason other than the name being taken.
    Raises:
        google_exceptions.AlreadyExists: if a snapshot with that name already exists.
    """
    try:
        client.subscriber.create_snapshot(
            request={"name": name, "subscription": client.subscription_path}
        )
    except google_exceptions.AlreadyExists:
        raise
    except google_exceptions.GoogleAPICallError as error:
        log.warning(f"Snapshot creation failed for {name}: {error}")
        return None
    log.info(f"Created Pub/Sub snapshot: {name}")
    return name


def delete_snapshot(client: PubsubClient, name: str):
    """
    Delete a snapshot. A snapshot that no longer exists counts as deleted.
    Args:
        client: the Pub/Sub client.
        name: the snapshot resource name.
    Raises:
        google_exceptions.GoogleAPICallError: if deletion fails for another reason.
    """
    try:
        client.subscriber.delete_snapshot(request={"snapshot": name})
    except google_exceptions.NotFound:
        log.warning(f"Pub/Sub snapshot already gone: {name}")
        return
    log.info(f"Deleted Pub/Sub snapshot: {name}")


def seek_to_snapshot(client: PubsubClient, name: str):
    """
    Seek the subscription back to a snapshot, so messages acknowledged after it are delivered again.
    A snapshot that is missing or expired is skipped and the sync continues from the current position.
    Args:
        client: the Pub/Sub client.
        name: the snapshot resource name.
    Raises:
        google_exceptions.GoogleAPICallError: if seeking fails for another reason.
    """
    try:
        client.subscriber.seek(
            request={"subscription": client.subscription_path, "snapshot": name}
        )
    except google_exceptions.NotFound:
        log.warning(f"Pub/Sub snapshot not found or expired, proceeding without seek: {name}")
        return
    log.info(f"Sought subscription to snapshot: {name}")


def granted_subscription_permissions(client: PubsubClient, permissions: list):
    """
    Return which of the given permissions the service account holds on the subscription.
    Args:
        client: the Pub/Sub client.
        permissions: the permissions to test.
    Returns:
        The list of granted permissions.
    """
    response = client.subscriber.test_iam_permissions(
        request={"resource": client.subscription_path, "permissions": permissions}
    )
    return list(response.permissions)


def granted_project_permissions(project_id: str, key_content: str, permissions: list):
    """
    Return which of the given permissions the service account holds on the project, using the
    Resource Manager testIamPermissions method. Snapshot permissions are granted at project level.
    Args:
        project_id: the Google Cloud project.
        key_content: the JSON content of the service account key.
        permissions: the permissions to test.
    Returns:
        The list of granted permissions.
    """
    credentials = service_account.Credentials.from_service_account_info(
        parse_service_account_key(key_content), scopes=[__CLOUD_PLATFORM_SCOPE]
    )
    response = AuthorizedSession(credentials).post(
        __RESOURCE_MANAGER_URL.format(project_id),
        json={"permissions": permissions},
        timeout=__HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("permissions", [])
