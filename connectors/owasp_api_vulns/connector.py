"""This connector fetches API security vulnerability data from the National Vulnerability Database (NVD) 2.0 API.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Standard library imports
import datetime  # For handling date and time objects
import json  # For reading configuration from a JSON file
import os  # For file path operations when writing temp files
import time  # For rate limiting and measuring sync duration
import re  # For regular expression pattern matching in vulnerability descriptions

# Third-party imports
import requests  # For making HTTP requests to the NVD API

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector  # The main class for creating a connector
from fivetran_connector_sdk import Logging as log  # For enabling Logs in the connector code
from fivetran_connector_sdk import (
    Operations as op,
)  # For performing data operations like upsert and checkpoint


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains valid parameters.

    Args:
        configuration (dict): A dictionary containing the connector's configuration settings.

    Raises:
        ValueError: if any configuration parameter is invalid.
    """
    # API key is optional but if provided, should not be empty
    if "api_key" in configuration and not configuration["api_key"]:
        log.warning(
            "No API key provided. The connector will use public access with stricter rate limits."
        )

    # Validate boolean flags
    for bool_flag in ["force_full_sync", "write_temp_files"]:
        if bool_flag in configuration:
            value = configuration[bool_flag].lower()
            if value not in ["true", "false"]:
                raise ValueError(f"{bool_flag} must be 'true' or 'false', got: {value}")

    # Validate logging_level
    if "logging_level" in configuration:
        level = configuration["logging_level"].lower()
        if level not in ["standard", "debug"]:
            raise ValueError(f"logging_level must be 'standard' or 'debug', got: {level}")


# Default OWASP API Top 10 CWE IDs plus CWE-79 (used if not specified in config)
__DEFAULT_CWE_IDS = [
    "CWE-285",
    "CWE-639",
    "CWE-287",
    "CWE-288",
    "CWE-290",
    "CWE-294",
    "CWE-301",
    "CWE-302",
    "CWE-303",
    "CWE-304",
    "CWE-306",
    "CWE-307",
    "CWE-521",
    "CWE-798",
    "CWE-269",
    "CWE-400",
    "CWE-770",
    "CWE-642",
    "CWE-918",
    "CWE-16",
    "CWE-209",
    "CWE-598",
    "CWE-20",
    "CWE-73",
    "CWE-200",
    "CWE-79",
]

