"""Shared pytest fixtures for the Best Buy Databricks connector tests.

Databricks ai_query() pattern (PAT auth + async polling). Mirrors the NOAA
weather connector conftest with Best Buy-specific deltas: Best Buy Products
API page response (sku/name/salePrice), single-table schema (products_enriched),
and the optional `search_category` URL-path filter.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fivetran_connector_sdk import Logging as _sdk_logging  # noqa: E402

if _sdk_logging.LOG_LEVEL is None:
    _sdk_logging.LOG_LEVEL = _sdk_logging.Level.INFO


@pytest.fixture
def base_config():
    """Known-good configuration with enrichment enabled and non-placeholder Databricks creds."""
    return {
        "api_key": "bestbuy_test_api_key_abc123",
        "databricks_workspace_url": "https://abc.cloud.databricks.com",
        "databricks_token": "dapi_test_token_abc123",
        "databricks_warehouse_id": "warehouse_test_abc123",
        "databricks_model": "databricks-claude-sonnet-4-6",
        "enable_enrichment": "true",
        "enable_genie_space": "false",
        "genie_table_identifier": "<CATALOG.SCHEMA.TABLE>",
        "search_category": "<CATEGORY_NAME_OR_EMPTY>",
        "max_products": "10",
        "max_enrichments": "5",
        "batch_size": "10",
        "databricks_timeout": "60",
    }


def make_product(
    sku,
    name="Test Product",
    sale_price=199.99,
    regular_price=249.99,
    review_avg=4.5,
    review_count=100,
    manufacturer="TestBrand",
    category="Laptops",
    short_description="A great test product.",
):
    """Build a minimal raw Best Buy product record."""
    return {
        "sku": sku,
        "name": name,
        "salePrice": sale_price,
        "regularPrice": regular_price,
        "onSale": sale_price < regular_price,
        "percentSavings": (
            ((regular_price - sale_price) / regular_price * 100) if regular_price else 0
        ),
        "customerReviewAverage": review_avg,
        "customerReviewCount": review_count,
        "manufacturer": manufacturer,
        "shortDescription": short_description,
        "categoryPath": [{"name": "Computers"}, {"name": category}],
        "condition": "New",
        "freeShipping": True,
        "inStoreAvailability": True,
        "onlineAvailability": True,
        "url": f"https://bestbuy.com/product/{sku}",
    }


@pytest.fixture
def minimal_product():
    return make_product(123456)


@pytest.fixture
def product_batch():
    """10 products with sequential SKUs."""
    return [make_product(100000 + i, name=f"Product {i}") for i in range(10)]


@pytest.fixture
def sample_enrichment_response():
    """Canonical ai_query() JSON content the connector parses."""
    return {
        "competitive_positioning": "PREMIUM",
        "price_optimization": "Price is competitive given strong reviews and category positioning.",
        "price_action": "MAINTAIN",
        "sentiment_summary": "Likely positive based on 4.5/5 review average.",
        "retail_category_ai": "Computing",
    }


@pytest.fixture
def captured_upserts(monkeypatch):
    """Patch op.upsert and op.checkpoint to no-ops; yield captured records."""
    import connector

    captured = {"upserts": [], "checkpoints": []}

    def fake_upsert(table, data):
        captured["upserts"].append({"table": table, "data": data})

    def fake_checkpoint(state):
        captured["checkpoints"].append(dict(state) if state else {})

    monkeypatch.setattr(connector.op, "upsert", fake_upsert)
    monkeypatch.setattr(connector.op, "checkpoint", fake_checkpoint)
    monkeypatch.setattr(connector.time, "sleep", lambda *_: None)
    return captured
