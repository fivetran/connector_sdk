"""Unit tests for validate_configuration().

These tests lock in the contract between the README and
validate_configuration() so drift is caught before a reviewer ever sees it.

New reviewer feedback on a config edge case should be encoded as a test
here before (or alongside) the fix so the contract is regression-protected.
"""

import pytest

import connector


class TestNumericValidation:
    def test_valid_config_passes(self, base_config):
        connector.validate_configuration(base_config)  # should not raise

    def test_max_events_negative_rejected(self, base_config):
        base_config["max_events"] = "-1"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_max_events_non_numeric_rejected(self, base_config):
        base_config["max_events"] = "not-a-number"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_max_events_ceiling_enforced(self, base_config):
        base_config["max_events"] = str(getattr(connector, "__MAX_EVENTS_CEILING") + 1)
        with pytest.raises(ValueError, match="exceeds ceiling"):
            connector.validate_configuration(base_config)

    def test_max_enrichments_ceiling_enforced(self, base_config):
        base_config["max_enrichments"] = str(getattr(connector, "__MAX_ENRICHMENTS_CEILING") + 1)
        with pytest.raises(ValueError, match="exceeds"):
            connector.validate_configuration(base_config)


class TestDatabricksCredentialsRequired:
    def test_missing_workspace_url_rejected(self, base_config):
        base_config["databricks_workspace_url"] = "<WORKSPACE_URL>"
        with pytest.raises(ValueError, match="databricks_workspace_url"):
            connector.validate_configuration(base_config)

    def test_missing_token_rejected(self, base_config):
        base_config["databricks_token"] = "<TOKEN>"
        with pytest.raises(ValueError, match="databricks_token"):
            connector.validate_configuration(base_config)

    def test_missing_warehouse_id_rejected(self, base_config):
        base_config["databricks_warehouse_id"] = "<WAREHOUSE>"
        with pytest.raises(ValueError, match="databricks_warehouse_id"):
            connector.validate_configuration(base_config)

    def test_non_https_workspace_url_rejected(self, base_config):
        base_config["databricks_workspace_url"] = "http://insecure.example.com"
        with pytest.raises(ValueError, match="https"):
            connector.validate_configuration(base_config)


class TestGenieSpaceValidation:
    def test_genie_enabled_requires_table_identifier(self, base_config):
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "<TABLE_IDENTIFIER>"
        with pytest.raises(ValueError, match="genie_table_identifier"):
            connector.validate_configuration(base_config)

    def test_genie_enabled_with_real_identifier_passes(self, base_config):
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "catalog.schema.weather_events"
        connector.validate_configuration(base_config)


class TestDataOnlyMode:
    """When enable_enrichment=false, Databricks credentials should not be
    required even if enable_discovery=true (or defaulted). Discovery is a
    phase *inside* enrichment, so disabling enrichment makes discovery
    unreachable regardless of its own flag (fix #570-6)."""

    def test_all_phases_disabled_no_creds_needed(self, base_config):
        """Trivial case: all flags explicitly off — this already works."""
        base_config["enable_enrichment"] = "false"
        base_config["enable_discovery"] = "false"
        base_config["enable_genie_space"] = "false"
        base_config["databricks_workspace_url"] = "<WORKSPACE_URL>"
        base_config["databricks_token"] = "<TOKEN>"
        base_config["databricks_warehouse_id"] = "<WAREHOUSE>"
        connector.validate_configuration(base_config)

    def test_enrichment_off_with_discovery_on_no_creds_needed(self, base_config):
        """Discovery runs only when enable_enrichment=true; flipping
        enable_enrichment to false should release the credential gate
        regardless of enable_discovery's value (fix #570-6)."""
        base_config["enable_enrichment"] = "false"
        base_config["enable_discovery"] = "true"  # irrelevant when enrichment off
        base_config["enable_genie_space"] = "false"
        base_config["databricks_workspace_url"] = "<WORKSPACE_URL>"
        base_config["databricks_token"] = "<TOKEN>"
        base_config["databricks_warehouse_id"] = "<WAREHOUSE>"
        connector.validate_configuration(base_config)  # should NOT raise

    def test_enrichment_off_with_discovery_defaulted_no_creds_needed(self, base_config):
        """The same flow with enable_discovery left unset (defaults to true)
        — most common form of the bug because new users typically only
        toggle enable_enrichment."""
        base_config["enable_enrichment"] = "false"
        base_config.pop("enable_discovery", None)  # use default (true)
        base_config["enable_genie_space"] = "false"
        base_config["databricks_workspace_url"] = "<WORKSPACE_URL>"
        base_config["databricks_token"] = "<TOKEN>"
        base_config["databricks_warehouse_id"] = "<WAREHOUSE>"
        connector.validate_configuration(base_config)  # should NOT raise

    def test_genie_on_still_requires_creds(self, base_config):
        """enable_genie_space=true must still require Databricks creds even
        if enrichment is off — Genie Space creation hits the Databricks API
        directly and is independent of the enrichment phase."""
        base_config["enable_enrichment"] = "false"
        base_config["enable_genie_space"] = "true"
        base_config["genie_table_identifier"] = "catalog.schema.weather_events"
        base_config["databricks_token"] = "<TOKEN>"
        with pytest.raises(ValueError, match="databricks_token"):
            connector.validate_configuration(base_config)


class TestDiscoveryRegionsCeiling:
    """max_discovery_regions has a ceiling constant; validate_configuration
    enforces it as a positive int and against the ceiling (fix #570-4)."""

    def test_max_discovery_regions_ceiling_enforced(self, base_config):
        base_config["max_discovery_regions"] = str(
            getattr(connector, "__MAX_DISCOVERY_REGIONS_CEILING") + 1
        )
        with pytest.raises(ValueError, match="exceeds"):
            connector.validate_configuration(base_config)

    def test_max_discovery_regions_negative_rejected(self, base_config):
        base_config["max_discovery_regions"] = "-1"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_max_discovery_regions_non_numeric_rejected(self, base_config):
        base_config["max_discovery_regions"] = "lots"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)


class TestDatabricksTimeoutValidation:
    """databricks_timeout must be a positive integer (fix #570-5)."""

    def test_databricks_timeout_negative_rejected(self, base_config):
        base_config["databricks_timeout"] = "-30"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_databricks_timeout_zero_rejected(self, base_config):
        base_config["databricks_timeout"] = "0"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_databricks_timeout_non_numeric_rejected(self, base_config):
        base_config["databricks_timeout"] = "soon"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_databricks_timeout_valid_value_accepted(self, base_config):
        base_config["databricks_timeout"] = "60"
        connector.validate_configuration(base_config)  # should not raise
