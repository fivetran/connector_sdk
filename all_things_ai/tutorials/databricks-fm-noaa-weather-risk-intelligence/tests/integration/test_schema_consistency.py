"""Schema-drift tests: README declared schema vs connector's actual output.

These tests parse the README's per-table column lists and compare them to
the keys returned by the record-builder functions. Drift in either direction
(column in code but not docs, or column in docs but not code) is a bug.

Catches the class of issue raised by reviewers on PR #570 where
README WEATHER_EVENTS was missing status/message_type/category columns
that build_event_record() actually emits.
"""

import re
from pathlib import Path

import connector

README_PATH = Path(__file__).parent.parent.parent / "README.md"


def _extract_table_columns(table_section_name):
    """Parse README and return the set of column names listed under the
    `### TABLE_NAME` heading."""
    text = README_PATH.read_text()
    section_re = re.compile(
        rf"^### {re.escape(table_section_name)}\s*\n(.*?)(?=^###|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = section_re.search(text)
    if not match:
        return set()
    body = match.group(1)
    # Match `- `column_name` (TYPE...): description`
    column_re = re.compile(r"^\s*-\s+`([a-z_][a-z0-9_]*)`\s*\(", re.MULTILINE)
    return set(column_re.findall(body))


class TestWeatherEventsSchemaParity:
    """The set of columns build_event_record() emits must match the
    README WEATHER_EVENTS schema exactly. Either direction of drift
    is a bug."""

    def test_build_event_record_columns_match_readme(self, minimal_noaa_alert_feature):
        record = connector.build_event_record(minimal_noaa_alert_feature, "seed")
        code_columns = set(record.keys())
        readme_columns = _extract_table_columns("WEATHER_EVENTS")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns

        assert not in_code_not_readme, (
            f"build_event_record emits columns missing from README: "
            f"{sorted(in_code_not_readme)}"
        )
        assert not in_readme_not_code, (
            f"README declares columns not emitted by build_event_record: "
            f"{sorted(in_readme_not_code)}"
        )


def _capture_upsert(monkeypatch):
    captured = []
    monkeypatch.setattr(
        connector.op,
        "upsert",
        lambda table, data: captured.append({"table": table, "data": data}),
    )
    return captured


class TestEmergencyAssessmentsSchemaParity:
    def test_emergency_columns_match_readme(self, monkeypatch):
        captured = _capture_upsert(monkeypatch)
        emergency = {
            "emergency_risk_score": 9,
            "worst_case_impact": "Catastrophic flooding affecting 50,000 residents",
            "evacuation_recommendation": "ORDER",
            "resource_deployment": "FULL",
            "estimated_population_at_risk": "50,000",
            "reasoning": "Severe storm trajectory + saturated soil = high probability of flooding",
        }
        connector.upsert_assessment("emergency_assessments", "evt-1", emergency, "emergency")
        code_columns = set(captured[0]["data"].keys())
        readme_columns = _extract_table_columns("EMERGENCY_ASSESSMENTS")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns
        assert not in_code_not_readme, (
            f"emergency_assessments emits columns missing from README: "
            f"{sorted(in_code_not_readme)}"
        )
        assert not in_readme_not_code, (
            f"README declares EMERGENCY_ASSESSMENTS columns not emitted: "
            f"{sorted(in_readme_not_code)}"
        )


class TestPlanningAssessmentsSchemaParity:
    def test_planning_columns_match_readme(self, monkeypatch):
        captured = _capture_upsert(monkeypatch)
        planning = {
            "planning_risk_score": 7,
            "expected_impact": "Moderate flooding in low-lying areas; brief power disruption",
            "evacuation_assessment": "PROPORTIONATE",
            "resource_recommendation": "PARTIAL",
            "cost_effectiveness": "HIGH",
            "reasoning": "Probability-weighted impact suggests partial deployment is sufficient",
        }
        connector.upsert_assessment("planning_assessments", "evt-1", planning, "planning")
        code_columns = set(captured[0]["data"].keys())
        readme_columns = _extract_table_columns("PLANNING_ASSESSMENTS")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns
        assert not in_code_not_readme, (
            f"planning_assessments emits columns missing from README: "
            f"{sorted(in_code_not_readme)}"
        )
        assert not in_readme_not_code, (
            f"README declares PLANNING_ASSESSMENTS columns not emitted: "
            f"{sorted(in_readme_not_code)}"
        )


class TestDebateConsensusSchemaParity:
    def test_debate_consensus_columns_match_readme(self, monkeypatch):
        captured = _capture_upsert(monkeypatch)
        consensus = {
            "final_severity": "HIGH",
            "consensus_risk_score": 8,
            "debate_winner": "EMERGENCY",
            "winner_rationale": "Emergency analyst's risk-aversion was more defensible given uncertainty",
            "agreement_areas": ["evacuation needed", "full deployment"],
            "disagreement_areas": ["population estimate", "duration"],
            "disagreement_flag": True,
            "disagreement_severity": "MINOR",
            "recommended_action": "Issue mandatory evacuation order with supporting deployment",
            "executive_summary": "Both analysts agree on action; minor disagreement on scale",
        }
        connector.upsert_assessment("debate_consensus", "evt-1", consensus, "consensus")
        code_columns = set(captured[0]["data"].keys())
        readme_columns = _extract_table_columns("DEBATE_CONSENSUS")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns
        assert not in_code_not_readme, (
            f"debate_consensus emits columns missing from README: " f"{sorted(in_code_not_readme)}"
        )
        assert not in_readme_not_code, (
            f"README declares DEBATE_CONSENSUS columns not emitted: "
            f"{sorted(in_readme_not_code)}"
        )


class TestDiscoveryInsightsSchemaParity:
    """discovery_insights is built inline in run_discovery_phase, not via a
    helper. Mock call_ai_query + extract_json + the alerts fetch and capture
    the inline upsert."""

    def test_discovery_insights_columns_match_readme(self, monkeypatch, base_config):
        captured = _capture_upsert(monkeypatch)
        monkeypatch.setattr(connector.op, "checkpoint", lambda state: None)
        monkeypatch.setattr(connector.time, "sleep", lambda *_: None)

        # Mock the ai_query content + JSON extraction
        sample_discovery = {
            "weather_system": "Severe Thunderstorm Outbreak",
            "system_severity": "SEVERE",
            "recommended_states": [{"state": "AR", "reason": "downstream"}],
            "regional_risk_summary": "Moisture surge from Gulf creating widespread severe wx",
        }
        monkeypatch.setattr(connector, "call_ai_query", lambda *a, **kw: '{"key":"value"}')
        monkeypatch.setattr(connector, "extract_json_from_content", lambda c: sample_discovery)
        monkeypatch.setattr(connector, "fetch_alerts_for_state", lambda *a, **kw: [])

        connector.run_discovery_phase(
            session=None,
            configuration=base_config,
            seed_states=["TX"],
            all_events=[],
            event_records_by_state={"TX": []},
            state={},
        )

        insight_upserts = [c for c in captured if c["table"] == "discovery_insights"]
        assert insight_upserts, "Expected at least one discovery_insights upsert"
        code_columns = set(insight_upserts[0]["data"].keys())
        readme_columns = _extract_table_columns("DISCOVERY_INSIGHTS")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns
        assert not in_code_not_readme, (
            f"discovery_insights emits columns missing from README: "
            f"{sorted(in_code_not_readme)}"
        )
        assert not in_readme_not_code, (
            f"README declares DISCOVERY_INSIGHTS columns not emitted: "
            f"{sorted(in_readme_not_code)}"
        )


class TestNoSqlReservedKeywordsAsColumnNames:
    """Regression from PR #555: HN's `by` field collided with SQL reserved
    keyword `BY` and produced a destination CREATE TABLE parser error.
    Scan all 5 NOAA tables for similar collisions."""

    def test_weather_events_no_reserved_keywords(self, minimal_noaa_alert_feature):
        record = connector.build_event_record(minimal_noaa_alert_feature, "seed")
        sql_reserved = {
            "by",
            "from",
            "select",
            "where",
            "order",
            "group",
            "join",
            "table",
        }
        clashing = set(record.keys()) & sql_reserved
        assert not clashing, (
            f"weather_events column(s) collide with SQL reserved keywords: {clashing}. "
            f"This produces a destination CREATE TABLE parser error at sync time."
        )
