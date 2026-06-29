# InfluxDB Connector Example

## Connector overview

This connector enables data synchronization from InfluxDB using Fivetran Connector SDK. It connects to an InfluxDB instance, retrieves time-series data from a specified measurement, and syncs it into destination. The connector supports incremental syncs by tracking the last synced timestamp, ensuring that only new or updated data is processed in subsequent syncs. 

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
fivetran init <project-path> --template connectors/influx_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Streams data from InfluxDB using Apache Arrow Flight for efficient data processing
- Supports incremental syncs based on timestamp tracking
- Handles timezone conversion for timestamp data
- Memory-efficient processing of large datasets through data chunking

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "token": "<YOUR_INFLUXDB_TOKEN>",
  "org": "<YOUR_INFLUXDB_ORGANIZATION_NAME>",
  "hostname": "<YOUR_INFLUXDB_HOST_URL>",
  "database": "<YOUR_INFLUXDB_DATABASE_NAME>",
  "measurement": "<YOUR_INFLUXDB_MEASUREMENT_NAME>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the `influxdb3_python` package to connect to InfluxDB.

The connector uses the following packages, which are specified in the `requirements.txt` file:

```
influxdb3_python
pandas
```

`influxdb3_python` is a lightweight Python client for InfluxDB 3.x, which provides an easy way to interact with InfluxDB instances. It supports basic operations like querying and writing data.

`pandas` is used for data manipulation and analysis, particularly for handling the nanosecond timestamps returned by InfluxDB. It is required in the production environment for safely converting microseconds to datetime.datetime.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses token-based authentication with InfluxDB. You'll need to:  
1. Log into your InfluxDB dashboard.
2. Navigate to `Data` > `API Tokens`.
3. Create a new token with appropriate read permissions.
4. Copy the token to the token field in your `configuration.json` file.

Refer to the `create_influx_client` function in the `connector.py` file for implementation details.

## Data handling

The connector processes data as follows:  
- Executes a SQL query against the specified InfluxDB measurement
- Processes the returned data in chunks using Apache Arrow RecordBatch
- Maintains state to track progress and support incremental syncs

Refer to the `execute_query_and_upsert` and `upsert_record_batch` functions in the `connector.py` file for implementation details.

## Error handling

The connector implements error handling in several ways:  
- Configuration validation to ensure all required parameters are provided
- Exception handling during client connection
- Runtime error raising with descriptive messages
- Logging at various levels (info, warning) for operational visibility

## Tables Created

The connector creates a single table named `census_table` with the following schema:  

```json
{
    "table": "census_table",
    "primary_key": [],
    "columns": {
        "ants": "INT",
        "bees": "INT",
        "location": "STRING",
        "time": "STRING"
    }
}
```

Refer to the `schema` function in the `connector.py` file for implementation details.

The data in `census_table` looks like this:

| ants | bees | location | time                        | _fivetran_id | _fivetran_synced              | _fivetran_deleted |
|------|------|----------|-----------------------------|--------------|-------------------------------|-------------------|
| 30   | 23   | Klamath  | 2025-06-02T06:36:58.190260Z | 965658472    | 2025-06-02 06:36:58.102 +0000 | false             |
| 32   | 28   | Portland | 2025-06-02T09:13:00.610947Z | 742608174    | 2025-06-02 06:36:58.119 +0000 | false             |


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
