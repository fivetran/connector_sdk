"""Integration tests for error paths in HTTP-touching functions.

These tests mock `requests.Session` responses to exercise the failure
branches that `fivetran debug` doesn't touch on the happy path.
"""

from unittest.mock import MagicMock

import pytest

import connector


@pytest.fixture
def mock_session():
    """A MagicMock standing in for a requests.Session. Tests configure
    `.post.return_value` and `.get.return_value` per scenario."""
    return MagicMock()


def _make_response(json_payload, status_code=200):
    """Build a fake requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    resp.raise_for_status.return_value = None
    return resp


class TestCallAiQueryStatementIdGuard:
    """Fix #570-7: when the initial response has state=PENDING/RUNNING
    but no statement_id, the connector must NOT poll a `.../None` URL.
    It should log and return None gracefully."""

    def test_pending_with_missing_statement_id_returns_none_without_polling(
        self, base_config, mock_session, monkeypatch
    ):
        # Initial POST returns RUNNING but no statement_id
        mock_session.post.return_value = _make_response(
            {"status": {"state": "RUNNING"}}  # statement_id intentionally absent
        )
        # If polling occurs, this returns SUCCEEDED — the test must not allow
        # it to even reach this. We track GET calls to assert.
        mock_session.get.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [["should-not-be-returned"]]},
            }
        )
        # Silence the rate-limit sleep
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        result = connector.call_ai_query(mock_session, base_config, "test prompt")

        assert result is None, (
            "Expected None when initial response is PENDING/RUNNING with " "no statement_id"
        )
        assert mock_session.get.call_count == 0, (
            f"Expected zero GET requests (no polling allowed), "
            f"got {mock_session.get.call_count}"
        )

    def test_succeeded_with_missing_statement_id_still_returns_data(
        self, base_config, mock_session, monkeypatch
    ):
        """When the initial response is SUCCEEDED, statement_id is irrelevant —
        we should return the data without ever polling."""
        mock_session.post.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [["happy-path-result"]]},
            }
        )
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        result = connector.call_ai_query(mock_session, base_config, "test prompt")

        assert result == "happy-path-result"
        assert mock_session.get.call_count == 0


class TestCallAiQueryWithStatementId:
    """Confirm the happy polling path still works after the guard is added."""

    def test_pending_then_succeeded_polls_and_returns_data(
        self, base_config, mock_session, monkeypatch
    ):
        mock_session.post.return_value = _make_response(
            {
                "status": {"state": "PENDING"},
                "statement_id": "stmt-abc-123",
            }
        )
        mock_session.get.return_value = _make_response(
            {
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [["polled-result"]]},
            }
        )
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        result = connector.call_ai_query(mock_session, base_config, "test prompt")

        assert result == "polled-result"
        # First poll URL should have the real statement_id, not None
        first_call_url = mock_session.get.call_args_list[0][0][0]
        assert "stmt-abc-123" in first_call_url
        assert "None" not in first_call_url
