"""Configuration validation tests.

Covers:
- Numeric validation for max_stories / batch_size / cortex_timeout / max_enrichments
- Cortex-enabled chain (account + token + suffix check)
- Snowflake account hostname **scheme rejection** (Hazard #4 — direct repeat
  of PR #561 NHTSA Finding A; api-profiling.md cites #561 as the motivating
  example for this hazard, but the rule was never applied to #555 either)
"""

import pytest

import connector


class TestNumericValidation:
    @pytest.mark.parametrize(
        "field", ["max_stories", "batch_size", "cortex_timeout", "max_enrichments"]
    )
    def test_zero_rejected(self, field, base_config):
        base_config[field] = "0"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    @pytest.mark.parametrize(
        "field", ["max_stories", "batch_size", "cortex_timeout", "max_enrichments"]
    )
    def test_negative_rejected(self, field, base_config):
        base_config[field] = "-1"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    @pytest.mark.parametrize(
        "field", ["max_stories", "batch_size", "cortex_timeout", "max_enrichments"]
    )
    def test_non_integer_rejected(self, field, base_config):
        base_config[field] = "abc"
        with pytest.raises(ValueError, match="positive integer"):
            connector.validate_configuration(base_config)

    def test_optional_when_missing(self, base_config):
        del base_config["max_stories"]
        connector.validate_configuration(base_config)  # must not raise


class TestCortexEnabledChain:
    def test_enabled_without_account_rejected(self, base_config):
        del base_config["snowflake_account"]
        with pytest.raises(ValueError, match="snowflake_account"):
            connector.validate_configuration(base_config)

    def test_enabled_without_token_rejected(self, base_config):
        del base_config["snowflake_pat_token"]
        with pytest.raises(ValueError, match="snowflake_pat_token"):
            connector.validate_configuration(base_config)

    def test_enabled_with_wrong_suffix_rejected(self, base_config):
        base_config["snowflake_account"] = "abc.example.com"
        with pytest.raises(ValueError, match="snowflakecomputing.com"):
            connector.validate_configuration(base_config)

    def test_disabled_skips_chain_validation(self, base_config):
        base_config["enable_cortex"] = "false"
        del base_config["snowflake_account"]
        del base_config["snowflake_pat_token"]
        connector.validate_configuration(base_config)  # must not raise


class TestSnowflakeAccountSchemeRejection:
    """Hazard #4 (api-profiling.md): URL-interpolated hostname configs MUST
    reject scheme prefixes. The connector builds:

        url = f"https://{account}{__CORTEX_INFERENCE_ENDPOINT}"

    If the user supplies `https://abc.snowflakecomputing.com`, the URL becomes
    `https://https://abc.snowflakecomputing.com/...` and fails at runtime with
    confusing 4xx errors.

    api-profiling.md cites PR #561 as the motivating example. PR #555 has
    the SAME bug — the rebuilt-skill rule has never been applied here either.
    Direct class-cousin of #561 Finding A. These tests fail RED until the
    validator gains an explicit scheme-prefix check.
    """

    def test_https_prefix_rejected(self, base_config):
        base_config["snowflake_account"] = "https://abc.snowflakecomputing.com"
        with pytest.raises(ValueError, match="hostname"):
            connector.validate_configuration(base_config)

    def test_http_prefix_rejected(self, base_config):
        base_config["snowflake_account"] = "http://abc.snowflakecomputing.com"
        with pytest.raises(ValueError, match="hostname"):
            connector.validate_configuration(base_config)