# Constants for magic values
__RAW_DATA_DIR = "raw_data"
__RESULTS_PER_PAGE = 2000
__API_RATE_LIMIT_DELAY = 0.6
__LOG_DESCRIPTION_MAX_LENGTH = 50
__CPE_MIN_PARTS = 5  # Minimum CPE parts required for valid processing (indices 0-4)
__FIX_DESCRIPTION_MAX_LENGTH = 100  # Maximum length for fix description text
__MAX_RETRIES = 5  # Maximum number of retries for API requests
__RETRY_DELAY_SECONDS = 1  # Initial delay in seconds for API request retries
__RETRY_BACKOFF = 2  # Backoff multiplier for exponential backoff


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration (dict): A dictionary that holds the configuration settings for the connector.

    Returns:
        list: A list of table schema dictionaries.
    """
    validate_configuration(configuration)

    log_level = configuration.get("logging_level", "standard").lower()
    is_debug_logging = log_level == "debug"

    if "api_key" not in configuration:
        log.warning(
            "No API key provided in configuration.json; using public access with rate limits."
        )
    else:
        if is_debug_logging:
            log.info("Using API key from configuration.json for access.")

    # The 'logging_level' configuration is used to control log verbosity.

    return [
        {
            "table": "owasp_api_vulnerabilities",
            "primary_key": ["cve_id"],
            "columns": {
                "cve_id": "STRING",
                "description": "STRING",
                "published_date": "STRING",
                "last_modified_date": "STRING",
                "cwe_ids": "JSON",
                "affected_libraries": "JSON",
                "fixed_versions": "JSON",
                "remediations": "JSON",
                "severity": "STRING",
            },
        },
        {
            "table": "owasp_api_sync_log",
            "primary_key": ["sync_datetime"],
            "columns": {
                "sync_datetime": "STRING",
                "sync_type": "STRING",
                "total_rows_upserted": "LONG",
            },
        },
    ]


def parse_date(date_str):
    """Parses and formats a date string to a specific ISO 8601 format (UTC).

    Args:
        date_str (str): The date string to parse.

    Returns:
        str: The formatted date string, or the original string if parsing fails.
             Returns None if the input is empty.
    """
    if not date_str:
        return None

    try:
        # Try parsing as-is first. If it has offset, fromisoformat handles it.
        dt_obj = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        try:
            # Fallback: If no timezone info, assume UTC
            dt_obj = datetime.datetime.fromisoformat(date_str)
            dt_obj = dt_obj.replace(tzinfo=datetime.timezone.utc)
        except ValueError as e:
            log.warning(f"Date parsing error for {date_str}: {str(e)} - Using original string")
            return date_str

    # Ensure consistent UTC output format with millisecond precision
    return dt_obj.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _get_sync_config(configuration: dict):
    """
    Parses sync-related configuration from the configuration dictionary.

    Args:
        configuration (dict): A dictionary containing the connector's configuration settings.

    Returns:
        tuple: A tuple containing sync settings:
               (is_debug_logging, headers, write_temp_files, force_full_sync, cwe_ids).
    """
    log_level = configuration.get("logging_level", "standard").lower()
    is_debug_logging = log_level == "debug"
    api_key = configuration.get("api_key", "")
    headers = {"apiKey": api_key} if api_key else {}
    write_temp_files = configuration.get("write_temp_files", "false").lower() == "true"
    force_full_sync = configuration.get("force_full_sync", "false").lower() == "true"

    cwe_ids_str = configuration.get("cwe_ids", ",".join(__DEFAULT_CWE_IDS))
    cwe_ids = [cwe.strip() for cwe in cwe_ids_str.split(",") if cwe.strip()]
    if not cwe_ids:
        log.warning("cwe_ids is empty or invalid in configuration.json; using default CWE IDs")
        cwe_ids = __DEFAULT_CWE_IDS

    if api_key:
        if is_debug_logging:
            log.info("Using API key from configuration.json for access")
    else:
        log.warning(
            "No API key found in configuration.json; falling back to public access with rate limits"
        )

    return is_debug_logging, headers, write_temp_files, force_full_sync, cwe_ids


def _initialize_state(state: dict, force_full_sync: bool, is_debug_logging: bool):
    """
    Initializes or loads the sync state, handling a forced full sync.

    Args:
        state (dict): The state dictionary from the previous sync.
        force_full_sync (bool): Flag to force a full sync, ignoring the existing state.
        is_debug_logging (bool): Flag to enable verbose logging.

    Returns:
        dict: The initialized or loaded state dictionary.
    """
    if force_full_sync:
        if is_debug_logging:
            log.info("Forcing full sync; ignoring previous state")
        return {"cwe_progress": {}}

    if is_debug_logging:
        log.info("Performing incremental sync based on previous state")
    if "cwe_progress" in state and state["cwe_progress"]:
        log.info(f"State loaded with progress for {len(state['cwe_progress'])} CWEs.")
    else:
        log.warning("No previous state found; defaulting to full sync")
        return {"cwe_progress": {}}
    return state


def _build_request_params(cwe: str, state: dict, force_full_sync: bool):
    """
    Builds the query parameters for the NVD API request.

    Args:
        cwe (str): The CWE identifier to filter vulnerabilities.
        state (dict): The current state dictionary containing last sync time.
        force_full_sync (bool): Whether to perform a full sync.

    Returns:
        dict: A dictionary of query parameters for the API request.

    Raises:
        ValueError: If the last_sync_time in state is malformed.
    """
    params = {"cweId": cwe}
    cwe_progress = state.get("cwe_progress", {})
    last_sync_time_for_cwe = cwe_progress.get(cwe)

    if not force_full_sync and last_sync_time_for_cwe:
        try:
            # Convert "Z" to "+00:00" for fromisoformat compatibility if needed
            last_sync = datetime.datetime.fromisoformat(
                last_sync_time_for_cwe.replace("Z", "+00:00")
            )

            # Use a 1-minute buffer to minimize overlap and avoid missing records due to clock skew.
            params["lastModStartDate"] = (
                (last_sync - datetime.timedelta(minutes=1))
                .replace(tzinfo=datetime.timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )

            params["lastModEndDate"] = (
                datetime.datetime.now(datetime.timezone.utc)
                .replace(microsecond=0)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            log.info(
                f"Incremental sync for {cwe}: lastModStartDate={params['lastModStartDate']}, "
                f"lastModEndDate={params['lastModEndDate']}"
            )
        except ValueError as e:
            log.error(f"Critical error: Invalid last_sync_time format in state for CWE {cwe}: {e}")
            raise ValueError(f"Malformed state for {cwe}: last_sync_time is invalid: {e}")
    else:
        params["resultsPerPage"] = __RESULTS_PER_PAGE
        params["startIndex"] = 0
    return params


def _is_relevant_vulnerability(
    cve: dict, cwe_ids_filter: list, is_debug_logging: bool
) -> "tuple[bool, list]":
    """
    Checks if a vulnerability is relevant based on CWE IDs or description.

    Args:
        cve (dict): The CVE data dictionary for a single vulnerability.
        cwe_ids_filter (list): A list of CWE IDs to filter for.
        is_debug_logging (bool): Flag to enable verbose logging.

    Returns:
        tuple: A tuple containing a boolean indicating relevance and a list of the CVE's CWEs.
    """
    cve_id = cve.get("id")
    cve_cwes = [
        d["value"]
        for w in cve.get("weaknesses", [])
        for d in w.get("description", [])
        if d.get("lang") == "en" and d.get("value", "").startswith("CWE-")
    ]

    descriptions = cve.get("descriptions", [])
    desc_lower = descriptions[0].get("value", "").lower() if descriptions else ""

    has_matching_cwe = bool(set(cve_cwes) & set(cwe_ids_filter))
    has_api_keyword = "api" in desc_lower

    if cve_cwes and not has_matching_cwe and not has_api_keyword:
        if is_debug_logging:
            log.info(f"No matching CWEs or 'api' in description for CVE {cve_id}; skipping")
        return False, cve_cwes

    if is_debug_logging:
        log.info(
            f"Processing CVE {cve_id} with CWEs: {cve_cwes}, "
            f"Description: {desc_lower[:__LOG_DESCRIPTION_MAX_LENGTH]}..."
        )
    return True, cve_cwes


def _extract_severity(cve: dict) -> str:
    """
    Extracts the CVSS v3.1 base severity from a CVE data dictionary.

    Args:
        cve (dict): The CVE data dictionary for a single vulnerability.

    Returns:
        str: The base severity string (e.g., "HIGH", "MEDIUM") or "UNKNOWN".
    """
    cvss_metrics = cve.get("metrics", {}).get("cvssMetricV31", [])
    if cvss_metrics:
        return cvss_metrics[0].get("cvssData", {}).get("baseSeverity", "UNKNOWN")
    return "UNKNOWN"


def _extract_affected_libraries(cve: dict) -> list:
    """
    Extracts affected Python/Java libraries from CPE matches in a CVE data dictionary.

    Args:
        cve (dict): The CVE data dictionary for a single vulnerability.

    Returns:
        list: A list of dictionaries, each representing an affected library.
    """
    affected = []
    for config in cve.get("configurations", []):
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                if not match.get("vulnerable"):
                    continue

                cpe = match["criteria"].split(":")
                # Ensure cpe has at least 5 elements (indices 0-4) before accessing
                if len(cpe) < __CPE_MIN_PARTS:
                    continue

                is_app_cpe = cpe[2] == "a"
                vendor = cpe[3]
                product = cpe[4]

                # Refactored to use intermediate variables to avoid W503 (line break before binary operator)
                # This structure is cleaner and satisfies both Black and Flake8
                is_python = "python" in vendor.lower() or "python" in product.lower()
                is_java = "java" in vendor.lower() or "java" in product.lower()

                if is_app_cpe and (is_python or is_java):
                    # Determine language based on keyword presence.
                    # The outer 'if' guarantees that one of these must be true.
                    if is_python:
                        lang = "python"
                    else:
                        lang = "java"

                    # Using f-strings avoids binary operators (+) at line starts
                    version_str = f"{match.get('versionStartIncluding', '')}-{match.get('versionEndExcluding', '')}"
                    affected.append(
                        {
                            "lang": lang,
                            "product": product,
                            "versions": version_str,
                        }
                    )
    return affected


def _extract_remediations_and_fixes(cve: dict) -> "tuple[list, list, str]":
    """
    Extracts remediation URLs and fixed versions from references and description.

    Args:
        cve (dict): The CVE data dictionary for a single vulnerability.

    Returns:
        tuple: A tuple containing a list of remediation URLs, a list of fixed versions,
               and the full description string.
    """
    remediations = [
        ref["url"]
        for ref in cve.get("references", [])
        if "patch" in ref.get("tags", []) or "vendor" in ref.get("tags", [])
    ]

    fixes = []
    descriptions = cve.get("descriptions", [])
    desc_full = descriptions[0].get("value", "") if descriptions else ""

    # Use regex for case-insensitive search for "fixed in" and capture version numbers only
    # More restrictive pattern to avoid capturing arbitrary text
    match = re.search(
        r"fixed in\s+(?:version\s+)?([0-9.]+(?:\s*(?:or|and)\s*[0-9.]+)*)",
        desc_full,
        re.IGNORECASE,
    )

    if match:
        fixes.append({"fix": match.group(1).strip()[:__FIX_DESCRIPTION_MAX_LENGTH]})

    return remediations, fixes, desc_full


def _process_vulnerability(vuln: dict, cwe_ids_filter: list, is_debug_logging: bool):
    """
    Processes a single vulnerability, validating and transforming it into a row for upsert.

    Args:
        vuln (dict): The raw vulnerability data dictionary from the NVD API.
        cwe_ids_filter (list): A list of CWE IDs to filter for.
        is_debug_logging (bool): Flag to enable verbose logging.

    Returns:
        dict or None: A dictionary representing the processed row for upsert,
                      or None if the vulnerability should be skipped.
    """
    cve = vuln.get("cve")
    if not cve or not cve.get("id"):
        log.warning("Invalid CVE structure or missing CVE ID in response.")
        return None

    cve_id = cve.get("id")
    is_relevant, cve_cwes = _is_relevant_vulnerability(cve, cwe_ids_filter, is_debug_logging)
    if not is_relevant:
        return None

    severity = _extract_severity(cve)
    if severity == "UNKNOWN":
        if is_debug_logging:
            log.info(f"Skipping CVE {cve_id} with UNKNOWN severity")
        return None

    affected_libraries = _extract_affected_libraries(cve)
    remediations, fixed_versions, description = _extract_remediations_and_fixes(cve)

    return {
        "cve_id": cve_id,
        "description": description,
        "published_date": parse_date(cve.get("published")),
        "last_modified_date": parse_date(cve.get("lastModified")),
        "cwe_ids": cve_cwes,
        "affected_libraries": affected_libraries,
        "fixed_versions": fixed_versions,
        "remediations": remediations,
        "severity": severity,
    }


def _save_temp_response(response_text: str, cwe: str, is_debug_logging: bool):
    """
    Saves the raw API response text to a temporary file for debugging.

    Args:
        response_text (str): The raw text content of the API response.
        cwe (str): The CWE identifier for which the data was fetched.
        is_debug_logging (bool): Flag to enable verbose logging.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file = os.path.join(__RAW_DATA_DIR, f"nvd_response-temp-{cwe}-{timestamp}.json")
    try:
        os.makedirs(__RAW_DATA_DIR, exist_ok=True)
        with open(temp_file, "w") as f:
            f.write(response_text)
        if is_debug_logging:
            log.info(f"Response saved to {temp_file} for {cwe}")
    except (OSError, IOError) as e:
        log.warning(f"Failed to save temp file {temp_file}: {str(e)}")


