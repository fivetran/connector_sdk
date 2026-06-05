# Netlify Connector Example

## Connector overview

This connector demonstrates how to fetch data from the Netlify API, including sites, deploys, forms, and form submissions. It implements incremental syncing based on timestamps and uses checkpointing to ensure reliable data synchronization. The connector is designed to handle pagination for large datasets and includes retry logic with exponential backoff for transient errors.

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
fivetran init <project-path> --template connectors/netlify
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental data synchronization based on timestamp fields
- Pagination support for large datasets
- Memory-efficient on-demand processing of sites without loading all data into memory
- Retry logic with exponential backoff for transient API errors
- Checkpointing strategy to enable resume capability
- Flattening of nested JSON objects for simplified table structures
- Support for multiple Netlify API endpoints: sites, deploys, forms, and form submissions

## Configuration file

The connector requires the following configuration parameter:

```json
{
  "api_token": "<YOUR_NETLIFY_API_TOKEN>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require any additional Python packages beyond those provided by the Fivetran SDK runtime.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses personal access token (PAT) authentication to access the Netlify API. The token is provided in the configuration file and included in the Authorization header of all API requests.

To obtain your Netlify API token:

1. Log in to your [Netlify account](https://app.netlify.com).
2. Navigate to **Applications** > **Personal access tokens**.
3. Select **New access token**.
4. Enter a descriptive name for the token.
5. Optionally, select **Allow access to my SAML-based Netlify team** if needed.
6. Select an expiration date for security purposes.
7. Select **Generate token**.
8. Make a note of the token to your clipboard and add it to the `configuration.json` file.
9. Store the token securely as you won't be able to access it again.

## Pagination

The connector implements pagination for endpoints that return large datasets. Refer to the `fetch_paginated_data()` function for the pagination implementation. The connector uses page-based pagination with a default limit of 100 records per page. The pagination loop continues until an empty response is received, indicating no more data is available.

## Data handling

The connector processes data from four main Netlify API endpoints and transforms the nested JSON responses into flattened table structures suitable for data warehousing. Single-level nested objects are flattened into the parent table, while complex nested structures like form fields and submission data are stored as JSON strings.

The processing logic is organized into focused helper functions to maintain code clarity:
- `process_site_child_records()` - Orchestrates pagination through sites and their child records
- `process_child_records_for_site()` - Handles both paginated and non-paginated child record endpoints
- `process_child_records_batch()` - Processes individual batches of records with checkpointing

Refer to the flattening functions `flatten_site_record()`, `flatten_deploy_record()`, `flatten_form_record()`, and `flatten_submission_record()` for more details.

## Error handling

The connector implements comprehensive error handling with retry logic for transient errors. It retries failed requests up to 3 times with exponential backoff starting at 1 second. HTTP status codes 429, 500, 502, 503, and 504 are treated as retryable errors, while 404 responses return empty results and other 4xx errors fail immediately.

The error handling logic is organized into focused helper functions:
- `make_api_request_with_retry()` - Main entry point for API requests with retry logic
- `handle_api_response()` - Processes HTTP responses and determines the appropriate action
- `handle_retryable_error()` - Implements exponential backoff for transient failures
- `handle_request_exception()` - Manages network-level exceptions with retry logic

## Tables created

The connector creates four tables in the destination:

### SITE

| Column         | Data Type    | Primary Key |
|----------------|--------------|-------------|
| id             | STRING       | Yes         |
| site_id        | STRING       | No          |
| name           | STRING       | No          |
| custom_domain  | STRING       | No          |
| url            | STRING       | No          |
| admin_url      | STRING       | No          |
| screenshot_url | STRING       | No          |
| created_at     | UTC_DATETIME | No          |
| updated_at     | UTC_DATETIME | No          |
| user_id        | STRING       | No          |
| state          | STRING       | No          |
| plan           | STRING       | No          |
| account_name   | STRING       | No          |
| account_slug   | STRING       | No          |

### DEPLOY

| Column         | Data Type    | Primary Key |
|----------------|--------------|-------------|
| id             | STRING       | Yes         |
| site_id        | STRING       | No          |
| name           | STRING       | No          |
| state          | STRING       | No          |
| url            | STRING       | No          |
| deploy_url     | STRING       | No          |
| admin_url      | STRING       | No          |
| created_at     | UTC_DATETIME | No          |
| updated_at     | UTC_DATETIME | No          |
| published_at   | UTC_DATETIME | No          |
| branch         | STRING       | No          |
| commit_ref     | STRING       | No          |
| commit_url     | STRING       | No          |
| context        | STRING       | No          |
| review_url     | STRING       | No          |
| screenshot_url | STRING       | No          |

### FORM

| Column           | Data Type    | Primary Key |
|------------------|--------------|-------------|
| id               | STRING       | Yes         |
| site_id          | STRING       | No          |
| name             | STRING       | No          |
| paths            | STRING       | No          |
| submission_count | INTEGER      | No          |
| fields           | STRING       | No          |
| created_at       | UTC_DATETIME | No          |

### SUBMISSION

| Column     | Data Type    | Primary Key |
|------------|--------------|-------------|
| id         | STRING       | Yes         |
| number     | INTEGER      | No          |
| email      | STRING       | No          |
| name       | STRING       | No          |
| first_name | STRING       | No          |
| last_name  | STRING       | No          |
| company    | STRING       | No          |
| summary    | STRING       | No          |
| body       | STRING       | No          |
| data       | JSON         | No          |
| created_at | UTC_DATETIME | No          |
| site_url   | STRING       | No          |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
