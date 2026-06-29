# Redshift Large Data Volume Example Connector

## Connector overview
This example connector demonstrates how to sync large tables from Amazon Redshift efficiently by using the Connector SDK. The connector follows best practices for high-volume ingestion scenarios using Connector SDK. It implements optimized data extraction techniques, including parallel processing and incremental loading, to handle large datasets effectively.


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
fivetran init <project-path> --template connectors/redshift/large_data_volume
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Incremental sync via `replication_key` with ordered SQL queries.
- Automatic schema detection from the source schema.
- Automatic replication key inference based on column semantic types.
- Supports both full and incremental syncs, with an option for complete resyncs.
- Large tables with incremental syncs support chunking of the data to optimize memory usage on the server and client sides.
- Periodic checkpointing every `CHECKPOINT_EVERY_ROWS`
- Parallel execution governed by `max_parallel_workers`
- Connection pooling to reduce overhead during parallel query execution
- Graceful fallback to complete resync when no suitable replication key is found


## Configuration file
The configuration file (`configuration.json`) contains the necessary parameters to connect to Amazon Redshift. The content of this file is as follows:

```json
{
  "redshift_host": "<YOUR_REDSHIFT_HOST>",
  "redshift_port": "<YOUR_REDSHIFT_PORT>",
  "redshift_database": "<YOUR_REDSHIFT_DATABASE>",
  "redshift_user": "<YOUR_REDSHIFT_USER>",
  "redshift_password": "<YOUR_REDSHIFT_PASSWORD>",
  "redshift_schema": "<YOUR_REDSHIFT_SCHEMA>",
  "batch_size": "<YOUR_BATCH_SIZE_FOR_FETCHING_DATA>",
  "auto_schema_detection": "<ENABLE_OR_DISABLE_AUTO_SCHEMA_DETECTION>",
  "enable_complete_resync": "<ENABLE_OR_DISABLE_FULL_RESYNC_DURING_EACH_SYNC>",
  "max_parallel_workers": "<NUMBER_OF_PARALLEL_WORKERS>"
}
```
The parameters include:
- `redshift_host`: The hostname of the Redshift cluster.
- `redshift_port`: The port number for the Redshift cluster.
- `redshift_database`: The name of the Redshift database to connect to.
- `redshift_user`: The username for authenticating with Redshift.
- `redshift_password`: The password for the Redshift user.
- `redshift_schema`: The schema within the Redshift database to extract data from.
- `batch_size`: The number of rows to fetch in each batch during data extraction.
- `auto_schema_detection`: A boolean flag to enable or disable automatic schema detection. To enable automatic schema detection, set this parameter to `true`. To pass the source schema manually using the `table_spec.py`, set this parameter to `false`.
- `enable_complete_resync`: A boolean flag that defines whether each sync is a [full re-sync](https://fivetran.com/docs/using-fivetran/features#fullresync).
- `max_parallel_workers`: The maximum number of parallel workers to use for data extraction. We recommend setting this value between 2 and 4. Setting it too high may lead to potential performance degradation.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The connector requires the following packages, which should be listed in the `requirements.txt` file:

```
redshift_connector
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector uses username and password authentication to connect to the Redshift database. The credentials are provided in the `configuration.json` file. Ensure that the Redshift user has the necessary permissions to read data from the specified schema and tables.


## Pagination
The connector handles large datasets by implementing batch fetching. The `batch_size` parameter in the `configuration.json` file determines the number of rows fetched in each batch. This approach helps manage memory usage and improves performance when dealing with large tables.


## Data handling
The connector uses the `redshift_connector` library to connect to the Redshift database and execute SQL queries. It retrieves data in batches, processes each batch, and sends it for ingestion. The connector also supports incremental loading by using a `replication_key` to track changes in the source data.

The steps involved in data handling include:
1. Establishing a connection to the Redshift database using the provided credentials.
2. Retrieving the list of tables from the specified schema.
3. For each table, determining the appropriate `replication_key` for incremental loading.
4. Fetching data in batches based on the `batch_size` parameter.
5. For tables with a `replication_key` and incremental sync strategy, fetching the data in chunks is also supported to optimize memory usage.
6. Processing each batch and sending it for ingestion.
7. Periodically checkpointing the state to ensure data integrity and support resumption in case of failures.

The connector also implements parallel processing to speed up data extraction. The `max_parallel_workers` parameter controls the number of concurrent workers used for fetching data from multiple tables simultaneously.


## Error handling
The connector includes robust error handling mechanisms to manage potential issues during data extraction and processing.


## Tables created
The connector creates tables in the destination based on the source schema. The table names and structures are derived from the Redshift schema specified in the `configuration.json` file. The connector creates a table for each table found in the specified Redshift schema with the name format `<schema_name>_<table_name>`.

The connector automatically detects the schema of each table and creates corresponding tables in the destination with appropriate data types. If automatic schema detection is disabled, the connector uses the schema defined in the `table_spec.py` file.


## Additional files
The connector includes the following additional files:
- `table_spec.py`: This file defines the schema for each table in the Redshift database. It is used when automatic schema detection is disabled. You can customize this file to specify the exact schema for each table, including column names and data types.
- `redshift_client.py`: This file contains the logic for connecting to the Redshift database and executing SQL queries. It encapsulates the connection handling, query execution, and data fetching logic.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
