"""Turns AMQP 1.0 messages into destination rows, used by connector.py.

The rules mirror how the Apache Qpid JMS client decides whether a message is a text message and how it renders
message ids, so rows match what a JMS-based consumer of the same queue would produce.
"""

# For parsing JSON payloads and serializing application properties
import json

# For recognising UUID message ids
import uuid

# For converting AMQP timestamps to UTC datetimes
from datetime import datetime, timezone

# For recognising AMQP ulong message ids
from proton import ulong

# The x-opt-jms-msg-type message annotation set by JMS producers, and the JMS class name each value maps to.
__JMS_MESSAGE_TYPE_ANNOTATION = "x-opt-jms-msg-type"
__JMS_TEXT_MESSAGE = 5
__JMS_CLASS_NAMES = {
    0: "org.apache.qpid.jms.message.JmsMessage",
    1: "org.apache.qpid.jms.message.JmsObjectMessage",
    2: "org.apache.qpid.jms.message.JmsMapMessage",
    3: "org.apache.qpid.jms.message.JmsBytesMessage",
    4: "org.apache.qpid.jms.message.JmsStreamMessage",
}
__BYTES_MESSAGE = __JMS_CLASS_NAMES[3]
__OBJECT_MESSAGE = __JMS_CLASS_NAMES[1]
__OCTET_STREAM = "application/octet-stream"
__SERIALIZED_JAVA_OBJECT = "application/x-java-serialized-object"
__TEXTUAL_APPLICATION_SUBTYPES = ("xml", "json", "javascript", "xml-dtd", "ecmascript")
__TEXTUAL_SUBTYPE_SUFFIXES = ("+xml", "+json")
__DEFAULT_CHARSET = "UTF-8"
__ID_PREFIX = "ID:"
__ENCODING_PREFIXES = (
    "AMQP_BINARY:",
    "AMQP_UUID:",
    "AMQP_ULONG:",
    "AMQP_STRING:",
    "AMQP_NO_PREFIX:",
)
__MILLIS_PER_SECOND = 1000
UNPACKED_COLUMN_PREFIX = "value"


class MessageProcessingError(Exception):
    """A message-specific problem, such as a payload that is not valid JSON. The message is skipped, not the sync."""


def symbol_property(value):
    """
    Return a symbol-typed message property, such as content-type, as text. proton reports an absent symbol property
    as the symbol 'None', so that value is treated as absent.
    Args:
        value: the property value from proton.
    Returns:
        The text, or None when the property is absent or empty.
    """
    if value is None or str(value) in ("", "None"):
        return None
    return str(value)


def text_charset(content_type):
    """
    Return the charset to decode a body with when the content type is textual, as Qpid JMS does: text/*,
    application/json, application/xml, application/javascript, application/ecmascript, application/xml-dtd and the
    +json and +xml variants. The charset parameter wins; UTF-8 is the default.
    Args:
        content_type: the AMQP content-type property, or None.
    Returns:
        The charset name, or None when the content type is missing, malformed or not textual.
    """
    if content_type is None or not str(content_type).strip() or "/" not in str(content_type):
        return None
    main_type, _, rest = str(content_type).partition("/")
    main_type = main_type.lower().strip()
    sub_type, _, parameters = rest.lower().partition(";")
    sub_type = sub_type.strip()
    if not sub_type:
        return None
    is_textual_application = sub_type in __TEXTUAL_APPLICATION_SUBTYPES or sub_type.endswith(
        __TEXTUAL_SUBTYPE_SUFFIXES
    )
    if main_type != "text" and not (main_type == "application" and is_textual_application):
        return None
    for parameter in parameters.split(";"):
        name, separator, value = parameter.strip().partition("=")
        if separator and name.strip() == "charset":
            value = value.strip()
            if len(value) > 1 and value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return value.upper()
    return __DEFAULT_CHARSET


def body_kind(message):
    """
    Classify a message the way Qpid JMS does when it builds a JMS message. The x-opt-jms-msg-type annotation wins;
    otherwise the body section and the content type decide. proton reports a Data section as inferred bytes, an
    AmqpSequence as an inferred list, and an AmqpValue as any other value.
    Args:
        message: the received proton message.
    Returns:
        A tuple of ("text", charset) for text messages, or ("other", JMS class name) for everything else.
    """
    annotations = message.annotations or {}
    annotated_type = annotations.get(__JMS_MESSAGE_TYPE_ANNOTATION)
    if annotated_type is not None:
        if int(annotated_type) == __JMS_TEXT_MESSAGE:
            return "text", __DEFAULT_CHARSET
        return "other", __JMS_CLASS_NAMES.get(int(annotated_type), __JMS_CLASS_NAMES[0])
    body = message.body
    content_type = symbol_property(message.content_type)
    if body is None or isinstance(body, str):
        # proton cannot tell an AmqpValue(null) body from a missing body, so both are null-text messages here.
        return "text", __DEFAULT_CHARSET
    if isinstance(body, (bytes, memoryview)):
        if not message.inferred:
            return "other", __BYTES_MESSAGE
        if content_type in (None, __OCTET_STREAM):
            return "other", __BYTES_MESSAGE
        if content_type == __SERIALIZED_JAVA_OBJECT:
            return "other", __OBJECT_MESSAGE
        charset = text_charset(content_type)
        return ("text", charset) if charset else ("other", __BYTES_MESSAGE)
    return "other", __OBJECT_MESSAGE


