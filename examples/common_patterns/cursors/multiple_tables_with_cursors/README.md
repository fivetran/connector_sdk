# Parent-Child Tables with Cursors Connector Example

## Connector overview
This connector demonstrates how to handle parent-child relationships between tables using incremental syncs with independent cursors per table. It simulates API calls for syncing company and department records and showcases how to manage per-entity cursors for nested data models.

Each company is incrementally synced based on its `updated_at` field, and for each company, the connector fetches and syncs its associated departments using a separate per-company cursor.

This example is intended for learning purposes and uses the [fivetran-api-playground](https://pypi.org/project/fivetran-api-playground/) package to mock the API responses locally. It is not meant for production use.


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
fivetran init <project-path> --template examples/common_patterns/cursors/multiple_tables_with_cursors
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates parent-child table syncs (company → department).
- Maintains independent cursors:
  - Global cursor for companies (company_cursor)
  - Per-company cursors for departments (department_cursor[company_id])
- Supports incremental loading with `updated_at` tracking.
- Includes checkpointing after every upserted record to ensure safe resumption.
- Simulates API calls and response handling using static mock data.


## Configuration file
No external configuration is required for this connector.

In a real-life implementation, you would include authentication tokens, API URLs, or pagination parameters in your `configuration.json`.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not use authentication.

In real-world scenarios, modify `get_api_response()` to add `Authorization` headers or include API keys in query parameters.


## Pagination
This example does not include pagination. In real-world APIs:
- Company and department data may be paginated.
- You would implement pagination in `fetch_companies()` and `fetch_departments_for_company()` using query parameters like limit, offset, or cursor tokens.


## Data handling
The connector processes data as follows:
- Initializes `company_cursor` and `department_cursor` from the last checkpointed state.
- Fetches companies updated since `company_cursor`.
- For each company:
  - Sync data via `op.upsert()` to the `COMPANY` table. 
  - Updates and checkpoints the new `company_cursor`.
- For each company, fetches its departments using its specific cursor.
- For each department:
  - Sync data via `op.upsert()` to the `DEPARTMENT` table. 
  - Updates and checkpoints the `department_cursor[company_id]`.

This approach ensures fine-grained incremental syncing for nested entities.


## Error handling
- All API calls log the request URL and parameters.
- In a real implementation, get_api_response() would raise exceptions on HTTP errors.
- Each checkpoint ensures partial progress is saved even if a later step fails.


## Tables created
The connector creates two tables:

`COMPANY`:

```
{
  "table": "company",
  "primary_key": ["company_id"],
  "columns": {
    "company_id": "STRING",
    "company_name": "STRING",
    "updatedAt": "UTC_DATETIME",
    "createdAt": "UTC_DATETIME"
  }
}
```

`DEPARTMENT`:

```
{
  "table": "department",
  "primary_key": ["department_id", "company_id"],
  "columns": {
    "department_id": "STRING",
    "company_id": "STRING",
    "department_name": "STRING",
    "updatedAt": "UTC_DATETIME",
    "createdAt": "UTC_DATETIME"
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.