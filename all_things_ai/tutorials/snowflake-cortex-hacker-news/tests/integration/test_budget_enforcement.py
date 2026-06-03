"""Budget enforcement tests — `max_stories` cap + `max_enrichments` cap.

Two independent budgets:
- `max_stories`: caps total stories synced per sync
- `max_enrichments`: caps Cortex-enriched stories per sync (cost control;
  remaining stories are still upserted but without enrichment)

The `max_enrichments` semantics here is "stories enriched", NOT "Cortex calls"
(each enriched story makes 2 Cortex calls — sentiment + classification —
so total Cortex calls = 2 * enriched_count). This naming subtlety is worth
documenting; tests assert the actual implemented contract.
"""

import pytest

import connector


@pytest.fixture
def stubbed_hn(monkeypatch, story_batch_20):
    """Stub HN API: topstories.json returns 20 IDs; per-story fetch returns
    the corresponding canned story."""
    by_id = {s["id"]: s for s in story_batch_20}
    all_ids = [s["id"] for s in story_batch_20]

    def fake_fetch(session, url, params=None, headers=None):
        if "topstories.json" in url:
            return all_ids
        # /item/{id}.json
        story_id = int(url.split("/item/")[-1].replace(".json", ""))
        return by_id.get(story_id)

    monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
    return by_id


@pytest.fixture
def cortex_call_counter(monkeypatch, sample_sentiment_response, sample_classification_response):
    """Replace both Cortex calls with counters."""
    sentiment_calls = []
    classification_calls = []

    def fake_sentiment(*args, **kwargs):
        sentiment_calls.append(args)
        return sample_sentiment_response

    def fake_classification(*args, **kwargs):
        classification_calls.append(args)
        return sample_classification_response

    monkeypatch.setattr(connector, "call_cortex_sentiment", fake_sentiment)
    monkeypatch.setattr(connector, "call_cortex_classification", fake_classification)
    return {"sentiment": sentiment_calls, "classification": classification_calls}


class TestMaxStoriesCap:
    """max_stories caps the total number of stories synced per sync."""

    @pytest.mark.parametrize("cap", [1, 3, 5, 10])
    def test_caps_synced_count(
        self, cap, base_config, captured_upserts, stubbed_hn, cortex_call_counter
    ):
        base_config["max_stories"] = str(cap)
        base_config["max_enrichments"] = "100"  # generous enough not to interfere
        connector.update(base_config, {})
        assert len(captured_upserts["upserts"]) == cap, (
            f"max_stories={cap} should cap synced count at {cap}, "
            f"got {len(captured_upserts['upserts'])}"
        )

    def test_zero_max_stories_rejected_by_validator(self, base_config):
        base_config["max_stories"] = "0"
        with pytest.raises(ValueError):
            connector.validate_configuration(base_config)


class TestMaxEnrichmentsCap:
    """max_enrichments caps the number of stories enriched (NOT raw Cortex
    calls — each enriched story makes 2 Cortex calls)."""

    def test_zero_enrichments_skips_all_cortex_calls(
        self, base_config, captured_upserts, stubbed_hn, cortex_call_counter
    ):
        # max_enrichments=0 must be rejected by the validator since the
        # connector requires positive integer. Verify the contract.
        base_config["max_enrichments"] = "0"
        with pytest.raises(ValueError):
            connector.validate_configuration(base_config)

    @pytest.mark.parametrize("budget", [1, 3, 5])
    def test_caps_enriched_stories(
        self, budget, base_config, captured_upserts, stubbed_hn, cortex_call_counter
    ):
        base_config["max_stories"] = "10"
        base_config["max_enrichments"] = str(budget)
        connector.update(base_config, {})
        # All 10 stories synced, only `budget` enriched
        assert len(captured_upserts["upserts"]) == 10
        # Exactly `budget` sentiment calls, exactly `budget` classification calls
        assert len(cortex_call_counter["sentiment"]) == budget, (
            f"max_enrichments={budget} should permit exactly {budget} sentiment calls, "
            f"got {len(cortex_call_counter['sentiment'])}"
        )
        assert len(cortex_call_counter["classification"]) == budget

    def test_unenriched_stories_still_upserted(
        self, base_config, captured_upserts, stubbed_hn, cortex_call_counter
    ):
        """When max_enrichments < max_stories, the un-enriched stories must
        still be upserted (just without cortex_* fields populated)."""
        base_config["max_stories"] = "5"
        base_config["max_enrichments"] = "2"
        connector.update(base_config, {})
        assert len(captured_upserts["upserts"]) == 5
        # First 2 stories should have cortex_sentiment populated
        enriched = [
            u for u in captured_upserts["upserts"] if u["data"].get("cortex_sentiment") is not None
        ]
        assert len(enriched) == 2
        # Remaining 3 stories are upserted without enrichment
        unenriched = [
            u for u in captured_upserts["upserts"] if u["data"].get("cortex_sentiment") is None
        ]
        assert len(unenriched) == 3


class TestCortexDisabledShortCircuits:
    """When enable_cortex=false, no Cortex calls happen at all — even if
    max_enrichments has a positive value."""

    def test_disabled_skips_all_cortex_calls(
        self, base_config, captured_upserts, stubbed_hn, cortex_call_counter
    ):
        base_config["enable_cortex"] = "false"
        # Remove now-unrequired fields
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        connector.update(base_config, {})
        assert len(cortex_call_counter["sentiment"]) == 0
        assert len(cortex_call_counter["classification"]) == 0
        # Stories still upserted
        assert len(captured_upserts["upserts"]) == 10
