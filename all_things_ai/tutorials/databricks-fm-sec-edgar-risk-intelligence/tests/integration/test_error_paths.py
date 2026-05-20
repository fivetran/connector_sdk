"""Integration tests for error paths in call_ai_query()."""

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


class TestCallAiQueryStatementIdGuard:
    """Hazard #3 (api-profiling.md): pre-poll guard for missing statement_id."""

    def test_pending_without_statement_id_returns_none_no_polling(self, base_config):
        get_calls = []
        session = MagicMock()
        session.post.return_value = _make_response({"status": {"state": "PENDING"}})
        session.get = lambda *a, **kw: get_calls.append(a) or _make_response(
            {"status": {"state": "PENDING"}}
        )

        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result is None
        assert len(get_calls) == 0


class TestCallAiQueryHappyPath:
    def test_immediate_success(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_abc",
                "result": {"data_array": [['{"risk_level": "HIGH"}']]},
            }
        )
        result = connector.call_ai_query(session, base_config, "test")
        assert result == '{"risk_level": "HIGH"}'


class TestCallAiQueryFailures:
    def test_timeout_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.Timeout("simulated")
        assert connector.call_ai_query(session, base_config, "test") is None

    def test_connection_error_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.ConnectionError("simulated")
        assert connector.call_ai_query(session, base_config, "test") is None


class TestExceptionSpecificity:
    def test_value_error_propagates(self, base_config):
        session = MagicMock()
        session.post.side_effect = ValueError("simulated programmer bug")
        with pytest.raises(ValueError, match="simulated programmer bug"):
            connector.call_ai_query(session, base_config, "test")
