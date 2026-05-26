"""Configuration validation tests including seed_companies format check."""

import pytest

import connector


class TestSeedCompaniesFormat:
    """Copilot finding L253: seed_companies must validate format, not just presence."""

    def test_missing_rejected(self, base_config):
        del base_config["seed_companies"]
        with pytest.raises(ValueError, match="seed_companies"):
            connector.validate_configuration(base_config)

    def test_placeholder_rejected(self, base_config):
        base_config["seed_companies"] = "<COMMA_SEPARATED_CIKS>"
        with pytest.raises(ValueError, match="seed_companies"):
            connector.validate_configuration(base_config)

    def test_empty_after_parsing_rejected(self, base_config):
        base_config["seed_companies"] = ", , ,"
        with pytest.raises(ValueError, match="at least one CIK"):
            connector.validate_configuration(base_config)

    def test_non_numeric_entry_rejected(self, base_config):
        base_config["seed_companies"] = "320193,abc,789019"
        with pytest.raises(ValueError, match="numeric CIK"):
            connector.validate_configuration(base_config)

    def test_valid_csv(self, base_config):
        base_config["seed_companies"] = "320193, 789019, 1018724"
        connector.validate_configuration(base_config)  # must not raise

    def test_too_many_entries_rejected(self, base_config):
        # ceiling is 20
        base_config["seed_companies"] = ",".join(str(i) for i in range(100, 125))
        with pytest.raises(ValueError, match="ceiling"):
            connector.validate_configuration(base_config)


class TestNumericValidation:
    @pytest.mark.parametrize("field", ["max_enrichments", "max_discovery_companies"])
    def test_zero_rejected(self, field, base_config):
        base_config[field] = "0"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)


class TestSanityCeilings:
    def test_max_enrichments_ceiling(self, base_config):
        base_config["max_enrichments"] = "9999"
        with pytest.raises(ValueError, match="ceiling"):
            connector.validate_configuration(base_config)

    def test_max_discovery_ceiling(self, base_config):
        base_config["max_discovery_companies"] = "9999"
        with pytest.raises(ValueError, match="ceiling"):
            connector.validate_configuration(base_config)


class TestDatabricksCredentialChain:
    def test_enrichment_enabled_requires_creds(self, base_config):
        base_config["enable_enrichment"] = "true"
        base_config["databricks_token"] = "<DATABRICKS_PAT_TOKEN>"
        with pytest.raises(ValueError, match="databricks_token"):
            connector.validate_configuration(base_config)

    def test_workspace_url_must_be_https(self, base_config):
        base_config["enable_enrichment"] = "true"
        base_config["databricks_workspace_url"] = "example.cloud.databricks.com"
        with pytest.raises(ValueError, match="https://"):
            connector.validate_configuration(base_config)

    def test_data_only_mode_skips_chain(self, base_config):
        """All Databricks-dependent flags off → no creds required."""
        base_config["enable_enrichment"] = "false"
        base_config["enable_discovery"] = "false"
        base_config["enable_genie_space"] = "false"
        base_config["databricks_token"] = "<DATABRICKS_PAT_TOKEN>"
        connector.validate_configuration(base_config)  # must not raise
