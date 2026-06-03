"""Pagination + record-count tests for Best Buy connector.

This connector uses snapshot semantics — every sync re-fetches the same
top-N products sorted by customerReviewCount.dsc. There is no incremental
cursor.

Two structural risks remain:

1. `pageSize=min(batch_size, max_products)` — if user sets max_products=100
   but leaves batch_size at the default 25, only 25 records are fetched.
   A reasonable connector either pages the request or clamps batch_size up
   so max_products is always honoured.

2. `search_category` interpolated unescaped into the URL path. If a user
   types `Laptops)` or `Laptops AND categoryPath.name=TVs` the URL becomes
   malformed.
"""

from urllib.parse import quote, urlparse

import connector
from tests.conftest import make_product


class TestMaxProductsHonoured:
    """When the user requests max_products=N, the connector should sync N
    records (or all available if fewer). The current implementation caps at
    min(batch_size, max_products) per API call and does not page, so a
    50-product request with default batch_size=25 only delivers 25."""

    def test_max_products_25_default_batch_returns_25(
        self, base_config, captured_upserts, monkeypatch
    ):
        """Sanity: max_products=25, batch_size=25, page returns 25 → 25 synced."""
        products = [make_product(100000 + i, name=f"Product {i}") for i in range(25)]
        config = dict(base_config)
        config["max_products"] = "25"
        config["batch_size"] = "25"
        config["enable_enrichment"] = "false"

        def fake_fetch(session, url, params=None):
            requested = params.get("pageSize", 25)
            return {
                "products": products[:requested],
                "total": len(products),
            }

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        connector.update(config, {})

        synced = [u for u in captured_upserts["upserts"] if u["table"] == "products_enriched"]
        assert len(synced) == 25

    def test_max_products_above_batch_size_should_still_honour_max(
        self, base_config, captured_upserts, monkeypatch
    ):
        """User requests max_products=50 but batch_size=25. The connector
        should either page the request or clamp pageSize up — either way,
        50 records should land. Currently, only 25 land, which is the bug
        this test pins."""
        products = [make_product(100000 + i, name=f"Product {i}") for i in range(50)]
        config = dict(base_config)
        config["max_products"] = "50"
        config["batch_size"] = "25"
        config["enable_enrichment"] = "false"

        page_calls = []

        def fake_fetch(session, url, params=None):
            page_calls.append(dict(params or {}))
            requested = int(params.get("pageSize", 25))
            page = int(params.get("page", 1))
            start = (page - 1) * requested
            return {
                "products": products[start : start + requested],
                "total": len(products),
            }

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        connector.update(config, {})

        synced = [u for u in captured_upserts["upserts"] if u["table"] == "products_enriched"]
        assert len(synced) == 50, (
            f"max_products=50 but only {len(synced)} synced — connector either "
            f"needs to page the API call or use pageSize=max_products. "
            f"page_calls={page_calls}"
        )


class TestSearchCategoryUrlSafety:
    """The search_category value is interpolated directly into the URL path
    via f"...products(categoryPath.name={search_category})". Special chars
    must be URL-encoded so user-supplied values can't break the URL."""

    def test_unencoded_close_paren_does_not_break_url(
        self, base_config, captured_upserts, monkeypatch
    ):
        """search_category='Laptops)' or value containing a close-paren must
        either be URL-encoded or rejected at validation. Otherwise the URL
        path becomes malformed (closes the categoryPath.name filter early)."""
        urls_seen = []

        def fake_fetch(session, url, params=None):
            urls_seen.append(url)
            return {"products": [], "total": 0}

        config = dict(base_config)
        config["search_category"] = "Laptops)"  # contains close-paren
        config["enable_enrichment"] = "false"
        config["max_products"] = "10"

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        connector.update(config, {})

        assert urls_seen, "Connector should have made at least one fetch call"
        url = urls_seen[0]
        # The unbalanced close-paren must not appear raw in the URL path.
        # Either it's URL-encoded as %29 OR the connector escapes it.
        # We check that the path is parseable and balanced.
        parsed = urlparse(url)
        opens = parsed.path.count("(")
        closes = parsed.path.count(")")
        assert opens == closes, (
            f"Unbalanced parens in URL path due to unescaped search_category. "
            f"path={parsed.path}"
        )

    def test_space_in_category_is_url_encoded(self, base_config, captured_upserts, monkeypatch):
        """A category like 'Smart Home' contains a space — must be URL-encoded."""
        urls_seen = []

        def fake_fetch(session, url, params=None):
            urls_seen.append(url)
            return {"products": [], "total": 0}

        config = dict(base_config)
        config["search_category"] = "Smart Home"
        config["enable_enrichment"] = "false"
        config["max_products"] = "10"

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        connector.update(config, {})

        url = urls_seen[0]
        # Either the space is encoded (%20) or replaced with +, but raw space
        # in a URL path is invalid.
        assert (
            " " not in urlparse(url).path
        ), f"Raw space in URL path — search_category not URL-encoded. url={url}"
        assert quote("Smart Home", safe="") in url or "Smart%20Home" in url or "Smart+Home" in url


class TestStateIsCheckpointed:
    """Even though this connector has no incremental cursor, op.checkpoint()
    must be called per Fivetran best practices."""

    def test_checkpoint_called_on_normal_run(
        self, base_config, captured_upserts, sample_enrichment_response, monkeypatch
    ):
        import json

        products = [make_product(100000 + i, name=f"Product {i}") for i in range(3)]

        def fake_fetch(session, url, params=None):
            return {"products": products, "total": 3}

        def fake_call(session, configuration, prompt):
            return json.dumps(sample_enrichment_response)

        config = dict(base_config)
        config["max_products"] = "3"
        config["batch_size"] = "3"

        monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
        monkeypatch.setattr(connector, "call_ai_query", fake_call)
        connector.update(config, {})

        assert len(captured_upserts["checkpoints"]) >= 1
