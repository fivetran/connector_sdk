# RabbitMQ Connector SDK Example

## Connector overview
This connector syncs messages from RabbitMQ queues to Fivetran. The connector retrieves messages from specified queues using RabbitMQ's `basic_get` method. It consumes the messages only after a successful sync to prevent duplicate reads.

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
fivetran init <project-path> --template connectors/rabbitmq
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Synchronizes messages from multiple RabbitMQ queues
- Captures complete message metadata including delivery tags, routing keys, headers, and timestamps
- Implements incremental sync with per-queue state tracking using delivery tags
- Configurable batch size for optimal performance
- Checkpointing every 500 messages for reliable sync resumption
- Supports CloudAMQP and self-hosted RabbitMQ deployments
- AMQPS/TLS support for secure communication

## Configuration file


```json
{
  "connection_url": "<YOUR_RABBITMQ_CONNECTION_URL>",
  "queues": "<YOUR_COMMA_SEPARATED_LIST_OF_RABBITMQ_QUEUES>",
  "batch_size": "<YOUR_BATCH_SIZE>"
}
```

The configuration keys required for your connector are as follows:

- `connection_url` (required) - Full AMQP/AMQPS connection URL including credentials, host, and virtual host (see Authentication section for format examples)
- `queues` (required) - Comma-separated list of queue names to sync (for example: "orders,payments,notifications")
- `batch_size` (optional) - Number of messages to process per batch (defaults to 100)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The `requirements.txt` file specifies the Python libraries required by the connector:

```
pika==1.3.2
```

The connector uses the `pika` library (version 1.3.2) for connecting to and consuming messages from RabbitMQ.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses AMQP connection URLs for authentication. The connection URL includes credentials embedded in the URL format.

Example configurations:

- CloudAMQP (recommended for testing):
```json
{
  "connection_url": "amqps://username:password@host.cloudamqp.com/vhost"
}
```

- Local RabbitMQ (default credentials):
```json
{
  "connection_url": "amqp://guest:guest@localhost:5672/"
}
```

- Self-hosted with custom credentials:
```json
{
  "connection_url": "amqps://myuser:mypassword@rabbitmq.example.com:5671/production"
}
```

The connector automatically handles AMQPS/TLS connections when using the `amqps://` protocol scheme.

## Data handling

**Important**: Messages are permanently removed from RabbitMQ after a successful sync. This connector consumes messages using `basic_ack`, which deletes them from the queue. Use this connector only with dedicated analytical queues (for example, dead-letter or audit queues); never use it on production operational queues.

The connector performs message consumption and transformation. Refer to the `fetch_and_upsert_messages_batch` function for message handling:

- Queue discovery - Declares queues passively to verify existence and get message counts
- Message retrieval - Uses `basic_get` with `auto_ack=False` to fetch messages with manual acknowledgment
- Incremental filtering - Skips messages with delivery tags less than or equal to the last synced tag
- Message parsing - Handles different content types (application/json, text) with proper decoding
- Metadata extraction - Captures all RabbitMQ message properties (headers, routing keys, timestamps, delivery mode)
- Message consumption - Acknowledges messages with `basic_ack` after a successful sync to prevent re-reading
- Upsert operations - All records are upserted based on a unique message_id (generated from queue, delivery_tag, and body hash)

The `update` function orchestrates the complete sync process with state management and error handling for multiple queues.

## Error handling

The connector implements comprehensive error handling strategies. Refer to the following functions:

- Configuration validation (`validate_configuration`) - Ensures required parameters (connection_url, queues) are present
- Connection error handling (`create_rabbitmq_connection`) - Handles AMQP connection errors with detailed logging and runtime errors
- Channel error handling (`fetch_and_upsert_messages_batch`) - Handles AMQP channel errors during message retrieval
- Message parsing errors (`fetch_and_upsert_messages_batch`) - Gracefully handles message decoding failures with fallback to string representation
- Connection cleanup (`update` function finally block) - Ensures RabbitMQ connections are properly closed even on errors

## Tables created

The connector creates a separate table for each queue specified in the configuration file. Column types are automatically inferred by Fivetran based on the data. Each table includes the following columns:

| Column | Type | Description |
|--------|------|-------------|
| message_id | STRING | Unique message identifier (Primary Key) - hash of queue, delivery_tag, and body |
| delivery_tag | INT | RabbitMQ delivery tag for message ordering |
| queue_name | STRING | Source queue name |
| routing_key | STRING | Routing key used to deliver the message |
| exchange | STRING | Source exchange name |
| message_body | STRING | Message content (JSON or text) |
| content_type | STRING | Content type (e.g., application/json) |
| content_encoding | STRING | Content encoding (e.g., utf-8) |
| delivery_mode | INT | Message persistence mode (1=non-persistent, 2=persistent) |
| priority | INT | Message priority (0-255) |
| correlation_id | STRING | Correlation ID for request-response patterns |
| reply_to | STRING | Reply-to queue for response messages |
| expiration | STRING | Message expiration time |
| message_id_header | STRING | Message ID from message headers |
| timestamp | UTC_DATETIME | Message timestamp from RabbitMQ |
| type | STRING | Message type identifier |
| user_id | STRING | User ID that published the message |
| app_id | STRING | Application ID that published the message |
| headers | STRING | Additional message headers as JSON string |
| redelivered | BOOLEAN | Whether message was redelivered |
| synced_at | UTC_DATETIME | Timestamp when message was synced by the connector |

Table names are derived from queue names (lowercase with special characters replaced by underscores).

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
