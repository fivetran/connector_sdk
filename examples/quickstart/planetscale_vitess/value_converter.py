"""Maps PlanetScale column types to Fivetran types and converts VStream values, used by connector.py.

The rules follow the PlanetScale connector's Go converters, including their quirks, so a destination written by an
earlier PlanetScale connector keeps the same values: for example, an INT larger than 2147483647 is written as NULL,
and an enum label that looks like a number is read as a position in the enum list.
"""

# For parsing column type declarations, numbers and timestamps
import re

# For reading geometry values in well-known binary format
import struct

# For parsing JSON values before they are sent to a JSON column
import json

# For validating and formatting dates, timestamps and decimals
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# For the VStream field type numbers
from vitess_messages import QUERY_TYPE

# Fivetran data types used in schema() and when converting values.
BOOLEAN = "BOOLEAN"
SHORT = "SHORT"
INT = "INT"
LONG = "LONG"
FLOAT = "FLOAT"
DOUBLE = "DOUBLE"
DECIMAL = "DECIMAL"
UTC_DATETIME = "UTC_DATETIME"
NAIVE_DATE = "NAIVE_DATE"
NAIVE_DATETIME = "NAIVE_DATETIME"
JSON = "JSON"
BINARY = "BINARY"
STRING = "STRING"

__DEFAULT_DECIMAL_PRECISION = 10
__DEFAULT_DECIMAL_SCALE = 0
__MAX_DECIMAL_PARAMETER = 0xFFFFFFFF
__INT_MAX = 2**31 - 1
__LONG_MIN = -(2**63)
__LONG_MAX = 2**63 - 1
__FLOAT_MAX = 3.4028234663852886e38
__UINT64_MAX = 2**64 - 1
__SET_BITS = 64
__SRID_BYTES = 4
__MAX_SHORTEST_DIGITS = 17
__PLAIN_EXPONENT_MIN = -6
__PLAIN_EXPONENT_MAX = 21

__DECIMAL_PARAMETERS = re.compile(r"-?\d[\d,]*")
__SIGNED_INTEGER = re.compile(r"[+-]?[0-9]+")
__UNSIGNED_INTEGER = re.compile(r"[0-9]+")
__FLOAT_LITERAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
__DECIMAL_LITERAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
__ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
__MYSQL_DATETIME = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.(\d{0,9}))?")
__GEOMETRY_PREFIXES = (
    "geometry",
    "geomcollection",
    "geometrycollection",
    "multipoint",
    "multipolygon",
    "polygon",
    "point",
    "linestring",
    "multilinestring",
)
__INTEGRAL_TYPES = {
    QUERY_TYPE[name]
    for name in (
        "INT8",
        "UINT8",
        "INT16",
        "UINT16",
        "INT24",
        "UINT24",
        "INT32",
        "UINT32",
        "INT64",
        "UINT64",
        "YEAR",
    )
}
__NUMBER_TYPES = __INTEGRAL_TYPES | {
    QUERY_TYPE["FLOAT32"],
    QUERY_TYPE["FLOAT64"],
    QUERY_TYPE["DECIMAL"],
}
__NAN_TEXT = {"nan", "+nan", "-nan"}
__POSITIVE_INFINITY_TEXT = {"inf", "+inf", "infinity", "+infinity"}
__NEGATIVE_INFINITY_TEXT = {"-inf", "-infinity"}
__ENUM_ESCAPES = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}

# WKB type numbers and the GeoJSON names they are written as.
__WKB_POINT = 1
__WKB_LINE_STRING = 2
__WKB_POLYGON = 3
__WKB_MULTI_POINT = 4
__WKB_MULTI_LINE_STRING = 5
__WKB_MULTI_POLYGON = 6
__WKB_GEOMETRY_COLLECTION = 7
__GEOJSON_NAMES = {
    __WKB_POINT: "Point",
    __WKB_LINE_STRING: "LineString",
    __WKB_POLYGON: "Polygon",
    __WKB_MULTI_POINT: "MultiPoint",
    __WKB_MULTI_LINE_STRING: "MultiLineString",
    __WKB_MULTI_POLYGON: "MultiPolygon",
    __WKB_GEOMETRY_COLLECTION: "GeometryCollection",
}
# EWKB mode flags in the second half of the type word, and the ISO WKB dimension offset.
__MODE_FLAGS = {
    0x0000: (False, False, False),
    0x4000: (False, False, True),
    0x8000: (False, True, False),
    0xC000: (False, True, True),
    0x2000: (True, False, False),
    0x6000: (True, False, True),
    0xA000: (True, True, False),
    0xE000: (True, True, True),
}
__ISO_DIMENSION_OFFSET = 1000
__ISO_DIMENSION_LIMIT = 4000


