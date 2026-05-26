"""Lock the README contract for max_enrichments and max_products.

`max_enrichments` caps the number of products that get enriched via
ai_query() per sync. `max_products` caps the number of products synced
to the destination per sync.
"""

import pytest

import connector


@pytest.mark.parametrize("max_enrichments", [1, 2, 3, 5])
def test_max_enrichments_caps_ai_query_calls(
    max_enrichments,
    base_config,
    product_batch,
    captured_upserts,
    sample_enrichment_response,
    monkeypatch,
):
    """README contract: max_enrichments caps the ai_query() calls per sync."""
    config = dict(base_config)
    config["max_enrichments"] = str(max_enrichments)
    config["max_products"] = "10"
    config["batch_size"] = "10"

    ai_calls = []

    def fake_call_ai_query(session, configuration, prompt):
        ai_calls.append(prompt[:60])
        import json

        return json.dumps(sample_enrichment_response)

    def fake_fetch(session, url, params=None):
        return {"products": product_batch, "total": len(product_batch)}

    monkeypatch.setattr(connector, "call_ai_query", fake_call_ai_query)
    monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)

    connector.update(config, {})

    assert len(ai_calls) <= max_enrichments, (
        f"Budget violated: max_enrichments={max_enrichments} but "
        f"{len(ai_calls)} ai_query() calls were made."
    )

    enriched = sum(
        1
        for u in captured_upserts["upserts"]
        if u["table"] == "products_enriched"
        if u["data"].get("competitive_positioning") is not None
    )
    assert (
        enriched <= max_enrichments
    ), f"max_enrichments={max_enrichments} but {enriched} records had enrichment."


def test_enrichment_disabled_makes_zero_ai_query_calls(
    base_config, product_batch, captured_upserts, monkeypatch
):
    config = dict(base_config)
    config["enable_enrichment"] = "false"
    config["max_products"] = "10"
    config["batch_size"] = "10"

    ai_calls = []

    def fake_call_ai_query(session, configuration, prompt):
        ai_calls.append(prompt)
        return None

    def fake_fetch(session, url, params=None):
        return {"products": product_batch, "total": len(product_batch)}

    monkeypatch.setattr(connector, "call_ai_query", fake_call_ai_query)
    monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)

    connector.update(config, {})

    assert len(ai_calls) == 0, "enable_enrichment=false must not call ai_query()"
    # All products should still be synced (data-only mode).
    assert len(captured_upserts["upserts"]) == len(product_batch)


def test_max_products_caps_synced_records(
    base_config, captured_upserts, sample_enrichment_response, monkeypatch
):
    """max_products=3 against a 10-product page should sync exactly 3."""
    from tests.conftest import make_product

    products = [make_product(100000 + i, name=f"Product {i}") for i in range(10)]

    config = dict(base_config)
    config["max_products"] = "3"
    config["max_enrichments"] = "<MAX_ENRICHMENTS_PER_SYNC>"
    config["enable_enrichment"] = "false"
    config["batch_size"] = "10"

    def fake_fetch(session, url, params=None):
        return {"products": products, "total": len(products)}

    monkeypatch.setattr(connector, "fetch_data_with_retry", fake_fetch)
    connector.update(config, {})

    synced = [u for u in captured_upserts["upserts"] if u["table"] == "products_enriched"]
    assert len(synced) == 3, f"max_products=3 but {len(synced)} records were upserted."