def _process_vulnerabilities_page(
    vulnerabilities: list,
    cwe_ids_filter: list,
    is_debug_logging: bool,
    upserted_cve_ids: set,
) -> int:
    """
    Processes a page of vulnerabilities, upserts them, and tracks unique CVEs.

    Args:
        vulnerabilities (list): A list of vulnerability data dictionaries from a single API page.
        cwe_ids_filter (list): A list of CWE IDs to filter for.
        is_debug_logging (bool): Flag to enable verbose logging.
        upserted_cve_ids (set): A set of CVE IDs that have already been upserted in this sync.

    Returns:
        int: The number of new rows upserted from this page.
    """
    upsert_count = 0
    for vuln in vulnerabilities:
        cve = vuln.get("cve", {})
        cve_id = cve.get("id")
        if not cve_id or cve_id in upserted_cve_ids:
            continue

        row = _process_vulnerability(vuln, cwe_ids_filter, is_debug_logging)

        if row:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="owasp_api_vulnerabilities", data=row)
            upserted_cve_ids.add(cve_id)
            upsert_count += 1
    return upsert_count


def _fetch_and_process_cwe_data(
    cwe: str,
    base_url: str,
    headers: dict,
    params: dict,
    write_temp_files: bool,
    is_debug_logging: bool,
    upserted_cve_ids: set,
    cwe_ids_filter: list,
):
    """
    Fetches and processes all vulnerabilities for a given CWE, handling pagination and retries.

    Args:
        cwe (str): The CWE identifier to fetch data for.
        base_url (str): The base URL of the NVD API.
        headers (dict): The request headers, including the API key if available.
        params (dict): The query parameters for the API request.
        write_temp_files (bool): Flag to save raw API responses to files.
        is_debug_logging (bool): Flag to enable verbose logging.
        upserted_cve_ids (set): A set of CVE IDs that have already been upserted in this sync.
        cwe_ids_filter (list): A list of all CWE IDs being targeted in the sync.

    Returns:
        int: The total number of rows upserted for this CWE.
    """
    upsert_count_per_cwe = 0

    while True:
        response = None
        # Unified retry logic with exponential backoff for transient errors
        for attempt in range(__MAX_RETRIES):
            try:
                response = requests.get(base_url, params=params, headers=headers)
                response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
                break  # If request is successful, break out of the retry loop
            except (
                requests.Timeout,
                requests.ConnectionError,
                requests.exceptions.HTTPError,
            ) as e:
                # For non-retriable 4xx client errors, fail fast.
                # We treat 403 (Forbidden) and 429 (Too Many Requests) as potentially transient and retriable.
                if isinstance(e, requests.exceptions.HTTPError) and response:
                    # Fail fast on client errors that are not related to rate limiting
                    if 400 <= response.status_code < 500 and response.status_code not in [
                        403,
                        429,
                    ]:
                        log.error(f"Client error for {cwe}: {e}")
                        raise  # Re-raise to be caught by the outer handler in update()

                # For 5xx server errors, 429 rate limit, or network errors, retry
                log.warning(
                    f"Retriable error for {cwe} (attempt {attempt + 1}/{__MAX_RETRIES}): {e}"
                )
                if attempt == __MAX_RETRIES - 1:
                    log.error(f"Failed to fetch data for {cwe} after {__MAX_RETRIES} attempts.")
                    raise  # Re-raise the exception after the final attempt

            # If we are here, it's a retriable error and not the last attempt.
            delay = min(60, __RETRY_DELAY_SECONDS * (__RETRY_BACKOFF**attempt))
            log.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)

        try:
            # The NVD API enforces a maximum page size of 2000 records, and each page is processed immediately
            # without accumulation, so loading one page's response into memory is acceptable.
            data = response.json()
        except json.JSONDecodeError as e:
            log.error(
                f"JSON decode error for {cwe} at startIndex {params.get('startIndex', 'N/A')}: {e}"
            )
            # Instead of break, raise an exception to fail processing for this CWE.
            # This allows the main update loop to catch it and continue to the next CWE without checkpointing.
            raise ValueError(f"Failed to decode JSON response for {cwe}") from e

        log.info(
            f"API response for {cwe}: status={response.status_code}, "
            f"totalResults={data.get('totalResults', 'N/A')}, "
            f"startIndex={params.get('startIndex', 'N/A')}"
        )

        vulnerabilities = data.get("vulnerabilities", [])
        # Check that vulnerabilities is actually a list and not empty
        if not isinstance(vulnerabilities, list) or not vulnerabilities:
            log.info(f"No more vulnerabilities returned for {cwe} at current startIndex.")
            break

        if write_temp_files:
            _save_temp_response(response.text, cwe, is_debug_logging)

        upsert_count_per_cwe += _process_vulnerabilities_page(
            vulnerabilities, cwe_ids_filter, is_debug_logging, upserted_cve_ids
        )

        # Handle pagination for full syncs
        if "resultsPerPage" in params:
            params["startIndex"] += data.get("resultsPerPage", 0)
            if params["startIndex"] >= data.get("totalResults", 0):
                break
        else:
            # Incremental syncs are not paginated in this connector's logic
            break

        time.sleep(__API_RATE_LIMIT_DELAY)

    return upsert_count_per_cwe


