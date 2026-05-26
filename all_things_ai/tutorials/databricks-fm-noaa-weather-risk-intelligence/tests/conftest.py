"""Shared pytest fixtures for NOAA Weather Intelligence connector tests."""

import json
import sys
from pathlib import Path

import pytest

# Put the connector folder on sys.path so tests can `import connector`.
sys.path.insert(0, str(Path(__file__).parent.parent))

# Initialize the SDK Logging level so log.info/log.warning work outside
# the fivetran debug harness (which normally sets LOG_LEVEL for us).
from fivetran_connector_sdk import Logging as _sdk_logging  # noqa: E402

if _sdk_logging.LOG_LEVEL is None:
    _sdk_logging.LOG_LEVEL = _sdk_logging.Level.INFO


@pytest.fixture
def base_config():
    """Known-good configuration with both phases enabled and non-placeholder
    Databricks credentials. Individual tests override fields as needed."""
    return {
        "databricks_workspace_url": "https://example.cloud.databricks.com",
        "databricks_token": "dapi_test_token_abc123",
        "databricks_warehouse_id": "warehouse_test_id",
        "databricks_model": "databricks-claude-sonnet-4-6",
        "databricks_timeout": "120",
        "enable_enrichment": "true",
        "enable_discovery": "true",
        "enable_genie_space": "false",
        "genie_table_identifier": "<OPTIONAL_GENIE_TABLE_IDENTIFIER>",
        "alert_states": "TX,OK,KS",
        "severity_filter": "Severe,Extreme",
        "max_events": "50",
        "max_enrichments": "5",
        "max_discovery_regions": "3",
    }


@pytest.fixture
def minimal_noaa_alert_feature():
    """Minimal NOAA alert feature matching build_event_record() expectations."""
    return {
        "id": "urn:oid:2.49.0.1.840.0.test",
        "properties": {
            "id": "urn:oid:2.49.0.1.840.0.test",
            "event": "Tornado Warning",
            "severity": "Severe",
            "urgency": "Immediate",
            "certainty": "Observed",
            "effective": "2026-04-24T12:00:00Z",
            "expires": "2026-04-24T13:00:00Z",
            "areaDesc": "Dallas County, TX",
            "headline": "Tornado warning for Dallas County",
            "description": "A tornado has been reported...",
            "instruction": "Take shelter immediately.",
            "status": "Actual",
            "messageType": "Alert",
            "category": "Met",
            "senderName": "NWS Fort Worth TX",
            "parameters": {},
        },
    }


@pytest.fixture
def noaa_alerts_batch(minimal_noaa_alert_feature):
    """A batch of 10 severe NOAA alerts."""
    features = []
    for i in range(10):
        feature = json.loads(json.dumps(minimal_noaa_alert_feature))
        feature["properties"]["id"] = f"urn:oid:2.49.0.1.840.0.{i}"
        feature["properties"]["headline"] = f"Severe event #{i}"
        features.append(feature)
    return features


@pytest.fixture
def sample_discovery_response():
    """Sample Databricks ai_query JSON response for discovery prompt."""
    return json.dumps(
        {
            "state_code": "TX",
            "weather_system": "Severe thunderstorm outbreak",
            "system_severity": "High",
            "recommended_states": [{"state": "NM", "reason": "Adjacent to frontal boundary"}],
            "regional_risk_summary": "Widespread severe weather risk.",
        }
    )


@pytest.fixture
def sample_emergency_response():
    """Sample ai_query JSON for emergency analyst prompt."""
    return json.dumps(
        {
            "urgency_level": "HIGH",
            "recommended_action": "Activate emergency response",
            "rationale": "Severe threat requires immediate mobilization",
            "confidence": 0.9,
        }
    )


@pytest.fixture
def sample_planning_response():
    """Sample ai_query JSON for planning analyst prompt."""
    return json.dumps(
        {
            "resource_allocation": "MEDIUM",
            "recommended_action": "Stage resources regionally",
            "rationale": "Risk is manageable with pre-positioning",
            "confidence": 0.7,
        }
    )


@pytest.fixture
def sample_consensus_response():
    """Sample ai_query JSON for consensus prompt."""
    return json.dumps(
        {
            "consensus_action": "HIGH_PRIORITY",
            "disagreement_flag": True,
            "disagreement_reason": "Urgency assessments diverge",
            "debate_winner": "emergency",
        }
    )


@pytest.fixture
def no_op_sdk_operations(monkeypatch):
    """Patch fivetran_connector_sdk.op.upsert and op.checkpoint to no-ops so
    update() can run outside the debug harness. Yields a dict with captured
    upserts and checkpoints for assertions."""
    import connector

    captured = {"upserts": [], "checkpoints": []}

    def fake_upsert(table, data):
        captured["upserts"].append({"table": table, "data": data})

    def fake_checkpoint(state):
        captured["checkpoints"].append(dict(state) if state else {})

    monkeypatch.setattr(connector.op, "upsert", fake_upsert)
    monkeypatch.setattr(connector.op, "checkpoint", fake_checkpoint)
    # Silence rate-limit sleeps in integration tests so they stay fast.
    monkeypatch.setattr(connector.time, "sleep", lambda *_: None)
    return captured