class ConversionError(ValueError):
    """A VStream value that cannot be converted to its column's type."""


def map_column_type(column_type: str, treat_tiny_int_as_boolean: bool):
    """
    Map a MySQL column declaration from information_schema to a Fivetran type.
    Args:
        column_type: the declaration, e.g. "decimal(10,2)" or "int unsigned".
        treat_tiny_int_as_boolean: whether tinyint(1) is written as BOOLEAN.
    Returns:
        A tuple of (type, precision, scale); precision and scale are set only for DECIMAL.
    """
    declared = column_type.lower()
    if declared.startswith("tinyint"):
        is_boolean = treat_tiny_int_as_boolean and declared == "tinyint(1)"
        return (BOOLEAN if is_boolean else INT), None, None
    if declared.startswith("bit"):
        return LONG, None, None
    if declared.startswith(("varbinary", "binary")):
        return BINARY, None, None
    if declared.startswith("int"):
        return (LONG if "unsigned" in declared else INT), None, None
    if declared.startswith("smallint"):
        return INT, None, None
    if declared.startswith("bigint"):
        return LONG, None, None
    if declared.startswith("decimal"):
        return decimal_type(declared)
    if declared.startswith(("double", "float")):
        return DOUBLE, None, None
    if declared.startswith("timestamp"):
        return UTC_DATETIME, None, None
    if declared.startswith("time"):
        return STRING, None, None
    if declared.startswith("datetime"):
        return NAIVE_DATETIME, None, None
    if declared.startswith("year"):
        return INT, None, None
    if declared.startswith(("varchar", "text", "enum", "char")):
        return STRING, None, None
    if declared.startswith("set") or declared.startswith(__GEOMETRY_PREFIXES):
        return JSON, None, None
    return exact_column_type(declared)


def exact_column_type(declared: str):
    """
    Map the column declarations that are matched by their whole name rather than a prefix.
    Args:
        declared: the lower-cased declaration.
    Returns:
        A tuple of (type, None, None); unknown declarations become STRING.
    """
    exact_types = {
        "date": NAIVE_DATE,
        "json": JSON,
        "mediumint": INT,
        "blob": BINARY,
        "longblob": BINARY,
        "mediumblob": BINARY,
        "tinyblob": BINARY,
    }
    return exact_types.get(declared, STRING), None, None


def decimal_type(declared: str):
    """
    Read the precision and scale of a decimal declaration, defaulting to DECIMAL(10,0).
    Args:
        declared: the lower-cased declaration, e.g. "decimal(12, 4)".
    Returns:
        A tuple of (DECIMAL, precision, scale).
    """
    parameters = re.sub(r"\s", "", declared.upper().replace("DECIMAL", "", 1))
    match = __DECIMAL_PARAMETERS.search(parameters)
    if not match:
        return DECIMAL, __DEFAULT_DECIMAL_PRECISION, __DEFAULT_DECIMAL_SCALE
    parts = match.group().split(",")
    precision = decimal_parameter(parts[0], __DEFAULT_DECIMAL_PRECISION)
    scale = decimal_parameter(parts[1], __DEFAULT_DECIMAL_SCALE) if len(parts) > 1 else 0
    return DECIMAL, precision, scale


def decimal_parameter(text: str, default: int):
    """
    Parse a decimal precision or scale, using the default when it is not a usable number.
    Args:
        text: the parameter text.
        default: the value to use instead.
    Returns:
        The parameter.
    """
    try:
        value = int(text)
    except ValueError:
        return default
    return value if 0 <= value <= __MAX_DECIMAL_PARAMETER else default


