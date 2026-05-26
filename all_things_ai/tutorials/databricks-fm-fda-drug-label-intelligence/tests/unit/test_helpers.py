"""Unit tests for connector helper functions."""

import json

import connector


class TestIsPlaceholder:
    def test_none_is_placeholder(self):
        assert connector._is_placeholder(None) is True

    def test_empty_string_is_placeholder(self):
        assert connector._is_placeholder("") is True

    def test_angle_bracketed_is_placeholder(self):
        assert connector._is_placeholder("<DATABRICKS_TOKEN>") is True

    def test_real_value_is_not_placeholder(self):
        assert connector._is_placeholder("dapi_real_token") is False

    def test_non_string_non_none_is_not_placeholder(self):
        """Type-safety regression — must not AttributeError on int/bool inputs."""
        assert connector._is_placeholder(42) is False
        assert connector._is_placeholder(True) is False


class TestParseBool:
    def test_bool_passthrough(self):
        assert connector._parse_bool(True) is True
        assert connector._parse_bool(False) is False

    def test_placeholder_returns_default(self):
        assert connector._parse_bool("<TRUE_OR_FALSE>", default=True) is True
        assert connector._parse_bool("<TRUE_OR_FALSE>", default=False) is False

    def test_string_true_variants(self):
        assert connector._parse_bool("true") is True
        assert connector._parse_bool("TRUE") is True

    def test_non_true_strings_are_false(self):
        assert connector._parse_bool("false") is False
        assert connector._parse_bool("yes") is False


class TestOptionalInt:
    def test_placeholder_returns_default(self):
        assert connector._optional_int({"foo": "<X>"}, "foo", 42) == 42

    def test_valid_int_string(self):
        assert connector._optional_int({"foo": "7"}, "foo", 42) == 7

    def test_invalid_int_returns_default(self):
        assert connector._optional_int({"foo": "abc"}, "foo", 42) == 42


class TestOptionalStr:
    def test_placeholder_returns_default(self):
        assert connector._optional_str({"foo": "<X>"}, "foo", "default") == "default"

    def test_valid_string(self):
        assert connector._optional_str({"foo": "value"}, "foo", "default") == "value"


class TestFlattenDict:
    def test_flat_unchanged(self):
        assert connector.flatten_dict({"a": 1}) == {"a": 1}

    def test_nested_underscore(self):
        assert connector.flatten_dict({"a": {"b": 1}}) == {"a_b": 1}

    def test_list_serialized_to_json(self):
        result = connector.flatten_dict({"items": [1, 2]})
        assert json.loads(result["items"]) == [1, 2]

    def test_empty_list_becomes_none(self):
        assert connector.flatten_dict({"items": []}) == {"items": None}


class TestTruncateText:
    def test_short_text_unchanged(self):
        assert connector.truncate_text("hello", 100) == "hello"

    def test_truncates_long_text(self):
        """Long text is truncated and an ellipsis suffix is appended."""
        long = "x" * 5000
        result = connector.truncate_text(long, 1000)
        # 1000 chars + "... [truncated]" suffix (15 chars)
        assert result.startswith("x" * 1000)
        assert result.endswith("... [truncated]")

    def test_handles_none(self):
        """None input returns empty string (not None) to keep prompt formatting safe."""
        assert connector.truncate_text(None, 100) == ""


class TestExtractLabelTextSections:
    def test_extracts_known_keys(self):
        label = {
            "indications_and_usage": ["Aspirin is for headache."],
            "warnings": ["Do not take aspirin if allergic."],
        }
        sections = connector.extract_label_text_sections(label)
        assert "indications_and_usage" in sections
        assert "warnings" in sections

    def test_missing_keys_become_none(self):
        sections = connector.extract_label_text_sections({})
        assert sections.get("warnings") is None or sections.get("warnings") == ""


class TestBuildLabelId:
    def test_set_id_with_version(self):
        assert connector.build_label_id({"set_id": "abc", "version": "1"}) == "abc_1"

    def test_falls_back_to_id_when_set_id_missing(self):
        assert connector.build_label_id({"id": "doc99", "version": "5"}) == "doc99"

    def test_deterministic(self):
        label = {"set_id": "abc", "version": "1"}
        assert connector.build_label_id(label) == connector.build_label_id(label)


class TestExtractJsonFromContent:
    def test_returns_none_for_no_json(self):
        assert connector.extract_json_from_content("just plain text") is None

    def test_parses_clean_json(self):
        result = connector.extract_json_from_content('{"sentiment": "positive"}')
        assert result == {"sentiment": "positive"}

    def test_returns_none_for_malformed_json(self):
        assert connector.extract_json_from_content("{not valid") is None
