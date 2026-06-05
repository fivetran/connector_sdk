# Snipe-IT Asset Management Connector Example

## Connector overview

This connector demonstrates how to integrate Snipe-IT Asset Management data with Fivetran using the Connector SDK. Snipe-IT is an open-source IT asset management system that helps organizations track hardware, licenses, accessories, and other IT assets. This connector fetches data from the Snipe-IT REST API and syncs it to your destination warehouse, enabling comprehensive analytics and reporting on your asset inventory. The connector supports incremental syncing based on updated timestamps and implements proper pagination and error handling to ensure reliable data delivery.

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
fivetran init <project-path> --template connectors/snipeitapp
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental syncing based on `updated_at` timestamps for efficient data updates
- Automatic pagination handling for large datasets with configurable page sizes
- Retry logic with exponential backoff for transient API failures
- Flattening of nested JSON objects for simplified table structures
- Support for multiple critical asset management tables
- Regular checkpointing to ensure resumability in case of interruptions
- Bearer token authentication for secure API access

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "api_token": "<YOUR_SNIPE_IT_BEARER_TOKEN>",
  "base_url": "<YOUR_SNIPEIT_BASE_URL>"
}
```

### Configuration parameters

- `api_token` (required): Your Snipe-IT Bearer token for API authentication with read permissions for all resources you want to sync
- `base_url` (required): The base URL of your Snipe-IT instance (e.g., `https://your-snipeit-instance.com` for cloud or `http://localhost:8000` for self-hosted)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require any additional Python packages beyond the standard library and the pre-installed SDK packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses Bearer token authentication to access the Snipe-IT API (refer to the `fetch_page()` function). The API token is passed in the `Authorization` header with each request.

To obtain your API token:

1. Log in to your Snipe-IT instance as an administrator.
2. Navigate to your user profile settings.
3. Click **API Keys** or **Personal Access Tokens**.
4. Generate a new API token with appropriate permissions.
5. Copy the token and add it to your `configuration.json` file.
6. Ensure the token has read permissions for all resources you want to sync.

## Pagination

The connector implements offset-based pagination to handle large datasets efficiently (refer to the `sync_table()` function). Each API request fetches a configurable number of records (default 100) using the `limit` and `offset` parameters. The connector continues fetching pages until the API returns fewer records than the page size, indicating the end of the dataset. This approach ensures that all data is retrieved without loading entire datasets into memory.

## Data handling

The connector processes data from the Snipe-IT API in the following manner (refer to the `flatten_record()` function):

- Nested JSON objects are flattened into single-level dictionaries with underscore-separated keys (e.g., `model.name` becomes `model_name`)
- Arrays are converted to string representations as they should typically be handled in separate breakout tables
- Timestamp fields are extracted from nested objects (e.g., `updated_at.datetime` becomes the checkpoint timestamp)
- All records are upserted to destination tables, allowing for both inserts and updates
- Data types are inferred automatically by the SDK, with only primary keys explicitly defined in the schema

## Error handling

The connector implements comprehensive error-handling strategies (refer to the `fetch_page()` function):

- Retry logic with exponential backoff for transient errors (HTTP 429, 500, 502, 503, 504)
- Maximum of 3 retry attempts with delays of 2, 4, and 8 seconds
- Immediate failure for authentication errors (HTTP 401, 403) without retries
- Timeout handling for slow API responses with retry logic
- Connection error handling for network issues
- Detailed error logging at each failure point to aid in troubleshooting
- Checkpoint recovery ensures syncs can resume from the last successful state

## Tables created

The connector creates the following tables in your destination (refer to the `schema()` function):

| Table | Description | Primary Key | Key Columns |
|-------|-------------|-------------|-------------|
| hardware | Primary asset/hardware items tracked in Snipe-IT | `id` | `id`, `asset_tag`, `serial`, `name`, `model_id`, `model_name`, `status_label_id`, `status_label_name`, `category_id`, `category_name`, `manufacturer_id`, `manufacturer_name`, `supplier_id`, `location_id`, `location_name`, `created_at_datetime`, `updated_at_datetime`, `purchase_date_date`, `purchase_cost` |
| users | Users who can be assigned assets or manage the system | `id` | `id`, `username`, `email`, `first_name`, `last_name`, `employee_num`, `jobtitle`, `phone`, `department_id`, `department_name`, `company_id`, `company_name`, `activated`, `created_at_datetime`, `updated_at_datetime` |
| companies | Companies that own or are associated with assets | `id` | `id`, `name`, `phone`, `email`, `assets_count`, `licenses_count`, `accessories_count`, `users_count`, `created_at_datetime`, `updated_at_datetime` |
| locations | Physical locations where assets are deployed | `id` | `id`, `name`, `address`, `city`, `state`, `country`, `zip`, `assets_count`, `assigned_assets_count`, `users_count`, `created_at_datetime`, `updated_at_datetime` |
| categories | Categories for organizing different types of assets | `id` | `id`, `name`, `category_type`, `assets_count`, `accessories_count`, `consumables_count`, `created_at_datetime`, `updated_at_datetime` |
| manufacturers | Manufacturers of hardware assets | `id` | `id`, `name`, `url`, `support_url`, `support_phone`, `support_email`, `assets_count`, `created_at_datetime`, `updated_at_datetime` |
| suppliers | Suppliers from whom assets are purchased | `id` | `id`, `name`, `address`, `phone`, `email`, `contact`, `url`, `assets_count`, `licenses_count`, `created_at_datetime`, `updated_at_datetime` |
| models | Asset models that define specific hardware configurations | `id` | `id`, `name`, `model_number`, `manufacturer_id`, `manufacturer_name`, `category_id`, `category_name`, `eol`, `assets_count`, `created_at_datetime`, `updated_at_datetime` |
| status_labels | Status labels that indicate the current state of assets (e.g., Ready to Deploy, In Use, Broken) | `id` | `id`, `name`, `status_type`, `status_meta`, `assets_count`, `created_at_datetime`, `updated_at_datetime` |
| departments | Organizational departments to which users and assets can be assigned | `id` | `id`, `name`, `company_id`, `company_name`, `users_count`, `created_at_datetime`, `updated_at_datetime` |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
