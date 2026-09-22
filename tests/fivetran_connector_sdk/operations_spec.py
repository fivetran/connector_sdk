import threading
import unittest

from fivetran_connector_sdk import Operations, constants
from fivetran_connector_sdk.helpers import _validate_table_name, _validate_message, _validate_trace
from fivetran_connector_sdk.protos import common_pb2


def set_debugging_true():
    constants.DEBUGGING = True

def reset_debugging():
    constants.DEBUGGING = False

class TestOperations(unittest.TestCase):

    def setUp(self):
        # set the batch size to 1 for tests
        from fivetran_connector_sdk import operation_stream
        operation_stream.MAX_RECORDS_IN_BATCH = 1

        from fivetran_connector_sdk.operations import Operations, _OperationStream
        # Reset the operation stream for each test
        Operations.operation_stream = _OperationStream()

    def tearDown(self):
        """Clean up global state modified by tests"""
        from fivetran_connector_sdk.constants import TABLES
        from fivetran_connector_sdk.operations import TABLES_COLUMNS_TYPES

        # Clear all entries from both dictionaries
        TABLES.clear()
        TABLES_COLUMNS_TYPES.clear()

    def test_upsert(self):
        Operations.upsert("test_table", {"id": 1, "name": "test"})
        response = next(Operations.operation_stream)

        self.assertEqual(response.structured_records.structured_records[0].table_name, "test_table")
        self.assertEqual(response.structured_records.structured_records[0].type, common_pb2.UPSERT)

    def test_update(self):
        Operations.update("test_table", {"id": 2, "name": "updated"})
        update_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(upsert_response, type(update_response))
        self.assertEqual(update_response.structured_records.structured_records[0].type, common_pb2.UPDATE)

    def test_delete(self):
        Operations.delete("test_table", {"id": 3})
        delete_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(delete_response, type(upsert_response))
        self.assertEqual(delete_response.structured_records.structured_records[0].type, common_pb2.DELETE)

    def test_truncate(self):
        Operations.truncate("test_table")
        response = next(Operations.operation_stream)
        record = response.structured_records.structured_records[0]
        self.assertEqual(record.table_name, "test_table")
        self.assertEqual(record.type, common_pb2.TRUNCATE)
        self.assertEqual(len(record.data), 0)

    def test_truncate_with_nonexistent_table(self):
        Operations.truncate("nonexistent_table")
        response = next(Operations.operation_stream)
        self.assertEqual(response.structured_records.structured_records[0].table_name, "nonexistent_table")
        self.assertEqual(response.structured_records.structured_records[0].type, common_pb2.TRUNCATE)

    def test_truncate_emits_no_schema_name(self):
        Operations.truncate("test_table")
        response = next(Operations.operation_stream)
        self.assertEqual(response.structured_records.structured_records[0].schema_name, "")

    def test_truncate_response_type_matches_upsert(self):
        Operations.truncate("test_table")
        truncate_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(truncate_response, type(upsert_response))

    def test_checkpoint(self):
        state = {"cursor": "2024-01-01T00:00:00.00Z"}
        def generate_checkpoint():
            Operations.checkpoint(state)
            Operations.upsert("test_table", {"id": 1})

        thread = threading.Thread(target=generate_checkpoint)
        thread.start()

        checkpoint_response = next(Operations.operation_stream)
        Operations.operation_stream.unblock()

        upsert_response = next(Operations.operation_stream)

        thread.join()
        self.assertIsInstance(checkpoint_response[0], type(upsert_response))
        self.assertTrue(hasattr(checkpoint_response[0], "checkpoint"))
        self.assertIn("cursor", checkpoint_response[0].checkpoint.state_json)

    def test_update_with_nonexistent_table(self):
        # Should not fail even if table is not in TABLES
        Operations.update("another_table", {"col": 42})
        response = next(Operations.operation_stream)
        self.assertEqual(response.structured_records.structured_records[0].table_name, "another_table")

    def test_delete_with_nonexistent_table(self):
        Operations.delete("yet_another_table", {"col": 99})
        response = next(Operations.operation_stream)
        self.assertEqual(response.structured_records.structured_records[0].table_name, "yet_another_table")

    def test_map_inferred_data_type(self):
        # int, float, bool, bytes, dict, str, object
        from fivetran_connector_sdk.operations import map_inferred_data_type
        import json
        mapped = {}
        map_inferred_data_type("a", mapped, 123)
        self.assertTrue(mapped["a"].HasField("long"))
        self.assertEqual(mapped["a"].long, 123)
        map_inferred_data_type("b", mapped, 1.23)
        self.assertTrue(mapped["b"].HasField("float"))
        self.assertAlmostEqual(mapped["b"].float, 1.23)
        map_inferred_data_type("c", mapped, True)
        self.assertTrue(mapped["c"].HasField("bool"))
        self.assertEqual(mapped["c"].bool, True)
        map_inferred_data_type("d", mapped, b"bytes")
        self.assertTrue(mapped["d"].HasField("binary"))
        self.assertEqual(mapped["d"].binary, b"bytes")
        map_inferred_data_type("e", mapped, {"k": "v"})
        self.assertTrue(mapped["e"].HasField("json"))
        self.assertEqual(json.loads(mapped["e"].json), {"k": "v"})
        map_inferred_data_type("f", mapped, "string")
        self.assertTrue(mapped["f"].HasField("string"))
        self.assertEqual(mapped["f"].string, "string")

        class Dummy: pass

        dummy_obj = Dummy()
        map_inferred_data_type("g", mapped, dummy_obj)
        self.assertTrue(mapped["g"].HasField("string"))
        self.assertTrue(mapped["g"].string == str(dummy_obj))

    def test_map_data_to_columns_mixed_none_and_values(self):
        from fivetran_connector_sdk.operations import _map_data_to_columns
        data = {"nullable": None, "int_val": 42, "str_val": "foo"}
        columns = {}
        mapped = _map_data_to_columns(data, columns)
        self.assertIn("nullable", mapped)
        self.assertTrue(mapped["nullable"].HasField("null"))
        self.assertIn("int_val", mapped)
        self.assertTrue(mapped["int_val"].HasField("long"))
        self.assertIn("str_val", mapped)
        self.assertTrue(mapped["str_val"].HasField("string"))

    def test_map_data_to_columns_defined_type(self):
        from fivetran_connector_sdk.operations import _map_data_to_columns
        from fivetran_connector_sdk.protos import common_pb2
        # Column with type INT
        columns = {"foo": common_pb2.DataType.INT}
        data = {"foo": 42}
        mapped = _map_data_to_columns(data, columns)
        self.assertTrue(mapped["foo"].HasField("int"))
        self.assertEqual(mapped["foo"].int, 42)

    def test_map_defined_data_type_decimal(self):
        from fivetran_connector_sdk.operations import map_defined_data_type
        from fivetran_connector_sdk.protos import common_pb2
        class Col:
            def __init__(self, t): self.type = t
        mapped = {}
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.DECIMAL)}
        map_defined_data_type(columns["a"].type, "a", mapped, "123.45")
        self.assertTrue(mapped["a"].HasField("decimal"))

    def test_map_inferred_data_type_list_as_json(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # Test list inference as JSON
        map_inferred_data_type("a", mapped, [1, 2, 3])
        self.assertTrue(mapped["a"].HasField("json"))
        self.assertEqual(mapped["a"].json, '[1, 2, 3]')

        # Test list with mixed types
        map_inferred_data_type("b", mapped, [1, "two", 3.0, True])
        self.assertTrue(mapped["b"].HasField("json"))
        self.assertEqual(mapped["b"].json, '[1, "two", 3.0, true]')

        # Test nested list
        map_inferred_data_type("c", mapped, [[1, 2], [3, 4]])
        self.assertTrue(mapped["c"].HasField("json"))
        self.assertEqual(mapped["c"].json, '[[1, 2], [3, 4]]')

        # Test empty list
        map_inferred_data_type("d", mapped, [])
        self.assertTrue(mapped["d"].HasField("json"))
        self.assertEqual(mapped["d"].json, '[]')

        # Test list with dict objects
        map_inferred_data_type("e", mapped, [{"key": "value1"}, {"key": "value2"}])
        self.assertTrue(mapped["e"].HasField("json"))
        self.assertEqual(mapped["e"].json, '[{"key": "value1"}, {"key": "value2"}]')

    def test_map_inferred_data_type_dict_as_json(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # Test simple dict
        map_inferred_data_type("a", mapped, {"key": "value"})
        self.assertTrue(mapped["a"].HasField("json"))
        self.assertEqual(mapped["a"].json, '{"key": "value"}')

        # Test nested dict
        map_inferred_data_type("b", mapped, {"outer": {"inner": "value"}})
        self.assertTrue(mapped["b"].HasField("json"))
        self.assertEqual(mapped["b"].json, '{"outer": {"inner": "value"}}')

        # Test empty dict
        map_inferred_data_type("c", mapped, {})
        self.assertTrue(mapped["c"].HasField("json"))
        self.assertEqual(mapped["c"].json, '{}')

        # Test dict with list values
        map_inferred_data_type("d", mapped, {"items": [1, 2, 3]})
        self.assertTrue(mapped["d"].HasField("json"))
        self.assertEqual(mapped["d"].json, '{"items": [1, 2, 3]}')

    def test_map_inferred_data_type_java_long_max(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        from fivetran_connector_sdk.constants import JAVA_LONG_MAX_VALUE
        mapped = {}
        big_val = JAVA_LONG_MAX_VALUE + 1
        map_inferred_data_type("big", mapped, big_val)
        self.assertTrue(mapped["big"].HasField("float"))
        self.assertEqual(mapped["big"].float, big_val)

    def test_map_defined_data_type_all(self):
        from fivetran_connector_sdk.operations import map_defined_data_type
        from fivetran_connector_sdk.protos import common_pb2

        mapped = {}
        # BOOLEAN
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.BOOLEAN)}
        map_defined_data_type(columns["a"].type, "a", mapped, True)
        self.assertTrue(mapped["a"].HasField("bool"))
        # SHORT
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.SHORT)}
        map_defined_data_type(columns["a"].type, "a", mapped, 1)
        self.assertTrue(mapped["a"].HasField("short"))
        # INT
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.INT)}
        map_defined_data_type(columns["a"].type, "a", mapped, 2)
        self.assertTrue(mapped["a"].HasField("int"))
        # LONG
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.LONG)}
        map_defined_data_type(columns["a"].type, "a", mapped, 3)
        self.assertTrue(mapped["a"].HasField("long"))
        # DECIMAL
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.DECIMAL)}
        map_defined_data_type(columns["a"].type, "a", mapped, "1.23")
        self.assertTrue(mapped["a"].HasField("decimal"))
        # FLOAT
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.FLOAT)}
        map_defined_data_type(columns["a"].type, "a", mapped, 1.23)
        self.assertTrue(mapped["a"].HasField("float"))
        # DOUBLE
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.DOUBLE)}
        map_defined_data_type(columns["a"].type, "a", mapped, 1.23)
        self.assertTrue(mapped["a"].HasField("double"))
        # NAIVE_DATE
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.NAIVE_DATE)}
        map_defined_data_type(columns["a"].type, "a", mapped, "2024-01-01")
        self.assertTrue(mapped["a"].HasField("naive_date"))
        self.assertEqual(mapped["a"].naive_date.seconds, 1704067200)
        # NAIVE_DATETIME
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.NAIVE_DATETIME)}
        map_defined_data_type(columns["a"].type, "a", mapped, "2024-01-01T01:02:03.000000")
        self.assertTrue(mapped["a"].HasField("naive_datetime"))
        self.assertEqual(mapped["a"].naive_datetime.seconds, 1704070923)
        # UTC_DATETIME
        from datetime import datetime, timezone
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.UTC_DATETIME)}
        dt = datetime(2024, 1, 1, 1, 2, 3, tzinfo=timezone.utc)
        map_defined_data_type(columns["a"].type, "a", mapped, dt)
        self.assertTrue(mapped["a"].HasField("utc_datetime"))
        self.assertEqual(mapped["a"].utc_datetime.seconds, 1704070923)
        # UTC_DATETIME with string
        map_defined_data_type(columns["a"].type, "a", mapped, "2024-01-01T01:02:03.000000+0000")
        self.assertTrue(mapped["a"].HasField("utc_datetime"))
        self.assertEqual(mapped["a"].utc_datetime.seconds, 1704070923)
        # BINARY
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.BINARY)}
        map_defined_data_type(columns["a"].type, "a", mapped, b"abc")
        self.assertTrue(mapped["a"].HasField("binary"))
        # XML
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.XML)}
        map_defined_data_type(columns["a"].type, "a", mapped, "<xml></xml>")
        self.assertTrue(mapped["a"].HasField("xml"))
        # STRING
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.STRING)}
        map_defined_data_type(columns["a"].type, "a", mapped, "abc")
        self.assertTrue(mapped["a"].HasField("string"))
        # JSON
        columns = {"a": common_pb2.Column(name="a", type=common_pb2.DataType.JSON)}
        map_defined_data_type(columns["a"].type, "a", mapped, {"k": "v"})
        self.assertTrue(mapped["a"].HasField("json"))

    def test_map_defined_data_type_unsupported(self):
        from fivetran_connector_sdk.operations import map_defined_data_type
        class Col:
            def __init__(self, t): self.type = t

        mapped = {}
        with self.assertRaises(ValueError):
            map_defined_data_type({"a": Col(9999)}["a"].type, "a", mapped, "abc")

    def test_map_inferred_data_type_string_patterns(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # Email pattern
        map_inferred_data_type("email", mapped, "user@example.com")
        self.assertTrue(mapped["email"].HasField("string"))
        self.assertEqual(mapped["email"].string, "user@example.com")
        # URL pattern
        map_inferred_data_type("url", mapped, "https://fivetran.com")
        self.assertTrue(mapped["url"].HasField("string"))
        self.assertEqual(mapped["url"].string, "https://fivetran.com")
        # Phone number pattern
        map_inferred_data_type("phone", mapped, "+1-800-555-1234")
        self.assertTrue(mapped["phone"].HasField("string"))
        self.assertEqual(mapped["phone"].string, "+1-800-555-1234")
        # UUID pattern
        map_inferred_data_type("uuid", mapped, "123e4567-e89b-12d3-a456-426614174000")
        self.assertTrue(mapped["uuid"].HasField("string"))
        self.assertEqual(mapped["uuid"].string, "123e4567-e89b-12d3-a456-426614174000")
        # JSON string detection
        map_inferred_data_type("json_str", mapped, '{"foo": "bar"}')
        self.assertTrue(mapped["json_str"].HasField("string"))
        self.assertEqual(mapped["json_str"].string, '{"foo": "bar"}')

    def test_map_inferred_data_type_datetime_formats(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # ISO date
        map_inferred_data_type("iso_date", mapped, "2024-06-01")
        self.assertTrue(mapped["iso_date"].HasField("string"))
        self.assertEqual(mapped["iso_date"].string, "2024-06-01")
        # US date
        map_inferred_data_type("us_date", mapped, "06/01/2024")
        self.assertTrue(mapped["us_date"].HasField("string"))
        self.assertEqual(mapped["us_date"].string, "06/01/2024")
        # European date
        map_inferred_data_type("eu_date", mapped, "01.06.2024")
        self.assertTrue(mapped["eu_date"].HasField("string"))
        self.assertEqual(mapped["eu_date"].string, "01.06.2024")
        # Epoch timestamp
        map_inferred_data_type("epoch", mapped, "1717200000")
        self.assertTrue(mapped["epoch"].HasField("string"))
        self.assertEqual(mapped["epoch"].string, "1717200000")
        # Relative date
        map_inferred_data_type("relative", mapped, "yesterday")
        self.assertTrue(mapped["relative"].HasField("string"))
        self.assertEqual(mapped["relative"].string, "yesterday")

    def test_map_inferred_data_type_datetime_variations(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # Mixed formats
        map_inferred_data_type("mixed", mapped, "06-01/2024")
        self.assertTrue(mapped["mixed"].HasField("string"))
        self.assertEqual(mapped["mixed"].string, "06-01/2024")
        # Partial date
        map_inferred_data_type("partial", mapped, "2024-06")
        self.assertTrue(mapped["partial"].HasField("string"))
        self.assertEqual(mapped["partial"].string, "2024-06")
        # Invalid date
        map_inferred_data_type("invalid", mapped, "not a date")
        self.assertTrue(mapped["invalid"].HasField("string"))
        self.assertEqual(mapped["invalid"].string, "not a date")

    def test_infer_data_types_should_handle_geojson_wkt_address(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # GeoJSON
        geojson = '{"type":"Point","coordinates":[125.6, 10.1]}'
        map_inferred_data_type("geojson", mapped, geojson)
        self.assertTrue(mapped["geojson"].HasField("string"))
        # WKT
        wkt = "POINT (30 10)"
        map_inferred_data_type("wkt", mapped, wkt)
        self.assertTrue(mapped["wkt"].HasField("string"))
        # Address/location
        address = "1600 Amphitheatre Parkway, Mountain View, CA"
        map_inferred_data_type("address", mapped, address)
        self.assertTrue(mapped["address"].HasField("string"))
        # Coordinate pair
        coords = "37.422,-122.084"
        map_inferred_data_type("coords", mapped, coords)
        self.assertTrue(mapped["coords"].HasField("string"))

    def test_infer_data_types_should_handle_corrupted_data(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # Malformed JSON
        malformed_json = '{"foo": "bar"'
        map_inferred_data_type("malformed_json", mapped, malformed_json)
        self.assertTrue(mapped["malformed_json"].HasField("string"))
        # Invalid UTF-8
        invalid_utf8 = b"\xff\xfe\xfd"
        map_inferred_data_type("invalid_utf8", mapped, invalid_utf8)
        self.assertTrue(mapped["invalid_utf8"].HasField("binary"))
        # Extremely long field value
        long_value = "a" * 100000
        map_inferred_data_type("long_value", mapped, long_value)
        self.assertTrue(mapped["long_value"].HasField("string"))
        # Binary data in text field
        binary_in_text = b"\x00\x01\x02"
        map_inferred_data_type("binary_in_text", mapped, binary_in_text)
        self.assertTrue(mapped["binary_in_text"].HasField("binary"))

    def test_infer_data_types_should_handle_schema_evolution(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type
        mapped = {}
        # Type widening: INT -> BIGINT
        map_inferred_data_type("widen", mapped, 2 ** 40)
        self.assertTrue(mapped["widen"].HasField("long") or mapped["widen"].HasField("float"))
        # Type narrowing: BIGINT -> INT
        map_inferred_data_type("narrow", mapped, 42)
        self.assertTrue(mapped["narrow"].HasField("long"))
        # Incompatible type change: INT -> USER-DEFINED DUMMY CLASS
        class Dummy:
            def __str__(self):
                return "dummy-object"

        map_inferred_data_type("custom_obj", mapped, Dummy())
        self.assertTrue(mapped["custom_obj"].HasField("string"))
        self.assertEqual(mapped["custom_obj"].string, "dummy-object")

    def test_map_inferred_data_type_assigns_correct_types_when_some_values_are_null(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type

        mapped_data = {}
        map_inferred_data_type("col_mixed", mapped_data, None)
        map_inferred_data_type("col_mixed", mapped_data, 123)
        self.assertTrue("col_mixed" in mapped_data)
        self.assertFalse(mapped_data["col_mixed"].null)
        self.assertTrue(hasattr(mapped_data["col_mixed"], "long"))

    def test_map_inferred_data_type_infers_float_for_scientific_notation(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type

        mapped_data = {}
        map_inferred_data_type("sci", mapped_data, 1.23e4)
        self.assertTrue(mapped_data["sci"].HasField("float"))
        self.assertEqual(mapped_data["sci"].float, 12300.0)

    def test_map_inferred_data_type_treats_leading_zeros_as_string(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type

        mapped_data = {}
        map_inferred_data_type("lead_zero", mapped_data, "00123")
        self.assertTrue(mapped_data["lead_zero"].HasField("string"))
        self.assertEqual(mapped_data["lead_zero"].string, "00123")

    def test_map_inferred_data_type_infers_string_for_mixed_numeric_and_string(self):
        from fivetran_connector_sdk.operations import map_inferred_data_type

        mapped_data = {}
        map_inferred_data_type("mixed", mapped_data, 42)
        self.assertTrue(mapped_data["mixed"].HasField("long"))
        map_inferred_data_type("mixed", mapped_data, "foo")
        self.assertTrue(mapped_data["mixed"].HasField("string"))
        self.assertEqual(mapped_data["mixed"].string, "foo")
        self.assertFalse(mapped_data["mixed"].HasField("long"))

    def test_connector_sdk_pb2_serialization(self):
        from fivetran_connector_sdk import Operations
        Operations.upsert("test_table", {"id": 1, "name": "test"})
        resp = Operations.operation_stream._queue.get()
        # Should be able to serialize to string (repr) or bytes (if supported)
        s = str(resp)
        self.assertIsInstance(s, str)
        # If protobuf supports SerializeToString, check that too
        if hasattr(resp, "SerializeToString"):
            b = resp.SerializeToString()
            self.assertIsInstance(b, (bytes, bytearray))

    def test_map_defined_data_type_string_with_non_string(self):
        """Test STRING type conversion for non-string values"""
        from fivetran_connector_sdk.operations import map_defined_data_type
        from fivetran_connector_sdk.protos import common_pb2

        mapped = {}
        # Test int to string conversion
        map_defined_data_type(common_pb2.DataType.STRING, "a", mapped, 123)
        self.assertTrue(mapped["a"].HasField("string"))
        self.assertEqual(mapped["a"].string, "123")

        # Test float to string conversion
        map_defined_data_type(common_pb2.DataType.STRING, "b", mapped, 1.23)
        self.assertTrue(mapped["b"].HasField("string"))
        self.assertEqual(mapped["b"].string, "1.23")

        # Test bool to string conversion
        map_defined_data_type(common_pb2.DataType.STRING, "c", mapped, True)
        self.assertTrue(mapped["c"].HasField("string"))
        self.assertEqual(mapped["c"].string, "True")

    def test_upsert_raises_for_empty_table_name(self):
        with self.assertRaises(ValueError):
            Operations.upsert("", {"id": 1})

    def test_upsert_raises_for_whitespace_table_name(self):
        with self.assertRaises(ValueError):
            Operations.upsert("   ", {"id": 1})

    def test_update_raises_for_empty_table_name(self):
        with self.assertRaises(ValueError):
            Operations.update("", {"id": 1})

    def test_update_raises_for_whitespace_table_name(self):
        with self.assertRaises(ValueError):
            Operations.update("   ", {"id": 1})

    def test_delete_raises_for_empty_table_name(self):
        with self.assertRaises(ValueError):
            Operations.delete("", {"id": 1})

    def test_delete_raises_for_whitespace_table_name(self):
        with self.assertRaises(ValueError):
            Operations.delete("   ", {"id": 1})

    def test_truncate_raises_for_empty_table_name(self):
        with self.assertRaises(ValueError):
            Operations.truncate("")

    def test_truncate_raises_for_whitespace_table_name(self):
        with self.assertRaises(ValueError):
            Operations.truncate("   ")

    def test_map_inferred_data_type_handler_dict(self):
        """Test the _INFERENCE_TYPE_HANDLERS dictionary directly"""
        from fivetran_connector_sdk.operations import _INFERENCE_TYPE_HANDLERS, JAVA_LONG_MAX_VALUE
        from fivetran_connector_sdk.protos import common_pb2

        # Test int handler
        result = _INFERENCE_TYPE_HANDLERS[int](100)
        self.assertTrue(result.HasField("long"))
        self.assertEqual(result.long, 100)

        # Test int handler with large value
        large_val = JAVA_LONG_MAX_VALUE + 1
        result = _INFERENCE_TYPE_HANDLERS[int](large_val)
        self.assertTrue(result.HasField("float"))

        # Test float handler
        result = _INFERENCE_TYPE_HANDLERS[float](1.5)
        self.assertTrue(result.HasField("float"))

        # Test bool handler
        result = _INFERENCE_TYPE_HANDLERS[bool](True)
        self.assertTrue(result.HasField("bool"))

        # Test bytes handler
        result = _INFERENCE_TYPE_HANDLERS[bytes](b"test")
        self.assertTrue(result.HasField("binary"))

        # Test dict handler
        result = _INFERENCE_TYPE_HANDLERS[dict]({"key": "value"})
        self.assertTrue(result.HasField("json"))

        # Test str handler
        result = _INFERENCE_TYPE_HANDLERS[str]("test")
        self.assertTrue(result.HasField("string"))


    def test_operations_new_path(self):
        from unittest.mock import patch
        from fivetran_connector_sdk import operations
        from fivetran_connector_sdk.protos import common_pb2

        with patch.object(operations, '_use_row_data', return_value=True):
            for method, expected_type in [
                (Operations.upsert, common_pb2.UPSERT),
                (Operations.update, common_pb2.UPDATE),
                (Operations.delete, common_pb2.DELETE),
            ]:
                Operations.operation_stream = operations._OperationStream()
                method("t", {"id": 1})
                rec = next(Operations.operation_stream).structured_records.structured_records[0]
                self.assertGreater(len(rec.row_data), 0)
                self.assertEqual(len(rec.data), 0)
                self.assertEqual(rec.type, expected_type)

            # truncate is not branched — always uses data={}, never row_data
            Operations.operation_stream = operations._OperationStream()
            Operations.truncate("t")
            rec = next(Operations.operation_stream).structured_records.structured_records[0]
            self.assertEqual(len(rec.row_data), 0)
            self.assertEqual(rec.type, common_pb2.TRUNCATE)

    def test_use_row_data_reads_env_var_set_after_import(self):
        # _use_row_data() must be a live check, not a value frozen at module import -- `fivetran
        # debug` only sets this env var after fivetran_connector_sdk (and this module) has already
        # been imported, so a module-level constant would never see it.
        import os
        from unittest.mock import patch
        from fivetran_connector_sdk import operations

        # Force a known baseline first -- an ambient ConnectorSdkRemoveValueType in the parent
        # process (developer shell, CI) must not affect this test either way.
        with patch.dict(os.environ, {"ConnectorSdkRemoveValueType": "false"}):
            self.assertFalse(operations._use_row_data())
            with patch.dict(os.environ, {"ConnectorSdkRemoveValueType": "true"}):
                self.assertTrue(operations._use_row_data())
            self.assertFalse(operations._use_row_data())

    def test_warning(self):
        import json
        Operations.warning("This is a warning message")
        warning_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(warning_response[0], type(upsert_response))
        self.assertTrue(hasattr(warning_response[0], "warning"))
        message_json = json.loads(warning_response[0].warning.message)
        self.assertEqual(message_json["message"], "This is a warning message")

    def test_error_without_trace_field(self):
        import json
        Operations.error("This is an error message")
        error_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(error_response[0], type(upsert_response))
        self.assertTrue(hasattr(error_response[0], "task"))
        message_json = json.loads(error_response[0].task.message)
        self.assertEqual(message_json["message"], "This is an error message")
        self.assertNotIn("trace", message_json)

    def test_error_with_trace_field(self):
        import json
        Operations.error("This is an error message", trace="Stack trace here")
        error_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(error_response[0], type(upsert_response))
        self.assertTrue(hasattr(error_response[0], "task"))
        message_json = json.loads(error_response[0].task.message)
        self.assertEqual(message_json["message"], "This is an error message")
        self.assertEqual(message_json["trace"], "Stack trace here")

    def test_error_with_blank_trace_field(self):
        import json
        Operations.error("This is an error message", trace="   ")
        error_response = next(Operations.operation_stream)
        Operations.upsert("test_table", {"id": 1})
        upsert_response = next(Operations.operation_stream)
        self.assertIsInstance(error_response[0], type(upsert_response))
        self.assertTrue(hasattr(error_response[0], "task"))
        message_json = json.loads(error_response[0].task.message)
        self.assertEqual(message_json["message"], "This is an error message")
        self.assertNotIn("trace", message_json)

    def test_error_raises_for_empty_message(self):
        with self.assertRaises(ValueError):
            Operations.error("")

    def test_error_raises_for_whitespace_message(self):
        with self.assertRaises(ValueError):
            Operations.error("   ")

    def test_error_raises_type_error_for_non_string_message(self):
        with self.assertRaises(TypeError):
            Operations.error(123)

    def test_warning_raises_for_empty_message(self):
        with self.assertRaises(ValueError):
            Operations.warning("")

    def test_warning_raises_for_whitespace_message(self):
        with self.assertRaises(ValueError):
            Operations.warning("   ")

    def test_warning_raises_type_error_for_non_string_message(self):
        with self.assertRaises(TypeError):
            Operations.warning(123)

    def test_error_raises_type_error_for_non_string_trace(self):
        with self.assertRaises(TypeError):
            Operations.error("Something went wrong", trace=12345)

    def test_error_allows_none_trace(self):
        Operations.error("Something went wrong")

class TestValidateMessage(unittest.TestCase):

    def test_raises_for_empty_string(self):
        with self.assertRaises(ValueError):
            _validate_message("")

    def test_raises_for_whitespace_string(self):
        with self.assertRaises(ValueError):
            _validate_message("   ")

    def test_raises_type_error_for_non_string(self):
        with self.assertRaises(TypeError):
            _validate_message(123)

    def test_valid_message(self):
        _validate_message("Something went wrong")

class TestValidateTrace(unittest.TestCase):

    def test_allows_none(self):
        _validate_trace(None)

    def test_allows_valid_string(self):
        _validate_trace("Stack trace here")

    def test_allows_empty_string(self):
        # An empty/blank trace is valid -- it's simply omitted from the payload.
        _validate_trace("")

    def test_raises_type_error_for_non_string(self):
        with self.assertRaises(TypeError):
            _validate_trace(12345)

class TestValidateTableName(unittest.TestCase):

    def test_raises_for_empty_string(self):
        with self.assertRaises(ValueError):
            _validate_table_name("")

    def test_raises_for_whitespace_string(self):
        with self.assertRaises(ValueError):
            _validate_table_name("   ")

    def test_raises_type_error_for_non_string(self):
        with self.assertRaises(TypeError):
            _validate_table_name(123)

    def test_valid_table_name(self):
        _validate_table_name("orders")

    def test_valid_table_name_with_numeric_characters(self):
        _validate_table_name("table123")

if __name__ == "__main__":
    unittest.main()
