# Connector SDK Frequently Asked Questions

## Overview

### Why Connector SDK?
Fivetran Connector SDK allows you to code a custom data connector using Python and deploy it as an extension of Fivetran. Fivetran automatically manages running Connector SDK connections on your scheduled frequency and manages the required compute resources, eliminating the need for a third-party provider.

Connector SDK provides native support for many Fivetran features and relies on existing Fivetran technology. It also eliminates timeout and data size limitations typical of iPaaS and serverless platforms.

### What sources can I use the Connector SDK for?
You can use the Connector SDK to connect to any data source that you can access using Python. You can connect using the Python standard library, a generic HTTP client, database drivers, or any other Python accessible interface. The only requirements are that you can implement it in Python and establish network connectivity to the source


## Installation & Setup

### How do I install the Connector SDK?
You can install Fivetran Connector SDK using `pip`. It is highly recommended to use a separate Python virtual environment for each custom connector to avoid dependency conflicts.

```bash
pip install fivetran-connector-sdk
```
For more detailed installation instructions, refer to the [installation guide](https://fivetran.com/docs/connector-sdk/setup-guide).

### What are the system requirements for Connector SDK?
You need a supported Python runtime and a 64-bit version of Windows, or either `macOS` or `Linux` on `arm64` or `x86_64` architectures. Refer to the [Requirements section](https://github.com/fivetran/connector_sdk?tab=readme-ov-file#requirements) of the [README](https://github.com/fivetran/connector_sdk/blob/main/README.md) for exact version bounds and supported distributions.

### How are Python version upgrades and dependencies handled for my connector?
The responsibility for managing dependencies and version upgrades is shared between Fivetran and you, the customer.
  - Fivetran's Responsibility: We manage the underlying Python runtime environment. We follow [Python's official release calendar](https://devguide.python.org/versions/) to add support for new versions and deprecate older ones. If a runtime upgrade causes a dependency issue, we will notify customers and provide a transition period.

  - Your Responsibility: You are responsible for managing the specific libraries your connector uses, which are defined in your `requirements.txt` file. You must ensure your code and its dependencies are compatible with the supported Python versions.

### Where can I find the Connector SDK documentation?
The Connector SDK documentation is available at https://fivetran.com/docs/connector-sdk. This comprehensive documentation provides detailed guides on how to build, test, and deploy custom connectors using Fivetran Connector SDK.

### I'm new to the Connector SDK. Is there a tutorial or a guide to help me get started?
Absolutely. The best place to start is with our [Beginner Tutorial](https://fivetran.com/docs/connector-sdk/tutorials/beginners-tutorial) for the Connector SDK. This step-by-step guide is an excellent resource designed to walk you through the process of building your first connector.

We encourage you to try the tutorial, and if you have any questions or run into issues, feel free to reach out to our [support team](https://support.fivetran.com/hc/en-us). We also welcome any feedback you may have on the tutorial or the SDK to help us improve. If you have feedback, feature requests, or run into issues, please [open an Issue on our GitHub repository](https://github.com/fivetran/connector_sdk/issues/new/choose).


## Development

### How do I test my connector locally?
You can use the `fivetran debug` command to test your connector. This will create a local `warehouse.db` file (a DuckDB instance) that you can inspect to verify that your data is being processed correctly. Refer to the [Test Your Custom Connector Section of the setup guide](https://fivetran.com/docs/connector-sdk/setup-guide#testyourcustomconnector) for more details.

### How do I handle sensitive information like API keys?
Configuration values are often sensitive. They are securely stored within Fivetran's platform. During connector deploy, a temporary `configuration.json` file can be used to set any configuration needed by your connector. Configuration values can also be managed in the Fivetran dashboard. Do not hardcode credentials in your source code. Refer to the [configuration section](https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#workingwithconfigurationjsonfile) for more details.

### How do I manage state for incremental syncs?
The SDK uses a `state.json` file to save cursors, which allows your connector to resume syncing from where it left off. Do not store sensitive information in the state file as it is not encrypted. Refer to the [state management section](https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#workingwithstatejsonfile) for best practices.

### What connection methods does Fivetran support for connecting to a source?
Fivetran supports several methods for establishing a secure connection between your source and our service. The primary options are:
- Directly by safelisting Fivetran's IP
- Using an SSH tunnel
- Using a reverse SSH tunnel
- Using private networking (AWS PrivateLink, Azure Private Link, or Google Cloud Private Service Connect)

Refer to the [Connection Options documentation page](https://fivetran.com/docs/connector-sdk/connection-options#connectionoptions) for more information.

### Can I use the Connector SDK with an SSH tunnel to connect to a data source on a private network?
Yes, you can. If your data source is on a private network that is not directly accessible from the internet, you can use an SSH tunnel to establish a secure connection. This is a common pattern where you connect to an intermediate server that has both internet access and access to the private data source.
You can refer to the [SSH tunnel example](https://github.com/fivetran/connector_sdk/blob/main/examples/common_patterns/ssh_tunnels/key_based_authentication/README.md) for this scenario.

### Will Fivetran automatically create a column in the destination if an API returns all NULL values for it?
No, Fivetran will not create the column automatically. To sync a column that contains only empty or NULL values from your source, you must explicitly define that column in the schema. If the column is not defined in the schema, Fivetran will ignore it during the sync, and it will not be created in your destination.

### How can I use a feature that is currently in Private Preview?
Features in [Private Preview](https://fivetran.com/docs/core-concepts#releasephases) are not enabled by default. To get more information about a specific feature and to have it enabled for your connector, contact our Professional Services team for assistance.

Feel free to open a [Save Me Time Ticket](https://support.fivetran.com/hc/en-us/requests/new?isSdkIssue=true) to get access to Private Preview features and free help to write and deploy your first Connector SDK connector.

### I'm encountering errors with my custom connector. Where can I find help?
For assistance with specific errors and common issues, refer to our comprehensive [Troubleshooting Guide](https://fivetran.com/docs/connector-sdk/troubleshooting). This document provides solutions and guidance for a variety of problems you may encounter while developing and running your Connector SDK connectors.

### How can I learn best practices for more advanced or complex API patterns?
We've developed the [Fivetran SDK Playground](https://pypi.org/project/fivetran-api-playground/), a Python package designed to help you explore and understand how to handle complex API behaviors with the Connector SDK.

This allows you to get hands-on experience by interacting with these patterns and exploring our example code in your own development environment. It's a great way to build confidence and learn how to build robust, high-quality connectors.



## Deployment

### How do I deploy my connector to Fivetran?
Once you have tested your connector locally, you can deploy it using the `fivetran deploy` command. You will need your Fivetran API key, a destination name, and a unique connection name. Refer to the [Example Commands section](https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#examplecommands) for detailed instructions.

### How can I view the logs for my connector?
You can access general [Fivetran logs](https://fivetran.com/docs/logs) for your Connector SDK connections through the [Fivetran Platform Connector](https://fivetran.com/docs/logs/fivetran-platform), or by using [external log services](https://fivetran.com/docs/logs/external-logs). You can see [Connector SDK-specific logs](https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#connectorsdklogs) on the **Connector SDK logs** tab of the Connection Details page in the [Fivetran dashboard](https://fivetran.com/dashboard/).


## Maintenance
The `connector_sdk` repository is actively maintained by Fivetran Developers. If you have any feedback, feature requests, or run into issues, please [open an Issue on our GitHub repository](https://github.com/fivetran/connector_sdk/issues/new/choose).
