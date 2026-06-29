# Google Cloud Pub/Sub Connector Example

## Connector overview

This connector demonstrates how to sync data from Google Cloud Pub/Sub to a destination using the Fivetran Connector SDK. It subscribes to a Pub/Sub subscription, pulls messages in batches, and delivers them to your destination.

> Note: This example includes topic creation and message publishing functionality for testing purposes only. In production deployments, your application would publish messages to existing topics, and the connector would only consume and sync those messages.


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
fivetran init <project-path> --template connectors/gcp_pub_sub
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- Batch message processing – Pulls messages in configurable batches to optimize performance
- Automatic acknowledgment – Removes successfully processed messages from the subscription queue
- JSON message parsing – Decodes and parses JSON-formatted message payloads
- State checkpointing – Tracks sync progress for reliable data delivery


## Configuration file

The connector requires the following configuration parameters:

```json
{
  "service_key": "<GOOGLE_SERVICE_KEY_JSON_STRING>",
  "max_messages": "<MAX_MESSAGE_COUNT>",
  "subscription_name": "<SUBSCRIPTION_NAME>",
  "topic_name": "<TOPIC_NAME>"
}
```

- `service_key` – Your GCP service account key as a JSON string. Ensure the string is properly escaped (e.g., escape double quotes as `\"`)
- `max_messages` – Maximum number of messages to pull from Pub/Sub in each batch (default: 5)
- `subscription_name` – Name of the Pub/Sub subscription to consume messages from
- `topic_name` – Name of the Pub/Sub topic associated with the subscription

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file

This connector requires the following Python libraries:

```
google-cloud-pubsub
google-auth
google-api-core
protobuf==6.30.1
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication

The connector uses Google Cloud service account authentication. The service account key must be provided as a JSON string in the `service_key` configuration parameter. The service account must have the necessary permissions.

To obtain a service account key:

1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).

2. Select your project.

3. Go to IAM & Admin > Service Accounts.

4. Create a new service account or select an existing one.

5. Click **Add Key > Create New Key** and select JSON format.

6. Copy the entire JSON content and paste it as a string in the `service_key` field of `configuration.json`.


## Pagination

The connector implements batch-based pagination using the `max_messages` configuration parameter. The `pull_and_upsert_messages()` function continuously pulls messages in batches until no more messages are available:

1. Requests up to `max_messages` from the subscription
2. Processes and upserts each message
3. Acknowledges all processed messages
4. Repeats until fewer messages than `max_messages` are returned, indicating all available messages have been processed

This approach efficiently handles large message volumes while maintaining memory efficiency.


## Data handling

The connector processes Pub/Sub messages through the following workflow (see `pull_and_upsert_messages()`):

1. Message retrieval – Pulls messages from the subscription using `subscriber.pull()`
2. Message parsing – Decodes the message payload from bytes to UTF-8 and parses as JSON
3. Key assignment – Uses the Pub/Sub message ID as the unique key for each record
4. Data upsert – Inserts or updates each message in the `SAMPLE_TABLE` destination table
5. Acknowledgment – Acknowledges processed messages to remove them from the subscription queue
6. Checkpointing – Saves sync state after processing all available messages


## Error handling

The connector implements error handling at multiple levels:

- Validates that all required configuration parameters are present
- Topic creation – Handles `AlreadyExists` exception gracefully when creating test topics
- Wraps message processing in try-except blocks to catch and report errors during:
- All exceptions are re-raised as `RuntimeError` with contextual error messages for debugging.


## Tables created

The connector creates a single table to store Pub/Sub messages:

### `SAMPLE_TABLE`

The sample table contains messages pulled from the Pub/Sub subscription. The schema is defined as follows:

```json
{
    "table": "sample_table",
    "primary_key": ["key"],
    "columns": {
        "key": "STRING",
        "timestamp": "UTC_DATETIME"
    }
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
