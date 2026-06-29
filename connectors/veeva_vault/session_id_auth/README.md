# Veeva Vault Connector - Using Session Authentication Example

## Connector overview
This connector demonstrates how to sync all object types and their records from Veeva Vault using the Fivetran Connector SDK. It leverages the Vault Configuration API to dynamically retrieve schema information and uses VQL (Vault Query Language) to query and paginate through object records.

This example supports:
- Retrieving object metadata using the `Objecttype` endpoint.
- Constructing schema dynamically based on object structure.
- Executing paginated queries with `VQL`.
- Upserting object data into a destination table per object type.
- Incremental syncing via `modified_date__v` filtering.
- Handling Veeva’s burst rate limits.

See [Veeva Vault API documentation](https://developer.veevavault.com/api/19.3/) for endpoint details.


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
fivetran init <project-path> --template connectors/veeva_vault/session_id_auth
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Dynamically defines schema from `Objecttype` metadata.
- Queries records using `VQL` with optional `modified_date__v` filters.
- Supports paginated record sync via Vault’s `next_page` mechanism.
- Automatically flattens and serializes list fields.
- Handles burst limit throttling with cooldown periods.
- Uses `op.checkpoint()` to persist per-object sync cursors.


## Configuration file
The connector requires the following configuration parameters:

```json
{
    "username": "<YOUR_VEEVA_VAULT_USERNAME>",
    "password": "<YOUR_VEEVA_VAULT_PASSWORD>",
    "subdomain": "<YOUR_VEEVA_VAULT_SUBDOMAIN>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any additional Python packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector uses Session ID authentication. The process involves:

- Obtaining a session ID using username and password via the `/api/v24.2/auth` endpoint
- Including the session ID in the Authorization header for subsequent API calls
- Properly ending the session with a `DELETE` request to `/api/v24.2/session` when the sync is complete


## Pagination
Pagination is handled via:
- `next_page` in the responseDetails object
- URL rewriting logic based on Vault’s `/api/v24.2/` URL structure

Pagination continues until `next_page` is no longer returned.


## Data handling
- Each object (e.g., `document__v`, `country__c`) results in a separate destination table.
- Fields are flattened and list values are serialized as JSON strings.
- Syncs are incremental based on `modified_date__v` (tracked per object).


## Error handling
- Failed API responses raise errors with descriptive logs.
- Burst limit violations result in a 5-minute delay before retrying.
- Field flattening ensures no nested structures are lost during sync.
- Sync state is saved per object in the form: `{"document__v_cursor": "timestamp"}`.


## Tables created
The connector creates tables dynamically based on the object types defined in Veeva Vault. Each table corresponds to an object type and includes all fields defined in the `Objecttype` metadata.:

Here is an example of the `DOCUMENT__V` table structure for the `document__v` object type:

```json
{
  "table": "document__v",
  "primary_key": ["id"],
  "columns": "inferred from type_fields"
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.