def convert(field, raw_value, data_type: str):
    """
    Convert one VStream value for its destination column.
    Args:
        field: the query.Field describing the value.
        raw_value: the value bytes, or None for SQL NULL.
        data_type: the column's Fivetran type.
    Returns:
        The value to upsert.
    Raises:
        ConversionError: if the value cannot be converted.
    """
    if raw_value is None or field.type == QUERY_TYPE["NULL_TYPE"]:
        return None
    if field.type == QUERY_TYPE["GEOMETRY"] and data_type == JSON:
        return convert_geometry(raw_value)
    if field.type == QUERY_TYPE["ENUM"] and column_kind(field.column_type) == "enum":
        return convert_enum(raw_value, enum_values(field.column_type))
    is_set_column = column_kind(field.column_type) == "set"
    if field.type == QUERY_TYPE["SET"] and data_type == JSON and is_set_column:
        return convert_set(raw_value, enum_values(field.column_type))
    converters = {
        BOOLEAN: convert_boolean,
        SHORT: convert_short,
        INT: convert_int,
        LONG: convert_long,
        FLOAT: convert_float,
        DOUBLE: lambda field_, value: parse_double(field_, value, "DataType_DOUBLE"),
        DECIMAL: lambda _, value: convert_decimal(value),
        NAIVE_DATE: lambda _, value: convert_date(value),
        NAIVE_DATETIME: lambda _, value: convert_datetime(value),
        UTC_DATETIME: lambda _, value: convert_timestamp(value),
        JSON: lambda _, value: convert_json(value),
        BINARY: lambda field_, value: to_bytes(field_, value, "DataType_BINARY"),
        STRING: lambda _, value: clean_string(value),
    }
    if data_type not in converters:
        raise ConversionError(f"don't know how to convert type {data_type}")
    return converters[data_type](field, raw_value)


def failure(type_name: str, detail: str):
    """
    Build the conversion error the Go converters report.
    Args:
        type_name: the Fivetran or Vitess type being converted.
        detail: what is wrong with the value.
    Returns:
        The ConversionError.
    """
    return ConversionError(f"failed to serialize {type_name}: {detail}")


def convert_boolean(field, raw_value: bytes):
    """
    Convert 0 or 1 to a boolean.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
    Returns:
        The boolean.
    """
    value = parse_integral(field, raw_value, "DataType_BOOLEAN")
    if value in (0, 1):
        return value == 1
    raise failure("DataType_BOOLEAN", "value is not 0 or 1")


def wrap_signed(value: int, bits: int):
    """
    Wrap an integer to a two's-complement width, the way a narrowing cast does.
    Args:
        value: the integer.
        bits: the target width.
    Returns:
        The wrapped integer.
    """
    half = 1 << (bits - 1)
    return ((value + half) % (1 << bits)) - half


def convert_short(field, raw_value: bytes):
    """
    Convert an integer to SHORT. Only values above the INT range become NULL; others wrap to 16 bits.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
    Returns:
        The integer, or None.
    """
    value = parse_integral(field, raw_value, "DataType_SHORT")
    return None if value > __INT_MAX else wrap_signed(value, 16)


def convert_int(field, raw_value: bytes):
    """
    Convert an integer to INT. Values above the INT range become NULL; values below it wrap to 32 bits.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
    Returns:
        The integer, or None.
    """
    value = parse_integral(field, raw_value, "DataType_INT")
    return None if value > __INT_MAX else wrap_signed(value, 32)


def convert_long(field, raw_value: bytes):
    """
    Convert an integer, or the bytes of a BIT column, to LONG.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
    Returns:
        The integer.
    """
    if field.type in __INTEGRAL_TYPES:
        return parse_integral(field, raw_value, "DataType_LONG")
    return bit_bytes_to_long(to_bytes(field, raw_value, "Type_BIT"))


def convert_float(field, raw_value: bytes):
    """
    Convert a number to FLOAT; values above the FLOAT range become NULL.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
    Returns:
        The float, or None.
    """
    value = parse_double(field, raw_value, "DataType_FLOAT")
    if value > __FLOAT_MAX:
        return None
    if value < -__FLOAT_MAX:
        # Narrowing a double below the FLOAT range gives negative infinity, as the Go converter does.
        return float("-inf")
    return struct.unpack("f", struct.pack("f", value))[0]


def convert_decimal(raw_value: bytes):
    """
    Convert a decimal literal to the plain-notation text a DECIMAL column accepts.
    Args:
        raw_value: the value bytes.
    Returns:
        The decimal text.
    """
    text = clean_string(raw_value)
    if not __DECIMAL_LITERAL.fullmatch(text):
        raise ConversionError("failed to serialize DataType_DECIMAL")
    try:
        return format(Decimal(text), "f")
    except InvalidOperation as error:
        raise ConversionError("failed to serialize DataType_DECIMAL") from error


