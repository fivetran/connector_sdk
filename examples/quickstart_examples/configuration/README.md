# Decryption Using Configuration Key Connector Example

## Connector overview
This connector demonstrates how to use the `configuration.json` file to securely pass in a `Base64` encryption key, which is then used to decrypt an encrypted message using the cryptography Python package.

It illustrates:
- How to handle secret keys passed via configuration
- How to use `Fernet` encryption and decryption
- How to safely upsert decrypted content into a Fivetran destination table

This example is ideal for understanding how to handle secrets, encryption, and decryption within the Fivetran Connector SDK environment.


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
fivetran init <project-path> --template examples/quickstart_examples/configuration
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Decrypts a predefined encrypted message using a config-passed key.
- Uses `Fernet` from the cryptography library.
- Upserts the decrypted message to the `CRYPTO` table.
- Uses `schema()` validation to ensure the key is provided.
- Demonstrates safe use of secrets and encoded data.


## Configuration file
The connector requires the following configuration parameters:
```json
{
  "my_key": "EKlFpH8sZmdhhZ9lGhezgMTwAw3_Y2e7wbco7Gxt3SA="
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:
```
cryptography==44.0.2
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not authenticate to any external system, but it demonstrates how to securely use secrets for decryption within your connector logic.


## Pagination
Not applicable - the connector performs a single transformation on each sync.


## Data handling
- Decryption key is loaded from the config.
- An encrypted message is decrypted using `Fernet`.
- The decoded message is written as a string to the `CRYPTO` table.
- The connector uses `op.upsert()` and `op.checkpoint()` to maintain sync state.


## Error handling
- If the key is missing from configuration, `schema()` raises a `ValueError`.
- Decryption failures will result in a runtime exception (e.g. invalid token format).
- Logs are written using `log.warning()` and `log.debug()` to trace execution.


## Tables Created
The connector creates a `CRYPTO` table:

```json
{
  "table": "crypto",
  "primary_key": ["msg"],
  "columns": {
    "msg": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.