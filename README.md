<p align="center">
  <a href="https://www.fivetran.com/">
    <img src="https://cdn.prod.website-files.com/6130fa1501794ed4d11867ba/63d9599008ad50523f8ce26a_logo.svg" alt="Fivetran">
  </a>
</p>

<p align="center">
  Fivetran Connector SDK allows Real-time, efficient data replication to your destination of choice.
</p>

<p align="center">
  <a href="https://github.com/fivetran/fivetran_connector_sdk/stargazers" target="_blank"><img src="https://img.shields.io/github/stars/fivetran/fivetran_connector_sdk?style=social&label=Star"></a>
  <a href="https://github.com/fivetran/fivetran_connector_sdk/blob/main/LICENSE" target="_blank"><img src="https://img.shields.io/badge/License-MIT-blue" alt="License"></a>
  <a href="https://pypi.org/project/fivetran-connector-sdk/" target="_blank"><img src="https://img.shields.io/pypi/v/fivetran-connector-sdk" alt="PyPI Release"></a>
  <a href="https://pepy.tech/project/fivetran-connector-sdk" target="_blank"><img src="https://static.pepy.tech/badge/fivetran-connector-sdk" alt="PyPI Downloads"></a>
<a href="https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md" target="_blank"><img src="https://img.shields.io/badge/Managed-Yes-green/" alt="Managed"></a>
</p>

# Overview

Explore practical examples and helpful resources for building custom data connectors with the Fivetran [Connector SDK](https://fivetran.com/docs/connectors/connector-sdk). Learn how to develop and deploy [custom data connectors](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) in Python, and extend Fivetran’s capabilities to fit your data integration needs.

You’ll also find tips on [using AI to help you code a custom connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/README.md) quickly.

## Why Connector SDK?

Fivetran Connector SDK allows you to code a custom data connector using Python and deploy it as an extension of Fivetran. Fivetran automatically manages running Connector SDK connections on your scheduled frequency and manages the required compute resources, eliminating the need for a third-party provider.

Connector SDK provides native support for many Fivetran features and relies on existing Fivetran technology. It also eliminates timeout and data size limitations seen in AWS Lambda.

## Requirements

- Python version ≥3.10 and ≤3.13
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

See [Setup guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

Run the `.github/scripts/setup-hooks.sh` script from the root of the repository to set up pre-commit hooks. This ensures that your code is formatted correctly and passes all tests before you commit them.

## Examples

Explore working code examples for common Connector SDK use cases. These [examples](examples/README.md) help you understand core implementation patterns and quickly adapt them to your own connector.

## Community connectors

Explore ready-to-use full connectors to get started. These connectors are useful when you want a stronger starting point or want to adapt an existing implementation for your source. For the full list, see the [Community Connectors Catalog](https://github.com/fivetran/fivetran_csdk_connectors/blob/main/README.md).


## AI and Connector SDK
- [Readme](https://github.com/fivetran/fivetran_connector_sdk/blob/main/all_things_ai/tutorials/README.md) - This is an introduction to using AI tools to leverage Connector SDK.
- [agents.md](https://github.com/fivetran/fivetran_connector_sdk/blob/main/all_things_ai/ai_agents/AGENTS.md) - This is a system instruction file that can be used in any IDE, API call or conversation with AI to rapidly develop Connector SDK solutions while following best practice.
- [claude_pokeapi tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/claude/pokeapi_tutorial) - This example contains the code produced by Claude AI to build a custom connector using our Connector SDK. See our [blog article](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai) for more details.
- [claude_fda_drug tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/claude/fda_drug_tutorial) - This example demonstrates how to use Claude to create a CSDK connector to get data from the FDA drug API.
- [cursor_fda_food tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/cursor/fda_food_tutorial/fda_food_connector) - This example demonstrates how to use Cursor to create a CSDK connector to get data from the FDA food API.
- [vscode_fda_tobacco tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/vscode/fda_tobacco_tutorial/fda_tobacco_connector) - This example demonstrates how to use VSCode to create a CSDK connector to get data from the FDA tobacco API.
- [snowflake-cortex-livestock-weather-intelligence](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/snowflake-cortex-livestock-weather-intelligence) - This example demonstrates real-time AI enrichment via Snowflake Cortex Agent REST API during Fivetran data ingestion. It syncs weather forecasts and enriches them with livestock health risk assessments using Snowflake's llama3.3-70b model with Cortex Analyst. It shows how to integrate Snowflake Intelligence into Fivetran pipelines for any industry vertical.
- [databricks-fm-fhir-healthcare-intelligence](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/databricks-fm-fhir-healthcare-intelligence) - This example syncs clinical data from a FHIR R4 server and enriches it with AI-powered hybrid analysis using Databricks `ai_query()`. It implements the Hybrid pattern (Discovery + Debate) to provide population health risk stratification and per-patient intervention recommendations using Databricks Foundation Models.

## Issue

Found an issue? Submit the [issue](https://github.com/fivetran/fivetran_connector_sdk/issues) and get connected to a Fivetran developer.

## Fivetran platform features

- [schema_change](https://github.com/fivetran/fivetran_connector_sdk/blob/main/examples/common_patterns_for_connectors/schema_change/README.md) - This is an example that illustrates how a deployed Connector SDK connection uses Fivetran's native [data type changes](https://fivetran.com/docs/core-concepts#changingdatatype) to change data types in the destination if they are changed in the source data.


## Support

Learn how we [support Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk#support).


## Additional considerations

We provide examples to help you effectively use Fivetran's Connector SDK. While we've tested the code provided in these examples, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples.

Note that API calls made by your Connector SDK connection may count towards your service’s API call allocation. Exceeding this limit could trigger rate limits, potentially impacting other uses of the source API.

It's important to choose the right design pattern for your target API. Using an inappropriate pattern may lead to data integrity issues. We recommend that you review all our examples carefully to select the one that best suits your target API. Keep in mind that some APIs may not support patterns for which we currently have examples.

As with other new connectors, SDK connectors have a [14-day trial period](https://fivetran.com/docs/getting-started/free-trials#newconnectorfreeuseperiod) during which your usage counts towards free [MAR](https://fivetran.com/docs/usage-based-pricing). After the 14-day trial period, your usage counts towards paid MAR. To avoid incurring charges, pause or delete any connections you created to run these examples before the trial ends.

## Maintenance

The `fivetran_connector_sdk` repository is actively maintained by Fivetran Developers. Reach out to our [Support team](https://support.fivetran.com/hc/en-us) for any inquiries.