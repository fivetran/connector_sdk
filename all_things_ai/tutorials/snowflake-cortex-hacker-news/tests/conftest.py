"""Shared pytest fixtures for the Hacker News + Snowflake Cortex connector tests.

Cortex Agent pattern (PAT auth + SSE-formatted response body, NOT stream=True).
Single-table schema (stories_enriched). ID-based incremental cursor with
halt-on-fetch-failure semantics.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fivetran_connector_sdk import Logging as _sdk_logging  # noqa: E402

if _sdk_logging.LOG_LEVEL is None:
    _sdk_logging.LOG_LEVEL = _sdk_logging.Level.INFO


@pytest.fixture
def base_config():
    """Known-good configuration with Cortex enabled and non-placeholder Snowflake creds."""
    return {
        "max_stories": "10",
        "batch_size": "5",
        "enable_cortex": "true",
        "snowflake_account": "abc12345.snowflakecomputing.com",
        "snowflake_pat_token": "snowflake_pat_test_token_abc",
        "cortex_model": "mistral-large2",
        "cortex_timeout": "30",
        "max_enrichments": "5",
    }


def make_story(story_id, title=None, type_="story", **fields):
    """Build a minimal raw HN story record."""
    if title is None:
        title = f"Test Story {story_id}"
    return {
        "id": story_id,
        "type": type_,
        "title": title,
        "by": "test_user",
        "time": 1700000000 + story_id,
        "score": 100,
        "descendants": 10,
        "url": f"https://example.com/story/{story_id}",
        **fields,
    }


@pytest.fixture
def story_batch():
    """5 stories with sequential IDs starting at 1000."""
    return [make_story(1000 + i) for i in range(5)]


@pytest.fixture
def story_batch_20():
    """20 stories — useful for testing max_stories cap and batch boundaries."""
    return [make_story(2000 + i) for i in range(20)]


@pytest.fixture
def sample_sentiment_response():
    """Canonical Cortex sentiment-analysis JSON output."""
    return {
        "sentiment": "positive",
        "score": 0.85,
        "reasoning": "Title indicates a successful launch.",
    }


@pytest.fixture
def sample_classification_response():
    """Canonical Cortex topic-classification JSON output."""
    return {
        "category": "AI",
        "confidence": 0.92,
        "keywords": ["machine learning", "neural network", "training"],
    }


@pytest.fixture
def captured_upserts(monkeypatch):
    """Patch op.upsert and op.checkpoint to no-ops; yield captured records."""
    import connector

    captured = {"upserts": [], "checkpoints": []}

    def fake_upsert(table, data):
        captured["upserts"].append({"table": table, "data": data})

    def fake_checkpoint(state):
        captured["checkpoints"].append(dict(state) if state else {})

    monkeypatch.setattr(connector.op, "upsert", fake_upsert)
    monkeypatch.setattr(connector.op, "checkpoint", fake_checkpoint)
    monkeypatch.setattr(connector.time, "sleep", lambda *_: None)
    return captured
