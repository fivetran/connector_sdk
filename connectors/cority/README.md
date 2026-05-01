# Cority Connector Example

## Connector overview

This connector syncs Cority user reports from a tenant of [Cority](https://www.cority.com/), an EHS and quality management SaaS platform. Cority does not expose a REST API for user reports; instead, it provides a SOAP service at `MRWPService.svc?singleWsdl` whose `GetUserReportResults` method returns a saved user report's full row set in a single response. The connector is configuration-driven and supports any number of user reports — each entry in the `reports` configuration list maps a Cority `userReportId` to a destination table and translates the generic `Field0..FieldN` columns to semantic names.

The first table shipped with this example is the absence report (`userReportId = 1389`), but new reports can be added by editing `configuration.json` only — no code changes required.

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
- Authenticates once per sync using `ValidateUser` and reuses the returned session key for every report.
- Supports any number of user reports through the `reports` configuration list — no code changes needed to add a new report.
- Maps Cority's generic `Field0..FieldN` columns to semantic destination column names per report.
- Performs full-refresh syncs and emits `op.delete` for primary keys that disappear between runs, so deletions in Cority propagate to the destination as `_fivetran_deleted = true`.
- Retries transient SOAP transport and Server-side Fault errors with exponential backoff; fails fast on auth and client-side faults.

## Configuration file

The connector reads four keys from `configuration.json`:

```
{
  "base_url": "<YOUR_CORITY_TENANT_BASE_URL_E_G_HTTPS_JBSSA_CORITY_COM>",
  "username": "<YOUR_CORITY_API_USERNAME>",
  "password": "<YOUR_CORITY_API_PASSWORD>",
  "reports": "<JSON_STRING_LIST_OF_REPORT_DESCRIPTORS>"
}
```

The `reports` value is a JSON-encoded string (Fivetran configuration values must be strings) that decodes to a list of report descriptors. Example for the absence report:

```json
[
  {
    "report_id": 1389,
    "table_name": "absence_report",
    "primary_key": ["absence_day_counts_id"],
    "field_map": {
      "Field0": "absence_status",
      "Field1": "start_date",
      "Field2": "percent_full_duty",
      "Field3": "case_no",
      "Field4": "employee_number",
      "Field5": "absence_id",
      "Field6": "absence_day_counts_id",
      "Field7": "lost_days",
      "Field8": "lost_restricted_date",
      "Field9": "restricted_days"
    }
  }
]
```

Each descriptor has four required keys:

- `report_id` – the integer Cority `userReportId`.
- `table_name` – the destination table name in `snake_case`.
- `primary_key` – an ordered list of destination column names that uniquely identify a row. At least one entry is required and every PK column must also appear in `field_map` values.
- `field_map` – mapping from Cority source field name (`Field0`, `Field1`, …) to destination column name. Use `snake_case` to keep Snowflake identifiers unquoted and case-insensitive.

To add a new report, append a new descriptor to the list and redeploy.

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors), ensure the `configuration.json` file has placeholder values. When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector depends on `zeep` for SOAP. `requirements.txt`:

```
zeep==4.2.1
```

> Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses Cority's session-key authentication. The connector calls `ValidateUser(username, password)` once per sync and supplies the returned key as the `key` argument to every subsequent `GetUserReportResults` call (refer to the `authenticate()` function in `connector.py`).

To set up authentication:

1. In Cority, create or identify an integration user that has read access to the user reports you intend to sync.
2. Record the username and password for that user.
3. Provide the credentials in `configuration.json` as `username` and `password`.

## Data handling

The connector retrieves each configured user report by calling `GetUserReportResults` and then deserializes the SOAP response with `zeep.helpers.serialize_object` (refer to `fetch_report()`). Because Cority can wrap report rows in varying parent elements depending on the report definition, the connector walks the deserialized response and locates the first list of dicts whose entries expose `Field<N>` keys (refer to `find_row_collection()`). Each raw row's `Field<N>` keys are then translated to the semantic destination columns declared in the `field_map` (refer to `map_row()`), and the result is sent to Fivetran via `op.upsert`. All non-primary-key columns are passed through with their inferred types so that adding new fields in Cority does not require a schema update.

## Error handling

- Transient transport errors (`requests.Timeout`, `requests.ConnectionError`, and zeep `TransportError`) trigger exponential backoff retries up to five attempts, capped at 60 seconds (refer to `call_soap_with_retry()`).
- SOAP `Fault` exceptions are inspected by their fault code: codes containing `Server` or `Receiver` are treated as transient and retried; other codes (typically client-side, including authentication failures) are re-raised immediately.
- Configuration validation runs at the start of every sync and raises `ValueError` with a specific field name on missing or malformed values (refer to `validate_configuration()`).
- An empty session key from `ValidateUser` is treated as an authentication failure and aborts the sync.

## Tables created

The connector creates one destination table per entry in the `reports` configuration list. The table name and primary key are taken directly from the descriptor; non-PK columns are inferred from the data.

For the example absence-report descriptor shown above, the connector creates:

```json
{
  "table": "absence_report",
  "primary_key": ["absence_day_counts_id"],
  "columns": {
    "absence_day_counts_id": "STRING"
  }
}
```

Additional columns (`absence_status`, `start_date`, `percent_full_duty`, `case_no`, `employee_number`, `absence_id`, `lost_days`, `lost_restricted_date`, `restricted_days`) are created with inferred types on first sync.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
