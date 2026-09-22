import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TextField(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PlainText: _ClassVar[TextField]
    Password: _ClassVar[TextField]
    Hidden: _ClassVar[TextField]

class DataType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNSPECIFIED: _ClassVar[DataType]
    BOOLEAN: _ClassVar[DataType]
    SHORT: _ClassVar[DataType]
    INT: _ClassVar[DataType]
    LONG: _ClassVar[DataType]
    DECIMAL: _ClassVar[DataType]
    FLOAT: _ClassVar[DataType]
    DOUBLE: _ClassVar[DataType]
    NAIVE_DATE: _ClassVar[DataType]
    NAIVE_DATETIME: _ClassVar[DataType]
    UTC_DATETIME: _ClassVar[DataType]
    BINARY: _ClassVar[DataType]
    XML: _ClassVar[DataType]
    STRING: _ClassVar[DataType]
    JSON: _ClassVar[DataType]
    NAIVE_TIME: _ClassVar[DataType]

class RecordType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UPSERT: _ClassVar[RecordType]
    UPDATE: _ClassVar[RecordType]
    DELETE: _ClassVar[RecordType]
    TRUNCATE: _ClassVar[RecordType]
PlainText: TextField
Password: TextField
Hidden: TextField
UNSPECIFIED: DataType
BOOLEAN: DataType
SHORT: DataType
INT: DataType
LONG: DataType
DECIMAL: DataType
FLOAT: DataType
DOUBLE: DataType
NAIVE_DATE: DataType
NAIVE_DATETIME: DataType
UTC_DATETIME: DataType
BINARY: DataType
XML: DataType
STRING: DataType
JSON: DataType
NAIVE_TIME: DataType
UPSERT: RecordType
UPDATE: RecordType
DELETE: RecordType
TRUNCATE: RecordType

class ConfigurationFormRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ConfigurationFormResponse(_message.Message):
    __slots__ = ("schema_selection_supported", "table_selection_supported", "fields", "tests")
    SCHEMA_SELECTION_SUPPORTED_FIELD_NUMBER: _ClassVar[int]
    TABLE_SELECTION_SUPPORTED_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    TESTS_FIELD_NUMBER: _ClassVar[int]
    schema_selection_supported: bool
    table_selection_supported: bool
    fields: _containers.RepeatedCompositeFieldContainer[FormField]
    tests: _containers.RepeatedCompositeFieldContainer[ConfigurationTest]
    def __init__(self, schema_selection_supported: bool = ..., table_selection_supported: bool = ..., fields: _Optional[_Iterable[_Union[FormField, _Mapping]]] = ..., tests: _Optional[_Iterable[_Union[ConfigurationTest, _Mapping]]] = ...) -> None: ...

class FormField(_message.Message):
    __slots__ = ("name", "label", "required", "description", "text_field", "dropdown_field", "toggle_field", "conditional_fields", "upload_field", "descriptive_dropdown_fields", "default_value", "placeholder")
    NAME_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_FIELD_NUMBER: _ClassVar[int]
    DROPDOWN_FIELD_FIELD_NUMBER: _ClassVar[int]
    TOGGLE_FIELD_FIELD_NUMBER: _ClassVar[int]
    CONDITIONAL_FIELDS_FIELD_NUMBER: _ClassVar[int]
    UPLOAD_FIELD_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTIVE_DROPDOWN_FIELDS_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_VALUE_FIELD_NUMBER: _ClassVar[int]
    PLACEHOLDER_FIELD_NUMBER: _ClassVar[int]
    name: str
    label: str
    required: bool
    description: str
    text_field: TextField
    dropdown_field: DropdownField
    toggle_field: ToggleField
    conditional_fields: ConditionalFields
    upload_field: UploadField
    descriptive_dropdown_fields: DescriptiveDropDownFields
    default_value: str
    placeholder: str
    def __init__(self, name: _Optional[str] = ..., label: _Optional[str] = ..., required: bool = ..., description: _Optional[str] = ..., text_field: _Optional[_Union[TextField, str]] = ..., dropdown_field: _Optional[_Union[DropdownField, _Mapping]] = ..., toggle_field: _Optional[_Union[ToggleField, _Mapping]] = ..., conditional_fields: _Optional[_Union[ConditionalFields, _Mapping]] = ..., upload_field: _Optional[_Union[UploadField, _Mapping]] = ..., descriptive_dropdown_fields: _Optional[_Union[DescriptiveDropDownFields, _Mapping]] = ..., default_value: _Optional[str] = ..., placeholder: _Optional[str] = ...) -> None: ...

class DescriptiveDropDownFields(_message.Message):
    __slots__ = ("descriptive_dropdown_field",)
    DESCRIPTIVE_DROPDOWN_FIELD_FIELD_NUMBER: _ClassVar[int]
    descriptive_dropdown_field: _containers.RepeatedCompositeFieldContainer[DescriptiveDropDownField]
    def __init__(self, descriptive_dropdown_field: _Optional[_Iterable[_Union[DescriptiveDropDownField, _Mapping]]] = ...) -> None: ...

class DescriptiveDropDownField(_message.Message):
    __slots__ = ("value", "label", "description")
    VALUE_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    value: str
    label: str
    description: str
    def __init__(self, value: _Optional[str] = ..., label: _Optional[str] = ..., description: _Optional[str] = ...) -> None: ...

class UploadField(_message.Message):
    __slots__ = ("allowed_file_type", "max_file_size_bytes")
    ALLOWED_FILE_TYPE_FIELD_NUMBER: _ClassVar[int]
    MAX_FILE_SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    allowed_file_type: _containers.RepeatedScalarFieldContainer[str]
    max_file_size_bytes: int
    def __init__(self, allowed_file_type: _Optional[_Iterable[str]] = ..., max_file_size_bytes: _Optional[int] = ...) -> None: ...

class ConditionalFields(_message.Message):
    __slots__ = ("condition", "fields")
    CONDITION_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    condition: VisibilityCondition
    fields: _containers.RepeatedCompositeFieldContainer[FormField]
    def __init__(self, condition: _Optional[_Union[VisibilityCondition, _Mapping]] = ..., fields: _Optional[_Iterable[_Union[FormField, _Mapping]]] = ...) -> None: ...

class VisibilityCondition(_message.Message):
    __slots__ = ("condition_field", "bool_value", "string_value", "empty_value")
    CONDITION_FIELD_FIELD_NUMBER: _ClassVar[int]
    BOOL_VALUE_FIELD_NUMBER: _ClassVar[int]
    STRING_VALUE_FIELD_NUMBER: _ClassVar[int]
    EMPTY_VALUE_FIELD_NUMBER: _ClassVar[int]
    condition_field: str
    bool_value: bool
    string_value: str
    empty_value: bool
    def __init__(self, condition_field: _Optional[str] = ..., bool_value: bool = ..., string_value: _Optional[str] = ..., empty_value: bool = ...) -> None: ...

class DropdownField(_message.Message):
    __slots__ = ("dropdown_field",)
    DROPDOWN_FIELD_FIELD_NUMBER: _ClassVar[int]
    dropdown_field: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, dropdown_field: _Optional[_Iterable[str]] = ...) -> None: ...

