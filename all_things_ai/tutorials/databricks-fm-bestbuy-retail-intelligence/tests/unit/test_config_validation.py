"""Unit tests for validate_configuration().

Encodes the README contract for every configurable field plus the sanity
ceilings on max_products and max_enrichments.

# see snowflake-cortex-code-clinical-trial-intelligence/tests/unit/test_config_validation.py
# for the analogous Cortex-side validation tests.
"""

import pytest

import connector


class TestRequiredApiKey:
    """Best Buy API key is the only always-required config field."""

    def test_valid_config_passes(self, base_config):
        connector.validate_configuration(base_config)

    def test_missing_api_key_rejected(self, base_config):
        base_config["api_key"] = "<BESTBUY_API_KEY>"
        with pytest.raises(ValueError, match="api_key"):
            connector.validate_configuration(base_config)


class TestDatabricksCredentialsRequiredWhenEnabled:
    def test_missing_workspace_url_rejected(self, base_config):
        base_config["databricks_workspace_url"] = "<DATABRICKS_WORKSPACE_URL>"
        with pytest.raises(ValueError, match="databricks_workspace_url"):
            connector.validate_configuration(base_config)

    def test_missing_token_rejected(self, base_config):
        base_config["databricks_token"] = "<DATABRICKS_PAT_TOKEN>"
        with pytest.raises(ValueError, match="databricks_token"):
            connector.validate_configuration(base_config)

    def test_missing_warehouse_id_rejected(self, base_config):
        base_config["databricks_warehouse_id"] = "<DATABRICKS_WAREHOUSE_ID>"
        with pytest.raises(ValueError, match="databricks_warehouse_id"):
            connector.validate_configuration(base_config)

    def test_enrichment_disabled_does_not_require_creds(self, base_config):
        """When enrichment AND genie are disabled, Databricks creds are optional."""
        base_config["enable_enrichment"] = "false"
        base_config["enable_genie_space"] = "false"
        base_config["databricks_workspace_url"] = "<DATABRICKS_WORKSPACE_URL>"
        base_config["databricks_token"] = "<DATABRICKS_PAT_TOKEN>"
        base_config["databricks_warehouse_id"] = "<DATABRICKS_WAREHOUSE_ID>"
        connector.validate_configuration(base_config)

    def test_genie_enabled_requires_creds_even_when_enrichment_off(self, base_config):
        base_config["enable_enrichment"] = "false"
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "catalog.schema.table"
        base_config["databricks_workspace_url"] = "<DATABRICKS_WORKSPACE_URL>"
        with pytest.raises(ValueError, match="databricks_workspace_url"):
            connector.validate_configuration(base_config)


class TestDatabricksWorkspaceUrlFormat:
    """workspace_url must be a full https:// URL, not a hostname or http://."""

    def test_https_required(self, base_config):
        base_config["databricks_workspace_url"] = "abc.cloud.databricks.com"
        with pytest.raises(ValueError, match="https://"):
            connector.validate_configuration(base_config)

    def test_http_rejected(self, base_config):
        base_config["databricks_workspace_url"] = "http://abc.cloud.databricks.com"
        with pytest.raises(ValueError, match="https://"):
            connector.validate_configuration(base_config)


class TestNumericValidation:
    """Every field consumed via int() must be in the validation loop."""

    def test_max_products_negative_rejected(self, base_config):
        base_config["max_products"] = "-1"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_max_products_zero_rejected(self, base_config):
        base_config["max_products"] = "0"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_max_enrichments_zero_rejected(self, base_config):
        base_config["max_enrichments"] = "0"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_max_products_non_numeric_rejected(self, base_config):
        base_config["max_products"] = "many"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_placeholder_values_pass(self, base_config):
        base_config["max_products"] = "<MAX_PRODUCTS_PER_SYNC>"
        base_config["max_enrichments"] = "<MAX_ENRICHMENTS_PER_SYNC>"
        connector.validate_configuration(base_config)


class TestSanityCeilings:
    """max_products and max_enrichments enforce sanity ceilings."""

    def test_max_products_above_ceiling_rejected(self, base_config):
        ceiling = getattr(connector, "_connector__MAX_PRODUCTS_CEILING", None) or getattr(
            connector, "__MAX_PRODUCTS_CEILING", 500
        )
        base_config["max_products"] = str(ceiling + 1)
        with pytest.raises(ValueError, match="exceeds"):
            connector.validate_configuration(base_config)

    def test_max_products_at_ceiling_accepted(self, base_config):
        ceiling = getattr(connector, "_connector__MAX_PRODUCTS_CEILING", None) or getattr(
            connector, "__MAX_PRODUCTS_CEILING", 500
        )
        base_config["max_products"] = str(ceiling)
        connector.validate_configuration(base_config)

    def test_max_enrichments_above_ceiling_rejected(self, base_config):
        ceiling = getattr(connector, "_connector__MAX_ENRICHMENTS_CEILING", None) or getattr(
            connector, "__MAX_ENRICHMENTS_CEILING", 100
        )
        base_config["max_enrichments"] = str(ceiling + 1)
        with pytest.raises(ValueError, match="exceeds"):
            connector.validate_configuration(base_config)


class TestGenieTableRequired:
    """When enable_genie_space=true, genie_table_identifier must be set."""

    def test_genie_enabled_without_table_rejected(self, base_config):
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "<CATALOG.SCHEMA.TABLE>"
        with pytest.raises(ValueError, match="genie_table_identifier"):
            connector.validate_configuration(base_config)

    def test_genie_enabled_with_table_passes(self, base_config):
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "catalog.schema.products_enriched"
        connector.validate_configuration(base_config)
