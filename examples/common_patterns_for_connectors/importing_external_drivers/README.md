# MySQL Connector Using External Driver Installation

## Connector overview

This example demonstrates how to build a Fivetran connector that requires external system-level libraries, such as `libmysqlclient-dev`, by using an `installation.sh` script. It connects to a MySQL database, reads all records from a specified table, and upserts them into a destination table named `ORDERS`.


## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns_for_connectors/importing_external_drivers
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Reads all rows from a MySQL table via MySQLdb.
- Converts `datetime.date` values to string for compatibility.
- Performs upserts into the `ORDERS` table.
- Uses `op.checkpoint()` to track progress after each sync.
- Uses `installation.sh` to install native drivers.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_HOST>",
  "database": "<YOUR_DATABASE>",
  "user": "<YOUR_USER>",
  "password": "<YOUR_PASSWORD>",
  "port": "<YOUR_PORT>",
  "table_name": "<YOUR_TABLE_NAME>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
mysqlclient==2.0.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled using the `user` and `password` fields in your `configuration.json`, and passed to the MySQL connection function.


## Pagination
This example retrieves all rows in a single call. You can modify the query to support offset-based or key-based pagination for large datasets.


## Data handling
The connector reads the data from the configured `table_name` (assumed to match `ORDERS`). Each row is upserted into the destination.


## Error handling
- Configuration is validated at the start of the sync; missing fields raise a `ValueError`.
- Any errors during MySQL connection or query execution are caught and logged using `log.error()`.
- The connector re-raises critical errors after logging to ensure sync visibility and failure propagation.

## Tables created
The connector creates the `ORDERS` table:
```json
{
  "table": "orders",
  "primary_key": ["id"],
  "columns": {
    "id": "LONG",
    "title": "STRING",
    "name": "STRING",
    "city": "STRING",
    "mobile": "STRING",
    "datetime": "STRING"
  }
}
```


## Additional files
The connector uses `MySqldb` to connect to the MySQL database and retrieve data. The `MySqldb` requires an additional system package, `default-libmysqlclient-dev`, which contains MySQL database development files. The `drivers/installation.sh` script installs `MySqldb` dependencies files. The script updates the packages for Linux distributions and installs the `default-libmysqlclient-dev` package.
Additionally, it's worth noting that the `installation.sh` script accepts a `configuration.json` file as a parameter. This file can be leveraged to provide any required configurations during package installation.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.