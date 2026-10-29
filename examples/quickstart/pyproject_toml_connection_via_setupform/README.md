# Pyproject.toml Connection Via Setup Form

## Connector overview

This example demonstrates how to make a Connector SDK package available for connection creation from the Fivetran dashboard by setting package metadata in `pyproject.toml` and defining a setup form in `configuration_form()`. It follows the same setup-form pattern used in the Connector SDK quickstart examples, but adds the required package metadata so the connector can be surfaced through the dashboard-based connection creation flow.

For the official guidance, see the Connector SDK documentation: https://fivetran.com/docs/connector-sdk/deploying-connectors/create-connection-via-setup-form

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- A Fivetran account with setup-form connection creation enabled
- A valid destination in your Fivetran account
- A custom connector package that defines `configuration_form()`

## Getting started

1. Review the connector package metadata in `pyproject.toml`.
2. Ensure the package name is unique and visible is set to `true`.
3. Run the package commands from the project directory:

```bash
fivetran package create --api-key <BASE_64_ENCODED_API_KEY>
```

4. In the Fivetran dashboard, open **Connections** and select the package in **Browse our connectors**.
5. Complete the setup form, run the setup test, and save the connection.

## How this example works

The connector exposes a setup form through `configuration_form()` and collects values such as:

- `api_base_url`
- `api_key`
- `my_host`
- `batch_size`
- `enable_metrics`
- `data_range`

The metadata in `pyproject.toml` tells Fivetran that the package is visible in the dashboard and pre-fills the setup form with the configured Python version and proxy host field.

```toml
[project]
name = "MyCustomConnector"
version = "0.1.0"
description = "A Fivetran connector example demonstrating how customer package_name and visible can be set in pyproject.toml."
dependencies = [
   "tenacity==9.1.4",
]

[tool.package-metadata]
visible = true
python_version = "3.14"
proxy_host_config_key = "my_host"
```

## Features

- Uses a setup form like the [quickstart configuration form example](../configuration_form/README.md)
- Provides a package `pyproject.toml` for dashboard visibility
- Lets users create a connection directly in the Fivetran UI
- Includes an example connection test for validating the API endpoint and credentials
- Demonstrates how to add a custom proxy host configuration key

## pyproject.toml metadata explanation

The important package metadata settings are:

- `name`: displayed in the dashboard when users search for a connector package
- `visible = true`: makes the package available for dashboard-based connection creation
- `python_version`: pre-fills the Python version in the setup form
- `proxy_host_config_key`: tells the setup form which field should pre-fill the proxy host value

## Data handling

This example is specific to the dashboard-based connection creation flow enabled by `pyproject.toml` package metadata. The key difference from the generic configuration form example is not the `post` API fetch itself, but that the package is made visible in the Fivetran dashboard via `[tool.package-metadata]` and then selected by a user when they create a connection.

Once the package is published with `visible = true`, Fivetran shows it in **Browse our connectors**. A user selects the package and fills in the setup form fields such as `api_base_url`, `api_key`, `my_host`, `batch_size`, `enable_metrics`, and `data_range`. Those values are then passed into `update()` as the `configuration` dictionary. The connector uses those setup form values to decide which records to fetch and how to sync them into the destination table.

This example remains intentionally simple and mirrors the setup form pattern from `examples/quickstart/configuration_form/connector.py`, but it highlights the additional step of making the package visible for connection creation in the dashboard.

## Error handling

The connector validates the required configuration values before sync and returns setup-test failures when the API URL or key is invalid. If the API request fails, the setup test surfaces a clean validation message instead of allowing a broken connection configuration to be saved.

## Additional considerations

This example is meant to help you understand how to combine Connector SDK setup forms with package visibility metadata. Use it as a starting point for production connectors that need custom connection creation through the Fivetran dashboard.
