# Apache Pulsar Connector Example

## Connector overview
This connector demonstrates how to fetch data from Apache Pulsar topics and sync it to a destination using the Fivetran Connector SDK. It supports multiple topics and uses Pulsar's Reader API to consume messages with proper checkpointing for incremental syncs. 

The connector is designed for organizations using Apache Pulsar who need to sync streaming data to their destination for analytics, such as clickstream events, payment transactions, and application logs.

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
fivetran init <project-path> --template connectors/apache_pulsar
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Supports syncing multiple Pulsar topics simultaneously, each to its own table
- Uses Pulsar's Reader API with checkpointing to track progress and resume from last position
- Automatically creates warehouse tables with proper data types
- Captures Pulsar metadata (message ID, publish time, producer info) alongside payload
- Uses configurable batch limits to prevent memory overflow
- Uses robust error handling with detailed logging

## Configuration file
The `configuration.json` file contains the connection details for your Apache Pulsar cluster. Update the following keys with your Pulsar cluster details:

```
{
  "service_url": "<YOUR_APACHE_PULSAR_SERVICE_URL>",
  "tenant": "<YOUR_APACHE_PULSAR_TENANT>",
  "namespace": "<YOUR_APACHE_PULSAR_NAMESPACE>",
  "topics": "<YOUR_TOPICS_COMMA_SEPARATED>",
  "auth_token": "<YOUR_OPTIONAL_APACHE_PULSAR_AUTH_TOKEN>"
}
```

Configuration parameters:
- `service_url` (required) - The Pulsar service URL (e.g., `pulsar://localhost:6650` or `pulsar+ssl://pulsar-aws-useast1.streaming.datastax.com:6651`).
- `tenant` (required) - The Pulsar tenant name.
- `namespace` (required) - The Pulsar namespace name
- `topics` (required) - Comma-separated list of topic names to sync.
- `auth_token` (optional) - Optional authentication token for secured Pulsar clusters.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The `requirements.txt` file specifies the Python libraries required by the connector. For this Apache Pulsar connector, the following library is required:

```
pulsar-client>=3.4.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector supports authentication using Apache Pulsar authentication tokens. For local standalone Pulsar instances, authentication is typically not required. For cloud or secured clusters, you can provide an authentication token in the `auth_token` configuration parameter. To obtain an authentication token, refer to your Pulsar provider's documentation (e.g., DataStax Astra Streaming, StreamNative Cloud).

## Pagination
The connector processes messages in batches to prevent memory overflow. It reads up to `__MAX_MESSAGES_PER_TOPIC` (default: `1000`) messages per topic per sync. The connector uses a timeout mechanism (`__READ_TIMEOUT_MS`, default: `5000ms`) to detect when all available messages have been read. This approach ensures efficient memory usage while maintaining good throughput.

## Data handling
Each Pulsar message is parsed and transformed into a structured record before being upserted to the destination. The connector creates a separate table for each topic, with the table name normalized from the topic name (replacing hyphens and dots with underscores). Message payloads are parsed as JSON when possible; otherwise, they are stored as raw strings or base64-encoded data. Refer to the `parse_message` function in `connector.py`.

## Error handling
The connector implements error handling at multiple levels. Configuration validation ensures all required parameters are present before sync starts. Connection errors are caught and raised with descriptive messages. Individual message processing errors are logged as warnings and the connector continues processing subsequent messages. Timeout exceptions are used to detect when all available messages have been consumed.

## Tables created
The connector creates one table per Pulsar topic. Each table has the following schema:

| Column | Type | Description |
|--------|------|-------------|
| `message_id` | STRING | Unique Pulsar message identifier (Primary Key) |
| `topic` | STRING | Source topic name |
| `publish_time` | UTC_DATETIME | When message was published to Pulsar |
| `event_time` | UTC_DATETIME | Event timestamp (if set by producer) |
| `message_key` | STRING | Message partition key |
| `data` | JSON | The actual message payload |
| `properties` | JSON | Message metadata/properties |
| `producer_name` | STRING | Name of the producer |
| `sequence_id` | INT | Message sequence ID |
| `synced_at` | UTC_DATETIME | When Fivetran synced this message |

Fore more details, refer to the `schema` function in `connector.py`.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
