"""Schema-drift tests: README ↔ build_product_record() + enrich_product() parity.

# see snowflake-cortex-code-clinical-trial-intelligence/tests/integration/test_schema_consistency.py
# for the canonical pattern.
"""

import json
import re
from pathlib import Path

import connector

README_PATH = Path(__file__).parent.parent.parent / "README.md"


def _extract_table_columns(table_name):
    text = README_PATH.read_text()
    section_re = re.compile(
        rf"^### {re.escape(table_name)}\s*\n(.*?)(?=^###|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = section_re.search(text)
    if not match:
        return set()
    return set(re.findall(r"^\s*-\s+`([a-z_][a-z0-9_]*)`\s*\(", match.group(1), re.MULTILINE))


class TestProductsEnrichedSchemaParity:
    def test_record_columns_match_readme(self, minimal_product, base_config, monkeypatch):
        """The full record (raw + enrichment) must match the README columns."""
        record = connector.build_product_record(minimal_product)
        # Stub call_ai_query so enrich_product runs without network.
        monkeypatch.setattr(
            connector,
            "call_ai_query",
            lambda *a, **kw: json.dumps(
                {
                    "competitive_positioning": "PREMIUM",
                    "price_optimization": "x",
                    "price_action": "MAINTAIN",
                    "sentiment_summary": "x",
                    "retail_category_ai": "Computing",
                }
            ),
        )
        enrichment = connector.enrich_product(None, base_config, record)
        record.update(enrichment)
        code_columns = set(record.keys())
        readme_columns = _extract_table_columns("PRODUCTS_ENRICHED")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns

        assert (
            not in_code_not_readme
        ), f"Code emits columns missing from README: {sorted(in_code_not_readme)}"
        assert (
            not in_readme_not_code
        ), f"README declares columns not emitted by code: {sorted(in_readme_not_code)}"


class TestEnrichmentPromptDeclaredColumns:
    """The enrichment prompt asks the model for specific keys; every key
    must be declared in the README."""

    def test_prompt_keys_all_in_readme(self, minimal_product, base_config, monkeypatch):
        # Capture the prompt the connector sends.
        prompts = []

        def fake_call(session, configuration, prompt):
            prompts.append(prompt)
            return None

        monkeypatch.setattr(connector, "call_ai_query", fake_call)
        record = connector.build_product_record(minimal_product)
        connector.enrich_product(None, base_config, record)

        assert prompts, "enrich_product should call ai_query"
        prompt = prompts[0]
        readme_columns = _extract_table_columns("PRODUCTS_ENRICHED")

        for key in (
            "competitive_positioning",
            "price_optimization",
            "price_action",
            "sentiment_summary",
            "retail_category_ai",
        ):
            assert key in prompt, f"Enrichment prompt missing key {key!r}"
            assert key in readme_columns, f"Prompt asks for {key!r} but README does not declare it"


class TestConfigKeysDocumented:
    def test_all_config_keys_in_readme(self):
        cfg = json.loads((Path(__file__).parent.parent.parent / "configuration.json").read_text())
        readme = README_PATH.read_text()
        missing = [k for k in cfg if k not in readme]
        assert not missing, f"Config keys missing from README: {missing}"
