"""Integration tests for error paths in the Databricks ai_query() polling code.

Async polling: when initial response.state is PENDING/RUNNING but
statement_id is missing, the polling URL becomes f".../{None}" and the
connector silently 404s. PR #570 lesson — a pre-poll guard is mandatory.

Specific exception types only — no `except Exception:`.
"""

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
    """The pre-poll guard from PR #570: when state is PENDING/RUNNING and
    the initial response omits statement_id, do NOT enter the poll loop —
    polling f"{url}/None" produces a confusing 404. Return None instead."""

    def test_pending_without_statement_id_returns_none_no_polling(self, base_config, monkeypatch):
        """Initial response says PENDING but has no statement_id. The connector
        must NOT issue a follow-up GET to f".../None" — it must return None
        immediately so an enrichment failure surfaces clearly."""
        post_calls = []
        get_calls = []

        def fake_post(*args, **kwargs):
            post_calls.append((args, kwargs))
            # State is PENDING but statement_id is missing — the bug shape from #570.
            return _make_response(
                {
                    "status": {"state": "PENDING"},
                    # NO statement_id key
                }
            )

        def fake_get(*args, **kwargs):
            get_calls.append((args, kwargs))
            return _make_response({"status": {"state": "PENDING"}})

        session = MagicMock()
        session.post = fake_post
        session.get = fake_get

        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result is None, "Missing statement_id must short-circuit to None"
        assert len(get_calls) == 0, (
            f"Connector polled {len(get_calls)} times despite missing statement_id — "
            "this builds the f'.../None' URL bug from PR #570."
        )

    def test_running_without_statement_id_returns_none_no_polling(self, base_config, monkeypatch):
        """Same guard, but initial state is RUNNING."""
        get_calls = []

        def fake_post(*args, **kwargs):
            return _make_response(
                {
                    "status": {"state": "RUNNING"},
                    "statement_id": None,  # explicitly null
                }
            )

        def fake_get(*args, **kwargs):
            get_calls.append((args, kwargs))
            return _make_response({"status": {"state": "PENDING"}})

        session = MagicMock()
        session.post = fake_post
        session.get = fake_get

        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result is None
        assert len(get_calls) == 0


class TestCallAiQueryHappyPath:
    def test_immediate_succeeded_returns_content(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_abc",
                "result": {"data_array": [['{"competitive_positioning": "PREMIUM"}']]},
            }
        )
        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result == '{"competitive_positioning": "PREMIUM"}'

    def test_pending_with_statement_id_polls_and_returns(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {
                "status": {"state": "PENDING"},
                "statement_id": "stmt_abc",
            }
        )
        session.get.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [['{"answer": "yes"}']]},
            }
        )
        result = connector.call_ai_query(session, base_config, "test prompt")
        assert result == '{"answer": "yes"}'
        assert session.get.called, "Connector should poll when initial state is PENDING with id"


class TestCallAiQueryFailures:
    def test_failed_state_returns_none(self, base_config):
        session = MagicMock()
        session.post.return_value = _make_response(
            {
                "status": {"state": "FAILED", "error": {"message": "warehouse paused"}},
                "statement_id": "stmt_abc",
            }
        )
        assert connector.call_ai_query(session, base_config, "test prompt") is None

    def test_timeout_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.Timeout("simulated")
        assert connector.call_ai_query(session, base_config, "test prompt") is None

    def test_connection_error_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.ConnectionError("simulated")
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
    """No `except Exception:` — programmer bugs must propagate to the
    outer update() handler, not be silently swallowed inside call_ai_query."""

    def test_unexpected_exception_not_swallowed(self, base_config):
        session = MagicMock()
        session.post.side_effect = ValueError("simulated programmer bug")
        with pytest.raises(ValueError, match="simulated programmer bug"):
            connector.call_ai_query(session, base_config, "test prompt")


class TestFetchDataWithRetry:
    """fetch_data_with_retry() retries on transient failures and raises after
    exhausting all attempts."""

    def test_retryable_500_retries_and_succeeds(self, monkeypatch):
        """A 500 on the first attempt is retried; success on the second attempt
        returns the JSON body."""
        call_count = [0]

        def fake_get(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                resp.status_code = 500
                err = _requests.exceptions.HTTPError("500 Server Error")
                err.response = resp
                resp.raise_for_status.side_effect = err
            else:
                resp.status_code = 200
                resp.raise_for_status.return_value = None
                resp.json.return_value = {"products": [{"sku": 1}], "total": 1}
            return resp

        session = MagicMock()
        session.get = fake_get
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        result = connector.fetch_data_with_retry(session, "https://example.com", {})
        assert result == {"products": [{"sku": 1}], "total": 1}
        assert call_count[0] == 2

    def test_all_retries_exhausted_raises(self, monkeypatch):
        """When all 3 attempts return a retryable error, a RuntimeError is raised."""
        call_count = [0]

        def fake_get(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status_code = 429
            err = _requests.exceptions.HTTPError("429 Too Many Requests")
            err.response = resp
            resp.raise_for_status.side_effect = err
            return resp

        session = MagicMock()
        session.get = fake_get
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        with pytest.raises(RuntimeError):
            connector.fetch_data_with_retry(session, "https://example.com", {})
        assert call_count[0] == 3  # __MAX_RETRIES = 3

    def test_auth_error_not_retried(self, monkeypatch):
        """A 401 is not retried — raises immediately."""
        call_count = [0]

        def fake_get(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status_code = 401
            err = _requests.exceptions.HTTPError("401 Unauthorized")
            err.response = resp
            resp.raise_for_status.side_effect = err
            return resp

        session = MagicMock()
        session.get = fake_get
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        with pytest.raises(RuntimeError, match="401"):
            connector.fetch_data_with_retry(session, "https://example.com", {})
        assert call_count[0] == 1, "Auth errors must not be retried"


class TestEmptyProductsShortCircuit:
    """When Best Buy returns zero products, update() must checkpoint and
    return cleanly without invoking ai_query()."""

    def test_empty_products_short_circuits(self, base_config, captured_upserts, monkeypatch):
        ai_calls = []

        def fake_call_ai_query(session, configuration, prompt):
            ai_calls.append(prompt)
            return None

        def fake_fetch(session, url, params=None):
            return {"products": [], "total": 0}

        monkeypatch.setattr(connector, "call_ai_query", fake_call_ai_query)
        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)

        connector.update(base_config, {})
        assert len(ai_calls) == 0
        assert len(captured_upserts["checkpoints"]) >= 1
        assert len(captured_upserts["upserts"]) == 0
