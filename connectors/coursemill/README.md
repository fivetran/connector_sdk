# CourseMill LMS Connector Example

> Note: This connector is a draft that has not been validated through direct testing against a live API. It is intended as a starting point and example implementation that should be confirmed and tested before production use.

## Connector overview
This connector integrates with the CourseMill LMS v7.5 REST API to synchronize learning management data into your destination. It fetches organizational structures, users, courses, curricula, sessions, prerequisites, enrollments, transcripts, and certificates, providing a complete view of LMS activity. Transcripts support incremental sync via date-range filtering; all other tables use full-pull with upsert deduplication.

CourseMill is a learning management system (LMS) that provides APIs for managing courses, student enrollments, curriculum assignments, training transcripts, and certifications.

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
fivetran init <project-path> --template connectors/coursemill
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Syncs 10 tables covering the full CourseMill LMS data model
- Incremental sync for transcripts using date-range filtering (`startDate`/`endDate` parameters)
- Full-pull sync with upsert deduplication for all other tables
- Dependency-ordered sync: parent tables sync before child tables that depend on them
- Resume cursors for child-table iterations (sessions, prerequisites, enrollments, curriculum courses)
- Automatic camelCase to snake_case field name conversion
- JWT-based authentication with automatic re-authentication on 401 responses
- Periodic checkpointing every 500 records and after each table completion
- Retry logic with exponential backoff for transient errors (5xx, 429, timeouts)

## Configuration file
The configuration file contains the CourseMill instance URL and admin credentials.

```json
{
  "base_url": "<YOUR_COURSEMILL_BASE_URL>",
  "username": "<YOUR_ADMIN_USERNAME>",
  "password": "<YOUR_ADMIN_PASSWORD>"
}
```

Configuration parameters:
- `base_url` (required): The base URL of your CourseMill instance, including the context path (e.g., `https://yourinstance.coursemill.com/cm-server`).
- `username` (required): CourseMill admin username with API access.
- `password` (required): CourseMill admin password.

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector uses standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses JWT token-based authentication. The connector posts username and password to `POST /api/v1/auth` and receives a JWT token. The token is sent in subsequent requests via the `X-Auth-Token` header. If the API returns a new token in any response body, the connector automatically updates its cached token. On 401 responses, the connector re-authenticates and retries the request. Refer to `CoursemillClient.authenticate` and `CoursemillClient._request`.

To obtain credentials:
1. Log in to your CourseMill LMS instance as an administrator.
2. Ensure your admin account has API access permissions enabled.
3. Add your CourseMill base URL, username, and password to the `configuration.json` file.

## Pagination
The connector uses page-based pagination with a configurable page size (default: 200 records per page). Refer to `CoursemillClient.get_paginated`.

Pagination details:
- Parameters: zero-based `page` and `size` query parameters
- The connector starts at `page=0` and increments after each request
- Pagination stops when the response includes `"last": true`
- Single-object responses wrapped in a `data` key are handled as a special case

## Data handling
- All camelCase field names from the API are converted to snake_case. Refer to `_camel_to_snake` and `_clean_record`.
- Array and object fields (e.g., `personalInfoList`, `subOrgList`) are serialized as JSON strings. Refer to `_serialize_value`.
- Child tables (sessions, prerequisites, enrollments, curriculum courses) are fetched by iterating over parent records (courses or curricula).
- Resume cursors track the last processed parent ID so that interrupted child-table syncs can resume without re-processing. These cursors are cleared after each full table sync completes.
- Schema column types are inferred automatically by Fivetran from the data.

## Error handling
- Automatic retry with exponential backoff (up to 5 retries, max 30 seconds wait) for 5xx and 429 errors. Refer to `CoursemillClient._request`.
- Automatic re-authentication on 401 responses.
- Per-course child table errors (sessions, prerequisites, enrollments) are logged as warnings and do not halt the overall sync.
- Checkpoint state is saved after each table completion and every 500 records for large tables.

## Tables created

The connector creates 10 tables, synced in dependency order:

- `organizations` – Organizational units (primary key: `org_id`). Full sync.
- `users` – User and student records (primary key: `student_id`). Full sync.
- `courses` – Course catalog (primary key: `course_id`). Full sync.
- `curricula` – Learning paths and curriculum definitions (primary key: `curriculum_id`). Full sync.
- `curriculum_courses` – Curriculum-to-course relationships (primary key: `curriculum_id`, `course_id`). Full sync, derived from curriculum detail responses.
- `sessions` – Instructor-led training sessions per course (primary key: `session_id`). Full sync.
- `course_prerequisites` – Prerequisite relationships per course (primary key: `course_id`, `prerequisite_course_id`). Full sync.
- `enrollments` – Class roster data per course (primary key: `student_id`, `course_id`, `session_id`). Full sync.
- `transcripts` – Training completion records (primary key: `student_id`, `course_id`, `session_id`). Incremental sync by date range.
- `certificates` – Earned certificates (primary key: `student_id`, `course_id`, `curriculum_id`). Full sync.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
