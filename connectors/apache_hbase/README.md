# Apache HBase Connector Example

## Connector overview

This connector shows how to sync data from Apache HBase databases using Fivetran Connector SDK. It enables extraction of data from HBase tables and synchronization to your destination using `happybase` and `thrift`. The connector supports incremental updates based on timestamps, allowing efficient data transfer.

## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/apache_hbase
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connects to Apache HBase databases using the `happybase` and `thrift` python libraries.
- Supports incremental data sync using timestamp-based filtering.
- Efficiently processes large datasets with batched streaming using `happybase`.
- Handles error recovery with detailed logging.
- Checkpoints progress to enable resumable syncs.

## Configuration file

The connector requires the following configuration parameters: 

```
{
  "hostname": "<YOUR_HBASE_HOSTNAME>",
  "port": "<YOUR_HBASE_PORT>",
  "table_name": "<YOUR_HBASE_TABLE_NAME>", 
  "column_family": "<YOUR_HBASE_COLUMN_FAMILY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector requires the happybase library to communicate with Apache HBase:

```
happybase==1.2.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses direct connection to the `HBase` server through the specified `hostname` and `port`. Ensure that your HBase instance is properly configured to accept connections from the connector's runtime environment. If your HBase instance requires additional authentication, you may need to modify the connection logic in the `create_hbase_connection` function.

## Pagination

The connector handles large datasets efficiently using happybase's native scanning capabilities. The `scan()` method in `happybase.Table` is the primary way to stream rows from HBase using a Thrift-based client. It allows to retrieve data row-by-row in an efficient and memory-friendly manner, particularly suited for large datasets.

Refer to the `execute_query_and_upsert` function, which implements batched data retrieval with the `batch_size` parameter along with `scan()` to control the chunk size for data transfer. This helps balance performance and memory usage. The data is internally buffered but exposed row-by-row.

## Data handling


The connector processes data from HBase in the following way:  
- Creates a connection to the HBase server using the `happybase` library.
- Scans the specified table with a filter based on the `created_at` timestamp.
- Decodes and transforms each row into a structured format
- Upserts the data into the destination table
- Updates the state with the latest `created_at` timestamp for incremental syncs

## Error handling

The connector implements error handling at multiple levels:  
- Connection errors: Captured in the `create_hbase_connection` function, raising a descriptive RuntimeError
- Data processing errors: The `execute_query_and_upsert` function uses try-except blocks to handle missing columns in row data, logging warnings and continuing execution without failing the entire sync

## Tables Created


The connector creates one table:  
- profile_table

The schema of the created table is as follows:

```
{
    "table": "profile_table",
    "primary_key": ["id"],
    "columns": {
        "id": "STRING",
        "created_at": "UTC_DATETIME",
    },
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
