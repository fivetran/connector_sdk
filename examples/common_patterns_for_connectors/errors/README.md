# Error Handling Patterns Connector Example

## Connector overview
This connector demonstrates common error handling patterns and best practices when developing Fivetran connectors. It simulates various error scenarios that might occur during connector execution, such as missing configuration, invalid state format, data generation errors, processing errors, and database operation errors. This example is designed to help developers understand how to implement robust error handling in their connectors.


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/errors
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Demonstrates five different error handling scenarios
- Shows proper error logging techniques
- Implements best practices for configuration validation
- Provides examples for state management error handling
- Shows how to handle errors during data operations


## Configuration file
The connector uses the following configuration parameter:

```json
{
  "error_simulation_type": "<YOUR_ERROR_SIMULATION_TYPE>"
}
```

The error_simulation_type parameter can be set to:

- "0": No error simulation (normal operation)
- "1": Missing Configuration error
- "2": Invalid State Format error
- "3": Data Generation Error
- "4": Processing Error
- "5": Database Operation Error

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any additional python packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not require authentication.


## Pagination
Pagination is not applicable for this connector.


## Data handling
The connector simulates data processing in the following way:

- Data Generation: The connector generates simulated data containing a response message, timestamp, and random numeric value based on the provided configuration.

- Data Processing: Generated data is transformed into a structured format with the following fields:

    - `key`: Timestamp used as the primary key
    - `request`: Configuration value
    - `result`: Response message from simulated data
    - `metadata`: JSON-serialized object containing timestamp and random value
- Data Storage: The processed data is upserted to the `DEMO_TEST` table using the Connector SDK's operations interface.

- State Management: The connector maintains state using a cursor timestamp that tracks the last successful sync time, ensuring proper incremental syncs.


## Error handling
This connector demonstrates five key error handling patterns:

- Configuration Validation: Verifies required configuration parameters are present before proceeding with any operations. Missing parameters trigger a critical error (Error type 1).

- State Validation: Validates the format and content of the state object before using it, preventing errors from invalid state data (Error type 2).

- Data Generation Error Handling: Implements try/except blocks around data retrieval logic with appropriate logging and error propagation (Error type 3).

- Processing Error Handling: Validates data integrity before processing and handles exceptions that occur during transformation (Error type 4).

- Database Operation Error Handling: Gracefully handles failures during data upsert operations to the destination (Error type 5).

All errors are processed through a centralized `handle_critical_error` function that does the following:

- Logs the errors with appropriate severity level
- Includes detailed error information when available
- Raises an exception to stop connector execution when necessary


## Tables created
This connector creates a single table:

- `DEMO_RESPONSE_TEST` - Contains simulated data with a primary key of `key`


## Additional files
This example does not include additional files.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
