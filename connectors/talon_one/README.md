# Talon.one Connector Example

## Connector overview

This connector fetches event data from Talon.one using the Management API. The connector retrieves application events with pagination support and incremental sync capabilities.

The connector maintains one table, `event`. This table contains application event data from Talon.one.


## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating System:  
- Windows 10 or later  
- macOS 13 (Ventura) or later
- Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/talon_one
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Fetches application events from Talon.one Management API
- Supports incremental sync based on event creation time
- Implements pagination with configurable page size
- Rate limiting compliance (3 calls per second)
- Automatic JSON conversion for list-type fields
- Checkpointing for reliable data synchronization

## Configuration file

The connector requires configuration with your Talon.one credentials and sync settings:

```json
{
    "base_url": "<YOUR_TALON.ONE_DOMAIN_URL>", 
    "api_key": "<YOUR_API_KEY>",
    "application_id": "<YOUR_TALON.ONE_APPLICATION_ID>"
}
```

> NOTE: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector uses minimal external dependencies. The `requirements.txt` file should be empty because all required packages are pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses Talon.one Management API authentication:
- API Key authentication using `ManagementKey-v1` format
- Requires a valid Talon.one Management API key
- API key must be included in the Authorization header

## Data handling

The connector processes data in the following way:
1. Connects to Talon.one Management API using provided credentials
2. Fetches application events for the configured application ID (currently set to 5)
3. Implements pagination to handle large datasets
4. Converts list-type fields to JSON strings for database compatibility
5. Uses incremental sync based on `createdAfter` parameter

The connector uses incremental sync based on the `created` field to avoid duplicate data and ensure efficient synchronization.

## Error handling

The connector implements error handling for:
- HTTP request failures with `raise_for_status()`
- API rate limiting with sleep delays
- Empty response handling
- Pagination boundary conditions

All errors are logged using the Fivetran logging system for debugging and monitoring.

## Tables Created

The connector creates one table:

### event
Primary key: `id`

Contains application event data including:
- Event ID
- Event type and attributes
- Creation timestamp
- Application-specific event data
- Customer and session information

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.