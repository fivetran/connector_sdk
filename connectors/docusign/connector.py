"""
This connector extracts data from Docusign eSignature API to enable
analytics for Sales, Legal and other departments and teams.
See the Technical Reference documentation:
https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
and the Best Practices documentation:
https://fivetran.com/docs/connectors/connector-sdk/best-practices
for details.
"""

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP API requests to Docusign (provided by SDK runtime)
import requests

# For handling date and time operations
from datetime import datetime, timezone

# For type hints
from typing import Any, Dict, List, Optional

# For encoding binary data of documents to base64
import base64

# For reading configuration from a JSON file
import json

# For handling retries and delays
import time

__DEFAULT_START_DATE = "2020-01-01T00:00:00.000Z"
__REQUEST_TIMEOUT_SECONDS = 30
__DOCUMENT_TIMEOUT_SECONDS = 60
__BATCH_SIZE = 100
__MAX_RETRIES = 3
__RETRY_DELAY_SECONDS = 2
__CHECKPOINT_INTERVAL = 10
__MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB file fetch limit


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["access_token", "base_url", "account_id"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your
    connector delivers.
    See the technical reference documentation for more details on the schema
    function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for
        the connector.
    """
    return [
        {
            "table": "envelopes",
            "primary_key": ["envelope_id"],
        },
        {
            "table": "recipients",
            "primary_key": ["envelope_id", "recipient_id"],
        },
        {
            "table": "enhanced_recipients",
            "primary_key": ["envelope_id", "recipient_id"],
        },
        {
            "table": "audit_events",
            "primary_key": ["envelope_id", "event_id"],
        },
        {
            "table": "envelope_notifications",
            "primary_key": ["envelope_id", "notification_id"],
        },
        {
            "table": "documents",
            "primary_key": ["envelope_id", "document_id"],
        },
        {
            "table": "document_contents",
            "primary_key": ["envelope_id", "document_id"],
        },
        {
            "table": "templates",
            "primary_key": ["template_id"],
        },
        {
            "table": "custom_fields",
            "primary_key": ["envelope_id", "field_name"],
        },
    ]


def get_Docusign_headers(configuration: dict) -> Dict[str, str]:
    """
    Generate authentication headers for Docusign API.
    Uses OAuth2 authentication with access token.
    Args:
        configuration: A dictionary containing the connector configuration.
    Returns:
        A dictionary of HTTP headers for Docusign API requests.
    """
    return {
        "Authorization": f"Bearer {configuration['access_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_base_url(configuration: dict) -> str:
    """
    Construct the base URL for Docusign API calls.
    Uses the account ID and base URL from configuration.
    Args:
        configuration: A dictionary containing the connector configuration.
    Returns:
        The base URL string for Docusign API endpoints.
    """
    return f"{configuration['base_url']}/v2.1/accounts/{configuration['account_id']}"


def make_api_request(
    url: str, headers: Dict[str, str], params: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Make API request to Docusign with retry logic and exponential backoff.
    Args:
        url: The API endpoint URL
        headers: Request headers including authentication
        params: Query parameters for the request
    Returns:
        Dictionary containing the API response
    Raises:
        RuntimeError: if API request fails after all retries
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.warning(f"API request failed (attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                # Exponential backoff strategy
                delay = __RETRY_DELAY_SECONDS * (2**attempt)
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Failed to make API request after {__MAX_RETRIES} attempts: {str(e)}"
                )

    raise RuntimeError(f"Failed to make API request after {__MAX_RETRIES} attempts")


def fetch_document_content(
    configuration: dict, envelope_id: str, document_id: str
) -> Optional[bytes]:
    """
    Fetch the binary content of a specific document.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
        document_id: The ID of the document.
    Returns:
        The binary content of the document, or None if failed.
    """
    base_url = get_base_url(configuration)
    # Use a modified header that doesn't demand JSON in response
    headers = {"Authorization": f"Bearer {configuration['access_token']}"}
    url = f"{base_url}/envelopes/{envelope_id}/documents/{document_id}"

    for attempt in range(__MAX_RETRIES):
        try:
            with requests.get(
                url, headers=headers, stream=True, timeout=__DOCUMENT_TIMEOUT_SECONDS
            ) as response:
                response.raise_for_status()

                #  Check Content-Length header before downloading
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > __MAX_FILE_SIZE_BYTES:
                    log.warning(
                        f"Skipping document {document_id}: Header size ({content_length} bytes) exceeds limit."
                    )
                    return None

                #  Read in chunks to monitor accumulation
                content = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    content.extend(chunk)
                    # Stop downloading if we cross the threshold
                    if len(content) > __MAX_FILE_SIZE_BYTES:
                        log.warning(
                            f"Skipping document {document_id}: Streamed size exceeds limit."
                        )
                        return None

                return bytes(content)
        except requests.exceptions.RequestException as e:
            log.warning(f"API request failed (attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                # Exponential backoff strategy
                delay = __RETRY_DELAY_SECONDS * (2**attempt)
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Failed to make API request after {__MAX_RETRIES} attempts: {str(e)}"
                )

    raise RuntimeError(f"Failed to make API request after {__MAX_RETRIES} attempts")


def fetch_envelopes(configuration: dict, state: Dict[str, Any]):
    """
    Fetch envelopes data with incremental sync support.
    Uses the last_modified_date from state for incremental updates.
    Args:
        configuration: A dictionary containing the connector configuration.
        state: A dictionary containing state information.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)

    params = {
        "from_date": state.get("last_sync_time", __DEFAULT_START_DATE),
        "count": __BATCH_SIZE,
    }

    start_position = 0
    total_count = 0

    while True:
        params["start_position"] = start_position
        url = f"{base_url}/envelopes"

        try:
            data = make_api_request(url, headers, params)
            envelopes = data.get("envelopes", [])

            if not envelopes:
                break

            for envelope in envelopes:
                yield envelope

            total_count += len(envelopes)
            start_position += len(envelopes)

            if len(envelopes) < params["count"]:
                break

        except requests.exceptions.HTTPError as exc:
            if exc.response.status_code == 401:  # Check specifically for a 401 Unauthorized error
                log.error(
                    "Received 401 Unauthorized. Access token is likely expired. Aborting fetch."
                )
                break
            else:
                log.error(f"Failed to fetch envelopes with HTTP error: {exc}")
                break

        except Exception as exc:
            log.error(f"Failed to fetch envelopes: {exc}")
            raise RuntimeError(f"Failed to fetch envelopes: {exc}")

    log.info(f"Fetched {total_count} envelopes")


