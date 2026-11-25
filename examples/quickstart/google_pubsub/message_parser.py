"""Turns Pub/Sub messages into destination rows, used by connector.py.

A message whose body is a JSON object with a string "table" field and a "data" field is written to
the table it names, with the "data" object as the row. Every other message is written to the table
named after the subscription, holding the raw content, its SHA-256 hash and the publish time; in the
UNPACKED sync format the top-level fields of a JSON body also become columns.
"""

# For hashing message content
import hashlib

# For parsing message bodies; floats are kept as exact decimals
import json

# For keeping the precision of decimal numbers in message bodies
from decimal import Decimal

__TABLE_FIELD = "table"
__DATA_FIELD = "data"
__UNIQUE_ID_FIELD = "unique_id"
__MESSAGE_ID_POSTFIX_DIGITS = 5

SYNC_FORMAT_PACKED = "PACKED"
SYNC_FORMAT_UNPACKED = "UNPACKED"
UNPACKING_LEVEL_ONE = "ONE"
UNPACKING_LEVEL_TWO = "TWO"


class MessageParseError(Exception):
    """A message body that cannot be turned into a row, so the message is returned for redelivery."""


def parse_json(text: str):
    """
    Parse JSON with floats as exact decimals, so a value such as 15000.80 keeps its scale.
    Args:
        text: the JSON text.
    Returns:
        The parsed value.
    Raises:
        ValueError: if the text is not valid JSON.
    """
    return json.loads(text, parse_float=Decimal)


def unique_id(message_id: str, counter: int):
    """
    Return a row id unique within a sync: the Pub/Sub message id followed by the last five digits of
    a per-sync counter, zero-padded.
    Args:
        message_id: the Pub/Sub message id.
        counter: the position of the message in this sync, starting at 1.
    Returns:
        The unique id.
    """
    digits = str(counter)
    if len(digits) >= __MESSAGE_ID_POSTFIX_DIGITS:
        return message_id + digits[-__MESSAGE_ID_POSTFIX_DIGITS:]
    return message_id + digits.zfill(__MESSAGE_ID_POSTFIX_DIGITS)


def content_hash(content: str):
    """
    Return the lowercase hex SHA-256 of the content serialized as a JSON string, which is how the
    message_hash column has always been computed.
    Args:
        content: the message body as text.
    Returns:
        The hex digest.
    """
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode("utf-8")).hexdigest()


def custom_table_payload(content: str):
    """
    Return the custom table envelope of a message, if it has one.
    Args:
        content: the message body as text.
    Returns:
        The parsed body when it is a JSON object with a string "table" field and a "data" field,
        otherwise None.
    """
    try:
        body = parse_json(content)
    except ValueError:
        return None
    if not isinstance(body, dict) or not isinstance(body.get(__TABLE_FIELD), str):
        return None
    return body if __DATA_FIELD in body else None


def build_row(content: str, message_id: str, publish_time, counter: int, configuration: dict):
    """
    Build the destination row for one message.
    Args:
        content: the message body as text.
        message_id: the Pub/Sub message id.
        publish_time: the publish time as a timezone-aware datetime.
        counter: the position of the message in this sync, starting at 1.
        configuration: the connector configuration.
    Returns:
        A (table, row) tuple. The table is None for the table named after the subscription.
    Raises:
        MessageParseError: if the body cannot be turned into a row.
    """
    row_id = unique_id(message_id, counter)
    payload = custom_table_payload(content)
    if payload is not None:
        data = payload[__DATA_FIELD]
        if not isinstance(data, dict):
            raise MessageParseError(
                f'Message {message_id} has a "data" field that is not an object'
            )
        return payload[__TABLE_FIELD], {**data, __UNIQUE_ID_FIELD: row_id}

    row = {
        "id": row_id,
        "message_hash": content_hash(content),
        "content": content,
        "timestamp": publish_time,
    }
    if configuration.get("sync_format") == SYNC_FORMAT_UNPACKED:
        row.update(unpack(content, configuration.get("unpacking_level")))
    return None, row


def unpack(content: str, unpacking_level):
    """
    Turn the top-level fields of a JSON body into columns. Null fields are left out. At level TWO a
    field that holds a JSON object, or a string containing one, is replaced by that object's fields.
    Args:
        content: the message body as text.
        unpacking_level: ONE or TWO.
    Returns:
        A dictionary of column name to value.
    Raises:
        MessageParseError: if the body is not valid JSON.
    """
    try:
        body = parse_json(content)
    except ValueError as error:
        raise MessageParseError("Failed to parse a message as JSON while unpacking") from error
    if not isinstance(body, dict):
        return {}
    columns = {}
    for key, value in body.items():
        if value is None:
            continue
        nested = nested_object(value) if unpacking_level == UNPACKING_LEVEL_TWO else None
        if nested is None:
            columns[key] = value
        else:
            columns.update(nested)
    return columns


def nested_object(value):
    """
    Return the JSON object a value holds, either directly or as a string such as '{"a": 1}'.
    Args:
        value: a top-level field value.
    Returns:
        The object, or None when the value holds no JSON object.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        try:
            parsed = parse_json(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def to_destination_value(value):
    """
    Make a value safe to upsert. Decimals stay exact at the top level; inside a JSON column they are
    written as plain numbers.
    Args:
        value: a parsed value.
    Returns:
        The value to pass to op.upsert().
    """
    if isinstance(value, (dict, list)):
        return json.loads(json.dumps(value, default=float))
    return value
