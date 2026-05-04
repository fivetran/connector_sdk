"""This connector syncs four user reports from a Cority tenant via the MRWPService SOAP API.
It authenticates with username + password, then pages through each report with
GetUserReportResultsNonPreview using offset-based pagination so reports larger than the
100,000-row system cap sync correctly. The destination tables are absences, ohcases,
incidents, and safetyfindings. Each sync is a full refresh; mid-sync interruptions resume
at the last successfully-committed page offset.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# For reading the local configuration.json file during fivetran debug
import json

# For exponential backoff sleeps between SOAP retries
import time

# SOAP client used to talk to Cority's MRWPService.svc
import zeep

# Converts a zeep response object tree into plain Python dicts/lists
from zeep import helpers

# SOAP-level fault and transport errors raised by zeep
from zeep.exceptions import Fault, TransportError

# zeep delegates HTTP transport to requests, so transient network errors surface as requests exceptions
import requests as rq

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Maximum number of retry attempts for transient SOAP/transport failures
__MAX_RETRIES = 5

# Base delay in seconds; combined with exponential backoff capped at 60s
__BASE_DELAY_SECONDS = 1
__MAX_DELAY_SECONDS = 60

# Cority's GetSystemSettingReportWriterMaxRecords returns 100,000 on this tenant.
# We page well below that to leave headroom for slow responses and to keep individual
# SOAP calls bounded in memory.
__PAGE_SIZE = 25000

# Entity type accepted by every report in __REPORTS (verified via GetUserReportById metadata)
__ENTITY_TYPE = "DataTable"

# The four user reports this connector syncs. Table names match the user-provided spec
# (absences, ohcases, incidents, safetyfindings); primary-key columns were chosen from each
# report's metadata as the most granular identifier exposed by the underlying entity model.
__REPORTS = [
    {
        "userReportId": 1474,
        "table": "safetyfindings",
        "primary_key": "finding_id",
    },
    {
        "userReportId": 1475,
        "table": "absences",
        "primary_key": "day_counts_with_status_id",
    },
    {
        "userReportId": 1476,
        "table": "ohcases",
        "primary_key": "case_no",
    },
    {
        "userReportId": 1477,
        "table": "incidents",
        "primary_key": "safety_incident_id",
    },
]

# Per-report mapping from a row's value-array index (Sequence in Cority metadata)
# to the destination column name. GetUserReportResultsNonPreview returns each row as
# an array of strings indexed by Sequence; gaps are normal (some reports start at
# Sequence=0, others at Sequence=1; sparse sequences are also possible).
# Captured from GetUserReportById on 2026-05-01. Update if Cority modifies a report.
__COLUMN_MAPS = {
    1474: {
        0: "finding_id",
        1: "action_id",
        2: "created_date",
        3: "assigned_to",
        4: "organization_code",
        5: "organization",
        8: "action_taken",
        9: "root_cause",
        10: "finding_type",
        11: "corporate_initiative",
        12: "date_completed",
        13: "verified_date",
        14: "status",
        15: "type",
        16: "finding_detail",
        17: "group_number",
        18: "modified_date",
    },
    1475: {
        0: "status_description",
        1: "start_date",
        2: "percent_full_duty",
        3: "case_no",
        4: "employee_number",
        5: "absence_id",
        6: "day_counts_with_status_id",
        7: "lost_days",
        8: "lost_restricted_date",
        9: "restricted_days",
        10: "modified_date",
    },
    1476: {
        0: "case_no",
        1: "organization_code",
        2: "date_became_recordable",
        3: "case_category_description",
        4: "injury",
        5: "illness",
        6: "employee_date_of_hire",
        7: "employee_full_name",
        8: "employee_number",
        9: "date_injured",
        10: "osha_recordable",
        11: "priority_description",
        12: "part_of_body_description",
        13: "side_of_body_description",
        14: "line_out",
        15: "udfdt6",
        16: "date_reported",
        17: "date_reported_to_carrier",
        18: "description",
        19: "activity",
        20: "cause_of_injury_description",
        21: "completed_date",
        22: "udfdt2",
        23: "udfdt1",
        24: "udfdt3",
        25: "date_returned",
        26: "organization_description",
        27: "org_unit",
        28: "employee_job_position_description",
        29: "udflu4_description",
        30: "case_type_description",
        31: "time_injured",
        32: "time_reported",
        33: "time_work_began",
        34: "shift_code_description",
        35: "incident_contribute_condition_description",
        36: "incident_general_incident_number",
        37: "incident_classification_description",
        38: "udfflag5",
    },
    1477: {
        1: "safety_incident_id",
        2: "case_no",
        3: "employee",
        4: "date_sent_to_carrier",
        5: "injured_date",
        6: "date_reported",
        7: "personnel_area_code",
        8: "personnel_area_description",
        9: "location_toi",
        10: "organizational_unit",
        11: "osha_recordable",
        12: "recordable_date",
        13: "filed_date",
        14: "severe_injury_date",
        15: "severity_type",
        16: "position",
        17: "injury_illness",
        18: "specific_activity",
        19: "description_safety",
        20: "part_of_body",
        21: "how_occurred",
        22: "cause",
        23: "cause_of_injury",
        24: "reason_recordable",
        25: "hire_date",
        26: "shift",
        27: "priority_description",
        28: "line_out",
    },
}


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["base_url", "username", "password"]
    for key in required_configs:
        if not configuration.get(key):
            raise ValueError(f"Missing required configuration value: {key}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    validate_configuration(configuration)

    schemas = []
    for report in __REPORTS:
        pk = report["primary_key"]
        schemas.append(
            {
                "table": report["table"],
                "primary_key": [pk],
                # Only the PK column is explicitly typed. Non-PK columns are inferred from
                # upsert payloads so the destination table can evolve when Cority adjusts a
                # report definition without requiring a connector redeploy.
                "columns": {pk: "STRING"},
            }
        )
    return schemas


def build_soap_client(wsdl_url: str) -> zeep.Client:
    """
    Build a zeep SOAP client pointed at the tenant's MRWPService WSDL.
    Args:
        wsdl_url: Full WSDL URL, e.g. https://<tenant>.cority.com/WebService/MRWPService.svc?singleWsdl
    Returns:
        A configured zeep.Client instance.
    """
    log.info(f"Loading WSDL from {wsdl_url}")
    return zeep.Client(wsdl=wsdl_url)


def call_with_retry(operation_name: str, callable_, *args, **kwargs):
    """
    Invoke a SOAP operation with exponential backoff for transient failures.
    Retries on transport errors and Server/Receiver SOAP faults; re-raises immediately on
    Sender/Client faults (auth failures, malformed arguments) so we fail fast.
    Args:
        operation_name: Human-readable name used in retry log messages.
        callable_: The bound zeep service method to invoke.
        args: Positional arguments forwarded to the SOAP method.
        kwargs: Keyword arguments forwarded to the SOAP method.
    Returns:
        Whatever the SOAP operation returns on success.
    Raises:
        The last exception encountered if all retry attempts are exhausted.
    """
    last_exception = None
    for attempt in range(__MAX_RETRIES):
        try:
            return callable_(*args, **kwargs)
        except (TransportError, rq.Timeout, rq.ConnectionError) as exc:
            last_exception = exc
            if attempt == __MAX_RETRIES - 1:
                log.severe(f"{operation_name} failed after {__MAX_RETRIES} attempts: {exc}")
                raise
            sleep_seconds = min(__MAX_DELAY_SECONDS, __BASE_DELAY_SECONDS * (2**attempt))
            log.warning(
                f"{operation_name} transport error on attempt {attempt + 1}/{__MAX_RETRIES}; "
                f"retrying in {sleep_seconds}s: {exc}"
            )
            time.sleep(sleep_seconds)
        except Fault as exc:
            fault_code = (getattr(exc, "code", "") or "").lower()
            is_transient = "server" in fault_code or "receiver" in fault_code
            if not is_transient or attempt == __MAX_RETRIES - 1:
                log.severe(f"{operation_name} failed with SOAP Fault: {exc}")
                raise
            sleep_seconds = min(__MAX_DELAY_SECONDS, __BASE_DELAY_SECONDS * (2**attempt))
            log.warning(
                f"{operation_name} server fault on attempt {attempt + 1}/{__MAX_RETRIES}; "
                f"retrying in {sleep_seconds}s: {exc}"
            )
            time.sleep(sleep_seconds)
    raise last_exception if last_exception else RuntimeError(f"{operation_name} exhausted retries")


def authenticate(client: zeep.Client, username: str, password: str) -> str:
    """
    Authenticate against the Cority MRWPService and return a session key for subsequent calls.
    Args:
        client: A configured zeep.Client.
        username: Cority API username.
        password: Cority API password.
    Returns:
        Session key string returned by ValidateUser.
    """
    log.info(f"Authenticating to Cority as user '{username}'")
    session_key = call_with_retry(
        "ValidateUser", client.service.ValidateUser, username=username, password=password
    )
    if not session_key:
        raise ValueError("ValidateUser returned an empty session key; check credentials")
    return session_key


def fetch_total_rows(client: zeep.Client, session_key: str, username: str, report_id: int) -> int:
    """
    Return the total row count for a Cority user report without pulling rows.
    Used to drive pagination so we know when to stop.
    """
    raw = call_with_retry(
        f"GetUserReportResultsCount({report_id})",
        client.service.GetUserReportResultsCount,
        username=username,
        criteria=None,
        having=None,
        groupFields=None,
        sortFields=None,
        userReportId=report_id,
        entityType=__ENTITY_TYPE,
        key=session_key,
        topNRows=0,
        rowLimit=0,
        rowLimitType="None",
        includeTies=False,
    )
    return int(raw or 0)


def fetch_page(
    client: zeep.Client,
    session_key: str,
    username: str,
    report_id: int,
    start_row: int,
    end_row: int,
) -> list:
    """
    Fetch rows [start_row, end_row] inclusive from a Cority user report.
    GetUserReportResultsNonPreview returns each row as a list-of-strings whose index
    corresponds to the Sequence value declared in GetUserReportById metadata.
    Args:
        client: Authenticated zeep client.
        session_key: Session key from authenticate().
        username: Cority API username.
        report_id: Numeric Cority userReportId.
        start_row: Zero-based inclusive start offset.
        end_row: Zero-based inclusive end offset (passed as maxRow).
    Returns:
        A list of value lists, one per row.
    """
    raw = call_with_retry(
        f"GetUserReportResultsNonPreview({report_id} {start_row}-{end_row})",
        client.service.GetUserReportResultsNonPreview,
        username=username,
        userCriteria=None,
        userHaving=None,
        userGroupFields=None,
        userSortFields=None,
        userReportId=report_id,
        entityType=__ENTITY_TYPE,
        key=session_key,
        topNRows=0,
        rowLimit=0,
        rowLimitType="None",
        includeTies=False,
        startRow=start_row,
        maxRow=end_row,
    )
    rows = helpers.serialize_object(raw, dict) or []
    out = []
    for row in rows:
        if isinstance(row, dict):
            values = row.get("string") or []
            out.append(values)
    return out


def map_row(values: list, column_map: dict, primary_key: str) -> dict:
    """
    Translate a row's positional value list into a dict keyed by destination column names.
    Rows without a value for the primary key column are skipped (returns None) so we never
    attempt an upsert that Fivetran would reject for a missing PK.
    """
    row = {}
    for seq, col in column_map.items():
        if seq < len(values):
            row[col] = values[seq]
    if not row.get(primary_key):
        return None
    return row


def sync_report(
    client: zeep.Client,
    session_key: str,
    username: str,
    report: dict,
    state: dict,
):
    """
    Sync one Cority report end-to-end: page through, upsert each page, checkpoint after each.
    Resumes from the last committed offset stored in state under '<table>_offset'.
    """
    table = report["table"]
    report_id = report["userReportId"]
    primary_key = report["primary_key"]
    column_map = __COLUMN_MAPS[report_id]
    offset_key = f"{table}_offset"

    total = fetch_total_rows(client, session_key, username, report_id)
    start_offset = int(state.get(offset_key) or 0)
    log.info(f"Report {report_id} -> '{table}': total={total}, resuming at offset={start_offset}")

    if total == 0 or start_offset >= total:
        state[offset_key] = 0
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)
        return

    offset = start_offset
    while offset < total:
        end_row = min(offset + __PAGE_SIZE - 1, total - 1)
        rows = fetch_page(client, session_key, username, report_id, offset, end_row)
        if not rows:
            log.warning(f"Report {report_id}: empty page at offset={offset}; stopping early")
            break

        upserted = 0
        skipped = 0
        for values in rows:
            mapped = map_row(values, column_map, primary_key)
            if mapped is None:
                skipped += 1
                continue
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=table, data=mapped)
            upserted += 1

        offset += len(rows)
        state[offset_key] = offset
        log.info(
            f"Report {report_id} -> '{table}': upserted {upserted} skipped {skipped}; "
            f"offset={offset}/{total}"
        )

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

    # Reset offset so the next sync starts from the beginning (full refresh on every sync).
    state[offset_key] = 0
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Source Examples : Cority Multi-Report SOAP Pagination")

    validate_configuration(configuration)

    client = build_soap_client(configuration["base_url"])
    session_key = authenticate(client, configuration["username"], configuration["password"])

    for report in __REPORTS:
        sync_report(client, session_key, configuration["username"], report, state)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)


# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
