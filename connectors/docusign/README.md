# Docusign eSignature Connector Example

## Connector overview

This connector extracts data from the Docusign eSignature API. It is designed to sync key objects related to the electronic signature process, including envelopes, recipients, documents (including their binary content), audit events, and templates. The extracted data can be used in a destination to enable analytics for Sales, Legal, Operations, and other teams tracking contract lifecycles, signature status, and compliance.

## Contributor

This example was contributed by [Arpit Kumar Khatri](https://github.com/ArpitKhatri1). The connector was developed as part of the [AI Accelerate](https://ai-accelerate.devpost.com/) hackathon.

## Requirements

  - [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
  - Operating system:
      - Windows: 10 or later (64-bit only)
      - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86\_64])
      - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86\_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/docusign
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

  - Extracts core Docusign resources such as envelopes and templates and their related child objects.
  - Incremental sync based on timestamp tracking.
  - Pagination and performance: uses offset-based pagination with sensible batch sizes to efficiently iterate large result sets.
  - Resiliency and partial-failure handling: per-envelope sub-resource failures are logged and skipped so a single broken item does not stop the entire sync.


## Configuration file

The configuration for this connector is defined in `configuration.json`.

```json
{
  "access_token": "<YOUR_DOCUSIGN_OAUTH_ACCESS_TOKEN>",
  "base_url": "<YOUR_DOCUSIGN_API_BASE_URL>",
  "account_id": "<YOUR_DOCUSIGN_ACCOUNT_ID>"
}
```
Configuration parameters:
  - access_token (required) - The OAuth2 access token for authenticating with the Docusign API.
  - base_url (required) - The base URL for the Docusign API (e.g., `https://demo.docusign.net/restapi` for demo or `https://na3.docusign.net/restapi` for production).
  - account_id (required) - The Account ID for your Docusign account.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses the `requests` library, which is pre-installed in the Fivetran environment. No additional libraries are required, so the `requirements.txt` file can be empty.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector authenticates using an OAuth2 bearer token. The token is provided in `configuration.json` and used in the `get_docusign_headers` function to create the required `Authorization` header for all API requests.

To obtain credentials:
1.  Configure an OAuth integration within your Docusign account (e.g., using JWT Grant or Authorization Code Grant).
2.  Generate a valid `access_token`.
3.  Find your `account_id` and correct `base_url` (e.g., `demo.docusign.net` or `na3.docusign.net`) from your Docusign Admin panel.
4.  Add these three values to the `configuration.json` file.

## Pagination

Pagination is implemented for the two main API endpoints: `envelopes` and `templates`.

Both functions use an offset-based pagination strategy. They send requests in a `while True` loop with a `count` of 100 and increment the `start_position` parameter by the number of records received in the previous call. The loop terminates when the API returns fewer records than the requested count, indicating the last page has been reached.

## Data handling

Data is processed within the `update` function and its various `fetch_*` helper functions.

- Schema: The connector schema, including all tables and their primary keys, is defined in the `schema` function.
- Type conversion: All data values are explicitly converted to strings (e.g., `str(envelope.get("status", ""))`) before being passed to `op.upsert` to ensure compatibility with the destination warehouse.
- Data flattening: For the `audit_events` table, the nested `eventFields` array from the API response is flattened into top-level columns in the destination table.
- Binary data: The `fetch_document_content` function downloads the binary content of documents. To ensure stability and prevent memory usage issues, documents are first validated against the `__MAX_FILE_SIZE_BYTES` limit and are only processed if they fall below this threshold. In the `update` function , this content is then base64-encoded (`base64.b64encode`) and stored as a string in the `document_contents` table.
- State management: The connector uses `state.get("last_sync_time", ...)` to fetch data incrementally. At the end of a successful sync, it checkpoints the new state using `op.checkpoint(new_state)`.
- Sync duration: Sync duration scales linearly with envelope count × sub-resources (present in `_process_envelope` function) due to the connector's N+1 data extraction pattern.

## Error handling

