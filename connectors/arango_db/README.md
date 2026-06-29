# ArangoDB Connector Example

## Connector overview
This connector demonstrates how to sync data from ArangoDB, a native multi-model database that combines document, graph, and key-value capabilities.

The connector syncs three collections from a travel dataset: airports (document collection), flights (edge collection for graph relationships), and points-of-interest (document collection). This example showcases ArangoDB's unique multi-model architecture and is ideal for use cases involving interconnected data like social networks, recommendation engines, and travel planning systems.

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
fivetran init <project-path> --template connectors/arango_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Syncs document collections (airports, points-of-interest) and edge collections (flights)
- Demonstrates ArangoDB's multi-model capabilities combining documents and graphs
- Implements batch processing with checkpointing for large datasets
- Uses offset-based pagination to handle collections with hundreds of thousands of records
- Preserves ArangoDB's native fields including `_key`, `_from`, and `_to` for graph relationships

## Configuration file
The connector requires the following configuration parameters:

```
{
  "host": "<YOUR_ARANGODB_HOST>",
  "database": "<YOUR_ARANGODB_DATABASE_NAME>",
  "username": "<YOUR_ARANGODB_USERNAME>",
  "password": "<YOUR_ARANGODB_PASSWORD>"
}
```

Configuration parameters:

- `host` (requried): Your ArangoDB host.
- `database` (requried): Your ArangoDB database name.
- `username` (requried):  Your ArangoDB username.
- `password` (requried): Your ArangoDB password.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The connector requires the `python-arango` package to connect to ArangoDB databases.

```
python-arango
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses username and password authentication to connect to ArangoDB. The credentials are specified in the configuration file and passed with the `ArangoClient.db()` method. Refer to the `connect_to_arangodb()` function in `connector.py`.

To set up authentication:

1. Obtain your ArangoDB instance URL (either cloud-hosted or self-hosted).
2. Create a database user with read permissions on the collections you want to sync.
3. Provide the host URL, database name, username, and password in the `configuration.json` file.
4. Ensure the user has `READ` permissions on the collections that need to be synced.

## Pagination
The connector implements offset-based pagination using ArangoDB's `skip` and `limit` parameters. Each collection is synced in batches of 1,000 records (defined by `__CHECKPOINT_BATCH_SIZE`).

The connector tracks the current offset in the state for each collection, allowing it to resume from the correct position after interruptions. Refer to the `sync_collection_batches()` function in `connector.py` for pagination logic details.

## Data handling
The connector processes each ArangoDB collection independently and upserts documents as-is to the destination tables. 

Document collections (airports, points-of-interest) contain standard fields like name, location coordinates, and metadata. Edge collections (flights) include special ArangoDB fields (`_from`, `_to`) that define graph relationships between airports. 

All ArangoDB system fields (`_key`, `_id`, `_rev`) are preserved in the destination for data lineage. The schema definition includes only the primary key (`_key`); Fivetran infers all other columns and data types automatically. Refer to the `schema()` and `sync_collection()` functions in `connector.py` for data handling details.

## Error handling
The connector implements comprehensive error handling with the following strategies:
- Connection failures are caught and logged with detailed error messages before raising a `RuntimeError`
- Collection access errors are caught at the collection level with specific error context
- Each collection is synced independently, so a failure in one collection does not prevent others from syncing successfully
- All errors are logged using the SDK's logging facility with appropriate severity levels

Refer to the `connect_to_arangodb()`, `sync_collection()`, and `update()` functions in `connector.py` for error handling details.

## Tables created
The connector creates the following tables:

| Table Name           | Type                | Primary Key | Description                                                                                                                                                                                         |
|----------------------|---------------------|-------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `AIRPORTS`           | Document Collection | `_key`      | Airport information including name, city, state, country, coordinates (lat, long), and VIP status. All ArangoDB system fields (`_key`, `_id`, `_rev`) are preserved.                                |
| `FLIGHTS`            | Edge Collection     | `_key`      | Flight connections between airports (graph relationships). Includes ArangoDB graph fields (`_from`, `_to`) plus flight details like date, times, carrier, flight number, tail number, and distance. |
| `POINTS_OF_INTEREST` | Document Collection | `_key`      | Travel destination information including title, type, description, coordinates (latitude, longitude), URL, article, contact information (phone, email), and `last_edit` timestamp.                  |

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
