"""Integration tests that lock in the README contract for max_enrichments.

README statement (README.md, parameter table):
  "max_enrichments (optional): Maximum ai_query() calls for discovery +
   debate combined."

These tests mock the HTTP boundaries (NOAA fetch + Databricks ai_query) and
run the full update() function, counting every ai_query() call that would
have been made. The invariant is simple and non-negotiable:

  total_ai_query_calls <= max_enrichments

This is the test that would have caught fix #570-1 before submission.
"""

import pytest

import connector


def _run_update_counting_ai_calls(
    config,
    noaa_alerts_batch,
    monkeypatch,
    no_op_sdk_operations,
    ai_responses_cycle,
):
    """Helper: run update() with mocked boundaries and return the list of
    ai_query call-count markers captured."""
    ai_calls = []
    response_iter = iter(ai_responses_cycle * 100)  # Enough to never run out

    def fake_call_ai_query(session, configuration, prompt):
        ai_calls.append(prompt[:60])
        return next(response_iter)

    def fake_fetch_alerts_for_state(session, state_code):
        # Return alerts for seed + any discovery-recommended state.
        return noaa_alerts_batch

    monkeypatch.setattr(connector, "call_ai_query", fake_call_ai_query)
    monkeypatch.setattr(connector, "fetch_alerts_for_state", fake_fetch_alerts_for_state)

    connector.update(config, {})
    return ai_calls


@pytest.mark.parametrize("max_enrichments", [1, 2, 3, 5, 10, 20])
def test_max_enrichments_combined_budget_honored(
    max_enrichments,
    base_config,
    noaa_alerts_batch,
    no_op_sdk_operations,
    sample_discovery_response,
    sample_emergency_response,
    sample_planning_response,
    sample_consensus_response,
    monkeypatch,
):
    """README contract: max_enrichments caps total ai_query() calls across
    discovery + debate combined, for any value from 1 up to the ceiling."""
    config = dict(base_config)
    config["max_enrichments"] = str(max_enrichments)
    config["enable_enrichment"] = "true"
    config["enable_discovery"] = "true"

    # Cycle through realistic response shapes so both phases get valid JSON.
    responses = [
        sample_discovery_response,
        sample_emergency_response,
        sample_planning_response,
        sample_consensus_response,
    ]

    ai_calls = _run_update_counting_ai_calls(
        config,
        noaa_alerts_batch,
        monkeypatch,
        no_op_sdk_operations,
        responses,
    )

    assert len(ai_calls) <= max_enrichments, (
        f"Budget violated: max_enrichments={max_enrichments} but "
        f"{len(ai_calls)} ai_query() calls were made. "
        f"README contract: max_enrichments is max ai_query() calls "
        f"combined across discovery + debate."
    )


def test_enrichment_disabled_makes_zero_ai_query_calls(
    base_config,
    noaa_alerts_batch,
    no_op_sdk_operations,
    sample_discovery_response,
    monkeypatch,
):
    """When enable_enrichment=false, no ai_query() calls should be made
    regardless of max_enrichments."""
    config = dict(base_config)
    config["enable_enrichment"] = "false"
    config["enable_discovery"] = "false"
    config["max_enrichments"] = "20"
    # Data-only mode still requires Databricks creds today (fix #6), so
    # keep them populated for this test.

    ai_calls = _run_update_counting_ai_calls(
        config,
        noaa_alerts_batch,
        monkeypatch,
        no_op_sdk_operations,
        [sample_discovery_response],
    )

    assert len(ai_calls) == 0, (
        f"Expected zero ai_query() calls with enrichment disabled, " f"got {len(ai_calls)}"
    )


def test_discovery_only_mode_respects_budget(
    base_config,
    noaa_alerts_batch,
    no_op_sdk_operations,
    sample_discovery_response,
    monkeypatch,
):
    """With debate disabled via small budget (only 1 seed state's worth of
    discovery), total ai_query calls should not exceed max_enrichments."""
    config = dict(base_config)
    config["alert_states"] = "TX"  # single seed state
    config["max_enrichments"] = "1"

    ai_calls = _run_update_counting_ai_calls(
        config,
        noaa_alerts_batch,
        monkeypatch,
        no_op_sdk_operations,
        [sample_discovery_response],
    )

    assert len(ai_calls) <= 1, (
        f"Single-seed-state discovery should cap at 1 ai_query, got " f"{len(ai_calls)}"
    )