def convert_date(raw_value: bytes):
    """
    Convert a YYYY-MM-DD date.
    Args:
        raw_value: the value bytes.
    Returns:
        The date as YYYY-MM-DD.
    """
    text = clean_string(raw_value)
    try:
        if not __ISO_DATE.fullmatch(text):
            raise ValueError(text)
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ConversionError("failed to serialize DataType_NAIVE_DATE") from error


def parse_mysql_datetime(text: str):
    """
    Parse a MySQL "YYYY-MM-DD HH:MM:SS[.fraction]" value strictly. Fractions beyond microseconds are truncated,
    because MySQL stores at most six fractional digits.
    Args:
        text: the value text.
    Returns:
        The naive datetime.
    """
    match = __MYSQL_DATETIME.fullmatch(text)
    if not match:
        raise ValueError(text)
    year, month, day, hour, minute, second, fraction = match.groups()
    microseconds = int((fraction or "").ljust(6, "0")[:6])
    return datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second), microseconds
    )


def convert_datetime(raw_value: bytes):
    """
    Convert a MySQL DATETIME to a naive timestamp.
    Args:
        raw_value: the value bytes.
    Returns:
        The timestamp in ISO 8601 format without an offset.
    """
    try:
        return parse_mysql_datetime(clean_string(raw_value)).isoformat()
    except ValueError as error:
        raise ConversionError("failed to serialize DataType_NAIVE_DATETIME") from error


def convert_timestamp(raw_value: bytes):
    """
    Convert a MySQL TIMESTAMP, stored in UTC, to a UTC timestamp. Zero dates become the epoch.
    Args:
        raw_value: the value bytes.
    Returns:
        The timestamp in ISO 8601 format with a Z suffix.
    """
    text = clean_string(raw_value)
    if "0000-00-0" in text:
        return "1970-01-01T00:00:00Z"
    try:
        return parse_mysql_datetime(text).isoformat() + "Z"
    except ValueError as error:
        raise ConversionError("failed to serialize DataType_UTC_DATETIME") from error


def json_value(text: str):
    """
    Prepare text for a JSON column: valid JSON is sent as parsed data and anything else as a JSON string.
    Args:
        text: the value text.
    Returns:
        The value to upsert.
    """
    try:
        return json.loads(text)
    except ValueError:
        return text


def convert_json(raw_value: bytes):
    """
    Convert a JSON value; an empty value becomes NULL.
    Args:
        raw_value: the value bytes.
    Returns:
        The value to upsert, or None.
    """
    text = clean_string(raw_value)
    return json_value(text) if text else None


def decode_hex(text: str, type_name: str):
    """
    Decode an even-length hexadecimal string.
    Args:
        text: the hexadecimal digits.
        type_name: the type named in an error.
    Returns:
        The bytes.
    """
    if len(text) % 2:
        raise failure(type_name, "invalid hexadecimal value")
    try:
        return bytes.fromhex(text)
    except ValueError as error:
        raise ConversionError(f"failed to serialize {type_name}") from error


def bit_number_to_bytes(text: str, type_name: str):
    """
    Convert a 0b-prefixed bit literal to its minimal big-endian bytes.
    Args:
        text: the literal.
        type_name: the type named in an error.
    Returns:
        The bytes.
    """
    if not text.startswith("0b") or len(text) < 3:
        raise failure(type_name, "invalid bit number")
    try:
        number = int(text[2:], 2)
    except ValueError as error:
        raise ConversionError(f"failed to serialize {type_name}") from error
    return number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""


def to_bytes(field, raw_value: bytes, type_name: str):
    """
    Return the bytes of a binary value, decoding hexadecimal and bit literals.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
        type_name: the type named in an error.
    Returns:
        The bytes.
    """
    text = raw_value.decode("ascii", errors="replace")
    if field.type == QUERY_TYPE["HEXVAL"]:
        if len(text) < 3 or text[0] not in "xX" or text[1] != "'" or text[-1] != "'":
            raise failure(type_name, "invalid hex value")
        return decode_hex(text[2:-1], type_name)
    if field.type == QUERY_TYPE["HEXNUM"]:
        if len(text) < 3 or not text.startswith("0x"):
            raise failure(type_name, "invalid hex number")
        return decode_hex(text[2:], type_name)
    if field.type == QUERY_TYPE["BITNUM"]:
        return bit_number_to_bytes(text, type_name)
    if field.type == QUERY_TYPE["EXPRESSION"]:
        raise failure(type_name, "expression cannot be converted to bytes")
    return bytes(raw_value)


