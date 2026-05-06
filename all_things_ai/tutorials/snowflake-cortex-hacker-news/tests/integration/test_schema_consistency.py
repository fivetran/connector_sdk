r"""Schema consistency tests — README columns ↔ stories_enriched emitted keys.

Catches the documentation drift bug: a column added to the upsert payload
but not to the README, or vice versa. README parsing here matches the
bullet-list format ``- `column_name` (TYPE...): description``.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import connector

README_PATH = Path(__file__).parent.parent.parent / "README.md"


def _extract_table_columns(table_name):
    """Extract backtick-delimited column names from the bullet-list section
    starting at `### TABLE_NAME`. Returns a set of column names."""
    text = README_PATH.read_text()
    section = re.search(
        rf"^### {re.escape(table_name)}\s*\n(.*?)(?=^### |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        return set()
    body = section.group(1)
    # Match bullet-list rows: `- `column_name` (TYPE...): ...`
    return set(re.findall(r"^-\s+`([a-z_][a-z0-9_]*)`\s*\(", body, re.MULTILINE))


def _maximally_populated_story(story_id=12345):
    """Build a story record exercising every field the README declares."""
    return {
        "id": story_id,
        "by": "test_user",
        "title": "Test Story Title",
        "url": "https://example.com/article",
        "score": 100,
        "descendants": 25,
        "time": 1700000000,
        "type": "story",
        "text": "Body text for an Ask HN style post.",
        "kids": [10001, 10002, 10003],
    }


@pytest.fixture
def captured_for_each_table(captured_upserts):
    def for_table(table_name):
        cols = set()
        for u in captured_upserts["upserts"]:
            if u["table"] == table_name:
                cols.update(u["data"].keys())
        return cols

    return for_table


class TestStoriesEnrichedSchemaParity:
    def test_columns_match_readme(
        self,
        base_config,
        captured_upserts,
        captured_for_each_table,
        monkeypatch,
        sample_sentiment_response,
        sample_classification_response,
    ):
        """Run process_batch with a maximally-populated story + Cortex
        enrichments enabled. Compare the upserted column set to the README
        declaration."""
        story = _maximally_populated_story()

        def fake_fetch(session, url, params=None, headers=None):
            return story

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        monkeypatch.setattr(
            connector, "call_cortex_sentiment", lambda *a, **kw: sample_sentiment_response
        )
        monkeypatch.setattr(
            connector,
            "call_cortex_classification",
            lambda *a, **kw: sample_classification_response,
        )

        session = MagicMock()
        connector.process_batch(
            session,
            base_config,
            [story["id"]],
            is_cortex_enabled=True,
            enriched_count=0,
            max_enrichments=10,
            state={"last_synced_id": 0},
        )

        code_columns = captured_for_each_table("stories_enriched")
        readme_columns = _extract_table_columns("STORIES_ENRICHED")

        missing_from_readme = code_columns - readme_columns
        missing_from_code = readme_columns - code_columns

        assert (
            not missing_from_readme
        ), f"Code emits columns missing from README: {missing_from_readme}"
        assert not missing_from_code, f"README declares columns not in code: {missing_from_code}"

    def test_no_sql_reserved_keywords_as_column_names(
        self,
        base_config,
        captured_upserts,
        captured_for_each_table,
        monkeypatch,
        sample_sentiment_response,
        sample_classification_response,
    ):
        """Regression: HN's `by` field collides with the reserved SQL keyword
        BY. Emitting it directly as a column name produces a destination
        CREATE TABLE parser error at sync time (verified empirically against
        DuckDB via `fivetran debug`). The connector must rename it before
        upsert. Test enforces: no commonly-reserved SQL keyword appears as a
        column name in the emitted payload."""
        story = _maximally_populated_story()

        def fake_fetch(session, url, params=None, headers=None):
            return story

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        monkeypatch.setattr(
            connector, "call_cortex_sentiment", lambda *a, **kw: sample_sentiment_response
        )
        monkeypatch.setattr(
            connector,
            "call_cortex_classification",
            lambda *a, **kw: sample_classification_response,
        )

        session = MagicMock()
        connector.process_batch(
            session,
            base_config,
            [story["id"]],
            is_cortex_enabled=True,
            enriched_count=0,
            max_enrichments=10,
            state={"last_synced_id": 0},
        )

        code_columns = captured_for_each_table("stories_enriched")
        # Non-exhaustive, but covers the high-frequency offenders. DuckDB
        # specifically chokes on BY without quoting; ANSI SQL reserves the others.
        sql_reserved = {"by", "from", "select", "where", "order", "group", "join", "table"}
        clashing = code_columns & sql_reserved
        assert not clashing, (
            f"Column name(s) collide with SQL reserved keywords: {clashing}. "
            f"This produces a destination CREATE TABLE parser error at sync time "
            f"(verified via `fivetran debug`)."
        )
        # Specific assertion for the `by` -> `submitted_by` rename
        assert "by" not in code_columns, (
            "`by` must not appear as a column name (reserved keyword in DuckDB "
            "and most warehouses). The connector renames HN's `by` field to "
            "`submitted_by` before upsert."
        )
        assert (
            "submitted_by" in code_columns
        ), "Renamed column `submitted_by` must appear in the emitted payload."

    def test_unenriched_story_omits_cortex_fields(
        self, base_config, captured_upserts, captured_for_each_table, monkeypatch
    ):
        """When enrichment is disabled, the cortex_* columns must NOT appear
        in the upsert payload (Fivetran handles missing columns gracefully)."""
        story = _maximally_populated_story()

        def fake_fetch(session, url, params=None, headers=None):
            return story

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)

        session = MagicMock()
        connector.process_batch(
            session,
            base_config,
            [story["id"]],
            is_cortex_enabled=False,
            enriched_count=0,
            max_enrichments=0,
            state={"last_synced_id": 0},
        )

        code_columns = captured_for_each_table("stories_enriched")
        cortex_cols = {c for c in code_columns if c.startswith("cortex_")}
        assert (
            not cortex_cols
        ), f"Cortex columns must NOT appear when enrichment is disabled, got: {cortex_cols}"
