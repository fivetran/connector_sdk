# AMQP Connector Example

## Connector overview
This connector consumes one queue of an AMQP 1.0 broker, such as Solace PubSub+, Azure Service Bus or RabbitMQ, and writes every message to a destination table named after the queue. Message bodies can be delivered as plain text, as packed JSON in a single `data` column, or as unpacked JSON with one `value_<field>` column per first-level field.

Consumption is destructive: after a message's row is checkpointed, the connector accepts the message and the broker removes it from the queue. Never point a sync at a queue that other consumers depend on.

Typical use cases include landing application events, order or audit messages published to a broker, and integration traffic that has no other durable store.


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
fivetran init <project-path> --template examples/quickstart/amqp
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects over TLS (`amqps`) and verifies the broker certificate, including its host name, against the system trust store.
- Authenticates with a username and password (SASL PLAIN) or with a client certificate (mutual TLS, SASL EXTERNAL).
- Writes Text, JSON Packed or JSON Unpacked rows, with the AMQP message properties as metadata columns.
- Accepts messages only after their rows are checkpointed, so a failed sync loses nothing; unaccepted messages are redelivered.
- Ends a sync at the first message created after the sync started, which stays in the queue for the next sync.
- Skips non-text messages, null bodies in JSON Unpacked mode and unparsable payloads with a warning instead of failing the sync.
- Defines a setup form with a connection test.
- Refuses hosts that resolve to loopback, private, link-local, multicast or carrier-grade NAT addresses.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_BROKER_HOST>",
  "port": "<YOUR_BROKER_AMQPS_PORT>",
  "namespace": "<YOUR_VHOST_OR_MESSAGE_VPN>",
  "queue_name": "<YOUR_QUEUE_NAME>",
  "auth_type": "<BasicAuth_OR_MutualTLS>",
  "username": "<YOUR_USERNAME>",
  "password": "<YOUR_PASSWORD>",
  "client_certificate": "<YOUR_BASE64_ENCODED_PEM_CLIENT_CERTIFICATE>",
  "client_private_key": "<YOUR_BASE64_ENCODED_PEM_CLIENT_PRIVATE_KEY>",
  "message_type": "<Text_OR_JSON>",
  "json_delivery_mode": "<Packed_OR_Unpacked>"
}
```

- `host` – The broker host name, IPv4 address or bracketed IPv6 address, without a scheme, port or path.
- `port` – The broker's AMQPS port, usually `5671`.
- `namespace` – The RabbitMQ vhost or Solace Message VPN. Only the broker's default is supported, so use `/`; see [Additional considerations](#additional-considerations).
- `queue_name` – The exact queue name, without prefixes.
- `auth_type` – `BasicAuth` (default) or `MutualTLS`.
- `username` and `password` – Required for `BasicAuth`.
- `client_certificate` and `client_private_key` – Required for `MutualTLS`. Provide the PEM client certificate chain and private key, base64-encoded so they fit in a single-line field. Plain PEM text is accepted too.
- `message_type` – `JSON` (default) or `Text`.
- `json_delivery_mode` – `Packed` (default) or `Unpacked`, used when `message_type` is `JSON`.

The same fields are defined in the setup form (refer to `def configuration_form()`).

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The connector requires the `python-qpid-proton` package, the Apache Qpid Proton AMQP 1.0 client.

```
python-qpid-proton==0.41.1
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector supports two authentication methods (refer to `def connect()` in `amqp_client.py`). Both run over TLS.

To use username and password authentication:

1. Create a broker user with permission to consume from the queue.
2. Set `auth_type` to `BasicAuth` and provide `username` and `password`.

To use mutual TLS:

1. Create a client private key and a client certificate signed by a certificate authority your broker trusts.
2. Register the certificate's common name with the broker, for example as a Solace client username or a RabbitMQ user with `ssl_cert_login_from = common_name`, and grant it permission to consume from the queue.
3. Set `auth_type` to `MutualTLS` and provide the base64-encoded certificate and key as `client_certificate` and `client_private_key`.

The broker's own certificate must chain to a certificate authority in the system trust store.


## Data handling
The connector reads messages until the queue has been idle for 10 seconds (refer to `def consume_queue()`). A sync also ends at the first message whose creation time is at or after the sync start; that message is not accepted, so the broker redelivers it on the next sync. If no message carries a creation time, the sync ends after one million messages.

