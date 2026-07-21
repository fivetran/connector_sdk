"""
You can define static configuration values in a separate Python file and import them into your connector.
This is useful for keeping your connector code clean and organized.

Important: Values defined this way cannot be viewed or modified from the Fivetran dashboard.
To change them, you must update the file and redeploy the connector.
If you need to edit the values from the Fivetran dashboard, define them in configuration.json instead.

Do not store secrets here. Always use configuration.json for sensitive values such as API keys or credentials.
"""

API_CONFIGURATIONS = {
    # You can define any static configuration values that your connector needs here
    # Never store secrets in this file. Use configuration.json for any sensitive values.
    "regions": ["us-east-1", "us-east-4", "us-central-1"],
    # You can also define more complex structures such as nested dictionaries and lists
    "currencies": [{"From": "USD", "To": "EUR"}, {"From": "USD", "To": "GBP"}],
}
