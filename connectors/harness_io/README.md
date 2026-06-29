# Harness.io API Connector Example


## Connector overview
This connector extracts data from `Harness.io` API and loads it into a destination using Fivetran's Connector SDK. It fetches information about user projects, connector catalog, budgets, and performance metrics like mean time to resolution, making it useful for organizations that want to analyze their Harness.io data alongside other business data.


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
fivetran init <project-path> --template connectors/harness_io
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Retrieval of user projects with detailed information
- Access to the connectors catalog
- Budget information extraction
- Performance metrics including mean time to resolution
- Support for pagination when retrieving large datasets
- Checkpointing to ensure sync process can resume from the correct position


## Configuration file
The connector requires the following configuration parameters:

```
{
  "api_token": "<YOUR_HARNESS_API_TOKEN>",
  "account_id": "<YOUR_HARNESS_ACCOUNT_ID>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector example uses the standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication with the Harness.io API is performed using an API token and account ID. These credentials are passed in the request headers and query parameters respectively.

1. Obtain your API token from your Harness.io account settings.
2. Identify your account ID from your Harness.io account.
3. Add these credentials to your `configuration.json` file.


## Pagination
Refer to the `upsert_all_projects_for_user function()` method for pagination implementation. The connector handles pagination for the projects endpoint by doing the following:

- Setting an initial page size (100 records)
- Making API requests in a loop until all pages are processed
- Using the `pageToken` returned in the API response to fetch the next page
- Breaking the loop when no more pages are available


## Data handling
The connector defines a schema for four destination tables and processes data used for each table in the following way:

- User projects: Data is fetched from the `/ng/api/projects` endpoint. The connector processes each project record, flattening nested structures before upserting to the destination table.

- Connectors catalog: Data is retrieved from the `/ng/api/connectors/catalogue` endpoint. Each connector category and its associated connectors are upserted to the destination.

- Budgets: The connector fetches budget data from the `/ccm/api/budgets` endpoint and upserts each budget record.

- Mean time to resolution: Performance metrics are obtained via a `POST` request to the `/v1/dora/mean-time` endpoint with specific filter parameters.


## Error handling
Refer to the `validate_configuration()` function. The connector validates that all required configuration parameters are present before attempting to connect to the API. If any required parameters are missing, the connector raises a `ValueError` with a descriptive message.


## Tables created
The connector creates the following tables:

- `USER_PROJECTS`: Information about projects the user has access to.
The schema for this table is as follows:

    ```json
    {
      "table": "user_projects",
      "primary_key": ["identifier"],
      "columns": {
        "identifier": "STRING",
        "modules": "JSON",
        "tags": "JSON"
      }
    }
    ```

- `CONNECTORS`: Information about available connectors. The schema for this table is as follows:
  
    ```json
    {
      "table": "connectors",
      "primary_key": ["category"],
      "columns": {
        "category": "STRING",
        "connectors": "JSON"
      }
    }
    ```

- `BUDGETS`: Budget information. The schema for this table is as follows:

    ```json
    {
      "table": "budgets",
      "primary_key": ["uuid"],
      "columns": {
        "uuid": "STRING",
        "scope": "JSON"
      }
    }
    ```
  
- `MEAN_TIME_TO_RESOLUTION`: Performance metrics related to mean time to resolution. The schema for this table is as follows:
  
    ```json
    {
      "table": "mean_time_to_resolution",
      "columns": {
        "unit": "STRING"
      }
    }
    ```


## Additional files
- `harness_api.py` – Contains the `HarnessAPI` class that handles communication with the Harness.io API. It provides methods for making `GET` and `POST` requests, building URLs with query parameters, and managing authentication headers.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
