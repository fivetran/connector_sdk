"""Cursor-advancement tests — locks in the fix for Codex P1 (PR #567).

Bug: OpenFDA's `effective_time:[X+TO+Y]` filter is inclusive on the lower
bound. Combined with the per-sync `max_labels` cap, a single day with more
than `max_labels` records caused permanent re-processing of the same
records on every sync (cursor never advanced past that day).

Fix: compound (effective_time, label_id) cursor with client-side skip of
records whose tuple is `<=` the cursor.

These tests prove:
  1. process_batch skips records already covered by the cursor
  2. the cursor advances to the highest (effective_time, label_id) seen
  3. running two consecutive batches with cap-hit scenarios doesn't
     re-upsert the same records
"""

import sys
from pathlib import Path

# Import path setup mirrors conftest, needed because pytest discovery from
# the connector dir lands here directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.conftest import make_label  # noqa: E402

import connector  # noqa: E402


class TestCursorSkipsAlreadySynced:
    """Records whose (effective_time, label_id) is <= the cursor must not
    be upserted again."""

    def test_skip_records_at_or_below_cursor(self, base_config, captured_upserts):
        labels = [
            make_label("set_001", "1", "20240310"),
            make_label("set_002", "1", "20240310"),
            make_label("set_003", "1", "20240310"),
            make_label("set_004", "1", "20240310"),
            make_label("set_005", "1", "20240311"),
        ]

        synced, _, latest_time, latest_id = connector.process_batch(
            session=None,
            configuration=base_config,
            labels=labels,
            is_enrichment_enabled=False,
            enriched_count=0,
            max_enrichments=0,
            last_effective_time="20240310",
            last_label_id="set_002_1",  # exclude set_001 and set_002 from re-sync
        )

        assert synced == 3, f"Expected 3 new records (set_003-005), got {synced}"
        assert latest_time == "20240311"
        assert latest_id == "set_005_1"
        # Verify the right ones were upserted
        upserted_ids = [u["data"].get("label_id") for u in captured_upserts["upserts"]]
        assert "set_001_1" not in upserted_ids
        assert "set_002_1" not in upserted_ids
        assert "set_003_1" in upserted_ids
        assert "set_005_1" in upserted_ids


class TestCapHitOnSingleDayDoesNotLoopForever:
    """The pre-fix bug: max_labels=2 + 4 records on the same day → infinite
    loop. The fix: cursor advances to (day, last_id_synced), so the next
    sync skips the first two and processes the remaining ones."""

    def test_two_consecutive_runs_advance_through_one_day(self, base_config, captured_upserts):
        # Day 20240310 has 4 labels; max_labels = 2 per sync
        all_labels = [
            make_label("set_001", "1", "20240310"),
            make_label("set_002", "1", "20240310"),
            make_label("set_003", "1", "20240310"),
            make_label("set_004", "1", "20240310"),
        ]

        # Sync 1: fresh state, process first 2
        synced1, _, lt1, li1 = connector.process_batch(
            session=None,
            configuration=base_config,
            labels=all_labels[:2],
            is_enrichment_enabled=False,
            enriched_count=0,
            max_enrichments=0,
            last_effective_time=None,
            last_label_id=None,
        )
        assert synced1 == 2
        assert lt1 == "20240310"
        assert li1 == "set_002_1"

        # Sync 2: same date filter [20240310+TO+20991231] returns ALL 4 records
        # again (inclusive), but the cursor (20240310, set_002_1) must skip
        # the first two.
        synced2, _, lt2, li2 = connector.process_batch(
            session=None,
            configuration=base_config,
            labels=all_labels,  # API would re-return all due to inclusive range
            is_enrichment_enabled=False,
            enriched_count=0,
            max_enrichments=0,
            last_effective_time=lt1,
            last_label_id=li1,
        )
        assert synced2 == 2, f"Expected 2 new records (set_003, set_004), got {synced2}"
        assert lt2 == "20240310"
        assert li2 == "set_004_1"

        # Total upserts across both runs should be exactly 4 — no duplicates.
        upserted_ids = [u["data"].get("label_id") for u in captured_upserts["upserts"]]
        assert sorted(upserted_ids) == ["set_001_1", "set_002_1", "set_003_1", "set_004_1"]


class TestBuildLabelId:
    """The compound cursor depends on a stable label_id. Verify the helper
    is deterministic across invocations."""

    def test_set_id_with_version_produces_stable_id(self):
        label = {"set_id": "abc-123", "version": "5", "id": "doc-99"}
        assert connector.build_label_id(label) == "abc-123_5"

    def test_falls_back_to_id_when_set_id_missing(self):
        label = {"id": "doc-99", "version": "5"}
        assert connector.build_label_id(label) == "doc-99"

    def test_two_calls_same_input_produce_same_id(self):
        label = {"set_id": "abc", "version": "1"}
        assert connector.build_label_id(label) == connector.build_label_id(label)
