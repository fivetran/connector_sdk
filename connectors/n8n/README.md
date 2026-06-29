# n8n Connector Example

## Connector overview
This connector syncs workflow automation data from n8n, including workflows and workflow executions. It enables teams to analyze workflow performance, track execution history, and monitor automation health. The connector uses the n8n REST API to fetch data incrementally based on update timestamps and execution IDs, ensuring efficient synchronization of only new or modified data.

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
fivetran init <project-path> --template connectors/n8n
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Incremental sync of workflows based on update timestamps
- Incremental sync of executions based on execution IDs
- Automatic retry logic with exponential backoff for transient API errors
- Pagination support for large datasets with configurable page sizes
- Checkpoint strategy that saves progress every 100 records
- Flattening of nested JSON objects for simplified analytics

**Note**: Credentials are not synced as the n8n public API does not expose credential endpoints for security reasons.

## Configuration file
The connector requires the following configuration parameters:

```json
{
  "base_url": "<YOUR_N8N_BASE_URL>",
  "api_key": "<YOUR_N8N_API_KEY>"
}
```

### Configuration parameters

- `base_url` (required): The base URL of your n8n instance (e.g., `https://your-n8n-instance.com` for cloud or `http://localhost:5678` for self-hosted)
- `api_key` (required): Your n8n API key with read permissions for workflows and executions

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The connector uses only the SDK-provided packages (`fivetran_connector_sdk` and `requests`). No additional dependencies are required, so the `requirements.txt` file is empty.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses API key authentication to access the n8n REST API. To obtain an API key:

1. Log in to your n8n instance (self-hosted or cloud).
2. Navigate to **Settings** > **n8n API**.
3. Click **Create an API key**.
4. Choose a descriptive label for the key and set an expiration time.
5. Copy the generated API key and add it to your `configuration.json` file.
6. Ensure the API key has appropriate permissions to read workflows and executions.

Note: API keys are not available during free trials. You must upgrade to a paid plan to access the n8n API.

## Pagination
The connector implements cursor-based pagination for all endpoints (refer to `fetch_workflows_page` and `fetch_executions_page_with_cursor` functions). Each API request fetches up to 100 records per page using the `limit` and `cursor` parameters. The connector continues fetching pages until an empty response is received or the page contains fewer records than the limit, indicating the end of available data.

## Data handling
The connector processes data from two main n8n endpoints:

- **Workflows**: Fetches workflow definitions including name, active status, nodes, connections, and settings. Nested JSON objects such as nodes, connections, and settings are serialized to JSON strings for storage (refer to the `flatten_workflow` function).

- **Executions**: Fetches workflow execution records including workflow ID, execution mode, status, timestamps, and execution data. Complex nested structures like execution data and waiting execution objects are serialized to JSON strings (refer to the `flatten_execution` function).

The connector implements incremental sync logic by tracking the latest update timestamp for workflows and the latest execution ID for executions.

## Error handling
The connector implements comprehensive error handling with retry logic for transient failures (refer to the `make_api_request` function):

- **Retryable errors**: HTTP status codes 429, 500, 502, 503, 504, along with timeout and connection errors, trigger automatic retries with exponential backoff (2 seconds base delay, doubling each attempt) up to 3 attempts.

- **Non-retryable errors**: Authentication failures (401), permission errors (403), and invalid requests (400, 404) fail immediately without retry.

- **Configuration validation**: The connector validates required configuration parameters at startup, ensuring `base_url` and `api_key` are present and properly formatted (refer to the `validate_configuration` function).

All errors are logged using the SDK logging framework with appropriate severity levels before raising exceptions to halt the sync.

## Tables created
The connector creates two tables in the destination:

### workflows

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| `id` | STRING | Primary key - Unique workflow identifier |
| `name` | STRING | Workflow name |
| `active` | BOOLEAN | Whether workflow is active |
| `created_at` | UTC_DATETIME | Workflow creation timestamp |
| `updated_at` | UTC_DATETIME | Last update timestamp |
| `tags` | JSON | Workflow tags array |
| `nodes` | JSON | Workflow nodes configuration |
| `connections` | JSON | Node connections definition |
| `settings` | JSON | Workflow settings |
| `static_data` | JSON | Static workflow data |
| `version_id` | STRING | Workflow version identifier |

### executions

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| `id` | STRING | Primary key - Unique execution identifier |
| `workflow_id` | STRING | Foreign key to workflows table |
| `mode` | STRING | Execution mode (trigger, manual, etc.) |
| `status` | STRING | Execution status (success, error, etc.) |
| `started_at` | UTC_DATETIME | Execution start timestamp |
| `stopped_at` | UTC_DATETIME | Execution stop timestamp |
| `finished` | BOOLEAN | Whether execution completed |
| `data` | JSON | Execution data and results |
| `waiting_execution` | JSON | Waiting execution details |
| `retry_of` | STRING | ID of execution being retried |
| `retry_success_id` | STRING | ID of successful retry |

Note: The credentials table is not synced as the n8n public API does not expose credential data for security reasons.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
