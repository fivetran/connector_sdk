# Base64 Encoding and Decoding Connector Example

## Connector overview
This connector demonstrates how to encode and decode data using `Base64` within a Fivetran Connector SDK implementation. It performs both transformations during a sync and writes the results to the same `USER` table.

This example is useful for:
- Understanding how to handle data that may be Base64-encoded in transit.
- Simulating systems where Base64 is used for transport or obfuscation.
- Testing decoding pipelines and output structure.

The connector upserts two rows per sync:
- One with the original values Base64-encoded.
- One with the values decoded back to their original form.


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
fivetran init <project-path> --template examples/quickstart_examples/base_64_encoding_decoding
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates use of Python’s `base64` module for encoding and decoding.
- Upserts both transformed and original values.
- Uses `op.upsert()` to insert data into the `USER` table.
- Logs each step using SDK's logging module.
- Safely checkpoints sync progress.


## Configuration file
No configuration file is required for this example.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not require authentication - this is a local static example. In a production scenario, use headers or token-based authentication in your request logic within `users_sync.py`.


## Pagination
Not applicable - this connector emits two records per sync.


## Data handling
- The `schema()` function defines the structure of the user table.
- The `update()` function:
  - Encodes values into Base64.
  - Then decodes them back to original values.
  - Upserts both versions sequentially.
- Demonstrates correct encoding/decoding of `UTF-8` strings.


## Error handling
- This example is minimal and does not simulate decoding failures.
- Encoding is performed safely using `.encode("utf-8")` before `base64.b64encode()`.
- You can extend this example to handle invalid `Base64` input gracefully.


## Tables Created
The connector creates a `USER` table:

```json
{
  "table": "user",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING",
    "name": "STRING",
    "email": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.