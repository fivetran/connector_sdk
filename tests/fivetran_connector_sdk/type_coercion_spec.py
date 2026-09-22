import unittest

from fivetran_connector_sdk.type_coercion import (
    _coerce_boolean, _coerce_integer, _coerce_float_type, _coerce_double_type,
    _coerce_utc_datetime, _coerce_naive_datetime, _coerce_naive_date,
    _coerce_json, _coerce_string, _coerce_decimal, _coerce_xml,
    _coerce_binary_type, _coerce_inferred,
    _encode_row_data,
    _parse_utc_datetime_str, _parse_naive_datetime_str, _parse_naive_date_str,
    _NULL_V, _PFX_SCALAR, _PFX_JSON, _PFX_BINARY, _PFX_FLOAT, _PFX_DOUBLE,
)
from fivetran_connector_sdk.constants import JAVA_LONG_MAX_VALUE, TABLES_COLUMNS_TYPES
from fivetran_connector_sdk.protos import common_pb2


class TestTypeCoercion(unittest.TestCase):

    def tearDown(self):
        TABLES_COLUMNS_TYPES.clear()

    def test_coerce_scalars(self):
        # boolean: bool/int accepted; "0"/"1" strings mapped to false/true
        self.assertEqual(_coerce_boolean(True),  (_PFX_SCALAR, b"true"))
        self.assertEqual(_coerce_boolean(False), (_PFX_SCALAR, b"false"))
        self.assertEqual(_coerce_boolean(0),     (_PFX_SCALAR, b"false"))
        self.assertEqual(_coerce_boolean("0"),   (_PFX_SCALAR, b"false"))
        self.assertEqual(_coerce_boolean("1"),   (_PFX_SCALAR, b"true"))
        # float accepted (safe extension — produces "true"/"false" destinations handle)
        self.assertEqual(_coerce_boolean(1.5),         (_PFX_SCALAR, b"true"))
        self.assertEqual(_coerce_boolean(0.0),         (_PFX_SCALAR, b"false"))
        self.assertEqual(_coerce_boolean(float("nan")), (_PFX_SCALAR, b"true"))
        # arbitrary strings rejected — would silently corrupt data at destination
        with self.assertRaises(TypeError):
            _coerce_boolean("yes")
        with self.assertRaises(TypeError):
            _coerce_boolean("true")
        with self.assertRaises(TypeError):
            _coerce_boolean("false")
        with self.assertRaises(TypeError):
            _coerce_boolean({"k": "v"})

        # integer: only int accepted; float rejected (was silently truncating)
        self.assertEqual(_coerce_integer(42),    (_PFX_SCALAR, b"42"))
        self.assertEqual(_coerce_integer(-7),    (_PFX_SCALAR, b"-7"))
        self.assertEqual(_coerce_integer(True),  (_PFX_SCALAR, b"1"))
        self.assertEqual(_coerce_integer(False), (_PFX_SCALAR, b"0"))
        with self.assertRaises(TypeError):
            _coerce_integer(3.9)

        # float: normal value and IEEE specials
        self.assertEqual(_coerce_float_type(1.5),  (_PFX_FLOAT, b"1.5"))
        self.assertEqual(_coerce_float_type(float("nan")),  (_PFX_FLOAT, b"NaN"))
        self.assertEqual(_coerce_float_type(float("inf")),  (_PFX_FLOAT, b"Infinity"))
        self.assertEqual(_coerce_float_type(float("-inf")), (_PFX_FLOAT, b"-Infinity"))

    def test_coerce_datetimes(self):
        from datetime import datetime, date, timezone
        # utc_datetime: aware, naive (gets Z appended), date, string with space + no-colon offset
        self.assertEqual(_coerce_utc_datetime(datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)),
                         (_PFX_SCALAR, b"2025-06-01T12:00:00Z"))
        self.assertEqual(_coerce_utc_datetime(datetime(2025, 6, 1, 12, 0, 0)),
                         (_PFX_SCALAR, b"2025-06-01T12:00:00Z"))
        self.assertEqual(_coerce_utc_datetime(date(2025, 6, 1)),
                         (_PFX_SCALAR, b"2025-06-01T00:00:00Z"))
        self.assertEqual(_coerce_utc_datetime("2025-06-01 12:00:00+0530"),
                         (_PFX_SCALAR, b"2025-06-01T06:30:00Z"))
        # naive_datetime: naive datetime, date, string with space separator
        self.assertEqual(_coerce_naive_datetime(datetime(2025, 6, 1, 12, 0, 0)),
                         (_PFX_SCALAR, b"2025-06-01T12:00:00"))
        self.assertEqual(_coerce_naive_datetime(date(2025, 6, 1)),
                         (_PFX_SCALAR, b"2025-06-01T00:00:00"))
        self.assertEqual(_coerce_naive_datetime("2025-06-01 12:00:00"),
                         (_PFX_SCALAR, b"2025-06-01T12:00:00"))
        # naive_date: date, datetime (extracts date part), string
        self.assertEqual(_coerce_naive_date(date(2025, 6, 1)),               (_PFX_SCALAR, b"2025-06-01"))
        self.assertEqual(_coerce_naive_date(datetime(2025, 6, 1, 12, 0, 0)), (_PFX_SCALAR, b"2025-06-01"))
        self.assertEqual(_coerce_naive_date("2025-06-01"),                   (_PFX_SCALAR, b"2025-06-01"))

    def test_coerce_json_and_binary(self):
        import json
        # json: all values go through json.dumps — strings are quoted as JSON string literals
        pfx, val = _coerce_json("hello")
        self.assertEqual(pfx, _PFX_JSON)
        self.assertEqual(json.loads(val), "hello")  # round-trips correctly

        pfx, val = _coerce_json({"a": 1})
        self.assertEqual(pfx, _PFX_JSON)
        self.assertEqual(json.loads(val), {"a": 1})

        pfx, val = _coerce_json([1, 2, 3])
        self.assertEqual(pfx, _PFX_JSON)
        self.assertEqual(json.loads(val), [1, 2, 3])

        # binary: bytes and bytearray accepted; non-bytes rejected with TypeError
        self.assertEqual(_coerce_binary_type(b"\x01\x02"),        (_PFX_BINARY, b"\x01\x02"))
        self.assertEqual(_coerce_binary_type(bytearray(b"\x03")), (_PFX_BINARY, b"\x03"))
        with self.assertRaises(TypeError):
            _coerce_binary_type("text")
        with self.assertRaises(TypeError):
            _coerce_binary_type(42)
        with self.assertRaises(TypeError):
            _coerce_binary_type({"k": "v"})

    def test_coerce_string(self):
        # str passthrough
        self.assertEqual(_coerce_string("hello"),    (_PFX_SCALAR, b"hello"))
        self.assertEqual(_coerce_string(""),         (_PFX_SCALAR, b""))
        # non-str converted via str() — matches production ValueType(string=str(val)) behavior
        self.assertEqual(_coerce_string(3.14),       (_PFX_SCALAR, b"3.14"))
        self.assertEqual(_coerce_string(True),       (_PFX_SCALAR, b"True"))   # capital T — matches production
        self.assertEqual(_coerce_string(False),      (_PFX_SCALAR, b"False"))  # capital F — matches production
        self.assertEqual(_coerce_string(42),         (_PFX_SCALAR, b"42"))
        # bytes and dicts become their Python repr (same as production str(val))
        self.assertEqual(_coerce_string(b"hi"),      (_PFX_SCALAR, b"b'hi'"))
        pfx, val = _coerce_string({"k": "v"})
        self.assertEqual(pfx, _PFX_SCALAR)
        self.assertIn(b"k", val)  # Python dict repr contains the key

    def test_coerce_decimal(self):
        # str accepted
        self.assertEqual(_coerce_decimal("123.45"),  (_PFX_SCALAR, b"123.45"))
        self.assertEqual(_coerce_decimal("-0"),       (_PFX_SCALAR, b"-0"))
        self.assertEqual(_coerce_decimal("+100.00"),  (_PFX_SCALAR, b"+100.00"))
        # int accepted (new capability — Java parseToBigDecimal handles it)
        self.assertEqual(_coerce_decimal(42),         (_PFX_SCALAR, b"42"))
        self.assertEqual(_coerce_decimal(-7),         (_PFX_SCALAR, b"-7"))
        # float rejected — would produce FLOAT tag causing destination type mismatch
        with self.assertRaises(TypeError):
            _coerce_decimal(3.14)
        with self.assertRaises(TypeError):
            _coerce_decimal(float("nan"))
        # bool rejected — bool is int subclass but "True"/"False" are not valid decimal strings
        with self.assertRaises(TypeError):
            _coerce_decimal(True)
        with self.assertRaises(TypeError):
            _coerce_decimal(False)

    def test_coerce_xml(self):
        # str accepted
        self.assertEqual(_coerce_xml("<root/>"),           (_PFX_SCALAR, b"<root/>"))
        self.assertEqual(_coerce_xml("<a>text</a>"),       (_PFX_SCALAR, b"<a>text</a>"))
        self.assertEqual(_coerce_xml("plain string"),      (_PFX_SCALAR, b"plain string"))
        # non-str rejected — would produce wrong type tag (FLOAT/JSON/BINARY)
        with self.assertRaises(TypeError):
            _coerce_xml(42)
        with self.assertRaises(TypeError):
            _coerce_xml({"k": "v"})
        with self.assertRaises(TypeError):
            _coerce_xml(b"<root/>")

    def test_coerce_inferred(self):
        import json
        self.assertEqual(_coerce_inferred("hello"), (_PFX_SCALAR, b"hello"))
        self.assertEqual(_coerce_inferred(True),    (_PFX_SCALAR, b"true"))
        self.assertEqual(_coerce_inferred(False),   (_PFX_SCALAR, b"false"))
        self.assertEqual(_coerce_inferred(42),      (_PFX_SCALAR, b"42"))
        self.assertEqual(_coerce_inferred(b"\xff"), (_PFX_BINARY, b"\xff"))

        pfx, val = _coerce_inferred({"k": "v"})
        self.assertEqual(pfx, _PFX_JSON)
        self.assertEqual(json.loads(val), {"k": "v"})

        pfx, val = _coerce_inferred([1, 2])
        self.assertEqual(pfx, _PFX_JSON)
        self.assertEqual(json.loads(val), [1, 2])

        # large int → float-encoded string, not a raw integer string
        pfx, val = _coerce_inferred(JAVA_LONG_MAX_VALUE + 1)
        self.assertEqual(pfx, _PFX_FLOAT)
        self.assertNotEqual(val, str(JAVA_LONG_MAX_VALUE + 1).encode())

        # float IEEE specials
        self.assertEqual(_coerce_inferred(float("nan")),  (_PFX_FLOAT, b"NaN"))
        self.assertEqual(_coerce_inferred(float("inf")),  (_PFX_FLOAT, b"Infinity"))
        self.assertEqual(_coerce_inferred(float("-inf")), (_PFX_FLOAT, b"-Infinity"))

        # custom object → str representation
        class Dummy:
            def __str__(self): return "dummy"
        self.assertEqual(_coerce_inferred(Dummy()), (_PFX_SCALAR, b"dummy"))

    def test_encode_row_data(self):
        import json
        self.assertEqual(_encode_row_data({}, {"col": None})["col"], _NULL_V)

        TABLES_COLUMNS_TYPES["t"] = {"flag": common_pb2.DataType.BOOLEAN}
        self.assertEqual(
            _encode_row_data(TABLES_COLUMNS_TYPES["t"], {"flag": True})["flag"],
            _PFX_SCALAR + b"true",
        )

        # STRING column: always SCALAR tag regardless of Python type
        TABLES_COLUMNS_TYPES["t2"] = {"s": common_pb2.DataType.STRING}
        self.assertEqual(_encode_row_data(TABLES_COLUMNS_TYPES["t2"], {"s": 3.14})["s"],
                         _PFX_SCALAR + b"3.14")
        self.assertEqual(_encode_row_data(TABLES_COLUMNS_TYPES["t2"], {"s": True})["s"],
                         _PFX_SCALAR + b"True")

        # DECIMAL column: SCALAR tag for str/int; TypeError for float
        TABLES_COLUMNS_TYPES["t3"] = {"d": common_pb2.DataType.DECIMAL}
        self.assertEqual(_encode_row_data(TABLES_COLUMNS_TYPES["t3"], {"d": "1.23"})["d"],
                         _PFX_SCALAR + b"1.23")
        with self.assertRaises(TypeError):
            _encode_row_data(TABLES_COLUMNS_TYPES["t3"], {"d": 1.23})

        # XML column: SCALAR tag for str; TypeError for non-str
        TABLES_COLUMNS_TYPES["t4"] = {"x": common_pb2.DataType.XML}
        self.assertEqual(_encode_row_data(TABLES_COLUMNS_TYPES["t4"], {"x": "<root/>"})["x"],
                         _PFX_SCALAR + b"<root/>")
        with self.assertRaises(TypeError):
            _encode_row_data(TABLES_COLUMNS_TYPES["t4"], {"x": 42})

        # inferred path (no column type declared)
        self.assertEqual(_encode_row_data({}, {"name": "alice"})["name"], _PFX_SCALAR + b"alice")
        self.assertEqual(_encode_row_data({}, {"x": 7})["x"], _PFX_SCALAR + b"7")

    def test_parse_utc_datetime_str(self):
        from datetime import datetime, timezone
        from google.protobuf import timestamp_pb2

        # Case 1: Test with datetime object
        dt = datetime(2025, 8, 12, 15, 0, 0, 123456, tzinfo=timezone.utc)
        ts = _parse_utc_datetime_str(dt)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        self.assertEqual(ts.seconds, int(dt.timestamp()))

        # Case 2: Test with ISO format string with microseconds
        dt_str = "2025-08-12T15:00:00.123456+00:00"
        ts = _parse_utc_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        self.assertEqual(ts.seconds, int(datetime(2025, 8, 12, 15, 0, 0, 123456, tzinfo=timezone.utc).timestamp()))

        # Case 3: Test with ISO format string without microseconds
        dt_str = "2025-08-12T15:00:00+00:00"
        ts = _parse_utc_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        self.assertEqual(ts.seconds, int(datetime(2025, 8, 12, 15, 0, 0, tzinfo=timezone.utc).timestamp()))

        # Case 4: Test with datetime string with space instead of 'T'
        dt_str = str(datetime(2025, 8, 12, 15, 0, 0, tzinfo=timezone.utc))
        ts = _parse_utc_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        self.assertEqual(ts.seconds, int(datetime.fromisoformat(dt_str).timestamp()))
        self.assertEqual(ts.seconds, int(datetime(2025, 8, 12, 15, 0, 0, tzinfo=timezone.utc).timestamp()))

        # Case 5: Test with ISO format string with different timezone offset
        dt_str = "2025-01-01T20:00:00.00000+0530"
        ts = _parse_utc_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        self.assertEqual(ts.seconds, 1735741800)

    def test_parse_naive_datetime_str(self):
        from datetime import datetime, timezone
        from google.protobuf import timestamp_pb2

        # Case 1: Test with datetime object
        dt = datetime(2025, 8, 12, 15, 0, 0, 123456)
        ts = _parse_naive_datetime_str(dt)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        dt_utc = dt.replace(tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(dt_utc.timestamp()))
        self.assertEqual(ts.nanos, dt_utc.microsecond * 1000)

        # Case 2: Test with ISO format string with microseconds
        dt_str = "2025-08-12T15:00:00.123456"
        ts = _parse_naive_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        expected_dt = datetime(2025, 8, 12, 15, 0, 0, 123456, tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(expected_dt.timestamp()))
        self.assertEqual(ts.nanos, expected_dt.microsecond * 1000)

        # Case 3: Test with ISO format string without microseconds
        dt_str = "2025-08-12T15:00:00"
        ts = _parse_naive_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        expected_dt = datetime(2025, 8, 12, 15, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(expected_dt.timestamp()))
        self.assertEqual(ts.nanos, 0)

        # Case 4: Test with datetime string with space instead of 'T'
        dt_str = str(datetime(2025, 8, 12, 15, 0, 0))
        ts = _parse_naive_datetime_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        expected_dt = datetime(2025, 8, 12, 15, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(expected_dt.timestamp()))
        self.assertEqual(ts.nanos, expected_dt.microsecond * 1000)

    def test_parse_naive_date_str(self):
        from datetime import datetime, timezone
        from google.protobuf import timestamp_pb2

        # Case 1: Test with datetime object
        dt = datetime(2025, 8, 12)
        ts = _parse_naive_date_str(dt)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        dt_utc = dt.replace(tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(dt_utc.timestamp()))
        self.assertEqual(ts.nanos, dt_utc.microsecond * 1000)

        # Case 2: Test with date string
        dt_str = "2025-08-12"
        ts = _parse_naive_date_str(dt_str)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        expected_dt = datetime(2025, 8, 12, 0, 0, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(expected_dt.timestamp()))
        self.assertEqual(ts.nanos, expected_dt.microsecond * 1000)

        # Case 3: Test with ISO format string with time — should raise ValueError
        with self.assertRaises(ValueError):
            _parse_naive_date_str("2025-08-12T15:00:00")

    def test_parse_naive_date_str_with_date_object(self):
        from datetime import date, datetime, timezone
        from google.protobuf import timestamp_pb2

        d = date(2025, 8, 12)
        ts = _parse_naive_date_str(d)
        self.assertIsInstance(ts, timestamp_pb2.Timestamp)
        expected_dt = datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)
        self.assertEqual(ts.seconds, int(expected_dt.timestamp()))

    def test_parse_naive_date_str_invalid_type(self):
        with self.assertRaises(TypeError):
            _parse_naive_date_str(12345)


if __name__ == "__main__":
    unittest.main()
