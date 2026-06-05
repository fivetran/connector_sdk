# Prefect Cloud Connector Example

## Connector overview

This connector syncs workflow orchestration data from Prefect Cloud to your data warehouse using the Prefect Cloud REST API. It enables you to analyze workflow execution patterns, monitor pipeline health, and optimize data orchestration workflows. The connector supports incremental syncing of flows, deployments, work pools, work queues, flow runs, task runs, artifacts, and variables with automatic checkpointing for reliable data synchronization.

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
fivetran init <project-path> --template connectors/prefect
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental syncing based on updated timestamps for all tables
- Automatic pagination handling for large datasets
- Retry logic with exponential backoff for transient API failures
- Automatic checkpointing every 500 records to ensure data consistency
- Flattening of nested JSON structures into relational tables
- Support for eight core Prefect resources: flows, deployments, work pools, work queues, flow runs, task runs, artifacts, and variables

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "api_key": "<YOUR_PREFECT_API_KEY>",
  "account_id": "<YOUR_PREFECT_ACCOUNT_ID>",
  "workspace_id": "<YOUR_PREFECT_WORKSPACE_ID>"
}
```

### Configuration parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `api_key` | string | Yes | Your Prefect Cloud API key used for authentication. This key should have read access to the workspace you want to sync. |
| `account_id` | string | Yes | Your Prefect Cloud account identifier. This can be found in your Prefect Cloud URL or account settings. |
| `workspace_id` | string | Yes | Your Prefect Cloud workspace identifier. This specifies which workspace's data will be synced to your data warehouse. |

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector does not require any additional Python packages beyond the Fivetran Connector SDK.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses Bearer token authentication to access the Prefect Cloud API. The API key is passed in the Authorization header for all requests.

To obtain your API credentials:

1. Log in to your [Prefect Cloud] (https://app.prefect.cloud/) account.
2. Navigate to your account settings and select **API Keys**.
3. Generate a new API key with appropriate permissions.
4. Make a note of the API key. You will need to add it to the `configuration.json` file.
5. Find your account ID and workspace ID in the Prefect Cloud URL or account settings.
6. Add all three values to your `configuration.json` file.

## Pagination

The connector implements pagination using the Prefect API filter endpoints with limit and offset parameters. Each API request fetches up to 100 records per page. Records are processed page-by-page to minimize memory usage, with each page being upserted immediately after fetching. The connector continues fetching pages until an empty response is received, indicating all available data has been retrieved. Pagination logic is implemented in the `fetch_and_process_paginated_data()` function.

## Data handling

The connector fetches data from Prefect Cloud API filter endpoints and processes it as follows:

- JSON responses are flattened using the `flatten_record()` function to convert nested dictionaries into single-level key-value pairs
- Nested objects are flattened with underscore-separated keys
- Arrays are serialized as JSON strings
- Each record is upserted to the destination table with its flattened structure
- The connector tracks the maximum updated timestamp for each table to enable incremental syncing
- State is maintained separately for each table to allow independent sync progress

## Error handling

The connector implements comprehensive error handling:

- Retry logic with exponential backoff for transient failures including network timeouts, connection errors, and HTTP 429/5xx status codes
- Maximum of 3 retry attempts with delays of 1, 2, and 4 seconds
- Specific exception handling for timeout and connection errors
- Failed requests after all retries raise RuntimeError with detailed error messages
- All errors are logged with severity levels for monitoring and debugging
- Non-retryable errors such as authentication failures result in immediate failure

Refer to the `make_api_request()` function for detailed error handling implementation.

## Tables created

The connector creates the following tables in your destination:

| Table Name       | Primary Key | Description                                                          | Key Columns                                                                                                                            |
|------------------|-------------|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| flow         | `id`        | Stores workflow definitions and metadata                             | `id`, `created`, `updated`, `name`, `tags`, `labels`                                                                                   |
| deployment   | `id`        | Stores deployment configurations with scheduling information         | `id`, `created`, `updated`, `name`, `flow_id`, `schedule`, `parameters`, `is_schedule_active`, `paused`                                |
| work_pool    | `id`        | Stores work pool configurations for workflow execution environments  | `id`, `created`, `updated`, `name`, `type`, `description`, `is_paused`, `base_job_template`                                            |
| work_queue   | `id`        | Stores work queue configurations for prioritizing workflow execution | `id`, `created`, `updated`, `name`, `description`, `priority`, `is_paused`, `concurrency_limit`, `work_pool_id`                        |
| flow_run     | `id`        | Stores execution records of workflow runs                            | `id`, `created`, `updated`, `name`, `flow_id`, `deployment_id`, `state_type`, `state_name`, `start_time`, `end_time`, `total_run_time` |
| task_run     | `id`        | Stores execution records of individual tasks within flows            | `id`, `created`, `updated`, `name`, `flow_run_id`, `task_key`, `state_type`, `state_name`, `start_time`, `end_time`, `total_run_time`  |
| artifact     | `id`        | Stores output data and results from workflow executions              | `id`, `created`, `updated`, `key`, `type`, `description`, `data`, `flow_run_id`, `task_run_id`                                         |
| variable     | `id`        | Stores workspace-level variables for configuration management        | `id`, `created`, `updated`, `name`, `value`, `tags`                                                                                    |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