- API request errors: The `make_api_request` function  uses `response.raise_for_status()` to automatically raise an exception for HTTP 4xx (client) or 5xx (server) errors.
- Resilient child object fetching: All functions that fetch data for a specific envelope (e.g., `fetch_audit_events`, `fetch_document_content`, `fetch_recipients_for_envelope`) are wrapped in `try...except` blocks. If an API call for one envelope's sub-resource fails, the error is logged using `log.warning` and an empty list or `None` is returned. This prevents a single failed document or recipient from stopping the entire sync.
- Global error handling: The entire `update` function is wrapped in a `try...except Exception as e` block. Any unhandled exception will be caught and raised as a `RuntimeError`, which signals to Fivetran that the sync has failed.

## Tables created

This connector creates the following tables in the destination, as defined in the `schema` function:

### ENVELOPES

  ```json
  {
    
  "table": "envelopes",
  "primary_key": [
    "envelope_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "status": "STRING",
    "sent_timestamp": "UTC_DATETIME",
    "completed_timestamp": "UTC_DATETIME",
    "created_timestamp": "UTC_DATETIME",
    "last_modified_timestamp": "UTC_DATETIME",
    "subject": "STRING",
    "expire_after": "STRING",
    "contract_cycle_time_hours": "DOUBLE",
    "conversion_status": "STRING"
  }
}
```

### RECIPIENTS

  ```json
  {
  "table": "recipients",
  "primary_key": [
    "envelope_id",
    "recipient_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "recipient_id": "STRING",
    "name": "STRING",
    "email": "STRING",
    "status": "STRING",
    "type": "STRING",
    "routing_order": "STRING"
  }
}
```

### ENHANCED_RECIPIENTS

  ```json
  {
  "table": "enhanced_recipients",
  "primary_key": [
    "envelope_id",
    "recipient_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "recipient_id": "STRING",
    "name": "STRING",
    "email": "STRING",
    "status": "STRING",
    "type": "STRING",
    "routing_order": "STRING",
    "declined_reason": "STRING",
    "sent_timestamp": "UTC_DATETIME",
    "signed_timestamp": "UTC_DATETIME"
  }
}
```

### AUDIT_EVENTS
  
  ```json
  {
  "table": "audit_events",
  "primary_key": [
    "envelope_id",
    "event_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "event_id": "STRING",
    "logtime": "UTC_DATETIME",
    "action": "STRING",
    "message": "STRING",
    "username": "STRING",
    "source": "STRING"
  }
}
```

### ENVELOPE_NOTIFICATIONS
  
  ```json
  {
  "table": "envelope_notifications",
  "primary_key": [
    "envelope_id",
    "notification_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "notification_id": "STRING",
    "notification_type": "STRING",
    "scheduled_date": "UTC_DATETIME",
    "sent_date": "UTC_DATETIME"
  }
}
```

### DOCUMENTS

  ```json
  {
  "table": "documents",
  "primary_key": [
    "envelope_id",
    "document_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "document_id": "STRING",
    "name": "STRING",
    "type": "STRING",
    "pages": "STRING"
  }
}
```

### DOCUMENT_CONTENTS

  ```json
  {
  "table": "document_contents",
  "primary_key": [
    "envelope_id",
    "document_id"
  ],
  "columns": {
    "envelope_id": "STRING",
    "document_id": "STRING",
    "content_base64": "STRING"
  }
}
```

### TEMPLATES

  ```json
  {
  "table": "templates",
  "primary_key": [
    "template_id"
  ],
  "columns": {
    "template_id": "STRING",
    "name": "STRING",
    "description": "STRING",
    "created_timestamp": "UTC_DATETIME",
    "last_modified_timestamp": "UTC_DATETIME",
    "shared": "BOOLEAN"
  }
}
```

### CUSTOM_FIELDS
  
  ```json
  {
  "table": "custom_fields",
  "primary_key": [
    "envelope_id",
    "field_name"
  ],
  "columns": {
    "envelope_id": "STRING",
    "field_name": "STRING",
    "value": "STRING",
    "type": "STRING"
  }
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
