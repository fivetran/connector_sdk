"""Integration tests for error paths in the Cortex API calls.

Covers:
- call_cortex_sentiment / call_cortex_classification: timeouts and HTTP errors
  return None (don't raise) so a single Cortex blip doesn't fail the whole sync
- enrich_story: when sentiment fails but classification succeeds (and vice
  versa), the surviving fields are still populated
- update(): the broad `except Exception:` at line 640 should re-raise (not
  swallow) — verify exception specificity at the integration layer
"""

from unittest.mock import MagicMock

import pytest
import requests as _requests

import connector


def _make_streaming_response(content_dict, status_code=200):
    """Build a mock requests.Response whose .text contains an SSE-formatted body
    encoding `content_dict` as a single Cortex content event."""
    import json as _json

    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    sse_event = _json.dumps({"choices": [{"delta": {"content": _json.dumps(content_dict)}}]})
    resp.text = f"data: {sse_event}\n"
    return resp


class TestCallCortexSentimentFailures:
    def test_timeout_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.Timeout("simulated")
        result = connector.call_cortex_sentiment(
            session,
            base_config["snowflake_account"],
            "test title",
            base_config["snowflake_pat_token"],
            base_config["cortex_model"],
            int(base_config["cortex_timeout"]),
        )
        assert result is None

    def test_http_error_returns_none(self, base_config):
        session = MagicMock()
        err_resp = MagicMock()
        err_resp.status_code = 500
        http_err = _requests.exceptions.HTTPError("500")
        http_err.response = err_resp
        session.post.side_effect = http_err
        result = connector.call_cortex_sentiment(
            session,
            base_config["snowflake_account"],
            "test title",
            base_config["snowflake_pat_token"],
            base_config["cortex_model"],
            int(base_config["cortex_timeout"]),
        )
        assert result is None

    def test_connection_error_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.ConnectionError("simulated")
        result = connector.call_cortex_sentiment(
            session,
            base_config["snowflake_account"],
            "test title",
            base_config["snowflake_pat_token"],
            base_config["cortex_model"],
            int(base_config["cortex_timeout"]),
        )
        assert result is None

    def test_success_returns_parsed_json(self, base_config, sample_sentiment_response):
        session = MagicMock()
        session.post.return_value = _make_streaming_response(sample_sentiment_response)
        result = connector.call_cortex_sentiment(
            session,
            base_config["snowflake_account"],
            "test title",
            base_config["snowflake_pat_token"],
            base_config["cortex_model"],
            int(base_config["cortex_timeout"]),
        )
        assert result == sample_sentiment_response


class TestCallCortexClassificationFailures:
    def test_timeout_returns_none(self, base_config):
        session = MagicMock()
        session.post.side_effect = _requests.exceptions.Timeout("simulated")
        result = connector.call_cortex_classification(
            session,
            base_config["snowflake_account"],
            "test title",
            base_config["snowflake_pat_token"],
            base_config["cortex_model"],
            int(base_config["cortex_timeout"]),
        )
        assert result is None

    def test_success_returns_parsed_json(self, base_config, sample_classification_response):
        session = MagicMock()
        session.post.return_value = _make_streaming_response(sample_classification_response)
        result = connector.call_cortex_classification(
            session,
            base_config["snowflake_account"],
            "test title",
            base_config["snowflake_pat_token"],
            base_config["cortex_model"],
            int(base_config["cortex_timeout"]),
        )
        assert result == sample_classification_response


class TestEnrichStoryPartialFailures:
    """If one of the two Cortex calls fails, the other's result must still
    populate. This ensures that an intermittent Cortex blip on one prompt
    type doesn't waste the other (already-paid-for) call."""

    def test_sentiment_fails_classification_succeeds(
        self, base_config, monkeypatch, sample_classification_response
    ):
        monkeypatch.setattr(connector, "call_cortex_sentiment", lambda *a, **kw: None)
        monkeypatch.setattr(
            connector,
            "call_cortex_classification",
            lambda *a, **kw: sample_classification_response,
        )
        session = MagicMock()
        result = connector.enrich_story(session, base_config, "test title")
        assert result["cortex_sentiment"] is None
        assert result["cortex_category"] == "AI"
        assert result["cortex_category_confidence"] == 0.92

    def test_classification_fails_sentiment_succeeds(
        self, base_config, monkeypatch, sample_sentiment_response
    ):
        monkeypatch.setattr(
            connector, "call_cortex_sentiment", lambda *a, **kw: sample_sentiment_response
        )
        monkeypatch.setattr(connector, "call_cortex_classification", lambda *a, **kw: None)
        session = MagicMock()
        result = connector.enrich_story(session, base_config, "test title")
        assert result["cortex_sentiment"] == "positive"
        assert result["cortex_sentiment_score"] == 0.85
        assert result["cortex_category"] is None

    def test_both_fail_returns_all_none(self, base_config, monkeypatch):
        monkeypatch.setattr(connector, "call_cortex_sentiment", lambda *a, **kw: None)
        monkeypatch.setattr(connector, "call_cortex_classification", lambda *a, **kw: None)
        session = MagicMock()
        result = connector.enrich_story(session, base_config, "test title")
        assert result["cortex_sentiment"] is None
        assert result["cortex_category"] is None
        # cortex_model_used should still be set — it doesn't depend on the call
        assert result["cortex_model_used"] == base_config["cortex_model"]


class TestUpdateExceptionSpecificity:
    """The connector wraps the entire sync in `except Exception as e: log.severe(...); raise`.
    This re-raises (good — Fivetran retries the sync) but the broad catch is
    still wider than ideal per hazard #6. Test verifies the re-raise contract."""

    def test_runtime_error_propagates(self, base_config, monkeypatch):
        def fake_fetch(*args, **kwargs):
            raise RuntimeError("simulated HN API outage")

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        with pytest.raises(RuntimeError, match="simulated HN API outage"):
            connector.update(base_config, {})

    def test_value_error_propagates(self, base_config, monkeypatch):
        def fake_fetch(*args, **kwargs):
            raise ValueError("simulated programmer bug")

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        with pytest.raises(ValueError, match="simulated programmer bug"):
            connector.update(base_config, {})