def parse_integral(field, raw_value: bytes, type_name: str):
    """
    Parse a signed 64-bit integer from an integral field.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
        type_name: the type named in an error.
    Returns:
        The integer.
    """
    if field.type not in __INTEGRAL_TYPES:
        raise failure(type_name, "incompatible type cast")
    text = raw_value.decode("ascii", errors="replace")
    if not __SIGNED_INTEGER.fullmatch(text):
        raise ConversionError(f"failed to serialize {type_name}")
    value = int(text)
    if not __LONG_MIN <= value <= __LONG_MAX:
        raise ConversionError(f"failed to serialize {type_name}")
    return value


def parse_double(field, raw_value: bytes, type_name: str):
    """
    Parse a double from a numeric field, accepting NaN and infinity spellings.
    Args:
        field: the query.Field.
        raw_value: the value bytes.
        type_name: the type named in an error.
    Returns:
        The float.
    """
    if field.type not in __NUMBER_TYPES:
        raise failure(type_name, "incompatible type cast")
    text = raw_value.decode("ascii", errors="replace").strip()
    lowered = text.lower()
    if lowered in __NAN_TEXT:
        return float("nan")
    if lowered in __POSITIVE_INFINITY_TEXT:
        return float("inf")
    if lowered in __NEGATIVE_INFINITY_TEXT:
        return float("-inf")
    if not __FLOAT_LITERAL.fullmatch(text):
        raise ConversionError(f"failed to serialize {type_name}")
    value = float(text)
    if value in (float("inf"), float("-inf")):
        raise ConversionError(f"failed to serialize {type_name}")
    return value


def bit_bytes_to_long(value: bytes):
    """
    Read up to eight big-endian bytes as a non-negative 64-bit integer.
    Args:
        value: the bytes.
    Returns:
        The integer.
    """
    if len(value) > 8:
        raise failure("Type_BIT", f"value uses {len(value)} bytes")
    number = int.from_bytes(value, "big")
    if number > __LONG_MAX:
        raise failure("Type_BIT", f"value {number} overflows int64")
    return number


def clean_string(value: bytes):
    """
    Decode text as UTF-8, falling back to ISO-8859-1 when the bytes are not valid UTF-8.
    Args:
        value: the bytes.
    Returns:
        The text.
    """
    try:
        return bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        return bytes(value).decode("iso-8859-1")


def column_kind(column_type: str):
    """
    Tell whether a column declaration is an enum or a set.
    Args:
        column_type: the declaration, e.g. "enum('a','b')".
    Returns:
        "enum", "set" or "".
    """
    declared = column_type.lstrip().lower()
    if declared.startswith("enum"):
        return "enum"
    return "set" if declared.startswith("set") else ""


def enum_values(column_type: str):
    """
    Parse the quoted labels of an enum or set declaration, honouring MySQL escapes and doubled quotes.
    Args:
        column_type: the declaration, e.g. "set('a','b''c')".
    Returns:
        The labels in declaration order.
    """
    opening = column_type.find("(")
    closing = column_type.rfind(")")
    if opening < 0 or closing <= opening:
        return []
    literal = column_type[opening + 1 : closing]
    values, current, in_quote, index = [], [], False, 0
    while index < len(literal):
        character = literal[index]
        if character == "\\" and in_quote and index + 1 < len(literal):
            index += 1
            current.append(__ENUM_ESCAPES.get(literal[index], literal[index]))
        elif character == "'":
            if in_quote and index + 1 < len(literal) and literal[index + 1] == "'":
                current.append("'")
                index += 1
            else:
                in_quote = not in_quote
        elif character == "," and not in_quote:
            values.append("".join(current))
            current = []
        elif in_quote or not character.isspace():
            current.append(character)
        index += 1
    if literal:
        values.append("".join(current))
    return values


def convert_enum(raw_value: bytes, labels: list):
    """
    Convert an enum value. A numeric value is a 1-based position in the label list and 0 is the empty label;
    numeric-looking labels are therefore read as positions, as the Go connector does.
    Args:
        raw_value: the value bytes.
        labels: the enum labels.
    Returns:
        The label text.
    """
    text = clean_string(raw_value)
    if not __SIGNED_INTEGER.fullmatch(text):
        return text
    index = int(text)
    if not __LONG_MIN <= index <= __LONG_MAX:
        return text
    if index == 0:
        return ""
    return labels[index - 1] if 0 < index <= len(labels) else text


