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
    """Hazard #3 (api-profiling.md): when initial response state is
    PENDING/RUNNING but statement_id is missing, polling .../None silently
    404s. Pre-poll guard returns None instead."""

    def test_pending_without_statement_id_returns_none_no_polling(self, base_config):
        get_calls = []

        def fake_post(*args, **kwargs):
            return _make_response({"status": {"state": "PENDING"}})

        def fake_get(*args, **kwargs):
            get_calls.append(args)
            return _make_response({"status": {"state": "PENDING"}})

        session = MagicMock()
        session.post = fake_post
        session.get = fake_get

        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result is None
        assert len(get_calls) == 0, (
            "Connector polled despite missing statement_id — this builds the "
            "f'.../None' URL bug from PR #570."
        )

    def test_running_without_statement_id_returns_none(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {"status": {"state": "RUNNING"}, "statement_id": None}
        )
        session.get = lambda *a, **kw: _make_response({"status": {"state": "PENDING"}})
        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result is None


class TestCallAiQueryHappyPath:
    def test_immediate_succeeded_returns_content(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_abc",
                "result": {"data_array": [['{"interaction_risk": "HIGH"}']]},
            }
        )
        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result == '{"interaction_risk": "HIGH"}'

    def test_pending_with_statement_id_polls_and_returns(self, base_config, monkeypatch):
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)
        session = MagicMock()
        session.post.return_value = _make_response(
            {"status": {"state": "PENDING"}, "statement_id": "stmt_abc"}
        )
        session.get.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [['{"answer": "yes"}']]},
            }
        )
        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result == '{"answer": "yes"}'


class TestCallAiQueryFailures:
    def test_failed_state_returns_none(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {
                "status": {
                    "state": "FAILED",
                    "error": {"message": "warehouse paused"},
                },
                "statement_id": "stmt_abc",
            }
        )
        assert connector.call_ai_query(session, base_config, "test prompt") is None

    def test_timeout_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.Timeout("simulated")
        assert connector.call_ai_query(session, base_config, "test prompt") is None

    def test_http_error_returns_none(self, base_config):
        session = MagicMock()
        err_resp = MagicMock()
        err_resp.json.return_value = {"message": "bad request"}
        err_resp.text = "bad request"
        http_err = _requests.exceptions.HTTPError("400 Client Error")
        http_err.response = err_resp
        session.post.side_effect = http_err
        assert connector.call_ai_query(session, base_config, "test prompt") is None


class TestExceptionSpecificity:
    def test_unexpected_exception_not_swallowed(self, base_config):
        session = MagicMock()
        session.post.side_effect = ValueError("simulated programmer bug")
        with pytest.raises(ValueError, match="simulated programmer bug"):
            connector.call_ai_query(session, base_config, "test prompt")
