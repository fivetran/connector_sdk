"""Unit tests for connector helper functions."""

import json

import connector


class TestIsPlaceholder:
    def test_none(self):
        assert connector._is_placeholder(None) is True

    def test_empty(self):
        assert connector._is_placeholder("") is True

    def test_angle_bracketed(self):
        assert connector._is_placeholder("<X>") is True

    def test_real_value(self):
        assert connector._is_placeholder("real") is False

    def test_non_string(self):
        assert connector._is_placeholder(42) is False


class TestParseBool:
    def test_passthrough(self):
        assert connector._parse_bool(True) is True
        assert connector._parse_bool(False) is False

    def test_placeholder_default(self):
        assert connector._parse_bool("<X>", default=True) is True

    def test_string_true_variants(self):
        assert connector._parse_bool("true") is True
        assert connector._parse_bool("TRUE") is True


class TestOptionalInt:
    def test_placeholder_default(self):
        assert connector._optional_int({"x": "<Y>"}, "x", 42) == 42

    def test_valid(self):
        assert connector._optional_int({"x": "7"}, "x", 42) == 7


class TestOptionalStr:
    def test_placeholder_default(self):
        assert connector._optional_str({"x": "<Y>"}, "x", "default") == "default"

    def test_valid(self):
        assert connector._optional_str({"x": "value"}, "x", "default") == "value"


class TestFlattenDict:
    def test_flat(self):
        assert connector.flatten_dict({"a": 1}) == {"a": 1}

    def test_nested(self):
        assert connector.flatten_dict({"a": {"b": 1}}) == {"a_b": 1}

    def test_list_serialized(self):
        result = connector.flatten_dict({"keys": [1, 2]})
        assert json.loads(result["keys"]) == [1, 2]


class TestPadCik:
    def test_pads_to_10(self):
        assert connector.pad_cik("320193") == "0000320193"

    def test_already_padded(self):
        assert connector.pad_cik("0000320193") == "0000320193"


class TestExtractLatestFacts:
    """Regression for Copilot finding L518: must select latest by `filed`
    date, not by list position."""

    def test_picks_latest_by_filed_date(self):
        facts_data = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "filed": "2022-01-01", "val": 100},
                                {"form": "10-K", "filed": "2024-01-01", "val": 300},
                                {"form": "10-K", "filed": "2023-01-01", "val": 200},
                            ]
                        }
                    }
                }
            }
        }
        records = connector.extract_latest_facts(facts_data, "0000320193")
        revenue_records = [r for r in records if r["metric"] == "Revenues"]
        assert len(revenue_records) == 1
        # Pre-fix bug: returned filing_values[-1] (the 2023 one — last in list).
        # Post-fix: returns the actual most recent filed date (2024).
        assert revenue_records[0]["value"] == 300, (
            "Latest fact must be selected by filed date, not list position. "
            "This was Copilot finding on connector.py:518."
        )
        assert revenue_records[0]["filed"] == "2024-01-01"

    def test_skips_non_10k_10q_filings(self):
        facts_data = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {"USD": [{"form": "8-K", "filed": "2024-01-01", "val": 999}]}
                    }
                }
            }
        }
        records = connector.extract_latest_facts(facts_data, "0000320193")
        assert records == [] or all(r["form"] in ("10-K", "10-Q") for r in records)
