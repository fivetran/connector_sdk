# Pyproject.toml Dependency Management Connector Example

## Connector overview
This connector demonstrates how to use a `pyproject.toml` file for dependency management instead of a `requirements.txt` file with the Fivetran Connector SDK.

It fetches the latest exchange rate from the [Frankfurter API](https://frankfurter.dev), a free, open-source API that requires no authentication, and uses the `tenacity` library (declared in `pyproject.toml`) for production-grade API retry logic with exponential backoff.


## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart_examples/pyproject_toml
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Demonstrates `pyproject.toml` as an alternative to `requirements.txt` for dependency management.
- Fetches the latest exchange rate from the Frankfurter API.
- Uses `tenacity` for declarative retry logic with exponential backoff (declared in `pyproject.toml`).
- Validates configuration to ensure required parameters are present.


## Configuration file
The connector requires the following configuration parameters:
```json
{
  "from_currency": "<YOUR_FROM_CURRENCY>",
  "to_currency": "<YOUR_TO_CURRENCY>"
}
```

Configuration paramaters:

- `from_currency` (required): The base currency code (e.g., `USD`, `EUR`, `GBP`) .
- `to_currency` (required): The target currency code (e.g., `INR`, `JPY`, `CAD`) .

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## pyproject.toml file
This connector uses a `pyproject.toml` file to declare dependencies instead of a `requirements.txt` file:
```toml
[project]
name = "pyproject-toml-example"
version = "0.1.0"
description = "A Fivetran connector example demonstrating pyproject.toml for dependency management"
requires-python = ">=3.10"
dependencies = [
    "tenacity==9.1.4",
]
```

### Key differences from requirements.txt
| Aspect | requirements.txt | pyproject.toml |
|---|---|---|
| Format | One package per line (e.g., `tenacity>=8.2`) | TOML format under `[project.dependencies]` |
| Metadata | Dependencies only | Project name, version, description, Python version, and dependencies |
| Standard | pip convention | Python packaging standard |
| Precedence | Used if no `pyproject.toml` present | Takes precedence over `requirements.txt` |

### Important notes
- If both `pyproject.toml` and `requirements.txt` are present in your project, `pyproject.toml` takes precedence.


## Authentication
Not applicable - the Frankfurter API is free and requires no authentication.


## Pagination
Not applicable - the connector fetches only the latest exchange rate in a single API call.


## Data handling
- The connector calls the Frankfurter `/v2/rates/latest` endpoint to get the most recent exchange rate.
- API calls use `tenacity`'s `@retry` decorator for automatic retry with exponential backoff on transient failures.
- If the API returns no records, the connector logs a warning and exits gracefully.
- The exchange rate record is upserted to the `exchange_rates` destination table using `op.upsert()`.


## Error handling
- If `from_currency` or `to_currency` is missing from configuration, `validate_configuration()` raises a `ValueError`.
- API request failures (timeouts, network errors, HTTP errors) are retried up to 3 times with exponential backoff (2s, 4s, up to 10s) using `tenacity`.
- After all retry attempts are exhausted, `tenacity` re-raises the last exception, which is caught, logged at `ERROR` level, and wrapped as a `RuntimeError`.
- If the API returns an empty response, the connector logs a warning and returns without upserting.
- Logs are written using `log.warning()`, `log.info()`, and `log.error()` to trace execution.


## Tables created
The connector creates the `EXCHANGE_RATES` table:

```json
{
  "table": "exchange_rates",
  "primary_key": ["date", "from_currency", "to_currency"],
  "columns": {
    "date": "NAIVE_DATE",
    "from_currency": "STRING",
    "to_currency": "STRING",
    "rate": {"type": "DECIMAL", "precision": 15, "scale": 6}
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
