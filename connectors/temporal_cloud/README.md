# Temporal Cloud Connector Example

## Connector overview

This connector syncs workflow and schedule data from Temporal Cloud to Fivetran. Temporal Cloud is a managed service for running Temporal workflows, which are durable, scalable, and fault-tolerant distributed applications. This connector retrieves workflow execution history and schedule configurations from your Temporal namespace, allowing you to analyze workflow performance, monitor execution patterns, and track schedule configurations in your data warehouse.

The connector fetches two main types of data:
- Workflow executions: Including workflow metadata, execution status, timing information, task queues, execution duration, and search attributes
- Schedules: Including schedule specifications (cron expressions, intervals, calendar-based schedules), next action times, recent execution history, workflow actions to be triggered, and schedule state (paused/active)


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
fivetran init <project-path> --template connectors/temporal_cloud
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- Extracts all workflow executions from your Temporal namespace
- Retrieves complete schedule configurations 
- Captures workflow metadata including status, task queue, and search attributes
- Extracts schedule specifications including cron expressions, intervals, and calendar-based schedules
- Implements async operations for efficient data retrieval
- Uses streaming approach to handle large datasets without memory overflow


## Configuration file

The connector requires three configuration parameters to connect to your Temporal Cloud account:

```json
{
  "temporal_host": "<YOUR_TEMPORAL_HOST>",
  "temporal_namespace": "<YOUR_TEMPORAL_NAMESPACE>",
  "temporal_api_key": "<YOUR_TEMPORAL_API_KEY>"
}
```

Configuration parameters:
- `temporal_host` – Your Temporal Cloud host address in the format `namespace.tmprl.cloud:7233`
- `temporal_namespace` – Your Temporal namespace identifier
- `temporal_api_key` – API key for authenticating with Temporal Cloud

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file

The connector requires the Temporal Python SDK for connecting to Temporal Cloud:

```
temporalio==1.22.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication

The connector uses API key authentication to access Temporal Cloud. To obtain the necessary credentials:

1. Log in to your [Temporal Cloud account](https://cloud.temporal.io).

2. Navigate to your namespace settings.

3. Generate an API key with read permissions for workflows and schedules.

4. Copy the API key and your namespace details.

5. Add these credentials to your `configuration.json` file.

The API key is passed securely via the TLS connection to Temporal Cloud. Configuration validation is performed by the `validate_configuration` function at the start of each sync.


## Pagination

The connector uses Temporal Cloud's native async iteration to handle large datasets efficiently. Both workflows and schedules are retrieved using async generators:

- Workflow pagination: This uses `client.list_workflows()`, which returns an async iterator. Workflows are processed one at a time without loading all data into memory.
- Schedule pagination: This uses `client.list_schedules()`, which returns an async iterator for streaming schedule data.

Progress is logged at every 1000 records for both workflows and schedules. The streaming approach ensures the connector can handle namespaces with thousands of workflows and schedules without memory overflow issues.


## Data handling

The connector implements several helper functions to extract and transform data from Temporal Cloud objects. Refer to `connector.py` for implementation details.

Workflow data processing:
- `_calculate_execution_time` – Calculates workflow execution duration in seconds from start and close timestamps
- `_build_workflow_data` – Transforms Temporal workflow objects into structured dictionaries for destination tables

Schedule data processing:
- `_extract_next_action_times` – Extracts upcoming execution times from schedule info
- `_extract_recent_actions` – Retrieves recent execution history with scheduled and actual times
- `_extract_schedule_spec` – Extracts schedule specifications including cron expressions, intervals, calendar settings, and timezone information
- `_extract_schedule_action` – Retrieves workflow action details that will be triggered by the schedule
- `_extract_schedule_state` – Extracts schedule state including paused status and notes
- `_build_schedule_data` – Orchestrates all schedule data extraction into a complete record

All timestamps are converted to ISO 8601 format with timezone awareness using `datetime.now(timezone.utc)`. The connector uses the upsert operation to insert or update records in destination tables, ensuring idempotent syncs.


## Error handling

The connector implements comprehensive error handling strategies. Refer to `connector.py` for implementation details.

- The `validate_configuration` function verifies that all required parameters are present before attempting connection
- The `is_transient_error` helper classifies errors into transient (safe to retry) and permanent (fail fast). Permanent errors include authentication failures and other 4xx client errors caused by invalid credentials or request parameters; these are not retried and are surfaced immediately
- The `_connect_temporal_client` and `_fetch_temporal_data` functions wrap Temporal client connection and data retrieval calls with centralized retry handling


## Tables created

The connector creates two tables in your destination:

### workflow

Contains workflow execution data from Temporal Cloud.

Primary key: `workflow_id`, `run_id`

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| `workflow_id` | STRING | Unique identifier for the workflow (primary key) |
| `run_id` | STRING | Unique identifier for this specific workflow execution (primary key) |
| `workflow_type` | STRING | Type/name of the workflow |
| `start_time` | UTC_DATETIME | Timestamp when the workflow execution started |
| `close_time` | UTC_DATETIME | Timestamp when the workflow execution completed |
| `status` | STRING | Execution status (e.g., COMPLETED, FAILED, RUNNING) |
| `task_queue` | STRING | Task queue where the workflow was executed |
| `execution_time_seconds` | DOUBLE | Total execution duration in seconds |
| `memo` | JSON | Workflow memo data |
| `search_attributes` | JSON | Custom search attributes attached to the workflow |

### schedule

Contains schedule configuration and execution history from Temporal Cloud.

Primary key: `schedule_id`

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| `schedule_id` | STRING | Unique identifier for the schedule (primary key) |
| `paused` | BOOLEAN | Indicates if the schedule is paused |
| `note` | STRING | Optional note attached to the schedule |
| `next_action_times` | JSON | Array of upcoming execution times |
| `recent_actions` | JSON | Array of recent execution history with scheduled and actual times |
| `schedule_spec` | JSON | Schedule specification including cron expressions, intervals, calendar settings, start/end times, timezone, and jitter |
| `schedule_action` | JSON | Workflow action to be triggered including workflow type, task queue, and workflow ID |
| `search_attributes` | JSON | Custom search attributes attached to the schedule |


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

