"""Regression for Copilot L995 — discovered_ciks must include seed CIKs so
LLM-recommended companies that overlap the seed set are not re-fetched."""

import connector


class TestDiscoveryDedup:
    def test_seed_ciks_seed_the_dedup_set(self, base_config, captured_upserts, monkeypatch):
        """If the LLM recommends a CIK that's already in the seed list, the
        connector must skip it. Pre-fix discovered_ciks = set() did not seed
        with the seed CIKs, so the same company could be fetched twice."""
        seed_companies = [("0000320193", "Apple Inc."), ("0000789019", "Microsoft")]
        all_facts = {"0000320193": [], "0000789019": []}

        def fake_call(session, configuration, prompt):
            return (
                '{"weather_system": null, "recommended_companies": ['
                '{"cik": "0000320193", "name": "Apple", "reason": "duplicate seed"},'
                '{"cik": "0000111111", "name": "NewCo", "reason": "novel"}'
                "]}"
            )

        fetch_calls = []

        def fake_fetch_and_upsert(session, cik, source_label, state):
            fetch_calls.append((cik, source_label))
            return f"Company-{cik}", []

        monkeypatch.setattr(connector, "call_ai_query", fake_call)
        monkeypatch.setattr(
            connector,
            "extract_json_from_content",
            lambda c: {
                "weather_system": None,
                "recommended_companies": [
                    {"cik": "0000320193", "name": "Apple", "reason": "duplicate seed"},
                    {"cik": "0000111111", "name": "NewCo", "reason": "novel"},
                ],
            },
        )
        monkeypatch.setattr(connector, "fetch_and_upsert_company", fake_fetch_and_upsert)

        connector.run_discovery_phase(
            session=None,
            configuration=base_config,
            seed_companies=seed_companies,
            all_facts=all_facts,
            state={},
        )

        # Only the novel CIK should have been fetched (seed CIKs are
        # pre-loaded into discovered_ciks).
        fetched_ciks = [cik for cik, _ in fetch_calls]
        assert "0000320193" not in fetched_ciks, (
            "Seed CIK 0000320193 was re-fetched during discovery — "
            "discovered_ciks should be seeded with seed CIKs to prevent this."
        )
