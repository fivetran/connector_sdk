"""Schema consistency tests — README columns ↔ build_label_record emitted keys."""

import re
from pathlib import Path

import connector

README_PATH = Path(__file__).parent.parent.parent / "README.md"


def _extract_table_columns(table_name):
    text = README_PATH.read_text()
    section = re.search(
        rf"^### {re.escape(table_name)}\s*\n(.*?)(?=^### |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        return set()
    body = section.group(1)
    return set(re.findall(r"^\s*-\s+`([a-z_][a-z0-9_]*)`\s*\(", body, re.MULTILINE))


def _maximally_populated_label():
    """Build a label dict exercising every field build_label_record touches."""
    return {
        "set_id": "abc-123",
        "version": "5",
        "id": "doc-99",
        "effective_time": "20240310",
        "openfda": {
            "brand_name": ["TestBrand"],
            "generic_name": ["testgeneric"],
            "manufacturer_name": ["TestPharma"],
            "product_type": ["HUMAN PRESCRIPTION DRUG"],
            "route": ["ORAL"],
            "rxcui": ["12345"],
            "spl_set_id": ["set-abc-123"],
        },
        "indications_and_usage": ["For headache."],
        "warnings": ["Consult doctor if pregnant."],
        "boxed_warning": ["Risk of bleeding."],
        "contraindications": ["Allergy to aspirin."],
        "adverse_reactions": ["Nausea."],
        "drug_interactions": ["Avoid alcohol."],
        "dosage_and_administration": ["Take 1 tablet."],
    }


_AI_ENRICHMENT_FIELDS = {
    "interaction_risk_level",
    "contraindication_summary",
    "has_black_box_warning",
    "black_box_summary",
    "patient_friendly_description",
    "therapeutic_category",
    "enrichment_model",
}


class TestDrugLabelsEnrichedSchemaParity:
    def test_base_record_columns_match_readme_minus_ai_fields(self):
        """build_label_record emits only the OpenFDA-derived columns. The AI
        enrichment fields are added downstream by enrich_drug_label() before
        upsert. The full README schema = build_label_record output ∪
        AI enrichment fields."""
        label = _maximally_populated_label()
        record = connector.build_label_record(label, connector.build_label_id(label))
        code_columns = set(record.keys())
        readme_columns = _extract_table_columns("DRUG_LABELS_ENRICHED")
        readme_minus_ai = readme_columns - _AI_ENRICHMENT_FIELDS

        in_code_not_readme = code_columns - readme_columns
        in_readme_minus_ai_not_code = readme_minus_ai - code_columns

        assert (
            not in_code_not_readme
        ), f"build_label_record emits columns missing from README: {sorted(in_code_not_readme)}"
        assert not in_readme_minus_ai_not_code, (
            f"README declares non-AI columns not emitted by build_label_record: "
            f"{sorted(in_readme_minus_ai_not_code)}"
        )

    def test_enrichment_fields_documented_in_readme(self):
        """Every AI enrichment field referenced in enrich_drug_label must be
        listed in the README schema. This catches drift where a new AI field
        is added to the connector but not docs."""
        readme_columns = _extract_table_columns("DRUG_LABELS_ENRICHED")
        missing_in_readme = _AI_ENRICHMENT_FIELDS - readme_columns
        assert (
            not missing_in_readme
        ), f"AI enrichment fields missing from README schema: {sorted(missing_in_readme)}"


class TestNoSqlReservedKeywordsAsColumnNames:
    """Regression scan from PR #555 — no column may collide with SQL
    reserved keywords."""

    def test_no_reserved_keywords(self):
        label = _maximally_populated_label()
        record = connector.build_label_record(label, connector.build_label_id(label))
        sql_reserved = {"by", "from", "select", "where", "order", "group", "join", "table"}
        clashing = set(record.keys()) & sql_reserved
        assert not clashing, (
            f"Column name(s) collide with SQL reserved keywords: {clashing}. "
            f"This produces a destination CREATE TABLE parser error at sync time."
        )
