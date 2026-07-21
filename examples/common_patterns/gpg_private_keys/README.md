# GPG-Signed Message Connector Example

## Connector overview
This example demonstrates how to use [GnuPG](https://www.gnupg.org/) via the `python-gnupg` library to sign data using a private GPG key. The connector takes a static message, signs it using a GPG private key provided in the configuration, verifies the signature, and upserts the signed message into a destination table named `SIGNED_MESSAGE`.

This example is ideal for learning how to:
- Import and manage PGP/GPG private keys within a connector.
- Sign and verify data using `gnupg`.
- Integrate cryptographic signing logic with the Fivetran Connector SDK.

This connector is built for educational purposes and uses hardcoded test data. It is not production-ready without further security hardening.


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
fivetran init <project-path> --template examples/common_patterns/gpg_private_keys
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## GPG key pair setup
To use this example, you must generate a GPG key pair and copy the private key (ASCII-armored) into your `configuration.json`.

Resources to help:
- [GnuPG Manual](https://www.gnupg.org/gph/en/manual/c14.html)
- [GitHub GPG Guide](https://docs.github.com/en/authentication/managing-commit-signature-verification/generating-a-new-gpg-key)
- [Red Hat: Creating GPG Keypairs](https://www.redhat.com/en/blog/creating-gpg-keypairs)


## Features
- Signs a message using a GPG private key
- Verifies the signature validity before syncing
- Uses `python-gnupg` for GPG operations
- Demonstrates use of `op.upsert()` to deliver signed data to a destination table


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "private_key": "<YOUR_ESCAPED_GPG_PRIVATE_KEY>",
  "passphrase": "<YOUR_PASSPHRASE>"
}
```

`private_key`: Your GPG private key, formatted as a single-line escaped JSON string (ASCII-armored).
To export your private key in this format, you can use:
```bash
gpg --armor --export-secret-keys <YOUR_KEY_ID>
```
Then properly escape newline characters (e.g., \n) for JSON compatibility.

`passphrase`: The GPG passphrase used to unlock your private key for signing.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
requests
python-gnupg
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not use API-based authentication, but relies on cryptographic signing via a user-provided GPG  private key and passphrase.
- The private key is imported dynamically at runtime using `gpg.import_keys()`.
- Signing is performed using `gpg.sign()`.
- Signature verification is done with `gpg.verify()`.

If either the key import or the signature validation fails, the connector raises an error and aborts the sync.


## Pagination
This connector does not interact with paginated data sources. It signs a static test message.


## Data handling
- Validates configuration to ensure `private_key` and `passphrase` are present.
- Imports the private key into a `gnupg.GPG()` object.
- Signs a fixed plaintext message.
- Verifies the signature is valid.
- Upserts the signed message into the `signed_message` table.
- Saves sync state using `op.checkpoint()`.


## Error handling
- If `private_key` or `passphrase` is missing, a `ValueError` is raised.
- If the GPG key import fails, a `RuntimeError` is raised.
- If the signature cannot be verified, the sync is aborted with an exception.
- All actions are logged using the SDK’s `Logging` module.


## Tables created
The connector creates the `SIGNED_MESSAGE` table:

```
{
  "table": "signed_message",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING",
    "message": "STRING"
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.