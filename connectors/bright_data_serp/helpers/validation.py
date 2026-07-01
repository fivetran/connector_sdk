"""Configuration validation utilities."""


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.

    Args:
        configuration: A dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: If any required configuration parameter is missing.
    """
    required_configs = ["api_token", "search_query"]
    for key in required_configs:
        if key not in configuration or not configuration.get(key):
            raise ValueError(f"Missing required configuration value: {key}")