class ToggleField(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ConfigurationTest(_message.Message):
    __slots__ = ("name", "label")
    NAME_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    name: str
    label: str
    def __init__(self, name: _Optional[str] = ..., label: _Optional[str] = ...) -> None: ...

class TestRequest(_message.Message):
    __slots__ = ("name", "configuration")
    class ConfigurationEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONFIGURATION_FIELD_NUMBER: _ClassVar[int]
    name: str
    configuration: _containers.ScalarMap[str, str]
    def __init__(self, name: _Optional[str] = ..., configuration: _Optional[_Mapping[str, str]] = ...) -> None: ...

class TestResponse(_message.Message):
    __slots__ = ("success", "failure")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FAILURE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    failure: str
    def __init__(self, success: bool = ..., failure: _Optional[str] = ...) -> None: ...

class SchemaList(_message.Message):
    __slots__ = ("schemas",)
    SCHEMAS_FIELD_NUMBER: _ClassVar[int]
    schemas: _containers.RepeatedCompositeFieldContainer[Schema]
    def __init__(self, schemas: _Optional[_Iterable[_Union[Schema, _Mapping]]] = ...) -> None: ...

class TableList(_message.Message):
    __slots__ = ("tables",)
    TABLES_FIELD_NUMBER: _ClassVar[int]
    tables: _containers.RepeatedCompositeFieldContainer[Table]
    def __init__(self, tables: _Optional[_Iterable[_Union[Table, _Mapping]]] = ...) -> None: ...

class Schema(_message.Message):
    __slots__ = ("name", "tables")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TABLES_FIELD_NUMBER: _ClassVar[int]
    name: str
    tables: _containers.RepeatedCompositeFieldContainer[Table]
    def __init__(self, name: _Optional[str] = ..., tables: _Optional[_Iterable[_Union[Table, _Mapping]]] = ...) -> None: ...

class DataTypeParams(_message.Message):
    __slots__ = ("decimal", "string_byte_length")
    DECIMAL_FIELD_NUMBER: _ClassVar[int]
    STRING_BYTE_LENGTH_FIELD_NUMBER: _ClassVar[int]
    decimal: DecimalParams
    string_byte_length: int
    def __init__(self, decimal: _Optional[_Union[DecimalParams, _Mapping]] = ..., string_byte_length: _Optional[int] = ...) -> None: ...

class DecimalParams(_message.Message):
    __slots__ = ("precision", "scale")
    PRECISION_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    precision: int
    scale: int
    def __init__(self, precision: _Optional[int] = ..., scale: _Optional[int] = ...) -> None: ...

class ValueType(_message.Message):
    __slots__ = ("null", "bool", "short", "int", "long", "float", "double", "naive_date", "naive_datetime", "utc_datetime", "decimal", "binary", "string", "json", "xml", "naive_time")
    NULL_FIELD_NUMBER: _ClassVar[int]
    BOOL_FIELD_NUMBER: _ClassVar[int]
    SHORT_FIELD_NUMBER: _ClassVar[int]
    INT_FIELD_NUMBER: _ClassVar[int]
    LONG_FIELD_NUMBER: _ClassVar[int]
    FLOAT_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_FIELD_NUMBER: _ClassVar[int]
    NAIVE_DATE_FIELD_NUMBER: _ClassVar[int]
    NAIVE_DATETIME_FIELD_NUMBER: _ClassVar[int]
    UTC_DATETIME_FIELD_NUMBER: _ClassVar[int]
    DECIMAL_FIELD_NUMBER: _ClassVar[int]
    BINARY_FIELD_NUMBER: _ClassVar[int]
    STRING_FIELD_NUMBER: _ClassVar[int]
    JSON_FIELD_NUMBER: _ClassVar[int]
    XML_FIELD_NUMBER: _ClassVar[int]
    NAIVE_TIME_FIELD_NUMBER: _ClassVar[int]
    null: bool
    bool: bool
    short: int
    int: int
    long: int
    float: float
    double: float
    naive_date: _timestamp_pb2.Timestamp
    naive_datetime: _timestamp_pb2.Timestamp
    utc_datetime: _timestamp_pb2.Timestamp
    decimal: str
    binary: bytes
    string: str
    json: str
    xml: str
    naive_time: _timestamp_pb2.Timestamp
    def __init__(self, null: bool = ..., bool: bool = ..., short: _Optional[int] = ..., int: _Optional[int] = ..., long: _Optional[int] = ..., float: _Optional[float] = ..., double: _Optional[float] = ..., naive_date: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., naive_datetime: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., utc_datetime: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., decimal: _Optional[str] = ..., binary: _Optional[bytes] = ..., string: _Optional[str] = ..., json: _Optional[str] = ..., xml: _Optional[str] = ..., naive_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class Table(_message.Message):
    __slots__ = ("name", "columns")
    NAME_FIELD_NUMBER: _ClassVar[int]
    COLUMNS_FIELD_NUMBER: _ClassVar[int]
    name: str
    columns: _containers.RepeatedCompositeFieldContainer[Column]
    def __init__(self, name: _Optional[str] = ..., columns: _Optional[_Iterable[_Union[Column, _Mapping]]] = ...) -> None: ...

class Column(_message.Message):
    __slots__ = ("name", "type", "primary_key", "params")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_KEY_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: DataType
    primary_key: bool
    params: DataTypeParams
    def __init__(self, name: _Optional[str] = ..., type: _Optional[_Union[DataType, str]] = ..., primary_key: bool = ..., params: _Optional[_Union[DataTypeParams, _Mapping]] = ...) -> None: ...

class Warning(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class Task(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...
