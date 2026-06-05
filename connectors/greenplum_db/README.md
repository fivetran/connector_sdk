# Greenplum DB Connector Example

## Connector overview

This connector example demonstrates how to fetch data from a Greenplum database and upsert it into destination table using Fivetran Connector SDK. It establishes a connection to a Greenplum database using the `psycopg2` library, executes SQL queries to retrieve data, and streams the results in a memory-efficient manner using server-side cursors.

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
fivetran init <project-path> --template connectors/greenplum_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connects to Greenplum database using `psycopg2`
- Uses server-side cursors for memory-efficient streaming of large result sets
- Supports incremental syncs with checkpointing
- Automatically converts datetime objects to ISO format
- Validates required configuration parameters

## Configuration file

The connector requires the following configuration parameters to connect to your Greenplum database:

```
{
  "HOST": "<YOUR_GREENPLUM_DATABASE_HOST>",
  "PORT": "<YOUR_GREENPLUM_DATABASE_PORT>",
  "DATABASE": "<YOUR_GREENPLUM_DATABASE_NAME>",
  "USERNAME": "<YOUR_GREENPLUM_DATABASE_USERNAME>",
  "PASSWORD": "<YOUR_GREENPLUM_DATABASE_PASSWORD>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the following Python libraries:

```
psycopg2-binary
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector authenticates with the Greenplum database using username and password credentials provided in the configuration file. Make sure the user has appropriate permissions to read from the tables or views you intend to query.

## Data handling

The connector performs the following data handling operations:  
- Executes SQL queries to fetch data from Greenplum (refer to `GreenplumClient.upsert_data()`)
- Uses server-side cursors to stream large results without loading everything into memory
- Converts datetime objects to ISO format for proper serialization (refer to `GreenplumClient.convert_datetime_to_iso()`)
- Checkpoints progress based on the "`query_start`" field to support incremental syncing

## Error handling

The connector includes error handling for database connection issues. In the `GreenplumClient.connect()` method, connection errors are caught and raised. 

The connector also performs validation of required configuration parameters in the `schema()` function to ensure all necessary credentials are provided before attempting to connect to the database.

## Tables created
The connector creates a single table,  `SAMPLE_TABLE`, in the destination:

```json
{
    "table": "sample_table",
    "primary_key": ["datid"],
    "columns": {
        "datid": "INT",
        "query_start": "UTC_DATETIME"
    }
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.