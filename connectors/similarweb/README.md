# Similarweb Connector SDK Example

## Connector overview
This example demonstrates how to build a Fivetran Connector SDK integration for [Similarweb](https://www.similarweb.com/), a digital intelligence platform that provides data, insights, and analytics about websites and apps. The connector pulls web traffic data from Similarweb's API for a configurable set of domains and countries, and delivers it to your Fivetran destination.

## Requirements

* [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/similarweb
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

* Supports batch report generation and download from Similarweb's API (see `request_report`, `check_report_status`, `download_report`)
* Configurable list of domains, countries, and metrics (see `DOMAIN_LIST`, `COUNTRY_LIST`, `__METRIC_LIST`)
* Handles both historical and incremental syncs (see `update` function)
* Delivers data to a single table: `ALL_TRAFFIC_VISITS`
* Uses Fivetran Connector SDK logging for status and error reporting (see `log` usage)

## Configuration file

The connector expects a `configuration.json` file with the following structure:

```
{
  "api_key": "YOUR_SIMILARWEB_API_KEY"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The `requirements.txt` file specifies any additional Python libraries required by the connector. For this example, the following libraries are required:

Example content of `requirements.txt`:

```
pytz
dateutil
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses an API key for authentication with Similarweb. You can obtain your API key from your Similarweb account dashboard. The key should be provided in the `configuration.json` file as the value for the `api_key` key. (See `update` function in `test.py`)

## Pagination

This connector does not implement explicit pagination. Data is retrieved in batch via report generation and download, as provided by the Similarweb API. (See `request_report`, `check_report_status`, and `download_report` functions)

## Data handling

* Data is requested from Similarweb using the `request_report` function
* The status of the report is checked using `check_report_status` 
* Once ready, the report is downloaded and parsed using `download_report` 
* Data is delivered to Fivetran using the `op.upsert` operation in the `update` function 
* The schema is defined in the `schema` function

## Error handling

* Uses Fivetran Connector SDK logging for info, warning, and error messages (see `log` usage throughout)
* Raises `RuntimeError` for failed report creation, failed status, or download errors (see `request_report`, `check_report_status`, `download_report`)

## Tables created

* `all_traffic_visits` – Contains daily web traffic metrics for each domain and country combination.

Sample data structure:

| domain              | country | date       | visits   | ... |
|---------------------|---------|------------|----------|-----|
| example-website.com | US      | 2024-05-01 | 1000000  | ... |

## Additional files

This example does not include additional files beyond the main connector script and configuration.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 