def convert_set(raw_value: bytes, labels: list):
    """
    Convert a set value. A numeric value is a bit mask over the label list; the result is the labels joined by
    commas, written to a JSON column.
    Args:
        raw_value: the value bytes.
        labels: the set labels.
    Returns:
        The joined labels.
    """
    text = clean_string(raw_value)
    if not __UNSIGNED_INTEGER.fullmatch(text) or int(text) > __UINT64_MAX:
        return json_value(text)
    mask = int(text)
    selected = []
    for index in range(__SET_BITS):
        if mask >> index & 1:
            if index >= len(labels):
                raise failure("Type_SET", f"bit {index + 1} has no mapped value")
            selected.append(labels[index])
    return json_value(",".join(selected))


def convert_geometry(raw_value: bytes):
    """
    Convert a MySQL geometry value (a four-byte SRID followed by WKB) to GeoJSON.
    Args:
        raw_value: the value bytes.
    Returns:
        The GeoJSON object.
    """
    if len(raw_value) < __SRID_BYTES:
        raise ConversionError("unable to serialize Geometry type")
    try:
        geometry, _ = read_wkb(bytes(raw_value), __SRID_BYTES)
    except (struct.error, ValueError) as error:
        raise ConversionError("unable to serialize Geometry type") from error
    return json.loads(geometry_json(geometry, True))


def read_wkb(data: bytes, offset: int):
    """
    Read one WKB or EWKB geometry. Each geometry carries its own byte order and dimension flags; Z and M values
    are read and dropped, because GeoJSON coordinates here are two-dimensional.
    Args:
        data: the WKB bytes.
        offset: where the geometry starts.
    Returns:
        A tuple of ((WKB type number, payload), offset after the geometry).
    """
    order = ">" if data[offset] == 0 else "<"
    type_number, mode = struct.unpack_from(order + "hh", data, offset + 1)
    offset += 5
    is_geography, has_z, has_m = __MODE_FLAGS.get(mode & 0xFFFF, (False, False, False))
    if mode == 0 and __ISO_DIMENSION_OFFSET < type_number < __ISO_DIMENSION_LIMIT:
        dimension = type_number // __ISO_DIMENSION_OFFSET
        has_z, has_m = dimension in (1, 3), dimension in (2, 3)
        type_number %= __ISO_DIMENSION_OFFSET
    if is_geography:
        offset += 4
    if type_number not in __GEOJSON_NAMES:
        raise ValueError(f"unsupported WKB geometry type {type_number}")
    width = 2 + has_z + has_m
    if type_number == __WKB_POINT:
        point = struct.unpack_from(order + "d" * width, data, offset)[:2]
        return (type_number, point), offset + 8 * width
    if type_number in (__WKB_LINE_STRING, __WKB_POLYGON):
        return read_rings(data, offset, order, width, type_number)
    (count,) = struct.unpack_from(order + "I", data, offset)
    offset += 4
    members = []
    for _ in range(count):
        member, offset = read_wkb(data, offset)
        members.append(member)
    expected = {
        __WKB_MULTI_POINT: __WKB_POINT,
        __WKB_MULTI_LINE_STRING: __WKB_LINE_STRING,
        __WKB_MULTI_POLYGON: __WKB_POLYGON,
    }.get(type_number)
    if expected is not None and any(member[0] != expected for member in members):
        raise ValueError("Unexpected shape")
    return (type_number, members), offset


def read_points(data: bytes, offset: int, order: str, width: int):
    """
    Read a counted list of points.
    Args:
        data: the WKB bytes.
        offset: where the count starts.
        order: the struct byte-order prefix.
        width: the number of doubles per point.
    Returns:
        A tuple of (list of (x, y), offset after the points).
    """
    (count,) = struct.unpack_from(order + "I", data, offset)
    offset += 4
    points = []
    for _ in range(count):
        points.append(struct.unpack_from(order + "d" * width, data, offset)[:2])
        offset += 8 * width
    return points, offset


def read_rings(data: bytes, offset: int, order: str, width: int, type_number: int):
    """
    Read a line string (one list of points) or a polygon (a counted list of rings).
    Args:
        data: the WKB bytes.
        offset: where the payload starts.
        order: the struct byte-order prefix.
        width: the number of doubles per point.
        type_number: __WKB_LINE_STRING or __WKB_POLYGON.
    Returns:
        A tuple of ((type number, payload), offset after the geometry).
    """
    if type_number == __WKB_LINE_STRING:
        points, offset = read_points(data, offset, order, width)
        return (type_number, points), offset
    (count,) = struct.unpack_from(order + "I", data, offset)
    offset += 4
    rings = []
    for _ in range(count):
        ring, offset = read_points(data, offset, order, width)
        rings.append(ring)
    return (type_number, rings), offset


