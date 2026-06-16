# Configuration form example

## Connector overview

This example demonstrates how to define a connector setup form using `ConfigurationForm`, `form_field`, and `Test` from the Fivetran Connector SDK. It covers plain text, password, dropdown, and toggle fields, including dropdown options with labels and descriptions. It also shows how to register a connection test that Fivetran runs when the user clicks **Test Connection** during setup.

The API fields (`api_base_url`, `api_key`) in the configuration form illustrate how a real connector would collect connection details. The `configuration.json` file provided contains sample values for running the connector locally.

Refer to `def configuration_form()` and `def connection_test()` in `connector.py` for the main setup form and test implementation.

## Example UI

### Configuration form

![Configuration form UI](./images/configuration_form.png)

### Setup tests

![Setup tests UI](./images/setup_tests.png)

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

For available CLI commands, refer to the [Connector SDK Commands](https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/connector-sdk-commands) reference.

1. Run the `fivetran configuration` command to interactively provide values for each form field. This generates (or overrides) a `configuration.json` file in the project directory.

   ```bash
   fivetran configuration
   ```

2. Optionally, run setup tests to validate your inputs without running a full sync.

   ```bash
   fivetran configuration --test
   ```

3. Run the connector locally using the generated `configuration.json`.

   ```bash
   fivetran debug --configuration configuration.json
   ```

## Features

- Demonstrates form field types: `TextField` (plain text and password variants), `DropdownField`, and `ToggleField`
- Registers a connection test function that Fivetran calls by its `__name__` during connector setup
- Shows how to read and use configuration form values inside `update()`
- Uses the `data_range` dropdown with option labels and descriptions to control how much sample data the sync reads
- Optionally logs extraction volume when the metrics toggle is enabled
- Supports the `fivetran configuration` command, which interactively prompts for each form field value and generates (or overrides) `configuration.json` — the resulting file can then be used with `fivetran debug --configuration configuration.json` to run the connector locally or with `fivetran deploy` to deploy it. Setup tests registered via `add_test()` can be run independently using `fivetran configuration --test`, which is useful for validating credentials, field values, or connection health without running a full sync

## Requirements file

This connector has no third-party dependencies and does not include a `requirements.txt` file.

> Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Data handling

The example uses the JSONPlaceholder API to illustrate the sync pattern. Configuration values from the form are read in `update()` to control sync behavior. `data_range` limits how many records are fetched for the demo (`last_7_days`, `last_30_days`, or `all_time`), `batch_size` shows how a page limit would be applied, and `enable_metrics` controls whether extraction stats are logged.

Refer to `def update()` for details.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
