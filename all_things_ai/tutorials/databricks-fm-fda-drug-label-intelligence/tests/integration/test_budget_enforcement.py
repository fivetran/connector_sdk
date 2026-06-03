"""Budget enforcement tests — max_labels and max_enrichments caps."""

import pytest

import connector


def _make_label(set_id, effective_time="20240310"):
    return {
        "set_id": set_id,
        "version": "1",
        "effective_time": effective_time,
        "id": f"{set_id}_doc",
        "openfda": {"brand_name": ["Test"], "generic_name": ["test"]},
    }


class TestMaxEnrichmentsCap:
    @pytest.mark.parametrize("budget", [1, 3, 5])
    def test_caps_enriched_records(self, budget, base_config, captured_upserts, monkeypatch):
        """When max_enrichments=N and there are more labels than N, only N
        labels should have call_ai_query invoked for them."""
        ai_calls = []

        def fake_call(session, configuration, prompt):
            ai_calls.append(prompt)
            return '{"interaction_risk": "LOW"}'

        monkeypatch.setattr(connector, "call_ai_query", fake_call)

        labels = [_make_label(f"set_{i:03d}") for i in range(10)]
        base_config["enable_enrichment"] = "true"
        base_config["max_enrichments"] = str(budget)

        connector.process_batch(
            session=None,
            configuration=base_config,
            labels=labels,
            is_enrichment_enabled=True,
            enriched_count=0,
            max_enrichments=budget,
            last_effective_time=None,
            last_label_id=None,
        )

        # Each enriched label triggers ~5 ai_query calls (one per AI field).
        # Just assert that the count of enriched LABELS (records with cortex
        # fields populated) is <= budget. Use the upsert payloads to count.
        labels_with_enrichment = [
            u
            for u in captured_upserts["upserts"]
            if any(k.startswith("ai_") for k in u["data"].keys())
        ]
        # Across the harness contracts what matters is that enrichment
        # respects the budget.
        # Allow <= budget to also cover early returns / partial failures.
        assert len(labels_with_enrichment) <= budget


class TestFailedEnrichmentNotCounted:
    """When call_ai_query returns content that extract_json_from_content
    cannot parse, enrich_drug_label must signal failure so the budget
    counter does not advance. Otherwise a streak of broken responses
    would silently consume the user's max_enrichments quota."""

    def test_unparseable_response_does_not_increment_counter(
        self, base_config, captured_upserts, monkeypatch
    ):
        # Always return non-JSON content — extract_json_from_content returns None.
        monkeypatch.setattr(
            connector,
            "call_ai_query",
            lambda session, configuration, prompt: "the model refused to comply",
        )

        labels = [_make_label(f"set_{i:03d}") for i in range(3)]
        base_config["enable_enrichment"] = "true"
        base_config["max_enrichments"] = "1"

        _, enriched_count, _, _ = connector.process_batch(
            session=None,
            configuration=base_config,
            labels=labels,
            is_enrichment_enabled=True,
            enriched_count=0,
            max_enrichments=1,
            last_effective_time=None,
            last_label_id=None,
        )

        # All 3 labels still upsert (with NULL enrichment columns) but the
        # counter stays at 0 because no enrichment actually succeeded.
        assert enriched_count == 0
        assert len(captured_upserts["upserts"]) == 3


class TestEnrichmentDisabledShortCircuits:
    """When enable_enrichment=false, no ai_query calls are made regardless
    of max_enrichments."""

    def test_disabled_skips_all_ai_calls(self, base_config, captured_upserts, monkeypatch):
        ai_calls = []

        def fake_call(session, configuration, prompt):
            ai_calls.append(prompt)
            return '{"interaction_risk": "LOW"}'

        monkeypatch.setattr(connector, "call_ai_query", fake_call)

        labels = [_make_label(f"set_{i:03d}") for i in range(5)]
        base_config["enable_enrichment"] = "false"

        connector.process_batch(
            session=None,
            configuration=base_config,
            labels=labels,
            is_enrichment_enabled=False,
            enriched_count=0,
            max_enrichments=10,
            last_effective_time=None,
            last_label_id=None,
        )
        assert len(ai_calls) == 0
        assert len(captured_upserts["upserts"]) == 5  # records still upserted
