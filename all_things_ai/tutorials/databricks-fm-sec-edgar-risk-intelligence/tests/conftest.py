"""Shared pytest fixtures for SEC EDGAR Risk Intelligence connector tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fivetran_connector_sdk import Logging as _sdk_logging  # noqa: E402

if _sdk_logging.LOG_LEVEL is None:
    _sdk_logging.LOG_LEVEL = _sdk_logging.Level.INFO


@pytest.fixture
def base_config():
    return {
        "seed_companies": "320193,789019",  # Apple, Microsoft
        "databricks_workspace_url": "https://example.cloud.databricks.com",
        "databricks_token": "dapi_test_token",
        "databricks_warehouse_id": "warehouse_test",
        "databricks_model": "databricks-claude-sonnet-4-6",
        "databricks_timeout": "120",
        "enable_enrichment": "false",
        "enable_discovery": "false",
        "enable_genie_space": "false",
        "max_enrichments": "5",
        "max_discovery_companies": "3",
    }


@pytest.fixture
def captured_upserts(monkeypatch):
    import connector

    captured = {"upserts": [], "checkpoints": []}

    def fake_upsert(table, data):
        captured["upserts"].append({"table": table, "data": data})

    def fake_checkpoint(state):
        captured["checkpoints"].append(dict(state) if state else {})

    monkeypatch.setattr(connector.op, "upsert", fake_upsert)
    monkeypatch.setattr(connector.op, "checkpoint", fake_checkpoint)
    return captured
