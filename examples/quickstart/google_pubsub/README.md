# Google Pub/Sub Connector Example

## Connector overview
This connector consumes messages from a [Google Cloud Pub/Sub](https://cloud.google.com/pubsub) subscription and writes them to your destination. It suits event and change streams that are already published to Pub/Sub, such as application events, IoT readings or change notifications from other systems.

Each sync pulls messages until the subscription is quiet, writes them, and acknowledges them only after they have been checkpointed. A Pub/Sub snapshot taken at the end of each sync gives the next sync a recovery point: if a sync acknowledges messages and then fails before it finishes, the next sync seeks back to the snapshot and receives those messages again.


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
fivetran init <project-path> --template examples/quickstart/google_pubsub
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Writes each message to a table named after the subscription, with its content, SHA-256 hash and publish time.
- Routes a message whose body is `{"table": "<name>", "data": {...}}` to the table it names, with the `data` object as the row.
- Optionally unpacks the top-level fields of JSON messages into columns, one or two levels deep.
- Acknowledges messages only after the rows that hold them have been checkpointed.
- Keeps a Pub/Sub snapshot as a recovery point, alternating between two snapshot slots so the previous one survives until the new one is saved.
- Ends the sync once the subscription is quiet, so a subscription that keeps receiving messages cannot keep one sync running forever.
- Defines a setup form with tests for subscription and snapshot permissions.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "project_id": "<YOUR_GOOGLE_CLOUD_PROJECT_ID>",
  "subscription_id": "<YOUR_PUBSUB_SUBSCRIPTION_ID>",
  "sync_format": "<PACKED_OR_UNPACKED>",
  "unpacking_level": "<ONE_OR_TWO_FOR_UNPACKED>",
  "key_content": "<YOUR_SERVICE_ACCOUNT_KEY_JSON>"
}
```

- `project_id` – The Google Cloud project that owns the subscription.
- `subscription_id` – The subscription to consume. It also names the destination table.
- `sync_format` – `PACKED` writes the message content as a single column. `UNPACKED` also turns the top-level fields of a JSON message into columns.
- `unpacking_level` – Required for `UNPACKED`. `ONE` keeps each top-level field as a column. `TWO` replaces a field that holds a JSON object, or a string containing one, with that object's fields.
- `key_content` – The content of a service account key file in JSON format. Only keys of type `service_account` are accepted.

The same fields are defined in the setup form (refer to `def configuration_form()`).

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The connector requires the `google-cloud-pubsub` package to pull messages and manage snapshots.

```
google-cloud-pubsub==2.31.1
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector authenticates with a Google Cloud service account key (refer to `def create_client()` in `pubsub_client.py`).

To set up authentication:

1. In the Google Cloud console, create a service account in the project that owns the subscription.
2. Grant it the `pubsub.subscriptions.consume` permission on the subscription, for example through the Pub/Sub Subscriber role.
3. Grant it the `pubsub.snapshots.create`, `pubsub.snapshots.delete` and `pubsub.snapshots.seek` permissions on the project, for example through the Pub/Sub Editor role. Without them the connector still syncs, but cannot recover messages acknowledged by a failed sync.
4. Create a JSON key for the service account and provide its content as `key_content`.

The setup tests check these permissions (refer to `def subscriber_test()` and `def snapshot_permissions_test()`). A missing consume permission fails the setup. Missing snapshot permissions are logged as a warning and do not block the setup, because snapshots only add recovery.


## Data handling
The connector uses the synchronous Pull API rather than streaming pull, so that it knows an acknowledgement has reached Pub/Sub before it takes a snapshot (refer to `def consume_messages()` and `def process_batch()`):

1. Pull up to 1,000 messages and extend their lease to 10 minutes.
2. Upsert a row for each message.
3. Checkpoint, which returns once the rows are committed.
4. Acknowledge the written messages.

After the last batch, the connector creates a snapshot of the subscription, records its name in the state, checkpoints, and only then deletes the previous snapshot (refer to `def save_snapshot()`). At the start of the next sync it seeks the subscription back to that snapshot (refer to `def update()`). A snapshot that has expired or been removed is skipped.

The sync stops when no message has been written for 60 seconds, or when no message published before the sync started has been written for 3 minutes (refer to `def should_stop()`).

Each row id is the Pub/Sub message id followed by a five-digit per-sync counter (refer to `def unique_id()` in `message_parser.py`). A message delivered again in a later sync, for example after a snapshot seek, therefore gets a new id and appears as a new row. Decimal numbers in message bodies keep their scale when they are top-level columns.


## Error handling
- Unparsable messages – A message that cannot be turned into a row, such as a non-JSON message with the `UNPACKED` format, is logged and left unacknowledged. Pub/Sub redelivers it once its 10-minute lease expires, normally in a later sync, instead of straight back into the current one.
- Missing or expired snapshot – The seek is skipped with a warning and the sync continues from the subscription's current position (refer to `def seek_to_snapshot()` in `pubsub_client.py`).
- Snapshot failures – If a snapshot cannot be created, the state keeps the previous snapshot name. A leftover snapshot with the same name is deleted and recreated. A failure to delete an outdated snapshot is logged and does not fail the sync.
- Write failures – An error while writing rows fails the sync before the batch is acknowledged, so its messages are redelivered when their lease expires.


## Tables created
The connector creates the following tables (refer to `def schema()`).

The table named after the subscription holds every message that does not name its own table:

```json
{
  "table": "<subscription_id>",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING",
    "message_hash": "STRING",
    "content": "STRING",
    "timestamp": "UTC_DATETIME"
  }
}
```

With the `UNPACKED` format the table also gets one column per top-level field of the JSON messages, with types inferred from the values.

A message of the form `{"table": "<name>", "data": {...}}` creates or updates the table `<name>`, with one column per field of `data` and a `unique_id` column holding the row id. These tables cannot be declared in `schema()` because their names come from the messages, so their column types are inferred from the values and Fivetran adds a `_fivetran_id` primary key.


## Additional files
- `pubsub_client.py` – Calls the Pub/Sub API: creates the client from the service account key, pulls, extends leases, acknowledges, manages snapshots and tests permissions.
- `message_parser.py` – Turns a message into a destination row: chooses the table, builds the row id and hash, and unpacks JSON fields.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
