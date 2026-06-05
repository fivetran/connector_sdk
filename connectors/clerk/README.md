# Clerk API Connector

## Connector overview
This connector integrates with the Clerk API to synchronize user data into your destination. It fetches user records from Clerk and flattens nested data structures into normalized tables, making it easy to analyze user data in your data warehouse. The connector supports incremental sync using timestamp-based cursors and handles pagination automatically to process large datasets efficiently.

Clerk is a user authentication and management platform that provides APIs for managing users, their email addresses, phone numbers, social accounts, and authentication methods. 

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
fivetran init <project-path> --template connectors/clerk
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Fetches user data from the Clerk API `/v1/users` endpoint
- Incremental sync support using `created_at_after` parameter to fetch only newly created users (defaults to January 1, 1990 for the initial sync)
- Automatic pagination using offset-based pagination (limit and offset parameters)
- Flattens nested JSON objects into the main table using underscore notation
- Separates nested arrays into child tables with foreign key relationships
- Implements retry logic with exponential backoff for transient errors
- Checkpoints state every 1000 records to enable resumption on interruption
- Memory-efficient processing using generator functions to avoid loading all the data at once

## Configuration file
The configuration file contains the API key required to authenticate with the Clerk API.

```json
{
  "api_key": "<YOUR_CLERK_API_KEY>"
}
```

Configuration parameters:
- `api_key` (required): Your Clerk API secret key.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector example uses standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses API key authentication with bearer tokens. The API key is passed in the `Authorization` header as `Bearer <api_key>`.

To obtain your Clerk API key:
1. Log in to your [Clerk Dashboard](https://dashboard.clerk.com/).
2. Navigate to **API Keys** in the left sidebar.
3. Make a note of your secret key (starts with `sk_test_` for test mode or `sk_live_` for production).
4. Add this key to your `configuration.json` file.

## Pagination

The connector implements offset-based pagination using the Clerk API's `limit` and `offset` query parameters.

Pagination details:
- Page size: 100 records per request (configurable via `__PAGE_LIMIT` constant)
- The connector starts with `offset=0` and increments by the page size after each request
- Pagination continues until the API returns fewer records than the page size
- For incremental syncs, the `created_at_after` parameter is added to fetch only new records

The pagination logic is implemented as a generator function to avoid loading all data into memory at once, which is critical for handling large datasets efficiently.

## Data handling

The connector processes Clerk user data with sophisticated flattening logic to normalize nested structures.

Main table flattening:
- Nested JSON objects (e.g., `public_metadata`, `private_metadata`) are flattened into the main `USER` table using underscore notation
- Example: `public_metadata.role` becomes the `public_metadata_role` column
- Deeply nested objects use multiple underscores: `verification.error.code` becomes `verification_error_code`

Array flattening:
- Nested arrays are extracted into separate child tables with foreign key relationships
- Each child table includes a `user_id` column linking back to the parent user
- Arrays within child records (e.g., `linked_to`, `backup_codes`) are converted to JSON strings

Data type inference:
- Only primary keys are explicitly defined in the schema
- Fivetran automatically infers data types for all other columns based on the data

## Error handling
The connector implements comprehensive error handling with retry logic.

Retry strategy:
- Maximum 3 retry attempts for transient errors (configurable via `__MAX_RETRIES`)
- Exponential backoff strategy is to wait `2^attempt` seconds between retries
- Rate limit (429) errors trigger automatic retry with exponential backoff
- Server errors (5xx) are retried, client errors (4xx) fail immediately

Error categories:
- Configuration errors: Validated at the start of sync with clear error messages
- HTTP errors: Caught and retried based on status code
- Network errors: Retried with exponential backoff
- Data processing errors: Wrapped in RuntimeError with descriptive messages

Timeout: All API requests have a 30-second timeout to prevent hanging connections.

## Tables created
The connector creates 8 tables in your destination:

| Table Name | Type | Primary Key | Foreign Key | Description |
|------------|------|-------------|-------------|-------------|
| `USER` | Main table | `id` | - | Contains flattened user profile data including metadata fields. Nested objects like `public_metadata`, `private_metadata`, `unsafe_metadata` are flattened into columns. |
| `USER_EMAIL_ADDRESS` | Child table | `id` | `user_id` → `USER.id` | Contains email addresses with verification details. |
| `USER_PHONE_NUMBER` | Child table | `id` | `user_id` → `USER.id` | Contains phone numbers with verification and 2FA configuration. |
| `USER_WEB3_WALLET` | Child table | `id` | `user_id` → `USER.id` | Contains Web3 wallet addresses with verification details. |
| `USER_PASSKEY` | Child table | `id` | `user_id` → `USER.id` | Contains passkey authentication methods. |
| `USER_EXTERNAL_ACCOUNT` | Child table | `id` | `user_id` → `USER.id` | Contains OAuth social login accounts (Google, GitHub, etc.). |
| `USER_SAML_ACCOUNT` | Child table | `id` | `user_id` → `USER.id` | Contains SAML SSO account information. |
| `USER_ENTERPRISE_ACCOUNT` | Child table | `id` | `user_id` → `USER.id` | Contains enterprise account connections and SSO details. |

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