def _finalize_sync(start_time: float, total_upserts: int, force_full_sync: bool):
    """
    Logs sync summary, upserts a sync log entry, and checkpoints the final state.

    Args:
        start_time (float): The timestamp when the sync started.
        total_upserts (int): The total number of rows upserted during the sync.
        force_full_sync (bool): Flag indicating if the sync was a full sync.
    """
    end_time = time.time()
    duration = end_time - start_time
    log.info(f"Sync completed. Total duration: {duration:.2f} seconds")
    log.info(f"Total upserts across all CWEs: {total_upserts}")

    sync_datetime = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sync_type = "full" if force_full_sync else "incremental"
    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(
        table="owasp_api_sync_log",
        data={
            "sync_datetime": sync_datetime,
            "sync_type": sync_type,
            "total_rows_upserted": total_upserts,
        },
    )


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: CONNECTOR: OWASP_API_VULNS")
    validate_configuration(configuration)
    start_time = time.time()

    is_debug_logging, headers, write_temp_files, force_full_sync, cwe_ids = _get_sync_config(
        configuration
    )
    state = _initialize_state(state, force_full_sync, is_debug_logging)

    base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    upserted_cve_ids = set()
    total_upserts = 0

    if write_temp_files:
        try:
            os.makedirs(__RAW_DATA_DIR, exist_ok=True)
        except OSError as e:
            log.warning(f"Failed to create raw data directory: {str(e)}")

    for cwe in cwe_ids:
        log.info(f"Now pulling CVEs pertaining to {cwe}")
        try:
            params = _build_request_params(cwe, state, force_full_sync)
        except ValueError as e:
            # Critical config error; stop processing this CWE
            log.error(f"Configuration/State error for {cwe}: {str(e)}")
            break

        if is_debug_logging:
            log.info(f"Request params for {cwe}: {params}")

        try:
            upsert_count_per_cwe = _fetch_and_process_cwe_data(
                cwe,
                base_url,
                headers,
                params,
                write_temp_files,
                is_debug_logging,
                upserted_cve_ids,
                cwe_ids,
            )
            total_upserts += upsert_count_per_cwe
            log.info(f"Results fetched for {cwe}")
            log.info(f"Rows upserted for {cwe}: {upsert_count_per_cwe}")

            # Checkpoint progress after each successful CWE sync
            sync_datetime = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state["cwe_progress"][cwe] = sync_datetime
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

        except requests.exceptions.RequestException as e:
            log.error(f"Network error fetching for {cwe}: {str(e)}")
            # Continue to next CWE
            continue
        except ValueError as e:
            log.error(f"Data validation error for {cwe}: {str(e)}")
            continue
        except Exception as e:
            log.error(f"Unexpected error fetching for {cwe}: {str(e)}")
            # Re-raise unexpected exceptions to fail the sync if it's critical
            raise

    _finalize_sync(start_time, total_upserts, force_full_sync)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Test the connector locally
    connector.debug(configuration=configuration)
