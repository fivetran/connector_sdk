# Complex Configuration Options Connector Example

## Connector overview
This example demonstrates how to handle cases when a connector requires static complex values, such as deeply nested structures or non-string values. 

A separate Python file can be used to define such complex values. These values must not contain any sensitive information. The connector needs to be redeployed to update the values defined in the separate Python file.

This pattern is useful for:
- Working with custom connector configurations passed through `configuration.json`
- Working with complex configuration values that are difficult to represent as simple strings
- Maintaining constants that are defined in `connector.py`
- Dynamically handling typed settings like lists, integers, booleans, and JSON objects

## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns/complex_configuration_options
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Use configuration values defined in `configuration.json`
- Use static configuration values from `config.py`
- Define and use constants in `connector.py`
- Casts configuration values to appropriate types as needed
- Uses assert statements to confirm parsing behavior
- Emits a test `hello world` message to confirm successful processing

## Configuration file

The connector requires the following configuration parameters:
```json
{
  "api_key": "<YOUR_API_KEY>",
  "client_id": "<YOUR_CLIENT_ID>",
  "client_secret": "<YOUR_CLIENT_SECRET>"
}
```

The configuration parameters are as follows:
- `api_key` (required): Your API key for authentication.
- `client_id` (required): Your client ID for authentication.
- `client_secret` (required): Your client secret for authentication.

You should always use `configuration.json` to define sensitive information required by the connector. For security reasons, you should never hardcode them in connector code or define them as static values in `config.py` or other Python files.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

When you have complex structures that are not sensitive and are difficult to encode as strings in`configuration.json`, you can define them directly in a separate Python file (e.g., `config.py`) using native Python types. Note that, once deployed, you can't update these values in the dashboard.

```python
API_CONFIGURATIONS = {
    # You can define any static configuration values that your connector needs here
    # Never store secrets in this file. Use configuration.json for any sensitive values.
    "regions": ["us-east-1", "us-east-4", "us-central-1"],
    # You can also define more complex structures such as nested dictionaries and lists
    "currencies": [
        {
            "From": "USD",
            "To": "EUR"
        },
        {
            "From": "USD",
            "To": "GBP"
        }
    ]
}

```

Note: Ensure that you do not use `config.py` to store sensitive information. You should always store sensitive information in your connector's `configuration.json`.

## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector does not require authentication - it is a demonstration example showing how to parse complex configuration options. In a production scenario, use headers or token-based authentication as necessary, and store credentials in your `configuration.json`.

## Pagination
Not applicable - this connector emits a single static row.

## Data handling
- Configuration values are parsed and validated.
- The connector sends a single record in the `CRYPTO` table using `op.upsert()`.

## Error handling
- The connector raises a `ValueError` if any required configuration field is missing.
- Raises errors from invalid or incompatible configuration values.
- Logs informative messages via the SDK’s logging module.

## Tables created
The connector creates a single, `CRYPTO` table:

```json
{
  "table": "crypto",
  "primary_key": ["msg"],
  "columns": {
    "msg": "STRING"
  }
}
```

## Additional files
- `config.py` – This file contains static configuration values that are not sensitive and do not need to be changed from the Fivetran dashboard. This file can be used to define complex structures that are difficult to encode as strings in `configuration.json`.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