def fetch_audit_events(configuration: dict, envelope_id: str) -> List[Dict[str, Any]]:
    """
    Fetch envelope audit events for SLA, deviation, and workflow tracking.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    Returns:
        A list of dictionaries representing audit events.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)
    url = f"{base_url}/envelopes/{envelope_id}/audit_events"

    try:
        data = make_api_request(url, headers)
        events = data.get("auditEvents", [])
        for event in events:
            event["envelope_id"] = envelope_id
        return events
    except Exception as exc:
        log.warning(f"Could not fetch audit events for envelope {envelope_id}: {exc}")
        return []


def fetch_envelope_notifications(configuration: dict, envelope_id: str) -> List[Dict[str, Any]]:
    """
    Fetch envelope notifications like reminders and expirations.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    Returns:
        A list of dictionaries representing envelope notifications.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)
    url = f"{base_url}/envelopes/{envelope_id}/notification"

    try:
        data = make_api_request(url, headers)
        notifications = data.get("notifications", [])
        for n in notifications:
            n["envelope_id"] = envelope_id
        return notifications
    except Exception as exc:
        log.warning(f"Could not fetch notifications for envelope {envelope_id}: {exc}")
        return []


def fetch_recipients_for_envelope(configuration: dict, envelope_id: str) -> List[Dict[str, Any]]:
    """
    Fetch recipients data for a specific envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    Returns:
        A list of dictionaries representing recipients.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)
    url = f"{base_url}/envelopes/{envelope_id}/recipients"

    try:
        data = make_api_request(url, headers)
        recipients: List[Dict[str, Any]] = []

        for recipient_type in [
            "signers",
            "carbon_copies",
            "certified_deliveries",
            "in_person_signers",
        ]:
            type_recipients = data.get(recipient_type, [])
            for recipient in type_recipients:
                recipient["recipient_type"] = recipient_type
                recipient["envelope_id"] = envelope_id
                recipients.append(recipient)

        return recipients
    except Exception as exc:
        log.warning(f"Could not fetch recipients for envelope {envelope_id}: {exc}")
        return []


def fetch_documents_for_envelope(configuration: dict, envelope_id: str) -> List[Dict[str, Any]]:
    """
    Fetch documents data for a specific envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    Returns:
        A list of dictionaries representing documents.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)
    url = f"{base_url}/envelopes/{envelope_id}/documents"

    try:
        data = make_api_request(url, headers)
        documents = data.get("envelopeDocuments", [])

        for document in documents:
            document["envelope_id"] = envelope_id

        return documents
    except Exception as exc:
        log.warning(f"Could not fetch documents for envelope {envelope_id}: {exc}")
        return []


