# Keycloak Connector Example

## Connector overview

Keycloak is an open-source identity and access management solution that provides authentication, authorization, and user management capabilities. This connector syncs identity and access management data from the Keycloak Admin API to enable security analytics, compliance reporting, and user behavior analysis. It extracts users, groups, roles, clients, authentication events, and admin events from a Keycloak realm and delivers them to your destination through Fivetran, enabling organizations to centralize their IAM data for security monitoring, compliance auditing, user lifecycle analytics, and multi-tenant SaaS operations.

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
fivetran init <project-path> --template connectors/keycloak
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Syncs users with attributes, required actions, and realm roles
- Extracts groups with member relationships
- Retrieves realm roles and OAuth clients
- Captures authentication events for security monitoring
- Tracks admin events for compliance auditing
- Implements incremental sync using timestamp-based checkpointing
- Handles pagination for large datasets with checkpointing every 100 records
- Automatic token refresh for long-running syncs
- Creates breakout tables for one-to-many and many-to-many relationships
- Flattens nested JSON objects for efficient querying

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "keycloak_url": "<YOUR_KEYCLOAK_SERVER_URL>",
  "realm": "<YOUR_KEYCLOAK_REALM>",
  "client_id": "<YOUR_CLIENT_ID>",
  "client_secret": "<YOUR_CLIENT_SECRET>",
  "sync_events": "<TRUE_OR_FALSE_DEFAULT_TRUE>",
  "start_date": "<START_DATE_YYYY_MM_DD_DEFAULT_30_DAYS_AGO>"
}
```

Configuration parameters:
- `keycloak_url` - Base URL of your Keycloak server (e.g., https://keycloak.example.com or http://localhost:8080 for local development)
- `realm` - Keycloak realm name to sync data from (e.g., master, production, or your custom realm)
- `client_id` - OAuth2 client ID for service account authentication
- `client_secret` - OAuth2 client secret for service account authentication
- `sync_events` - String value "true" or "false" to enable/disable event syncing (default: "true")
- `start_date` - Start date for incremental event sync in YYYY-MM-DD format (e.g., 2024-01-01). If not specified, defaults to 30 days ago from the current date

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require any additional Python packages beyond the Fivetran Connector SDK. The [requirements.txt](requirements.txt) file is empty as all necessary dependencies are pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses the OAuth2 Client Credentials grant type to authenticate with the Keycloak Admin API. A dedicated service account with specific view permissions is required.

To set up authentication:

1. Log in to your Keycloak Admin Console (e.g., http://localhost:8080/admin).
2. Navigate to **Clients** and click **Create client**.
3. Set **Client ID** to a descriptive name (e.g., fivetran_connector).
4. Set **Client Protocol** to OpenID Connect.
5. Click **Next**.
6. Enable **Client authentication**.
7. Enable **Service accounts roles**.
8. Disable **Standard flow** and **Direct access grants**.
9. Click **Save**.
10. Go to the **Credentials** tab.
11. Copy the **Client Secret** and add it to your `configuration.json` file.
12. Go to the **Service account roles** tab.
13. Click **Assign role** and filter by clients.
14. Select **realm-management** client.
15. Assign the following roles: view-users, view-events, view-realm, view-clients.
16. Click **Assign**.

The connector uses these credentials to obtain access tokens via the `/realms/{realm}/protocol/openid-connect/token` endpoint and automatically refreshes tokens as they expire during sync operations.

## Pagination

The connector implements pagination using Keycloak's `first` and `max` query parameters. Each API endpoint is queried in batches of 100 records to prevent memory overflow and enable efficient incremental syncing.

The pagination logic processes each page immediately upon retrieval, upserting records to the destination and checkpointing state after every 100 records. This ensures that if the sync is interrupted, it can resume from the last successful checkpoint without reprocessing data.

For APIs that do not support pagination (such as roles and some event endpoints), the connector fetches all available data in a single request and processes it in memory-efficient batches.

## Data handling

The connector processes Keycloak data as follows:

- User records - Flattens nested `access` object fields into parent table columns, creates breakout tables for `attributes`, `realmRoles`, and `requiredActions` arrays
- Group records - Stores group metadata in parent table, creates breakout table for group member relationships
- Event records - Converts millisecond timestamps to ISO 8601 format, generates synthetic IDs from timestamp, type, user ID, session ID, and client ID
- Admin event records - Flattens `authDetails` nested object into parent table columns, generates synthetic IDs from timestamp, operation type, resource type, and resource path

All data types are automatically inferred by Fivetran based on the actual values encountered during sync. Only primary keys are explicitly defined in the schema to enable proper upsert behavior.

## Error handling

The connector implements comprehensive error handling with the following strategies:

- Retry logic with exponential backoff - Retries transient errors (HTTP 429, 500, 502, 503, 504) up to 3 times with delays of 1s, 2s, and 4s
- Token expiration handling - Monitors token expiration time and automatically refreshes tokens between table syncs
- Specific exception handling - Catches `requests.exceptions.RequestException` for network errors and provides detailed logging
- Graceful degradation - If optional resources like events or admin-events are unavailable, the connector logs warnings and continues with other tables
- Authentication failures - Immediately fails on HTTP 401 (invalid token) and HTTP 403 (insufficient permissions) with actionable error messages

All errors are logged using the Fivetran SDK logging framework with appropriate severity levels (warning for retryable errors, error for fatal errors).

## Tables created

The connector creates the following tables in your destination:

### user

Main table containing Keycloak user data with flattened access fields.

Primary key: `id`

| Column | Description |
|--------|-------------|
| id | Unique identifier for the user |
| username | Username for authentication |
| email | User's email address |
| first_name | User's first name |
| last_name | User's last name |
| enabled | Whether the user account is enabled |
| created_timestamp | When the user was created |
| access_manage_group_membership | Permission to manage group membership |
| access_view | Permission to view user details |
| access_map_roles | Permission to map roles |
| access_impersonate | Permission to impersonate user |
| access_manage | Permission to manage user |

### user_attribute

Breakout table for user attributes (key-value pairs).

Primary key: `user_id`, `attribute_key`, `attribute_value`

| Column | Description |
|--------|-------------|
| user_id | Foreign key to the user table |
| attribute_key | Name of the attribute |
| attribute_value | Value of the attribute |

### user_realm_role

Breakout table for user realm role assignments.

Primary key: `user_id`, `role_name`

| Column | Description |
|--------|-------------|
| user_id | Foreign key to the user table |
| role_name | Name of the assigned realm role |

### user_required_action

Breakout table for user required actions.

Primary key: `user_id`, `required_action`

| Column | Description |
|--------|-------------|
| user_id | Foreign key to the user table |
| required_action | Action required from the user (e.g., VERIFY_EMAIL, UPDATE_PASSWORD) |

### group

Table containing Keycloak group data.

Primary key: `id`

| Column | Description |
|--------|-------------|
| id | Unique identifier for the group |
| name | Name of the group |
| path | Full path of the group in the hierarchy |

### group_member

Breakout table for group membership relationships.

Primary key: `group_id`, `user_id`

| Column | Description |
|--------|-------------|
| group_id | Foreign key to the group table |
| user_id | Foreign key to the user table |

### role

Table containing realm roles.

Primary key: `id`

| Column | Description |
|--------|-------------|
| id | Unique identifier for the role |
| name | Name of the role |
| description | Description of the role |
| composite | Whether this is a composite role |
| client_role | Whether this is a client-specific role |

### client

Table containing OAuth/OIDC client applications.

Primary key: `id`

| Column | Description |
|--------|-------------|
| id | Unique identifier for the client |
| client_id | Client ID used in OAuth flows |
| name | Display name of the client |
| description | Description of the client application |
| enabled | Whether the client is enabled |
| public_client | Whether this is a public client |
| protocol | Authentication protocol (e.g., openid-connect) |
| base_url | Base URL of the client application |

### event

Table containing authentication events.

Primary key: `id`

| Column | Description |
|--------|-------------|
| id | Unique identifier for the event (composite: timestamp + type + user_id + session_id + client_id) |
| time | When the event occurred |
| type | Type of authentication event (e.g., LOGIN, LOGOUT, LOGIN_ERROR) |
| user_id | ID of the user associated with the event |
| session_id | Session identifier |
| ip_address | IP address of the client |
| client_id | ID of the client application |

### admin_event

Table containing administrative events for audit trails.

Primary key: `id`

| Column | Description |
|--------|-------------|
| id | Unique identifier for the admin event (composite: timestamp + operation_type + resource_type + resource_path) |
| time | When the admin event occurred |
| operation_type | Type of operation (CREATE, UPDATE, DELETE, ACTION) |
| resource_type | Type of resource modified (USER, GROUP, ROLE, CLIENT, etc.) |
| resource_path | Path to the modified resource |
| auth_realm_id | Realm ID of the authenticated admin |
| auth_client_id | Client ID used by the admin |
| auth_user_id | User ID of the admin who performed the action |

## Additional files

The connector does not require any additional files beyond those included in this directory.
## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
