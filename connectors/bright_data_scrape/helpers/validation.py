"""Configuration validation utilities."""


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.

    This function is called at the start of the update method to ensure that the connector
    has all necessary configuration values.

    Args:
        configuration: A dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: If any required configuration parameter is missing.
    """
    required_configs = ["api_token", "dataset_id", "scrape_url"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")
