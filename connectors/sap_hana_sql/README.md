# SAP HANA Connector Example

## Connector overview

This connector extracts data from a SAP HANA database using the `hdbcli`. The connector demonstrates how to establish a connection to a SAP HANA database, execute SQL queries to fetch data in batches, and efficiently upsert this data into Fivetran's destination. This example also shows how to sync the data incrementally by tracking the last synced timestamp and using it to filter new or updated records.

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
fivetran init <project-path> --template connectors/sap_hana_sql
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connects to SAP HANA database using `hdbcli`
- Implements incremental updates based on record creation date
- Processes data in batches to optimize memory usage
- Validates configuration parameters before attempting connections
- Error handling for connection failures

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_SAP_HANA_SERVER>",
  "port": "<YOUR_SAP_HANA_PORT>",
  "database": "<YOUR_SAP_HANA_DATABASE>",
  "username": "<YOUR_SAP_HANA_USER_ID>",
  "password": "<YOUR_SAP_HANA_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector requires the `hdbcli` library to connect to SAP HANA databases.

```
hdbcli==2.25.29
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses basic database authentication with a `username` and `password`. These credentials are specified in the configuration file and used to establish a connection to the SAP HANA database.

To obtain credentials for your SAP HANA database:

1. Contact your database administrator for the relevant access credentials.
2. Ensure your database user has appropriate read permissions to the required tables.

Refer to `create_sap_hana_database_connection()` function for implementation details.

## Pagination

The connector uses a batch-based approach for data retrieval rather than traditional API pagination. Data is fetched in configurable batches (default: 1000 rows) using the `cursor.fetchmany()` method.

This approach accomplishes the following:

1. Prevents memory overflow when handling large datasets.
2. Enables incremental processing of data without loading the entire result set
3. Allows for checkpointing progress after each batch

Refer to the `fetch_and_upsert()` function, specifically the `cursor.fetchmany(batch_size)` implementation.

## Data handling

The connector processes data as follows:

1. Defines a schema for the `transactions` table with specific data types.
2. Fetches data incrementally based on the `created_at` field.
3. Processes data in configurable batch sizes (default: 1000 rows). This prevents memory overflow errors when syncing large datasets.
4. Uses checkpoints to save progress during synchronization. This allows the connector to resume from the last synced record in case of interruptions.

Refer to `fetch_and_upsert()` function for data processing implementation.

## Error handling

The connector implements error handling in several key areas:

- Configuration validation ensures all required parameters are present.
- Connection errors are caught and raised with meaningful error messages.
- Resource cleanup is handled properly even if exceptions occur

## Tables created

This connector replicates the `sales` table which contains sales information with the following schema:

- `transaction_id` (STRING) - Primary key
- `created_at` (NAIVE_DATE) - The creation date of transaction

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.