def fetch_templates(configuration: dict, state: Dict[str, Any]):
    """
    Fetch templates data for standard template usage tracking.
    Uses incremental sync by filtering templates modified after last_sync_time.
    Args:
        configuration: A dictionary containing the connector configuration.
        state: A dictionary containing state information.
    Returns:
        A generator yielding dictionaries representing templates.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)
    url = f"{base_url}/templates"
    params = {"count": __BATCH_SIZE}

    start_position = 0
    last_sync_time = state.get("last_sync_time", __DEFAULT_START_DATE)

    while True:
        params["start_position"] = start_position

        try:
            data = make_api_request(url, headers, params)
            templates = data.get("envelopeTemplates", [])

            if not templates:
                break

            # Filter templates that have been modified since last sync
            for template in templates:
                last_modified = template.get("lastModified", "")
                if last_modified:
                    try:
                        modified_dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                        sync_dt = datetime.fromisoformat(last_sync_time.replace("Z", "+00:00"))
                        if modified_dt > sync_dt:
                            yield template
                    except ValueError:
                        # If parsing fails, include the template to be safe
                        yield template

            start_position += len(templates)

            if len(templates) < params["count"]:
                break

        except requests.exceptions.HTTPError as exc:
            if exc.response.status_code == 401:  # Check specifically for a 401 Unauthorized error
                log.error(
                    "Received 401 Unauthorized. Access token is likely expired. Aborting fetch."
                )
                break
            else:
                log.error(f"Failed to fetch templates with HTTP error: {exc}")
                break

        except Exception as exc:
            log.error(
                f"Failed to fetch templates: {exc}"
            )  # If a non-HTTP exception occurs, break the loop to avoid infinite calls
            raise RuntimeError(f"Failed to fetch templates: {exc}")


def fetch_custom_fields_for_envelope(
    configuration: dict, envelope_id: str
) -> List[Dict[str, Any]]:
    """
    Fetch custom fields for a specific envelope such as envelope type.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    Returns:
        A list of dictionaries representing custom fields.
    """
    base_url = get_base_url(configuration)
    headers = get_Docusign_headers(configuration)
    url = f"{base_url}/envelopes/{envelope_id}/custom_fields"

    try:
        data = make_api_request(url, headers)
        custom_fields = data.get("textCustomFields", []) + data.get("listCustomFields", [])

        for field in custom_fields:
            field["envelope_id"] = envelope_id

        return custom_fields
    except Exception as exc:
        log.warning(f"Could not fetch custom fields for envelope {envelope_id}: {exc}")
        return []


def _upsert_recipients(configuration: dict, envelope_id: str):
    """
    Fetch and upsert recipients for a given envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    """
    recipients = fetch_recipients_for_envelope(configuration, envelope_id)
    for r in recipients:
        if r.get("recipientId"):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(
                "recipients",
                {
                    "envelope_id": str(envelope_id),
                    "recipient_id": str(r["recipientId"]),
                    "name": str(r.get("name", "")),
                    "email": str(r.get("email", "")),
                    "status": str(r.get("status", "")),
                    "type": str(r.get("recipient_type", "")),
                    "routing_order": str(r.get("routingOrder", "0")),
                },
            )


def _upsert_enhanced_recipients(configuration: dict, envelope_id: str):
    """
    Fetch and upsert enhanced recipients for a given envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    """
    enhanced_recipients = fetch_recipients_for_envelope(configuration, envelope_id)
    for er in enhanced_recipients:
        if er.get("recipientId"):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(
                "enhanced_recipients",
                {
                    "envelope_id": str(envelope_id),
                    "recipient_id": str(er["recipientId"]),
                    "name": str(er.get("name", "")),
                    "email": str(er.get("email", "")),
                    "status": str(er.get("status", "")),
                    "type": str(er.get("recipient_type", "")),
                    "routing_order": str(er.get("routingOrder", 0)),
                    "declined_reason": str(er.get("declinedReason", "")),
                    "sent_timestamp": str(er.get("sentDateTime", "")),
                    "signed_timestamp": str(er.get("signedDateTime", "")),
                },
            )


def _upsert_audit_events(configuration: dict, envelope_id: str):
    """
    Fetch and upsert audit events for a given envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    """
    audit_events = fetch_audit_events(configuration, envelope_id)
    for event in audit_events:
        # Flatten eventFields into a dict
        flat_event = {
            field["name"].lower(): str(field.get("value", ""))
            for field in event.get("eventFields", [])
        }

        flat_event["envelope_id"] = envelope_id
        # Use a combination of envelope_id + logTime as a surrogate primary key
        flat_event["event_id"] = f"{envelope_id}_{flat_event.get('logtime', '')}"
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted.
        op.upsert("audit_events", flat_event)


def _upsert_envelope_notifications(configuration: dict, envelope_id: str):
    """
    Fetch and upsert envelope notifications for a given envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    """
    notifications = fetch_envelope_notifications(configuration, envelope_id)
    for n in notifications:
        if n.get("notificationId"):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(
                "envelope_notifications",
                {
                    "envelope_id": str(envelope_id),
                    "notification_id": str(n.get("notificationId")),
                    "notification_type": str(n.get("notificationType", "")),
                    "scheduled_date": str(n.get("scheduledDate", "")),
                    "sent_date": str(n.get("sentDate", "")),
                },
            )


def _upsert_documents_and_content(configuration: dict, envelope_id: str):
    """
    Fetch and upsert documents and their content for a given envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    """
    documents = fetch_documents_for_envelope(configuration, envelope_id)
    for d in documents:
        document_id = d.get("documentId")
        if document_id:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(
                "documents",
                {
                    "envelope_id": str(envelope_id),
                    "document_id": str(document_id),
                    "name": str(d.get("name", "")),
                    "type": str(d.get("type", "")),
                    "pages": str(d.get("pages", "0")),
                },
            )

            log.info(f"Fetching content for document {document_id} in envelope {envelope_id}")
            content = fetch_document_content(configuration, envelope_id, document_id)
            if content:
                # Content is stored as a Base64 encoded string to handle binary data safely.
                encoded_content = base64.b64encode(content).decode("utf-8")
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted.
                op.upsert(
                    "document_contents",
                    {
                        "envelope_id": str(envelope_id),
                        "document_id": str(document_id),
                        "content_base64": encoded_content,
                    },
                )


def _upsert_custom_fields(configuration: dict, envelope_id: str):
    """
    Fetch and upsert custom fields for a given envelope.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope_id: The ID of the envelope.
    """
    custom_fields = fetch_custom_fields_for_envelope(configuration, envelope_id)
    for f in custom_fields:
        if f.get("name"):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(
                "custom_fields",
                {
                    "envelope_id": str(envelope_id),
                    "field_name": str(f["name"]),
                    "value": str(f.get("value", "")),
                    "type": str(f.get("fieldType", "")),
                },
            )


def _process_envelope(configuration: dict, envelope: Dict[str, Any]):
    """
    Process a single envelope and its related data.
    Args:
        configuration: A dictionary containing the connector configuration.
        envelope: A dictionary containing envelope data from the API.
    """
    envelope_id = envelope.get("envelopeId")
    if not envelope_id:
        log.warning("Skipping an envelope record due to missing envelopeId.")
        return

    processed_envelope = {
        "envelope_id": str(envelope_id),
        "status": str(envelope.get("status", "")),
        "sent_timestamp": str(envelope.get("sentDateTime", "")),
        "completed_timestamp": str(envelope.get("completedDateTime", "")),
        "created_timestamp": str(envelope.get("createdDateTime", "")),
        "last_modified_timestamp": str(envelope.get("statusChangedDateTime", "")),
        "subject": str(envelope.get("emailSubject", "")),
        "expire_after": str(envelope.get("expireAfter", "")),
        "contract_cycle_time_hours": "",
    }

    if envelope.get("status") == "completed":
        sent_time = envelope.get("sentDateTime")
        completed_time = envelope.get("completedDateTime")
        if sent_time and completed_time:
            try:
                sent_dt = datetime.fromisoformat(sent_time.replace("Z", "+00:00"))
                completed_dt = datetime.fromisoformat(completed_time.replace("Z", "+00:00"))
                cycle_time = (completed_dt - sent_dt).total_seconds() / 3600
                processed_envelope["contract_cycle_time_hours"] = str(cycle_time)
            except Exception as exc:
                log.warning(f"Could not calculate cycle time for envelope {envelope_id}: {exc}")

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The op.upsert method is called with two arguments:
    # - The first argument is the name of the table to upsert the data into.
    # - The second argument is a dictionary containing the data to be upserted.
    op.upsert("envelopes", processed_envelope)

    # --- Fetch and Process Child Tables ---
    _upsert_recipients(configuration, envelope_id)
    _upsert_enhanced_recipients(configuration, envelope_id)
    _upsert_audit_events(configuration, envelope_id)
    _upsert_envelope_notifications(configuration, envelope_id)
    _upsert_documents_and_content(configuration, envelope_id)
    _upsert_custom_fields(configuration, envelope_id)


def _process_templates(configuration: dict, state: Dict[str, Any]):
    """
    Fetch and process templates.
    Args:
        configuration: A dictionary containing the connector configuration.
        state: A dictionary containing state information.
    """
    log.info("Fetching templates data...")
    template_count = 0
    for t in fetch_templates(configuration, state):
        if t.get("templateId"):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted.
            op.upsert(
                "templates",
                {
                    "template_id": str(t["templateId"]),
                    "name": str(t.get("name", "")),
                    "description": str(t.get("description", "")),
                    "created_timestamp": str(t.get("created", "")),
                    "last_modified_timestamp": str(t.get("lastModified", "")),
                    "shared": str(t.get("shared", "false")).lower(),
                },
            )
            template_count += 1
    log.info(f"Upserted {template_count} templates")


def update(configuration: dict, state: Dict[str, Any]):
    """
    Define the update function, which is a required function, and is called by
    Fivetran during each sync.
    See the technical reference documentation for more details on the update
    function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing Docusign API connection details
        state: A dictionary containing state information from previous runs
    """
    log.warning("Example: Source Examples - Docusign: eSignature API Connector")
    validate_configuration(configuration)
    try:
        if not state:
            state = {"last_sync_time": __DEFAULT_START_DATE}

        current_time = datetime.now(timezone.utc).isoformat()

        # --- Process Envelopes and Related Data ---
        log.info(f"Fetching envelopes data at {current_time}")
        envelopes_generator = fetch_envelopes(configuration, state)
        envelope_count = 0

        for envelope in envelopes_generator:
            _process_envelope(configuration, envelope)
            envelope_count += 1
            if envelope_count % __CHECKPOINT_INTERVAL == 0:
                log.info(f"Processed {envelope_count} envelopes, checkpointing state.")
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)

        log.info(f"Total processed envelopes: {envelope_count}")
        # --- Process Templates ---
        _process_templates(configuration, state)

        # Update state with the current sync time for the next run
        new_state = {"last_sync_time": str(current_time)}
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(new_state)

    except Exception as exc:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(exc)}")

    log.info("Docusign connector update completed successfully")


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