def message_text(message, charset: str):
    """
    Return the text of a text message: the string value, the Data section decoded with the charset, or None.
    Args:
        message: the received proton message.
        charset: the charset from body_kind().
    Returns:
        The text, or None for a null body.
    Raises:
        MessageProcessingError: if the Data section cannot be decoded with the charset.
        ValueError: if an annotated text message carries a body that is not text, as Qpid JMS fails on it too.
    """
    body = message.body
    if body is None or isinstance(body, str):
        return body
    if isinstance(body, (bytes, memoryview)) and message.inferred:
        try:
            return bytes(body).decode(charset)
        except (UnicodeDecodeError, LookupError) as error:
            raise MessageProcessingError(f"Cannot decode String in {charset}: {error}") from error
    raise ValueError(f"Unexpected message body type for a text message: {type(body).__name__}")


def message_id_text(value, is_correlation_id: bool = False):
    """
    Render a message-id or correlation-id the way Qpid JMS renders JMSMessageID and JMSCorrelationID. Non-string ids
    get a type prefix; a message-id string without the ID: prefix gets ID:AMQP_NO_PREFIX:, while a correlation-id
    string is kept as-is.
    Args:
        value: the AMQP id: str, UUID, ulong or binary, or None.
        is_correlation_id: True for a correlation-id, which is not prefixed when it is a plain string.
    Returns:
        The id text, or None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if not value.startswith(__ID_PREFIX):
            return value if is_correlation_id else f"{__ID_PREFIX}AMQP_NO_PREFIX:{value}"
        if value[len(__ID_PREFIX) :].startswith(__ENCODING_PREFIXES):
            return f"{__ID_PREFIX}AMQP_STRING:{value}"
        return value
    if isinstance(value, uuid.UUID):
        return f"{__ID_PREFIX}AMQP_UUID:{value}"
    if isinstance(value, (ulong, int)):
        return f"{__ID_PREFIX}AMQP_ULONG:{int(value)}"
    if isinstance(value, (bytes, memoryview)):
        return f"{__ID_PREFIX}AMQP_BINARY:{bytes(value).hex().upper()}"
    return str(value)


def created_time(message):
    """
    Return the creation-time property as a UTC datetime with millisecond precision.
    Args:
        message: the received proton message.
    Returns:
        The datetime, or None when the producer did not set a creation time.
    """
    milliseconds = round((message.creation_time or 0) * __MILLIS_PER_SECOND)
    if milliseconds == 0:
        return None
    return datetime.fromtimestamp(milliseconds / __MILLIS_PER_SECOND, tz=timezone.utc)


def iso_text(moment):
    """
    Format a UTC datetime as ISO 8601 with milliseconds and a Z suffix.
    Args:
        moment: the datetime, or None.
    Returns:
        The text, or None.
    """
    if moment is None:
        return None
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def metadata_columns(message, event_id: str, creation_time):
    """
    Return the metadata columns every row carries, read from the AMQP properties and application-properties sections.
    Args:
        message: the received proton message.
        event_id: the primary key generated for this row.
        creation_time: the creation time from created_time(), or None.
    Returns:
        A dictionary of column name to value.
    """
    user_id = bytes(message.user_id).decode("utf-8", errors="replace") if message.user_id else None
    expiry_milliseconds = round((message.expiry_time or 0) * __MILLIS_PER_SECOND)
    application_properties = message.properties or {}
    return {
        "event_id": event_id,
        "message_id": message_id_text(message.id),
        "user_id": user_id,
        "to": message.address or None,
        "subject": message.subject or None,
        "reply_to": message.reply_to or None,
        "correlation_id": message_id_text(message.correlation_id, is_correlation_id=True),
        "content_type": symbol_property(message.content_type),
        "content_encoding": symbol_property(message.content_encoding),
        "absolute_expiry_time": expiry_milliseconds or None,
        "created_time": iso_text(creation_time),
        "group_id": message.group_id or None,
        # proton reports an absent group-sequence as 0, so 0 is treated as absent.
        "group_sequence": message.group_sequence or None,
        "reply_to_group_id": message.reply_to_group_id or None,
        "application_properties": (
            json.dumps(dict(application_properties), default=str)
            if application_properties
            else None
        ),
    }


def reject_constant(name: str):
    """
    Reject NaN and Infinity, which are not valid JSON and which Jackson also refuses.
    Args:
        name: the non-standard constant found in the payload.
    Raises:
        ValueError: always.
    """
    raise ValueError(f"Non-standard JSON constant: {name}")


def packed_json(payload):
    """
    Parse a payload for the data column of JSON Packed mode. An empty payload stays an empty JSON string.
    Args:
        payload: the message text, or None.
    Returns:
        The parsed JSON value, or None for a null body.
    Raises:
        MessageProcessingError: if the payload is not valid JSON.
    """
    if payload is None or payload == "":
        return payload
    try:
        return json.loads(payload, parse_constant=reject_constant)
    except ValueError as error:
        raise MessageProcessingError(f"Payload is not valid JSON: {error}") from error


def unpacked_json(payload: str):
    """
    Parse a payload for JSON Unpacked mode: one value_<field> column per first-level field of a JSON object.
    Args:
        payload: the message text.
    Returns:
        A dictionary of column name to value, or None when the payload is not a JSON object and must fall back to
        packed mode.
    """
    if payload == "":
        return {}
    try:
        parsed = json.loads(payload, parse_constant=reject_constant)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {f"{UNPACKED_COLUMN_PREFIX}_{key}": value for key, value in parsed.items()}
