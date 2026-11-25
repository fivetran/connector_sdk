"""Protobuf message classes for PlanetScale's Vitess VStream API, used by vstream_reader.py.

The messages are a subset of the public Vitess v0.24.1 protos (https://github.com/vitessio/vitess, Apache-2.0):
query.proto, topodata.proto, binlogdata.proto, vtgate.proto and vtgateservice.proto, plus TableCursor from
PlanetScale's psdbconnect API. They are built from descriptors at import time, so the example needs no generated
code or protoc step. Field numbers, types and enum values are copied unchanged, which keeps the messages
wire-compatible with the server and keeps saved cursors decodable by other PlanetScale connectors. Fields this
connector never reads or sets are left out; protobuf keeps them as unknown fields when parsing, so re-serializing
a parsed message does not lose them.
"""

# For defining the message types without generated code
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

_FIELD = descriptor_pb2.FieldDescriptorProto
_OPTIONAL = _FIELD.LABEL_OPTIONAL
_REPEATED = _FIELD.LABEL_REPEATED
_STRING = _FIELD.TYPE_STRING
_BYTES = _FIELD.TYPE_BYTES
_BOOL = _FIELD.TYPE_BOOL
_INT64 = _FIELD.TYPE_INT64
_UINT32 = _FIELD.TYPE_UINT32
_UINT64 = _FIELD.TYPE_UINT64
_SINT64 = _FIELD.TYPE_SINT64
_ENUM = _FIELD.TYPE_ENUM
_MESSAGE = _FIELD.TYPE_MESSAGE

# The method this connector calls on PlanetScale's gRPC endpoint.
VSTREAM_METHOD = "/vtgateservice.Vitess/VStream"

_QUERY_TYPES = [
    ("NULL_TYPE", 0),
    ("INT8", 257),
    ("UINT8", 770),
    ("INT16", 259),
    ("UINT16", 772),
    ("INT24", 261),
    ("UINT24", 774),
    ("INT32", 263),
    ("UINT32", 776),
    ("INT64", 265),
    ("UINT64", 778),
    ("FLOAT32", 1035),
    ("FLOAT64", 1036),
    ("TIMESTAMP", 2061),
    ("DATE", 2062),
    ("TIME", 2063),
    ("DATETIME", 2064),
    ("YEAR", 785),
    ("DECIMAL", 18),
    ("TEXT", 6163),
    ("BLOB", 10260),
    ("VARCHAR", 6165),
    ("VARBINARY", 10262),
    ("CHAR", 6167),
    ("BINARY", 10264),
    ("BIT", 2073),
    ("ENUM", 2074),
    ("SET", 2075),
    ("TUPLE", 28),
    ("GEOMETRY", 2077),
    ("JSON", 2078),
    ("EXPRESSION", 31),
    ("HEXNUM", 4128),
    ("HEXVAL", 4129),
    ("BITNUM", 4130),
    ("VECTOR", 2083),
    ("RAW", 36),
    ("ROW_TUPLE", 37),
]

_TABLET_TYPES = [
    ("UNKNOWN", 0),
    ("PRIMARY", 1),
    ("MASTER", 1),
    ("REPLICA", 2),
    ("RDONLY", 3),
    ("BATCH", 3),
    ("SPARE", 4),
    ("EXPERIMENTAL", 5),
    ("BACKUP", 6),
    ("RESTORE", 7),
    ("DRAINED", 8),
]

_VEVENT_TYPES = [
    ("UNKNOWN", 0),
    ("GTID", 1),
    ("BEGIN", 2),
    ("COMMIT", 3),
    ("ROLLBACK", 4),
    ("DDL", 5),
    ("INSERT", 6),
    ("REPLACE", 7),
    ("UPDATE", 8),
    ("DELETE", 9),
    ("SET", 10),
    ("OTHER", 11),
    ("ROW", 12),
    ("FIELD", 13),
    ("HEARTBEAT", 14),
    ("VGTID", 15),
    ("JOURNAL", 16),
    ("VERSION", 17),
    ("LASTPK", 18),
    ("SAVEPOINT", 19),
    ("COPY_COMPLETED", 20),
    ("PREVIOUS_GTIDS", 21),
    ("ROWS_QUERY", 22),
]

