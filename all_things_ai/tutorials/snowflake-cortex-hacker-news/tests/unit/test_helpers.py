"""Unit tests for connector helper functions.

Covers flatten_dict (Fivetran-required nested-to-flat transform),
parse_cortex_streaming_response (SSE parsing), and extract_json_from_content
(LLM output JSON extraction).
"""

import json

import connector


class TestFlattenDict:
    def test_flat_unchanged(self):
        assert connector.flatten_dict({"a": 1}) == {"a": 1}

    def test_nested_underscore(self):
        assert connector.flatten_dict({"a": {"b": 1}}) == {"a_b": 1}

    def test_deep_nesting(self):
        assert connector.flatten_dict({"a": {"b": {"c": 1}}}) == {"a_b_c": 1}

    def test_list_serialized_to_json(self):
        result = connector.flatten_dict({"keywords": ["ml", "ai"]})
        assert json.loads(result["keywords"]) == ["ml", "ai"]

    def test_empty_list_becomes_none(self):
        assert connector.flatten_dict({"items": []}) == {"items": None}

    def test_preserves_none_values(self):
        assert connector.flatten_dict({"a": None}) == {"a": None}


class TestParseCortexStreamingResponse:
    """Cortex inference response is a synchronous body containing
    SSE-formatted lines; the parser must concatenate the content deltas
    across all data: events and ignore non-data lines."""

    def _make_response(self, body):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.text = body
        return resp

    def test_single_data_event(self):
        body = 'data: {"choices":[{"delta":{"content":"Hello"}}]}\n'
        result = connector.parse_cortex_streaming_response(self._make_response(body))
        assert result == "Hello"

    def test_multiple_data_events_concatenated(self):
        body = (
            'data: {"choices":[{"delta":{"content":"Hello "}}]}\n'
            'data: {"choices":[{"delta":{"content":"world"}}]}\n'
        )
        result = connector.parse_cortex_streaming_response(self._make_response(body))
        assert result == "Hello world"

    def test_non_data_lines_ignored(self):
        body = "event: start\n" 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n' "event: end\n"
        result = connector.parse_cortex_streaming_response(self._make_response(body))
        assert result == "Hi"

    def test_malformed_json_skipped(self):
        body = "data: not json at all\n" 'data: {"choices":[{"delta":{"content":"OK"}}]}\n'
        result = connector.parse_cortex_streaming_response(self._make_response(body))
        assert result == "OK"

    def test_missing_choices_skipped(self):
        body = 'data: {"unrelated":"key"}\n' 'data: {"choices":[{"delta":{"content":"OK"}}]}\n'
        result = connector.parse_cortex_streaming_response(self._make_response(body))
        assert result == "OK"

    def test_empty_body_returns_empty_string(self):
        result = connector.parse_cortex_streaming_response(self._make_response(""))
        assert result == ""


class TestExtractJsonFromContent:
    """LLM output may include surrounding prose; the extractor finds the
    first '{' and the last '}' and tries to json.loads that range."""

    def test_returns_none_for_no_braces(self):
        assert connector.extract_json_from_content("just plain text") is None

    def test_returns_none_for_empty(self):
        assert connector.extract_json_from_content("") is None

    def test_parses_clean_json(self):
        result = connector.extract_json_from_content('{"sentiment":"positive","score":0.9}')
        assert result == {"sentiment": "positive", "score": 0.9}

    def test_parses_json_inside_text(self):
        text = 'Here is the analysis: {"category":"AI"} done.'
        assert connector.extract_json_from_content(text) == {"category": "AI"}

    def test_returns_none_for_malformed_json(self):
        assert connector.extract_json_from_content("{not valid json") is None

    def test_handles_nested_objects(self):
        text = '{"outer": {"inner": "value"}, "list": [1,2]}'
        assert connector.extract_json_from_content(text) == {
            "outer": {"inner": "value"},
            "list": [1, 2],
        }
