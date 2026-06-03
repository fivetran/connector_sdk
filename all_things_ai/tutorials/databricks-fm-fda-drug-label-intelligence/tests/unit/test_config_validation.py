"""Configuration validation tests."""

import pytest

import connector


class TestNumericValidation:
    @pytest.mark.parametrize("field", ["max_labels", "batch_size", "max_enrichments"])
    def test_zero_rejected(self, field, base_config):
        base_config[field] = "0"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    @pytest.mark.parametrize("field", ["max_labels", "batch_size", "max_enrichments"])
    def test_non_integer_rejected(self, field, base_config):
        base_config[field] = "abc"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)


class TestSanityCeilings:
    def test_max_labels_ceiling_enforced(self, base_config):
        base_config["max_labels"] = "9999"
        with pytest.raises(ValueError, match="ceiling"):
            connector.validate_configuration(base_config)

    def test_max_enrichments_ceiling_enforced(self, base_config):
        base_config["max_enrichments"] = "9999"
        with pytest.raises(ValueError, match="ceiling"):
            connector.validate_configuration(base_config)


class TestEnrichmentDisabledSkipsCredentialChecks:
    """Data-only mode: enable_enrichment=false means no Databricks creds required."""

    def test_data_only_mode_passes_without_token(self, base_config):
        base_config["enable_enrichment"] = "false"
        base_config["enable_genie_space"] = "false"
        base_config["databricks_token"] = "<DATABRICKS_PAT_TOKEN>"
        base_config["databricks_workspace_url"] = "<DATABRICKS_WORKSPACE_URL>"
        connector.validate_configuration(base_config)  # must not raise


class TestEnrichmentEnabledRequiresCredentials:
    def test_missing_token_rejected(self, base_config):
        base_config["enable_enrichment"] = "true"
        base_config["databricks_token"] = "<DATABRICKS_PAT_TOKEN>"
        with pytest.raises(ValueError, match="databricks_token"):
            connector.validate_configuration(base_config)

    def test_missing_warehouse_id_rejected(self, base_config):
        base_config["enable_enrichment"] = "true"
        base_config["databricks_warehouse_id"] = "<DATABRICKS_SQL_WAREHOUSE_ID>"
        with pytest.raises(ValueError, match="databricks_warehouse_id"):
            connector.validate_configuration(base_config)


class TestWorkspaceUrlSchemeRequired:
    """Class-cousin of PR #561 hazard #4 (URL-interpolated hostname). Here the
    contract is INVERTED — `databricks_workspace_url` MUST start with
    `https://` because it's used as the URL prefix, not just the hostname."""

    def test_missing_https_prefix_rejected(self, base_config):
        base_config["enable_enrichment"] = "true"
        base_config["databricks_workspace_url"] = "example.cloud.databricks.com"
        with pytest.raises(ValueError, match="https://"):
            connector.validate_configuration(base_config)


class TestGenieSpaceValidation:
    def test_missing_table_identifier_rejected(self, base_config):
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "<CATALOG.SCHEMA.TABLE>"
        with pytest.raises(ValueError, match="genie_table_identifier"):
            connector.validate_configuration(base_config)
