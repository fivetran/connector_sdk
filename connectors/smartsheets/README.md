# Smartsheet API Connector Example

## Connector overview
This connector demonstrates how to sync row-level data from Smartsheet using the Fivetran Connector SDK, and the Smartsheet [Sheets API](https://smartsheet.redoc.ly/tag/sheets) and [Reports API](https://smartsheet.redoc.ly/tag/reports). It retrieves rows from sheets and reports, dynamically maps columns using column IDs, and emits those rows to destination tables.


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
fivetran init <project-path> --template connectors/smartsheets
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Incremental syncs using `rowsModifiedSince` to sync only updated rows
- Dynamic schema based on column headers, mapping `columnId` to column names
- Optional row-level metadata fields like `rowNumber`, `createdAt`, and `modifiedAt`
- Configurable authentication and sheet selection
- Multiple sheets and reports in a single connector instance
- Uses `op.upsert()` for each row and checkpoints with the current sync timestamp


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "api_token": "<YOUR_SMARTSHEET_API_TOKEN>",
  "sheets": "<SHEET_ID_1>:<SHEET_NAME_1>,<SHEET_ID_2>:<SHEET_NAME_2>",
  "reports": "<REPORT_ID_1>:<REPORT_NAME_1>,<REPORT_ID_2>:<REPORT_NAME_2>",
  "requests_per_minute": "<60>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled via a Bearer token using the Authorization header.


## Pagination
Pagination is not currently implemented in this example.


## Data handling
- Each row in the Smartsheet is returned as a dictionary of cell values, mapped to the correct column titles.
- Column names are dynamically derived from the `columns` array in the API response.
- Null or empty cells are ignored.


## Error handling
- API errors are surfaced using `requests.raise_for_status()`.
- Any failure in authentication, network, or sheet access will raise an exception.
- You can extend this with `try/except` blocks and log warnings for partial errors.


## Tables created
The connector creates a `SMARTSHEET_TABLE_NAME` table:

```json
{
  "table": "smartsheet_table_name",
  "primary_key": ["id"],
  "columns": {
    "id": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.