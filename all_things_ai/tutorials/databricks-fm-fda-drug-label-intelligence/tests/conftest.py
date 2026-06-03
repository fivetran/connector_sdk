"""Shared pytest fixtures for FDA Drug Label Intelligence connector tests.

Mirrors the harness pattern from databricks-fm-noaa-weather-risk-intelligence —
when the skill is updated, this layout becomes the canonical scaffold for
every Databricks-AI-pattern connector.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Initialize SDK Logging level so log.info / log.warning work outside the
# fivetran debug harness.
from fivetran_connector_sdk import Logging as _sdk_logging  # noqa: E402

if _sdk_logging.LOG_LEVEL is None:
    _sdk_logging.LOG_LEVEL = _sdk_logging.Level.INFO


@pytest.fixture
def base_config():
    return {
        "databricks_workspace_url": "https://example.cloud.databricks.com",
        "databricks_token": "dapi_test_token_abc123",
        "databricks_warehouse_id": "warehouse_test_id",
        "databricks_model": "databricks-claude-sonnet-4-6",
        "databricks_timeout": "120",
        "enable_enrichment": "false",
        "enable_genie_space": "false",
        "max_labels": "100",
        "max_enrichments": "5",
        "batch_size": "50",
    }


@pytest.fixture
def captured_upserts(monkeypatch):
    """Patch op.upsert and op.checkpoint to no-ops so process_batch / update
    can run outside the debug harness. Yields the captured records for
    assertions."""
    import connector

    captured = {"upserts": [], "checkpoints": []}

    def fake_upsert(table, data):
        captured["upserts"].append({"table": table, "data": data})

    def fake_checkpoint(state):
        captured["checkpoints"].append(dict(state) if state else {})

    monkeypatch.setattr(connector.op, "upsert", fake_upsert)
    monkeypatch.setattr(connector.op, "checkpoint", fake_checkpoint)
    return captured


def make_label(set_id, version, effective_time):
    """Build a minimal raw OpenFDA label dict with the fields the connector
    consumes for ID + cursor tracking."""
    return {
        "set_id": set_id,
        "version": version,
        "effective_time": effective_time,
        "id": f"{set_id}_doc",
    }