def unique_points(points: list):
    """
    Drop repeated points, keeping the first occurrence; NaN points are always kept and -0 equals 0.
    Args:
        points: (x, y) pairs.
    Returns:
        The unique points in order.
    """
    seen, unique = set(), []
    for x, y in points:
        if x != x or y != y:
            unique.append((x, y))
            continue
        key = (x + 0.0, y + 0.0)
        if key not in seen:
            seen.add(key)
            unique.append((x, y))
    return unique


def format_number(value: float):
    """
    Format a coordinate with the shortest digits that round-trip, in plain notation for decimal exponents from
    -6 to 20 and in e-notation otherwise, as the Go connector's JSON encoder does.
    Args:
        value: the coordinate.
    Returns:
        The number text.
    Raises:
        ConversionError: if the coordinate is NaN or infinite, which GeoJSON cannot represent.
    """
    if value != value or value in (float("inf"), float("-inf")):
        raise ConversionError("unable to serialize Geometry type")
    number = Decimal(repr(value)).normalize()
    digits = number.as_tuple()
    exponent = len(digits.digits) + digits.exponent - 1
    if number.is_zero():
        return "0"
    if exponent < __PLAIN_EXPONENT_MIN or exponent >= __PLAIN_EXPONENT_MAX:
        mantissa = "".join(str(digit) for digit in digits.digits[:__MAX_SHORTEST_DIGITS])
        sign = "-" if digits.sign else ""
        fraction = "." + mantissa[1:] if len(mantissa) > 1 else ""
        return f"{sign}{mantissa[0]}{fraction}e{exponent:+d}"
    return format(number, "f")


def coordinates_json(points: list, close_ring: bool):
    """
    Format a list of points as GeoJSON coordinates, closing a polygon ring with its first point.
    Args:
        points: (x, y) pairs.
        close_ring: whether to repeat the first point at the end.
    Returns:
        The JSON text.
    """
    unique = unique_points(points)
    if close_ring and unique:
        unique = unique + [unique[0]]
    return "[" + ",".join(f"[{format_number(x)},{format_number(y)}]" for x, y in unique) + "]"


def geometry_json(geometry: tuple, top_level: bool):
    """
    Format a parsed geometry as GeoJSON text. An empty collection is {"type":"GeometryCollection"} at the top
    level and null inside another collection.
    Args:
        geometry: (WKB type number, payload) from read_wkb.
        top_level: whether this is the outermost geometry.
    Returns:
        The JSON text.
    """
    type_number, payload = geometry
    if type_number == __WKB_GEOMETRY_COLLECTION and not payload:
        return '{"type":"GeometryCollection"}' if top_level else "null"
    prefix = '{"type":"' + __GEOJSON_NAMES[type_number] + '"'
    if type_number == __WKB_POINT:
        x, y = payload
        body = f',"coordinates":[{format_number(x)},{format_number(y)}]'
    elif type_number == __WKB_MULTI_POINT:
        body = ',"coordinates":' + coordinates_json([point for _, point in payload], False)
    elif type_number == __WKB_LINE_STRING:
        body = ',"coordinates":' + coordinates_json(payload, False)
    elif type_number == __WKB_MULTI_LINE_STRING:
        lines = ",".join(coordinates_json(line, False) for _, line in payload)
        body = ',"coordinates":[' + lines + "]"
    elif type_number == __WKB_POLYGON:
        body = ',"coordinates":' + polygon_json(payload)
    elif type_number == __WKB_MULTI_POLYGON:
        body = ',"coordinates":[' + ",".join(polygon_json(rings) for _, rings in payload) + "]"
    else:
        members = ",".join(geometry_json(member, False) for member in payload)
        body = ',"geometries":[' + members + "]"
    return prefix + body + "}"


def polygon_json(rings: list):
    """
    Format polygon rings as GeoJSON coordinates.
    Args:
        rings: lists of (x, y) pairs.
    Returns:
        The JSON text.
    """
    return "[" + ",".join(coordinates_json(ring, True) for ring in rings) + "]"
