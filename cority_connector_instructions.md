# Cority connector — build instructions

This document describes what the connector does and the design choices made
during the build. It reflects what was actually built (not the original
yearly-chunking idea, which the SOAP API made unnecessary).

## Goal

Fivetran Connector SDK example that pulls four user-reports from Cority's
SOAP API into Snowflake via a Fivetran connection. The connector code is
destination-agnostic; Snowflake is configured on the Fivetran destination
side.

## Target location in repo

`connectors/cority/` — full rewrite from scratch, replacing the previous files.

## API surface

- **Protocol:** SOAP (WSDL).
- **WSDL URL:** `base_url` in `connectors/cority/configuration.json`
  (a `MRWPService.svc?singleWsdl` endpoint on the tenant).
- **Auth:** `ValidateUser(username, password)` returns a session key reused
  for every subsequent call. `username` and `password` come from
  `configuration.json`.
- **Client library:** `zeep==4.3.2` (4.2.x imports `cgi`, removed in Py 3.13).
- **Row cap per response:** 100,000, returned by
  `GetSystemSettingReportWriterMaxRecords`. Anything larger must paginate.

> Before any commit: replace real credentials in `configuration.json` with
> `<YOUR_CORITY_USERNAME>` / `<YOUR_CORITY_PASSWORD>` placeholders. Treat the
> earlier leaked password as compromised and rotate it.

## Reports synced

Each report becomes one Fivetran table.

| Table name        | userReportId | Cority report name    | Approx rows |
|-------------------|--------------|------------------------|-------------|
| `safetyfindings`  | 1474         | Qlik Safety Findings   | 52,691      |
| `absences`        | 1475         | Qlik Absences          | 78,903      |
| `ohcases`         | 1476         | Qlik Cases             | 95,054      |
| `incidents`       | 1477         | Qlik Incidents         | 143,745     |

Only `incidents` exceeds the 100,000-row cap, so all four use the same
pagination code path.

## Sync strategy (what was actually built)

**Server-side pagination via `GetUserReportResultsNonPreview`.** Discovery
showed the WSDL exposes operations the previous connector ignored:

- `GetUserReportResultsCount` — returns the row count without pulling rows.
- `GetUserReportResultsNonPreview` — returns rows in chunks via `startRow`
  (zero-based, inclusive) and `maxRow` (zero-based, inclusive). The response
  is `[{"string": [val_at_seq_0, val_at_seq_1, ...]}]` where each row's
  array index equals the `Sequence` declared by the report's metadata.
- `GetUserReportById` — returns the report's `Fields` array
  (`Sequence`, `AliasName`, `FieldName`) used to build column maps.

The connector flow per report:

1. `GetUserReportResultsCount` for the total.
2. Loop `startRow = 0, __PAGE_SIZE, 2*__PAGE_SIZE, …` until `>= total`,
   calling `GetUserReportResultsNonPreview` with
   `maxRow = min(start + __PAGE_SIZE - 1, total - 1)`.
3. Per page: `op.upsert` each row, advance `state["<table>_offset"]`,
   `op.checkpoint`. A mid-sync interruption resumes at the last committed
   offset; a clean run resets the offset to 0.

`__PAGE_SIZE = 25_000` to leave headroom under the 100k cap.

> The original instruction said "incremental by date, one year at a time."
> That assumed the API had no pagination. It does, so yearly chunking is
> unnecessary and was not built.

## Primary keys

No row-level natural Id is exposed. Each report's PK is hardcoded to the
metadata column that uniquely identifies a row at the report's grain:

| Table             | Primary key column           | Cority `FieldName`           |
|-------------------|------------------------------|------------------------------|
| `safetyfindings`  | `finding_id`                 | `Action.Finding.Id`          |
| `absences`        | `day_counts_with_status_id`  | `AbsenceDayCountsWithStatus.Id` |
| `ohcases`         | `case_no`                    | `CaseMaster.CaseNo`          |
| `incidents`       | `safety_incident_id`         | `SafetyIncident.Id`          |

Rows missing a PK value are skipped (logged) rather than upserted.

## Column naming convention

Per-report `Sequence -> destination column` maps live in `__COLUMN_MAPS`
in `connector.py`. Columns are derived from `AliasName` snake-cased, with
the table-entity prefix stripped to keep names compact:

- `safetyfindings`: strip `action_` (kept `action_id`, `action_taken`).
- `absences`: strip `absence_` (kept `absence_id` to avoid bare `id`).
- `ohcases`: strip `case_master_`. Also fixed `osharecordable` to
  `osha_recordable`.
- `incidents`: strip `incident_` / `safety_incident_` where redundant
  (kept `safety_incident_id` as PK to avoid bare `id`).

If Cority adds or rearranges fields, update `__COLUMN_MAPS` in `connector.py`.

## Configuration

### `connectors/cority/configuration.json` (runtime)

```json
{
  "base_url": "<CORITY_WSDL_URL>",
  "username": "<YOUR_CORITY_USERNAME>",
  "password": "<YOUR_CORITY_PASSWORD>"
}
```

No `start_date` key — the connector full-refreshes every sync; there is no
incremental cursor in this version.

### `.env` (deploy-time only — never read by `connector.py`)

Used by the deploy script / `fivetran deploy`, not by the connector runtime:

- `Fivetran_API_Key`
- `Fivetran_API_Secret`
- `Fivetran_Destination`  (Snowflake destination name)
- `Connection_Name`

## Error handling

- Transient transport errors (`requests.Timeout`, `requests.ConnectionError`,
  zeep `TransportError`) and SOAP `Server`/`Receiver` faults: exponential
  backoff, 3–5 attempts, 60 s cap.
- `Sender`/`Client` SOAP faults (auth failures, malformed args): re-raise
  immediately.

## Dependencies (`requirements.txt`)

```
zeep==4.3.2
```

`fivetran_connector_sdk` and `requests` are pre-installed in the runtime
and must not be declared.

## Out of scope (this pass)

- Date-based incremental sync via `MedgateUserReportCriteria`. Feasible —
  the criteria struct accepts `FieldName` + `Value` + `Value2` for ranges —
  but not built; the connector full-refreshes.
- Delete tracking. The previous connector tracked PKs across runs and
  emitted `op.delete` for missing rows. Removed for simplicity in this pass.
- Schema discovery at runtime. Column maps are hardcoded from metadata
  captured during build. Cority schema changes require a code update.

## Coding standards

Follow `CLAUDE.md`, `.github/instructions/python-review.instructions.md`,
and the `andrej-karpathy-skills:karpathy-guidelines` skill (surface
assumptions, simplicity first, surgical changes, verifiable success).
