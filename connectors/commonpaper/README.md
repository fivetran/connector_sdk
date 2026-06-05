# Common Paper Connector

## Connector overview

This connector fetches and syncs agreement data from the Common Paper API. It provides a simple implementation that:
- Fetches agreements using the Common Paper REST API
- Handles incremental syncs using updated_at timestamps
- Converts nested data structures to JSON strings for storage
- Maintains sync state using checkpoints

## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/commonpaper
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

* Fetches agreement data from Common Paper API
* Supports incremental syncs using updated_at timestamps
* Handles list values by converting them to JSON strings
* Maintains sync state for resumable operations
* Simple authentication using API key

## Configuration file

The connector requires the following configuration parameters in `configuration.json`:

```json
{
    "api_key": "<YOUR_COMMONPAPER_API_KEY>",
    "initial_sync_timestamp": "2023-01-01T00:00:00Z"
}
```

Configuration parameters:
- `api_key`: Your Common Paper API key
- `initial_sync_timestamp`: ISO format timestamp for the initial sync (optional, defaults to current time)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector does not use any additional Python packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses API key authentication to access the Common Paper API. The API key should be added to the configuration file for debugging and deploying.

## Data handling

The connector processes data in the following way:
1. Fetches agreements from the Common Paper API using the updated_at filter
2. Processes each agreement record:
   - Extracts attributes from the record
   - Converts any list fields to JSON strings for storage
   - Upserts the data to the destination table
3. Maintains sync state using checkpoints to enable resumable operations

## Error handling

The connector implements basic error handling:
- Validates API responses and raises exceptions for non-200 status codes
- Logs errors using the Fivetran logging system
- Uses checkpoints to ensure sync progress is saved

## Tables Created

The connector creates a single table:

### agreements
Primary key: `id`

This table contains all agreement data from Common Paper, with nested structures stored as JSON strings.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team. 