Each message becomes one row with an `event_id` primary key made of the receive time in milliseconds and a per-sync counter, so a message the broker redelivers becomes a new row. The body is written according to the message type (refer to `def message_values()`):

- Text – The text goes to the `data` column.
- JSON Packed – The parsed JSON goes to the `data` column, which is typed `JSON`.
- JSON Unpacked – Each first-level field of a JSON object goes to a `value_<field>` column. A payload that is not a JSON object, such as an array, falls back to Packed. A null body is skipped.

A message counts as text when the Qpid JMS client would read it as a JMS text message (refer to `def body_kind()` in `amqp_message.py`): a string body, a null body, a data section with a textual content type such as `text/*` or `application/json`, or the `x-opt-jms-msg-type` annotation for text. Message ids are rendered the way Qpid JMS renders `JMSMessageID`, for example `ID:AMQP_NO_PREFIX:order-1` (refer to `def message_id_text()`).

The connector checkpoints every 10,000 messages and at the end of the sync, and accepts the processed messages only after each checkpoint (refer to `def checkpoint_and_acknowledge()`). The state keeps the creation time of the last synced message as `last_message_creation_time`.


## Error handling
- Skipped messages – Non-text messages and null bodies in JSON Unpacked mode are skipped with one dashboard warning per sync (`op.warning()`), and a payload that cannot be parsed is skipped with a log warning. Skipped messages are accepted with the batch, so they do not block the queue (refer to `def process_message()`).
- Customer-actionable failures – Rejected credentials, a queue the broker reports as not found, and certificate problems end the sync with an error on the dashboard (`op.error()`) (refer to `def classify_failure()` in `amqp_client.py`).
- Acknowledgment failures – Accepting a batch is retried three times with exponential backoff from 300 ms; after that the sync fails and the unaccepted messages are redelivered next time (refer to `def acknowledge_pending()`).
- Other failures – Connection errors, timeouts and restricted hosts fail the sync with the underlying error, and Fivetran retries on the next schedule.


## Tables created
The connector creates one table named after the queue (refer to `def schema()`). Columns are created as values arrive, so a metadata column that is null for every message so far is not created yet.

| Column | Type | Description |
| --- | --- | --- |
| `event_id` | STRING | Primary key: receive time in milliseconds and a per-sync counter. |
| `data` | JSON or STRING | The payload: `JSON` for the JSON message type, `STRING` for Text. Absent for JSON Unpacked rows that unpacked. |
| `value_<field>` | inferred | One column per first-level field, JSON Unpacked only. |
| `message_id` | STRING | The message id, as rendered by Qpid JMS. |
| `correlation_id` | STRING | The correlation id, as rendered by Qpid JMS. |
| `user_id` | STRING | The user id property, decoded as UTF-8. |
| `to` | STRING | The to address property. |
| `subject` | STRING | The subject property. |
| `reply_to` | STRING | The reply-to address. |
| `content_type` | STRING | The content type property. |
| `content_encoding` | STRING | The content encoding property. |
| `absolute_expiry_time` | LONG | The absolute expiry time, in epoch milliseconds. |
| `created_time` | UTC_DATETIME | The creation time property. |
| `group_id` | STRING | The group id property. |
| `group_sequence` | LONG | The group sequence property. |
| `reply_to_group_id` | STRING | The reply-to group id property. |
| `application_properties` | STRING | The application properties, as a JSON object. |


## Additional files
- `amqp_client.py` – Validates the host, opens the TLS connection and queue receiver, and classifies failures.
- `amqp_message.py` – Classifies messages as text or not, renders message ids, and builds the row values.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

Only the broker's default virtual host or Message VPN is supported. RabbitMQ selects another vhost through an AMQP open hostname of the form `vhost:<name>`, and `python-qpid-proton` 0.41.1 crashes the process on TLS connections whose open hostname contains a colon. When the broker rejects the connection while a non-default `namespace` is configured, the sync fails with an error that explains this.

The connector refuses hosts that resolve to loopback or private addresses, so it cannot be tested against a broker running on your own machine without changing `def check_destination_allowed()` in `amqp_client.py`.
