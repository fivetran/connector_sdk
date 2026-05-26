"""Tests for the Genie Space creation path.

Covers: happy path (space_id returned), idempotency (existing space_id skips
POST), API failure returns None, and payload shape (question/content are
strings, not single-element lists).
"""

import json
from unittest.mock import MagicMock

import pytest
import requests as _requests

import connector


def _make_response(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def genie_config(base_config):
    """Base config extended with genie enabled and a real table identifier."""
    return {
        **base_config,
        "enable_genie_space": "true",
        "genie_table_identifier": "catalog.schema.products_enriched",
    }


class TestCreateGenieSpaceHappyPath:
    def test_returns_space_id_on_success(self, genie_config):
        session = MagicMock()
        session.post.return_value = _make_response({"space_id": "space_abc123"})

        result = connector.create_genie_space(session, genie_config, {})
        assert result == "space_abc123"

    def test_idempotent_when_space_id_already_in_state(self, genie_config):
        """If state already has a space_id, skip POST entirely."""
        session = MagicMock()
        state = {"genie_space_id": "existing_space_xyz"}

        result = connector.create_genie_space(session, genie_config, state)
        assert result == "existing_space_xyz"
        assert not session.post.called, "POST must not be called when space_id already exists"


class TestCreateGenieSpaceFailures:
    def test_http_error_returns_none(self, genie_config):
        session = MagicMock()
        err = _requests.exceptions.HTTPError("500 Server Error")
        session.post.side_effect = err

        result = connector.create_genie_space(session, genie_config, {})
        assert result is None

    def test_request_exception_returns_none(self, genie_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.ConnectionError("network down")

        result = connector.create_genie_space(session, genie_config, {})
        assert result is None

    def test_missing_space_id_in_response_returns_none(self, genie_config):
        session = MagicMock()
        session.post.return_value = _make_response({"status": "created"})  # no space_id key

        result = connector.create_genie_space(session, genie_config, {})
        assert result is None


class TestCreateGenieSpacePayload:
    """The Genie API requires question and content as plain strings, not lists.
    This bug surfaced in PR #572 and is caught by inspecting the serialized payload."""

    def test_question_and_content_are_strings(self, genie_config):
        """Verify that every sample question is a string and the instruction
        content is a string — not a single-element list."""
        session = MagicMock()
        session.post.return_value = _make_response({"space_id": "space_test"})

        connector.create_genie_space(session, genie_config, {})
        assert session.post.called

        _, call_kwargs = session.post.call_args
        payload = call_kwargs.get("json") or session.post.call_args[0][1]
        serialized = json.loads(payload.get("serialized_space", "{}"))

        for q_item in serialized["config"]["sample_questions"]:
            assert isinstance(
                q_item["question"], str
            ), f"question must be a string, got {type(q_item['question'])}: {q_item['question']!r}"

        for instr in serialized["instructions"]["text_instructions"]:
            assert isinstance(
                instr["content"], str
            ), f"content must be a string, got {type(instr['content'])}: {instr['content']!r}"
