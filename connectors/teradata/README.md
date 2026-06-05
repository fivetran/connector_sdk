# Teradata Vantage Connector Example

## Connector overview
This connector demonstrates how to use the Fivetran Connector SDK to extract data from a Teradata Vantage database using the `teradatasql` Python library. It fetches employee records from a specified table, incrementally syncs new records based on the `JoiningDate`, and upserts them into a destination table.

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
fivetran init <project-path> --template connectors/teradata
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to Teradata Vantage using `teradatasql`
- Incremental sync based on `JoiningDate`
- Batch data fetching to optimize memory usage

## Configuration file
The connector uses a configuration file to specify connection details and table information.

```json
{
  "teradata_host": "<YOUR_TERADATA_HOST>",
  "teradata_user": "<YOUR_TERADATA_USER>",
  "teradata_password": "<YOUR_TERADATA_PASSWORD>",
  "teradata_database": "<YOUR_TERADATA_DATABASE>",
  "teradata_table": "<YOUR_TERADATA_TABLE>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The `requirements.txt` file specifies the Python libraries required by the connector. This connector uses the following library:

```
teradatasql
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector authenticates to Teradata Vantage using username and password credentials provided in the configuration file. Obtain these credentials from your Teradata administrator.


## Pagination
Data is fetched in batches using the fetchmany method with a configurable batch size (`__BATCH_SIZE`).
Refer to method `fetch_and_upsert_data(cursor, configuration, state)`.


## Data handling
- Data is selected from the source table where `JoiningDate` is greater than the last synced value.
- Each row is converted to a dictionary and upserted into the destination table.
- The state is updated with the latest `JoiningDate` after each batch.
Refer to method `fetch_and_upsert_data(cursor, configuration, state)`.


## Error handling
- Configuration validation raises a `ValueError` if required keys are missing.
- Connection errors raise a `ConnectionError`.
- All exceptions during update are caught and re-raised as `RuntimeError`.
- Database connections and cursors are closed in a `finally` block.

## Tables created
- `EMPLOYEE`: Contains columns `EmployeeID` (INT, primary key) and `JoiningDate` (NAIVE_DATE).

The destination table schema is as follows:

```json
{
  "table": "Employee",
  "primary_key": ["EmployeeID"],
  "columns": {
    "EmployeeID": "INT",
    "JoiningDate": "NAIVE_DATE",
    "full_name": "STRING",
    "city": "STRING"
  }
}
```

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
