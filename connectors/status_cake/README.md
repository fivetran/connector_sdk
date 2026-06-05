# StatusCake Uptime Monitoring Connector Example


## Connector overview
This connector fetches uptime monitoring data from [StatusCake](https://app.statuscake.com/), a website monitoring service. It extracts uptime test configurations, historical performance data, downtime periods, and alert information to provide comprehensive monitoring insights. The connector integrates with StatusCake's API to pull data for all configured uptime tests and their associated monitoring metrics, enabling users to analyze website performance and reliability trends in their data warehouse.


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
fivetran init <project-path> --template connectors/status_cake
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Fetches all uptime test configurations and metadata
- Retrieves historical performance data with response times and status codes
- Collects downtime period information with start/end times and duration
- Extracts alert history with trigger timestamps and status details
- Handles API rate limiting with automatic retry logic
- Flattens nested JSON structures for optimal data warehouse storage
- Supports full data refresh on each sync 


## Configuration file
The configuration requires your StatusCake API key for authentication. You can obtain this from your StatusCake account dashboard under API settings.

```json
{
  "api_key": "<YOUR_STATUS_CAKE_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The `requirements.txt` file specifies additional Python libraries required by the connector. Following Fivetran best practices, this connector doesn't require additional dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses Bearer token authentication with StatusCake's API. You need to provide your API key in the configuration file. To obtain an API key:

1. Log into your StatusCake account.
2. Navigate to **Account Settings → API Keys**.
3. Create a new API key or copy an existing one.
4. Add the key to your `configuration.json` file as shown above.


## Data handling
The connector processes data from four main StatusCake API endpoints and flattens complex nested structures into relational table format. Each API response is parsed and nested objects are flattened using underscore notation. Arrays are converted to comma-separated strings for easier analysis. All data is upserted to ensure the latest information is always available.


## Error handling
The connector implements comprehensive error handling with exponential backoff retry logic for transient failures. API rate limiting (HTTP 429) is handled with automatic delays, and connection errors are retried up to 3 times with increasing delay intervals.


## Tables created
The connector creates four tables to store different aspects of StatusCake monitoring data:

- **UPTIME_TEST** - Core uptime test configurations and current status information
- **UPTIME_TEST_HISTORY** - Historical performance data with response times and status codes
- **UPTIME_TEST_PERIOD** - Downtime and uptime period records with durations
- **UPTIME_TEST_ALERT** - Alert notifications with trigger times and status changes


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.