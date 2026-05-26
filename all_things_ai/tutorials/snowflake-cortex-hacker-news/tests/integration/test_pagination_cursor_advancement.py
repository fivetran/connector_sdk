"""Cursor advancement tests — `last_synced_id` correctness across batches and
across the halt-on-fetch-failure code path.

The connector uses an ID-based incremental cursor (`last_synced_id`). The
`process_batch` function has explicit halt-on-fetch-failure semantics
(commit cff5845e fixed the regression where a failed lower-ID story would
let the cursor jump past it). These tests prevent that regression.

Plus: repeated syncs against a window > max_stories must drain all stories
exactly once, with no duplicate upserts.
"""

import pytest

import connector


@pytest.fixture
def hn_universe(monkeypatch):
    """Stub HN topstories + per-story fetch with a closure-controlled universe.
    Tests can populate `state["all_ids"]`, `state["stories"]`, and
    `state["fail_ids"]` (set of IDs whose fetch should raise RuntimeError)."""
    state = {"all_ids": [], "stories": {}, "fail_ids": set()}

    def fake_fetch(session, url, params=None, headers=None):
        if "topstories.json" in url:
            return list(state["all_ids"])
        story_id = int(url.split("/item/")[-1].replace(".json", ""))
        if story_id in state["fail_ids"]:
            raise RuntimeError(f"simulated fetch failure for story {story_id}")
        return state["stories"].get(story_id)

    monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
    return state


@pytest.fixture
def cortex_disabled(monkeypatch):
    """Disable Cortex in the test config to keep these tests focused on cursor logic."""
    pass  # config-level disable handled per-test


def _make_story(sid):
    return {
        "id": sid,
        "type": "story",
        "title": f"Story {sid}",
        "by": "u",
        "time": 1700000000 + sid,
    }


class TestCursorAdvancement:
    def test_cursor_advances_to_highest_synced_id(
        self, base_config, captured_upserts, hn_universe
    ):
        """After syncing stories 100, 101, 102, the cursor lands at 102."""
        base_config["enable_cortex"] = "false"
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        hn_universe["all_ids"] = [100, 101, 102]
        hn_universe["stories"] = {sid: _make_story(sid) for sid in [100, 101, 102]}

        state = {}
        connector.update(base_config, state)
        # Final checkpoint must record 102
        assert captured_upserts["checkpoints"][-1] == {"last_synced_id": 102}

    def test_cursor_does_not_advance_past_failed_lower_id(
        self, base_config, captured_upserts, hn_universe
    ):
        """If fetching story 101 fails (mid-batch), the cursor must stop at
        100, NOT advance to 102. This is the regression that commit cff5845e
        fixed — without halt-on-failure, the cursor would jump to 102 and
        story 101 would be lost."""
        base_config["enable_cortex"] = "false"
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        base_config["max_stories"] = "10"
        base_config["batch_size"] = "10"

        hn_universe["all_ids"] = [100, 101, 102, 103]
        hn_universe["stories"] = {sid: _make_story(sid) for sid in [100, 101, 102, 103]}
        hn_universe["fail_ids"] = {101}

        state = {}
        connector.update(base_config, state)

        # Cursor must land at 100 (story before the failure) — NOT 103
        last_checkpoint = captured_upserts["checkpoints"][-1]
        assert last_checkpoint["last_synced_id"] == 100, (
            f"Cursor must halt at 100 when story 101 fails to fetch, "
            f"got {last_checkpoint['last_synced_id']}. "
            f"This is the regression fixed in commit cff5845e."
        )
        # Only story 100 should have been upserted (101 failed; loop halted before 102/103)
        synced_ids = [u["data"]["id"] for u in captured_upserts["upserts"]]
        assert synced_ids == [100]

    def test_cursor_advances_past_legitimate_skips(
        self, base_config, captured_upserts, hn_universe
    ):
        """Items that are deleted (None response) or non-story types (comment,
        job, poll) are legitimate skips; the cursor SHOULD advance past them."""
        base_config["enable_cortex"] = "false"
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        base_config["max_stories"] = "10"
        base_config["batch_size"] = "10"

        hn_universe["all_ids"] = [100, 101, 102]
        hn_universe["stories"] = {
            100: _make_story(100),
            101: {"id": 101, "type": "comment", "text": "a comment"},  # legit skip
            102: _make_story(102),
        }

        state = {}
        connector.update(base_config, state)

        # Cursor must land at 102 (advanced past the comment at 101)
        assert captured_upserts["checkpoints"][-1]["last_synced_id"] == 102
        # Only stories 100 and 102 upserted; 101 is a comment, skipped
        synced_ids = sorted([u["data"]["id"] for u in captured_upserts["upserts"]])
        assert synced_ids == [100, 102]


class TestRepeatedSyncsNoDuplicates:
    """Repeated syncs against a window > max_stories must drain all stories
    exactly once."""

    def test_drains_all_in_finite_runs_no_duplicates(
        self, base_config, captured_upserts, hn_universe
    ):
        base_config["enable_cortex"] = "false"
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        base_config["max_stories"] = "5"
        base_config["batch_size"] = "5"

        all_ids = list(range(1000, 1015))  # 15 stories
        hn_universe["all_ids"] = all_ids
        hn_universe["stories"] = {sid: _make_story(sid) for sid in all_ids}

        state = {}
        for _ in range(5):  # 5 syncs of 5 stories each — should drain all 15
            connector.update(base_config, state)
            state = (
                dict(captured_upserts["checkpoints"][-1])
                if captured_upserts["checkpoints"]
                else {}
            )

        synced_ids = sorted([u["data"]["id"] for u in captured_upserts["upserts"]])
        assert synced_ids == sorted(all_ids), (
            f"Repeated syncs must drain all 15 stories exactly once. "
            f"Got {len(synced_ids)} unique IDs (expected 15)."
        )
        # And no duplicates
        assert len(synced_ids) == len(set(synced_ids))


class TestSortedAscending:
    """The connector sorts new_story_ids ascending so that a failure on a
    lower-ID story halts before higher-ID stories. This test verifies the
    sort happens (regression: if someone removes the sort, halt-on-failure
    could skip past lower-ID stories that fail later in fetch order)."""

    def test_processes_in_ascending_id_order(self, base_config, captured_upserts, hn_universe):
        base_config["enable_cortex"] = "false"
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        base_config["max_stories"] = "10"
        base_config["batch_size"] = "10"

        # HN topstories often returns in score-rank order (effectively random
        # by ID). Provide IDs in non-sorted order to verify the sort happens.
        hn_universe["all_ids"] = [105, 100, 110, 102, 108]
        hn_universe["stories"] = {sid: _make_story(sid) for sid in hn_universe["all_ids"]}

        connector.update(base_config, {})

        synced_ids = [u["data"]["id"] for u in captured_upserts["upserts"]]
        assert synced_ids == [100, 102, 105, 108, 110], (
            f"Stories must be processed in ascending ID order so that "
            f"halt-on-failure correctly preserves cursor invariants. Got: {synced_ids}"
        )
