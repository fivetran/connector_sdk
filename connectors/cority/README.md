# Cority Connector Example

## Connector overview

This connector syncs four user reports from a tenant of [Cority](https://www.cority.com/), an EHS and quality management SaaS platform. Cority does not expose a REST API for these reports; the connector talks to Cority's `MRWPService.svc` SOAP service using `zeep`. Reports are fetched with offset-based pagination via `GetUserReportResultsNonPreview` so that reports larger than the 100,000-row system cap (`GetSystemSettingReportWriterMaxRecords`) sync correctly.

The connector ships with hardcoded report definitions for four destination tables: `safetyfindings` (Cority `userReportId` 1474), `absences` (1475), `ohcases` (1476), and `incidents` (1477). Each report's column map is captured from `GetUserReportById` metadata and stored in the `__COLUMN_MAPS` constant in `connector.py`.

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
fivetran init <project-path> --template connectors/cority
```

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Calls Cority's `MRWPService.svc` SOAP API via `zeep`.
- Authenticates once per sync with `ValidateUser` and reuses the returned session key for every report.
- Server-side paginated fetch via `GetUserReportResultsNonPreview` with `startRow`/`maxRow`, sized at 25,000 rows per page to stay well under the 100,000-row Cority system cap.
- Driven by `GetUserReportResultsCount` so the connector knows the exact stopping offset before paging.
- Four destination tables hardcoded with per-report primary key and column maps derived from `GetUserReportById` metadata.
- Resumable mid-sync: each successfully-committed page advances `state["<table>_offset"]`; an interrupted sync resumes at that offset on the next run.
- Retries transient SOAP transport errors and Server/Receiver SOAP faults with exponential backoff; fails fast on Sender/Client faults including authentication failures.

## Configuration file

The connector reads three keys from `configuration.json`:

```
{
  "base_url": "<YOUR_CORITY_TENANT_WSDL_URL>",
  "username": "<YOUR_CORITY_API_USERNAME>",
  "password": "<YOUR_CORITY_API_PASSWORD>"
}
```

The `base_url` value must be the full WSDL URL, for example `https://<tenant>.cority.com/WebService/MRWPService.svc?singleWsdl`.

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values. When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector depends on `zeep` for SOAP. `requirements.txt`:

```
zeep==4.3.2
```

> Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses Cority's session-key authentication. The connector calls `ValidateUser(username, password)` once per sync and supplies the returned key as the `key` argument to every subsequent SOAP call (refer to `def authenticate` in `connector.py`).

To set up authentication:

1. In Cority, create or identify an integration user that has read access to the four user reports listed in the Tables created section.
2. Record the username and password for that user.
3. Provide the credentials in `configuration.json` as `username` and `password`.

## Pagination

The connector uses Cority's built-in offset-based pagination via `GetUserReportResultsNonPreview` (refer to `def fetch_page` in `connector.py`). Before paging, `def fetch_total_rows` calls `GetUserReportResultsCount` to determine the total number of rows. The connector then iterates pages of `__PAGE_SIZE = 25000` rows by passing `startRow` (zero-based, inclusive) and `maxRow` (zero-based, inclusive) until `offset >= total`. After each page, the connector calls `op.upsert` for every row, advances `state["<table>_offset"]`, and calls `op.checkpoint`. If a sync is interrupted, the next run resumes at the last committed offset.

## Data handling

`GetUserReportResultsNonPreview` returns each row as an array of strings whose index corresponds to the `Sequence` declared by the report's field metadata. The connector keeps a hardcoded per-report `Sequence -> destination column name` map in `__COLUMN_MAPS` (refer to `def map_row` in `connector.py`). Sequence values are 0-indexed for some reports (for example, 1474) and 1-indexed for others (for example, 1477); sparse sequences are handled correctly because the map keys explicitly enumerate each populated index.

The connector declares only the primary key column type in `def schema`. All other columns are inferred by Fivetran from the upsert payloads, allowing the destination table to evolve if Cority adjusts a report.

A row whose primary-key value is missing or empty is skipped to avoid Fivetran rejecting the upsert; the skip count is logged at the page level.

## Error handling

- Transient transport errors (`requests.Timeout`, `requests.ConnectionError`, and zeep `TransportError`) trigger exponential backoff retries up to five attempts, capped at 60 seconds (refer to `def call_with_retry` in `connector.py`).
- SOAP `Fault` exceptions are inspected by their fault code: codes containing `server` or `receiver` are treated as transient and retried; other codes (typically Sender/Client faults including authentication failures) are re-raised immediately.
- Configuration validation runs at the start of every sync and raises `ValueError` with a specific field name on missing or empty values (refer to `def validate_configuration`).
- An empty session key from `ValidateUser` is treated as an authentication failure and aborts the sync.

## Tables created

The connector creates four destination tables, one per Cority user report. The table name and primary key are captured below; the row count column lists the population observed during connector development on 2026-05-01.

| Table name | userReportId | Cority report name | Primary key column | Approximate rows |
|---|---|---|---|---|
| `safetyfindings` | 1474 | Qlik Safety Findings | `finding_id` | 52,691 |
| `absences` | 1475 | Qlik Absences | `day_counts_with_status_id` | 78,903 |
| `ohcases` | 1476 | Qlik Cases | `case_no` | 95,054 |
| `incidents` | 1477 | Qlik Incidents | `safety_incident_id` | 143,745 |

Non-primary-key columns are inferred by Fivetran from upsert payloads. The full list of columns per table is the value set of the corresponding entry in `__COLUMN_MAPS` in `connector.py`.

## Additional considerations

- This connector performs a full refresh on every sync. It does not currently track deletes; rows removed in Cority will remain in the destination until a manual reset. Date-based incremental sync via `MedgateUserReportCriteria` is feasible but is intentionally out of scope for this example.
- Column maps are captured from `GetUserReportById` and hardcoded in `connector.py`. If Cority modifies a report's field set or sequence ordering, update `__COLUMN_MAPS` accordingly.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
