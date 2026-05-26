"""Unit tests for connector helper functions.

# see snowflake-cortex-code-clinical-trial-intelligence/tests/unit/test_helpers.py
# for the analogous Cortex-side helper tests.
"""

import json

import connector


class TestIsPlaceholder:
    """_is_placeholder must be type-safe."""

    def test_none_is_placeholder(self):
        assert connector._is_placeholder(None) is True

    def test_empty_string_is_placeholder(self):
        assert connector._is_placeholder("") is True

    def test_angle_bracketed_is_placeholder(self):
        assert connector._is_placeholder("<BESTBUY_API_KEY>") is True
        assert connector._is_placeholder("<DATABRICKS_PAT_TOKEN>") is True

    def test_real_value_is_not_placeholder(self):
        assert connector._is_placeholder("real_api_key") is False
        assert connector._is_placeholder("https://abc.cloud.databricks.com") is False

    def test_partial_brackets_are_not_placeholder(self):
        assert connector._is_placeholder("<only-open") is False
        assert connector._is_placeholder("only-close>") is False

    def test_non_string_non_none_is_not_placeholder(self):
        """Type-safety regression — must not AttributeError on int/bool inputs."""
        assert connector._is_placeholder(42) is False
        assert connector._is_placeholder(True) is False
        assert connector._is_placeholder(0) is False


class TestParseBool:
    def test_bool_passthrough(self):
        assert connector._parse_bool(True) is True
        assert connector._parse_bool(False) is False

    def test_placeholder_returns_default(self):
        assert connector._parse_bool("<TRUE_OR_FALSE>", default=True) is True
        assert connector._parse_bool("<TRUE_OR_FALSE>", default=False) is False

    def test_none_returns_default(self):
        assert connector._parse_bool(None, default=True) is True

    def test_string_true_variants(self):
        assert connector._parse_bool("true") is True
        assert connector._parse_bool("TRUE") is True
        assert connector._parse_bool("  true  ") is True

    def test_non_true_strings_are_false(self):
        assert connector._parse_bool("false") is False
        assert connector._parse_bool("yes") is False
        assert connector._parse_bool("1") is False


class TestOptionalInt:
    def test_placeholder_returns_default(self):
        assert connector._optional_int({}, "foo", 42) == 42
        assert connector._optional_int({"foo": "<X>"}, "foo", 42) == 42

    def test_valid_int_string(self):
        assert connector._optional_int({"foo": "7"}, "foo", 42) == 7

    def test_invalid_int_returns_default(self):
        assert connector._optional_int({"foo": "abc"}, "foo", 42) == 42

    def test_none_returns_default(self):
        assert connector._optional_int({"foo": None}, "foo", 42) == 42


class TestOptionalStr:
    def test_placeholder_returns_default(self):
        assert connector._optional_str({}, "foo", "default") == "default"
        assert connector._optional_str({"foo": "<X>"}, "foo", "default") == "default"

    def test_valid_string(self):
        assert connector._optional_str({"foo": "value"}, "foo", "default") == "value"


class TestFlattenDict:
    def test_flat_unchanged(self):
        assert connector.flatten_dict({"a": 1}) == {"a": 1}

    def test_nested_underscore(self):
        assert connector.flatten_dict({"a": {"b": 1}}) == {"a_b": 1}

    def test_list_serialized(self):
        result = connector.flatten_dict({"items": [1, 2]})
        assert json.loads(result["items"]) == [1, 2]

    def test_empty_list_becomes_none(self):
        result = connector.flatten_dict({"items": []})
        assert result["items"] is None


class TestExtractJsonFromContent:
    def test_returns_none_for_no_json(self):
        assert connector.extract_json_from_content("just plain text") is None

    def test_returns_none_for_empty(self):
        assert connector.extract_json_from_content("") is None
        assert connector.extract_json_from_content(None) is None

    def test_parses_clean_json(self):
        result = connector.extract_json_from_content('{"a": 1, "b": "two"}')
        assert result == {"a": 1, "b": "two"}

    def test_parses_json_inside_text(self):
        text = 'Here is the analysis: {"competitive_positioning": "PREMIUM"} done.'
        assert connector.extract_json_from_content(text) == {"competitive_positioning": "PREMIUM"}

    def test_returns_none_for_malformed_json(self):
        assert connector.extract_json_from_content("{not valid json at all") is None


class TestBuildProductRecord:
    def test_minimal_returns_required_keys(self, minimal_product):
        record = connector.build_product_record(minimal_product)
        assert record["sku"] == "123456"
        assert record["name"] == "Test Product"
        assert record["sale_price"] == 199.99
        assert record["manufacturer"] == "TestBrand"
        assert record["category"] == "Laptops"

    def test_category_path_serialized_as_json(self, minimal_product):
        record = connector.build_product_record(minimal_product)
        assert json.loads(record["category_path"]) == ["Computers", "Laptops"]

    def test_short_description_truncated_to_500(self):
        product = {"sku": 1, "shortDescription": "x" * 600}
        record = connector.build_product_record(product)
        assert record["short_description"] is not None
        assert len(record["short_description"]) == 500

    def test_missing_optional_fields_become_none(self):
        product = {"sku": 1}
        record = connector.build_product_record(product)
        assert record["sku"] == "1"
        assert record["name"] is None
        assert record["sale_price"] is None
        assert record["category"] is None
