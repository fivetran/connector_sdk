"""Schema consistency tests — README columns ↔ build_company_record + financial_facts schema."""

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


def _maximally_populated_company_info():
    return {
        "cik": "320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "exchanges": ["Nasdaq"],
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "category": "Large accelerated filer",
        "fiscalYearEnd": "0930",
        "stateOfIncorporation": "CA",
        "addresses": {"business": {"city": "Cupertino"}},
        "phone": "1-408-996-1010",
    }


class TestCompanyFilingsSchemaParity:
    def test_columns_match_readme(self):
        record = connector.build_company_record(
            _maximally_populated_company_info(),
            "0000320193",
            "seed",
        )
        code_columns = set(record.keys())
        readme_columns = _extract_table_columns("COMPANY_FILINGS")

        in_code_not_readme = code_columns - readme_columns
        in_readme_not_code = readme_columns - code_columns

        assert (
            not in_code_not_readme
        ), f"Code emits columns missing from README: {sorted(in_code_not_readme)}"
        assert (
            not in_readme_not_code
        ), f"README declares columns not emitted by build_company_record: {sorted(in_readme_not_code)}"


class TestNoSqlReservedKeywordsAsColumnNames:
    """Regression scan from PR #555."""

    def test_no_reserved_keywords(self):
        record = connector.build_company_record(
            _maximally_populated_company_info(),
            "0000320193",
            "seed",
        )
        sql_reserved = {
            "by",
            "from",
            "select",
            "where",
            "order",
            "group",
            "join",
            "table",
        }
        clashing = set(record.keys()) & sql_reserved
        assert not clashing, (
            f"Column name(s) collide with SQL reserved keywords: {clashing}. "
            f"This produces a destination CREATE TABLE parser error at sync time."
        )
