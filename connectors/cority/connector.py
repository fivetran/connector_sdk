"""This connector syncs Cority user reports via the MRWPService SOAP API.
It authenticates with HTTP Basic-style username/password to ValidateUser, then calls GetUserReportResults
for each report defined in the configuration. Because Cority user reports return generic Field0..FieldN columns
without a built-in updated_at filter, the connector performs a full refresh on every sync and emits delete
operations for primary keys that disappeared between runs.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# For reading configuration from a JSON file and parsing the reports list
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

# Path to the WSDL appended to the tenant base_url
__WSDL_PATH = "/WebService/MRWPService.svc?singleWsdl"

# Maximum number of retry attempts for transient SOAP/transport failures
__MAX_RETRIES = 5

# Base delay in seconds; combined with exponential backoff capped at 60s
__BASE_DELAY_SECONDS = 1
__MAX_DELAY_SECONDS = 60

# Checkpoint cadence inside a per-report upsert loop. Cority reports are returned in one SOAP call
# (no pagination), so this guards against very large reports by checkpointing periodically.
__CHECKPOINT_INTERVAL = 500

# Separator used to flatten composite primary keys into a single string for state storage
__PK_SEPARATOR = "|"


def validate_configuration(configuration: dict) -> list:
    """
    Validate the configuration dictionary to ensure it contains all required parameters and that
    the embedded `reports` JSON string parses into a well-formed list of report descriptors.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        A list of parsed report descriptor dicts, each with keys report_id, table_name, primary_key, field_map.
    Raises:
        ValueError: if any required configuration parameter is missing or malformed.
    """
    required_configs = ["base_url", "username", "password", "reports"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    raw_reports = configuration["reports"]
    try:
        reports = json.loads(raw_reports) if isinstance(raw_reports, str) else raw_reports
    except json.JSONDecodeError as exc:
        raise ValueError(f"Configuration value 'reports' is not valid JSON: {exc}")

    if not isinstance(reports, list) or len(reports) == 0:
        raise ValueError("Configuration value 'reports' must be a non-empty list")

    for index, report in enumerate(reports):
        if not isinstance(report, dict):
            raise ValueError(f"reports[{index}] must be an object")
        for key in ("report_id", "table_name", "primary_key", "field_map"):
            if key not in report:
                raise ValueError(f"reports[{index}] is missing required key: {key}")
        if not isinstance(report["report_id"], int):
            raise ValueError(f"reports[{index}].report_id must be an integer")
        if not isinstance(report["table_name"], str) or not report["table_name"]:
            raise ValueError(f"reports[{index}].table_name must be a non-empty string")
        if not isinstance(report["primary_key"], list) or len(report["primary_key"]) == 0:
            raise ValueError(
                f"reports[{index}].primary_key must be a non-empty list of column names"
            )
        if not isinstance(report["field_map"], dict) or len(report["field_map"]) == 0:
            raise ValueError(f"reports[{index}].field_map must be a non-empty object")
        for pk_column in report["primary_key"]:
            if pk_column not in report["field_map"].values():
                raise ValueError(
                    f"reports[{index}].primary_key column '{pk_column}' is not present in field_map values"
                )

    return reports


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    reports = validate_configuration(configuration)

    schemas = []
    for report in reports:
        schemas.append(
            {
                "table": report["table_name"],
                "primary_key": report["primary_key"],
                # Only PK columns are explicitly typed; remaining columns are inferred from upsert payloads
                # so the table can evolve as Cority adds new Field<N> values to a report.
                "columns": {pk: "STRING" for pk in report["primary_key"]},
            }
        )
    return schemas


def build_soap_client(base_url: str) -> zeep.Client:
    """
    Build a zeep SOAP client pointed at the tenant's MRWPService WSDL.
    Args:
        base_url: The Cority tenant base URL, e.g. https://jbssa.cority.com
    Returns:
        A configured zeep.Client instance.
    """
    wsdl_url = base_url.rstrip("/") + __WSDL_PATH
    log.info(f"Loading WSDL from {wsdl_url}")
    return zeep.Client(wsdl=wsdl_url)


def call_soap_with_retry(operation_name: str, callable_, *args, **kwargs):
    """
    Invoke a SOAP operation with exponential backoff for transient failures.
    Retries on transport errors and 5xx-equivalent server faults; re-raises immediately
    on client-side faults (bad credentials, invalid arguments) so we fail fast.
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
            # SOAP Faults with code 'Server' / 'Receiver' are typically transient; 'Client' / 'Sender' are not.
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
    session_key = call_soap_with_retry(
        "ValidateUser", client.service.ValidateUser, username=username, password=password
    )
    if not session_key:
        raise ValueError("ValidateUser returned an empty session key; check credentials")
    return session_key