# Each file: (file name, package, dependencies, enums, messages). A message is (name, fields, nested messages,
# nested enums) and a field is (name, number, type, label, type name for messages and enums).
_FILES = [
    (
        "vitess/query.proto",
        "query",
        [],
        [("Type", _QUERY_TYPES)],
        [
            (
                "Field",
                [
                    ("name", 1, _STRING, _OPTIONAL, None),
                    ("type", 2, _ENUM, _OPTIONAL, ".query.Type"),
                    ("table", 3, _STRING, _OPTIONAL, None),
                    ("org_table", 4, _STRING, _OPTIONAL, None),
                    ("database", 5, _STRING, _OPTIONAL, None),
                    ("org_name", 6, _STRING, _OPTIONAL, None),
                    ("column_length", 7, _UINT32, _OPTIONAL, None),
                    ("charset", 8, _UINT32, _OPTIONAL, None),
                    ("decimals", 9, _UINT32, _OPTIONAL, None),
                    ("flags", 10, _UINT32, _OPTIONAL, None),
                    ("column_type", 11, _STRING, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            (
                "Row",
                [
                    ("lengths", 1, _SINT64, _REPEATED, None),
                    ("values", 2, _BYTES, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            (
                "QueryResult",
                [
                    ("fields", 1, _MESSAGE, _REPEATED, ".query.Field"),
                    ("rows_affected", 2, _UINT64, _OPTIONAL, None),
                    ("insert_id", 3, _UINT64, _OPTIONAL, None),
                    ("rows", 4, _MESSAGE, _REPEATED, ".query.Row"),
                    ("info", 6, _STRING, _OPTIONAL, None),
                    ("session_state_changes", 7, _STRING, _OPTIONAL, None),
                    ("insert_id_changed", 8, _BOOL, _OPTIONAL, None),
                ],
                [],
                [],
            ),
        ],
    ),
    ("vitess/topodata.proto", "topodata", [], [("TabletType", _TABLET_TYPES)], []),
    (
        "vitess/binlogdata.proto",
        "binlogdata",
        ["vitess/query.proto"],
        [("VEventType", _VEVENT_TYPES)],
        [
            ("VGtid", [("shard_gtids", 1, _MESSAGE, _REPEATED, ".binlogdata.ShardGtid")], [], []),
            (
                "ShardGtid",
                [
                    ("keyspace", 1, _STRING, _OPTIONAL, None),
                    ("shard", 2, _STRING, _OPTIONAL, None),
                    ("gtid", 3, _STRING, _OPTIONAL, None),
                    ("table_p_ks", 4, _MESSAGE, _REPEATED, ".binlogdata.TableLastPK"),
                ],
                [],
                [],
            ),
            (
                "TableLastPK",
                [
                    ("table_name", 1, _STRING, _OPTIONAL, None),
                    ("lastpk", 3, _MESSAGE, _OPTIONAL, ".query.QueryResult"),
                ],
                [],
                [],
            ),
            # Rule's map fields (3, 4 and 8) are not used by this connector.
            (
                "Rule",
                [
                    ("match", 1, _STRING, _OPTIONAL, None),
                    ("filter", 2, _STRING, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            (
                "Filter",
                [
                    ("rules", 1, _MESSAGE, _REPEATED, ".binlogdata.Rule"),
                    (
                        "field_event_mode",
                        2,
                        _ENUM,
                        _OPTIONAL,
                        ".binlogdata.Filter.FieldEventMode",
                    ),
                    ("workflow_type", 3, _INT64, _OPTIONAL, None),
                    ("workflow_name", 4, _STRING, _OPTIONAL, None),
                ],
                [],
                [("FieldEventMode", [("ERR_ON_MISMATCH", 0), ("BEST_EFFORT", 1)])],
            ),
            (
                "RowChange",
                [
                    ("before", 1, _MESSAGE, _OPTIONAL, ".query.Row"),
                    ("after", 2, _MESSAGE, _OPTIONAL, ".query.Row"),
                ],
                [],
                [],
            ),
            (
                "RowEvent",
                [
                    ("table_name", 1, _STRING, _OPTIONAL, None),
                    ("row_changes", 2, _MESSAGE, _REPEATED, ".binlogdata.RowChange"),
                    ("keyspace", 3, _STRING, _OPTIONAL, None),
                    ("shard", 4, _STRING, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            (
                "FieldEvent",
                [
                    ("table_name", 1, _STRING, _OPTIONAL, None),
                    ("fields", 2, _MESSAGE, _REPEATED, ".query.Field"),
                    ("keyspace", 3, _STRING, _OPTIONAL, None),
                    ("shard", 4, _STRING, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            (
                "LastPKEvent",
                [
                    ("table_last_p_k", 1, _MESSAGE, _OPTIONAL, ".binlogdata.TableLastPK"),
                    ("completed", 2, _BOOL, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            (
                "VEvent",
                [
                    ("type", 1, _ENUM, _OPTIONAL, ".binlogdata.VEventType"),
                    ("timestamp", 2, _INT64, _OPTIONAL, None),
                    ("gtid", 3, _STRING, _OPTIONAL, None),
                    ("row_event", 5, _MESSAGE, _OPTIONAL, ".binlogdata.RowEvent"),
                    ("field_event", 6, _MESSAGE, _OPTIONAL, ".binlogdata.FieldEvent"),
                    ("vgtid", 7, _MESSAGE, _OPTIONAL, ".binlogdata.VGtid"),
                    ("last_p_k_event", 21, _MESSAGE, _OPTIONAL, ".binlogdata.LastPKEvent"),
                    ("keyspace", 22, _STRING, _OPTIONAL, None),
                    ("shard", 23, _STRING, _OPTIONAL, None),
                ],
                [],
                [],
            ),
        ],
    ),
    (
        "vitess/vtgate.proto",
        "vtgate",
        ["vitess/binlogdata.proto", "vitess/topodata.proto"],
        [],
        [
            (
                "VStreamFlags",
                [
                    ("minimize_skew", 1, _BOOL, _OPTIONAL, None),
                    ("cells", 4, _STRING, _OPTIONAL, None),
                ],
                [],
                [],
            ),
            # caller_id (1) is not used by this connector.
            (
                "VStreamRequest",
                [
                    ("tablet_type", 2, _ENUM, _OPTIONAL, ".topodata.TabletType"),
                    ("vgtid", 3, _MESSAGE, _OPTIONAL, ".binlogdata.VGtid"),
                    ("filter", 4, _MESSAGE, _OPTIONAL, ".binlogdata.Filter"),
                    ("flags", 5, _MESSAGE, _OPTIONAL, ".vtgate.VStreamFlags"),
                ],
                [],
                [],
            ),
            (
                "VStreamResponse",
                [("events", 1, _MESSAGE, _REPEATED, ".binlogdata.VEvent")],
                [],
                [],
            ),
        ],
    ),
    (
        "psdbconnect/v1alpha1/connect.proto",
        "psdbconnect.v1alpha1",
        ["vitess/query.proto"],
        [],
        [
            (
                "TableCursor",
                [
                    ("shard", 1, _STRING, _OPTIONAL, None),
                    ("keyspace", 2, _STRING, _OPTIONAL, None),
                    ("position", 3, _STRING, _OPTIONAL, None),
                    ("last_known_pk", 4, _MESSAGE, _OPTIONAL, ".query.QueryResult"),
                ],
                [],
                [],
            ),
        ],
    ),
]


def add_enum(enum_proto, name: str, values: list):
    """
    Fill an enum descriptor; aliased values (two names for one number) need allow_alias.
    Args:
        enum_proto: the EnumDescriptorProto to fill.
        name: the enum name.
        values: (value name, number) pairs.
    """
    enum_proto.name = name
    numbers = [number for _, number in values]
    if len(set(numbers)) != len(numbers):
        enum_proto.options.allow_alias = True
    for value_name, number in values:
        enum_proto.value.add(name=value_name, number=number)


def add_message(message_proto, message: tuple):
    """
    Fill a message descriptor with its fields, nested messages and nested enums.
    Args:
        message_proto: the DescriptorProto to fill.
        message: (name, fields, nested messages, nested enums).
    """
    name, fields, nested_messages, nested_enums = message
    message_proto.name = name
    for field_name, number, field_type, label, type_name in fields:
        field = message_proto.field.add(
            name=field_name, number=number, type=field_type, label=label
        )
        if type_name is not None:
            field.type_name = type_name
    for nested in nested_messages:
        add_message(message_proto.nested_type.add(), nested)
    for enum_name, values in nested_enums:
        add_enum(message_proto.enum_type.add(), enum_name, values)


def build_pool():
    """
    Build a descriptor pool holding every file this connector uses.
    Returns:
        The DescriptorPool.
    """
    pool = descriptor_pool.DescriptorPool()
    for file_name, package, dependencies, enums, messages in _FILES:
        file_proto = descriptor_pb2.FileDescriptorProto(
            name=file_name, package=package, syntax="proto3", dependency=dependencies
        )
        for enum_name, values in enums:
            add_enum(file_proto.enum_type.add(), enum_name, values)
        for message in messages:
            add_message(file_proto.message_type.add(), message)
        pool.Add(file_proto)
    return pool


_POOL = build_pool()


def message_class(full_name: str):
    """
    Return the generated message class for a fully qualified message name.
    Args:
        full_name: e.g. "query.Field".
    Returns:
        The message class.
    """
    return message_factory.GetMessageClass(_POOL.FindMessageTypeByName(full_name))


def enum_value(full_name: str, value_name: str):
    """
    Return the number of an enum value.
    Args:
        full_name: the fully qualified enum name, e.g. "query.Type".
        value_name: the value name, e.g. "INT64".
    Returns:
        The enum number.
    """
    return _POOL.FindEnumTypeByName(full_name).values_by_name[value_name].number


Field = message_class("query.Field")
Row = message_class("query.Row")
QueryResult = message_class("query.QueryResult")
VGtid = message_class("binlogdata.VGtid")
ShardGtid = message_class("binlogdata.ShardGtid")
TableLastPK = message_class("binlogdata.TableLastPK")
Rule = message_class("binlogdata.Rule")
Filter = message_class("binlogdata.Filter")
RowChange = message_class("binlogdata.RowChange")
RowEvent = message_class("binlogdata.RowEvent")
FieldEvent = message_class("binlogdata.FieldEvent")
LastPKEvent = message_class("binlogdata.LastPKEvent")
VEvent = message_class("binlogdata.VEvent")
VStreamFlags = message_class("vtgate.VStreamFlags")
VStreamRequest = message_class("vtgate.VStreamRequest")
VStreamResponse = message_class("vtgate.VStreamResponse")
TableCursor = message_class("psdbconnect.v1alpha1.TableCursor")

# The numeric values the reader and converter compare against.
QUERY_TYPE = {name: number for name, number in _QUERY_TYPES}
VEVENT_TYPE = {name: number for name, number in _VEVENT_TYPES}
TABLET_TYPE = {name: number for name, number in _TABLET_TYPES}