def fetch_report(client: zeep.Client, session_key: str, username: str, report_id: int) -> dict:
    """
    Call GetUserReportResults and return the deserialized response as a plain dict.
    Args:
        client: A configured zeep.Client.
        session_key: Session key from authenticate().
        username: Cority API username (required by the SOAP method).
        report_id: Numeric Cority user-report ID.
    Returns:
        Plain Python dict/list tree produced by zeep helpers.serialize_object.
    """
    log.info(f"Fetching Cority user report {report_id}")
    raw = call_soap_with_retry(
        f"GetUserReportResults({report_id})",
        client.service.GetUserReportResults,
        key=session_key,
        username=username,
        userReportId=report_id,
    )
    return helpers.serialize_object(raw, dict)


def find_row_collection(serialized_response):
    """
    Locate the list-of-row-dicts inside the deserialized SOAP response.
    Cority wraps the rows under varying nesting (typically a Tables/Rows/Row chain). To avoid hardcoding
    a single path, this walker returns the first list of dicts whose elements expose at least one Field<N> key.
    Args:
        serialized_response: dict / list / scalar tree from helpers.serialize_object.
    Returns:
        A list of row dicts, or an empty list if no plausible collection is found.
    """

    def looks_like_row(value):
        return isinstance(value, dict) and any(
            isinstance(k, str) and k.startswith("Field") and k[5:].isdigit() for k in value.keys()
        )

    def walk(node):
        if isinstance(node, list):
            if node and all(looks_like_row(item) for item in node):
                return node
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        elif isinstance(node, dict):
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        return None

    rows = walk(serialized_response)
    if rows is None:
        # Single-row case: top-level dict already exposes Field<N> keys.
        if looks_like_row(serialized_response):
            return [serialized_response]
        return []
    return rows


def map_row(raw_row: dict, field_map: dict) -> dict:
    """
    Translate a single Cority row's Field<N> keys into the semantic column names defined in field_map.
    Args:
        raw_row: A row dict from the SOAP response (e.g. {"Field0": "Open", "Field1": "2024-01-01", ...}).
        field_map: Mapping of source field name -> destination column name (e.g. {"Field0": "absence_status"}).
    Returns:
        Dict keyed by destination column names, suitable for op.upsert.
    """
    return {
        target_column: raw_row.get(source_field)
        for source_field, target_column in field_map.items()
    }


def build_pk_string(row: dict, primary_key: list) -> str:
    """
    Stringify a row's primary-key values into a single delimited string for set membership tracking.
    Args:
        row: A mapped row dict.
        primary_key: Ordered list of PK column names.
    Returns:
        A "|"-joined string of stringified PK values.
    """
    return __PK_SEPARATOR.join(
        "" if row.get(col) is None else str(row[col]) for col in primary_key
    )


def parse_pk_string(pk_string: str, primary_key: list) -> dict:
    """
    Reverse of build_pk_string — reconstruct the keys dict needed by op.delete.
    Args:
        pk_string: The delimited string previously stored in state.
        primary_key: Ordered list of PK column names.
    Returns:
        Dict suitable for op.delete(keys=...).
    """
    parts = pk_string.split(__PK_SEPARATOR)
    return dict(zip(primary_key, parts))


def sync_report(client: zeep.Client, session_key: str, username: str, report: dict, state: dict):
    """
    Sync one Cority user report: fetch all rows, upsert them, then delete rows whose primary keys
    appeared in the previous sync but not in the current one.
    Args:
        client: Authenticated zeep client.
        session_key: Session key from authenticate().
        username: Cority API username.
        report: A single report descriptor from configuration["reports"].
        state: Connector state dict (mutated in place).
    """
    table_name = report["table_name"]
    primary_key = report["primary_key"]
    field_map = report["field_map"]
    state_key = f"previous_pks_{table_name}"
    previous_pks = set(state.get(state_key, []))

    raw_response = fetch_report(client, session_key, username, report["report_id"])
    raw_rows = find_row_collection(raw_response)
    log.info(
        f"Report {report['report_id']} -> table '{table_name}': {len(raw_rows)} row(s) returned"
    )

    current_pks = set()
    upsert_count = 0
    for raw_row in raw_rows:
        row = map_row(raw_row, field_map)
        pk_string = build_pk_string(row, primary_key)
        current_pks.add(pk_string)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table_name, data=row)
        upsert_count += 1

        if upsert_count % __CHECKPOINT_INTERVAL == 0:
            state[state_key] = list(current_pks | previous_pks)
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)

    deletions = previous_pks - current_pks
    if deletions:
        log.info(f"Marking {len(deletions)} row(s) as deleted in '{table_name}'")
    for pk_string in deletions:
        keys = parse_pk_string(pk_string, primary_key)
        # The 'delete' operation marks a row as deleted in the destination by setting _fivetran_deleted = true.
        # All primary key columns must be supplied; partial keys raise an error.
        op.delete(table=table_name, keys=keys)

    state[state_key] = list(current_pks)
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
    log.warning("Example: Connector - Cority Multi-Report SOAP")

    reports = validate_configuration(configuration)

    client = build_soap_client(configuration["base_url"])
    session_key = authenticate(client, configuration["username"], configuration["password"])

    for report in reports:
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
