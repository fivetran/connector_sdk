"""
Syncs CSV and Excel file data from multiple SharePoint Online sites using the Microsoft Graph API.
Extracted data is loaded into two destination tables: 'files' (metadata) and 'file_rows' (row data).
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import csv
import io
import json
import time
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote, urlparse

# For Excel file (.xlsx, .xlsm) parsing
import openpyxl

# For HTTP requests to the Microsoft Graph API
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Microsoft Graph API base URL
__GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# File extensions supported for row-level extraction
__SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xlsm"}

# Token cache keyed by "{tenant_id}:{client_id}" → (access_token, expiry_timestamp)
# Supports multiple configurations within the same process without token cross-contamination
__TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}

# Sentinel sheet key used for CSV files (which have no sheet name) in the row_counts state dict
__CSV_SHEET_KEY = ""


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _token_cache_key(configuration: dict) -> str:
    """Return the cache key for the given tenant/client pair."""
    return f"{configuration['tenant_id']}:{configuration['client_id']}"


def get_access_token(configuration: dict) -> str:
    """
    Return a valid OAuth2 Bearer token for the Microsoft Graph API.
    Tokens are cached per tenant/client pair and refreshed 60 seconds before expiry.
    Args:
        configuration: connector configuration containing tenant_id, client_id, client_secret.
    Returns:
        A valid Bearer access token string.
    """
    cache_key = _token_cache_key(configuration)
    token, expiry = __TOKEN_CACHE.get(cache_key, ("", 0.0))
    if token and time.time() < expiry - 60:
        return token

    token_url = (
        f"https://login.microsoftonline.com/{configuration['tenant_id']}"
        "/oauth2/v2.0/token"
    )
    response = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": configuration["client_id"],
            "client_secret": configuration["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    __TOKEN_CACHE[cache_key] = (
        payload["access_token"],
        time.time() + payload.get("expires_in", 3600),
    )
    log.info("Access token obtained/refreshed")
    return __TOKEN_CACHE[cache_key][0]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_graph_request(
    configuration: dict,
    url: str,
    params: dict = None,
    as_bytes: bool = False,
):
    """
    Make a GET request to the Microsoft Graph API with automatic retry logic.
    Retries on 401 (token expiry), 429 (rate limiting), and 503/504 (service unavailable).
    Uses exponential backoff for transient server errors to avoid hammering a degraded endpoint.
    Args:
        configuration: connector configuration used for authentication.
        url: the full Graph API URL to request.
        params: optional query parameters.
        as_bytes: if True, return raw response bytes; otherwise return a parsed JSON dict.
    Returns:
        Parsed JSON dict or raw bytes depending on as_bytes.
    Raises:
        RuntimeError: if all four retry attempts are exhausted.
    """
    cache_key = _token_cache_key(configuration)
    timeout = 120 if as_bytes else 60
    backoff = 30

    for _ in range(4):
        token = get_access_token(configuration)
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=timeout,
            allow_redirects=as_bytes,
        )

        if response.status_code == 401:
            # Token may have been revoked externally; invalidate cache and retry
            __TOKEN_CACHE.pop(cache_key, None)
            continue

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 30))
            log.warning(f"Rate limited; retrying in {retry_after}s")
            time.sleep(retry_after)
            continue

        if response.status_code in (503, 504):
            log.warning(
                f"Service unavailable ({response.status_code}); retrying in {backoff}s"
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
            continue

        response.raise_for_status()
        return response.content if as_bytes else response.json()

    raise RuntimeError(f"Failed after retries: GET {url}")


def graph_get(configuration: dict, url: str, params: dict = None) -> dict:
    """Make a Graph API GET request and return the parsed JSON response."""
    return make_graph_request(configuration, url, params=params)


def graph_download(configuration: dict, drive_id: str, item_id: str) -> bytes:
    """Download and return the raw bytes of a drive item's content."""
    url = f"{__GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
    return make_graph_request(configuration, url, as_bytes=True)


def paginate(configuration: dict, url: str, params: dict = None) -> Iterator[dict]:
    """Yield all items from a paginated Graph API endpoint, following @odata.nextLink."""
    while url:
        payload = graph_get(configuration, url, params)
        params = None
        yield from payload.get("value", [])
        url = payload.get("@odata.nextLink")


# ---------------------------------------------------------------------------
# Configuration and site helpers
# ---------------------------------------------------------------------------

def validate_configuration(configuration: dict) -> None:
    """
    Validate that all required configuration keys are present and non-empty.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required key is missing or if neither site_ids nor site_urls is provided.
    """
    required = ["tenant_id", "client_id", "client_secret"]
    missing = [k for k in required if not configuration.get(k, "").strip()]
    if missing:
        raise ValueError(
            f"Missing required configuration key(s): {', '.join(missing)}"
        )
    has_sites = configuration.get("site_ids", "").strip() or configuration.get("site_urls", "").strip()
    if not has_sites:
        raise ValueError("Provide at least one of: site_ids or site_urls")


def resolve_sites(configuration: dict) -> List[Tuple[str, str]]:
    """
    Return a list of (site_id, site_name) pairs for all configured SharePoint sites.
    Uses site_ids directly if provided; otherwise resolves each site_urls entry via the Graph API.
    Args:
        configuration: connector configuration containing site_ids or site_urls.
    Returns:
        List of (graph_site_id, display_name) tuples.
    """
    site_ids_raw = configuration.get("site_ids", "").strip()
    site_urls_raw = configuration.get("site_urls", "").strip()

    if site_ids_raw:
        sites = []
        for site_id in [x.strip() for x in site_ids_raw.split(",") if x.strip()]:
            payload = graph_get(configuration, f"{__GRAPH_BASE}/sites/{site_id}")
            sites.append(
                (payload["id"], payload.get("displayName") or payload.get("name") or site_id)
            )
        return sites

    sites = []
    for raw_url in [x.strip() for x in site_urls_raw.split(",") if x.strip()]:
        parsed = urlparse(raw_url)
        hostname = parsed.netloc
        path = parsed.path.rstrip("/")
        payload = graph_get(configuration, f"{__GRAPH_BASE}/sites/{hostname}:{path}")
        sites.append(
            (payload["id"], payload.get("displayName") or payload.get("name") or raw_url)
        )
    return sites


def get_default_drive(configuration: dict, site_id: str) -> dict:
    """Return the default document library drive for the given site."""
    return graph_get(configuration, f"{__GRAPH_BASE}/sites/{site_id}/drive")


def get_children_url(drive_id: str, folder_path: str) -> str:
    """
    Return the Graph API URL to list the children of the given folder path.
    The folder path is percent-encoded to handle spaces and special characters.
    """
    clean_path = folder_path.strip("/")
    if clean_path:
        encoded = quote(clean_path, safe="/")
        return f"{__GRAPH_BASE}/drives/{drive_id}/root:/{encoded}:/children"
    return f"{__GRAPH_BASE}/drives/{drive_id}/root/children"


def get_extension(file_name: str) -> str:
    """Return the lowercase extension of file_name if it is supported, else empty string."""
    file_name = (file_name or "").lower()
    for ext in __SUPPORTED_EXTENSIONS:
        if file_name.endswith(ext):
            return ext
    return ""


def file_matches(item: dict, file_pattern: Optional[str]) -> bool:
    """Return True if the item is a supported file matching the optional name pattern."""
    if "folder" in item:
        return False
    if not item.get("file"):
        return False
    if get_extension(item.get("name", "")) == "":
        return False
    if not file_pattern:
        return True
    return file_pattern.lower() in item.get("name", "").lower()


def list_files_in_folder(
    configuration: dict,
    drive_id: str,
    folder_path: str,
    recurse: bool,
    file_pattern: Optional[str],
) -> List[dict]:
    """
    Return all matching files under folder_path in the given drive.
    Uses an iterative stack to traverse sub-folders safely on any nesting depth,
    avoiding Python recursion limits on deeply nested SharePoint document libraries.
    Args:
        configuration: connector configuration.
        drive_id: the Graph API drive ID to search.
        folder_path: root folder path to start from (empty string for the drive root).
        recurse: if True, descend into sub-folders.
        file_pattern: optional substring filter applied case-insensitively to file names.
    Returns:
        List of Graph API drive item dicts for all matched files.
    """
    files: List[dict] = []
    pending_urls = [get_children_url(drive_id, folder_path)]

    while pending_urls:
        url = pending_urls.pop()
        for item in paginate(configuration, url):
            if "folder" in item:
                if recurse:
                    child_url = (
                        f"{__GRAPH_BASE}/drives/{drive_id}/items/{item['id']}/children"
                    )
                    pending_urls.append(child_url)
            elif file_matches(item, file_pattern):
                files.append(item)

    return files


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_csv_rows(
    content_bytes: bytes,
    delimiter: Optional[str],
) -> Iterator[Tuple[Optional[str], int, Dict]]:
    """
    Yield (sheet_name, row_number, row_dict) tuples for each data row in a CSV file.
    sheet_name is always None for CSV files.
    Attempts automatic dialect detection via csv.Sniffer when no delimiter is configured.
    Args:
        content_bytes: raw file bytes (UTF-8 or UTF-8-BOM encoded).
        delimiter: explicit column delimiter; None triggers auto-detection.
    """
    text = content_bytes.decode("utf-8-sig")
    stream = io.StringIO(text)

    if delimiter:
        reader = csv.DictReader(stream, delimiter=delimiter)
    else:
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            reader = csv.DictReader(stream, dialect=dialect)
        except csv.Error:
            reader = csv.DictReader(stream)

    for row_number, row in enumerate(reader, start=1):
        cleaned = {}
        for key, value in row.items():
            if key is None:
                continue
            key = str(key).strip()
            if not key:
                continue
            cleaned[key] = value
        yield None, row_number, cleaned


def parse_excel_rows(
    content_bytes: bytes,
    skip_rows: int,
) -> Iterator[Tuple[Optional[str], int, Dict]]:
    """
    Yield (sheet_name, row_number, row_dict) tuples for each data row across ALL sheets.
    The first non-skipped row of each sheet is used as the header; columns with blank
    headers are auto-named col_N.  skip_rows is applied independently to each sheet.
    Args:
        content_bytes: raw .xlsx or .xlsm file bytes.
        skip_rows: number of leading rows to skip before the header on each sheet.
    """
    workbook = openpyxl.load_workbook(
        io.BytesIO(content_bytes),
        read_only=True,
        data_only=True,
    )
    try:
        for worksheet in workbook.worksheets:
            row_iter = worksheet.iter_rows(values_only=True)

            for _ in range(skip_rows):
                next(row_iter, None)

            header_row = next(row_iter, None)
            if not header_row:
                continue

            headers: List[str] = []
            for index, value in enumerate(header_row, start=1):
                if value is None or str(value).strip() == "":
                    headers.append(f"col_{index}")
                else:
                    headers.append(str(value).strip())

            for row_number, raw_row in enumerate(row_iter, start=1):
                record: Dict[str, Optional[str]] = {}
                for header, value in zip(headers, raw_row):
                    record[header] = None if value is None else str(value)
                yield worksheet.title, row_number, record
    finally:
        workbook.close()


def parse_file_rows(
    file_name: str,
    content_bytes: bytes,
    delimiter: Optional[str],
    skip_rows: int,
) -> Iterator[Tuple[Optional[str], int, Dict]]:
    """
    Dispatch to the correct row parser based on file extension.
    Yields (sheet_name, row_number, row_dict) tuples.
    Args:
        file_name: file name used to determine the extension.
        content_bytes: raw file bytes.
        delimiter: optional CSV delimiter (ignored for Excel files).
        skip_rows: rows to skip before the header row (Excel only).
    """
    ext = get_extension(file_name)
    if ext == ".csv":
        yield from parse_csv_rows(content_bytes, delimiter)
    elif ext in {".xlsx", ".xlsm"}:
        yield from parse_excel_rows(content_bytes, skip_rows)


# ---------------------------------------------------------------------------
# Row sync helpers
# ---------------------------------------------------------------------------

def build_row_id(file_id: str, sheet_name: Optional[str], source_row_number: int) -> str:
    """Build a unique, stable row identifier combining file ID, sheet name, and row position."""
    if sheet_name:
        return f"{file_id}::{sheet_name}::{source_row_number}"
    return f"{file_id}::{source_row_number}"


def flatten_file_record(item: dict, drive_id: str, site_id: str, site_name: str) -> dict:
    """Build the 'files' table record dict from a Graph API drive item."""
    parent_ref = item.get("parentReference", {})
    return {
        "file_id": item.get("id"),
        "drive_id": drive_id,
        "site_id": site_id,
        "site_name": site_name,
        "file_name": item.get("name"),
        "web_url": item.get("webUrl"),
        "size_bytes": item.get("size"),
        "mime_type": item.get("file", {}).get("mimeType"),
        "parent_id": parent_ref.get("id"),
        "parent_path": parent_ref.get("path"),
        "created_date_time": item.get("createdDateTime"),
        "last_modified_date_time": item.get("lastModifiedDateTime"),
        "etag": item.get("eTag"),
    }


def delete_orphaned_rows(
    file_id: str,
    previous_row_counts: Dict[str, int],
    new_row_counts: Dict[str, int],
) -> None:
    """
    Delete file_rows records that no longer exist after a file has changed.
    State stores the maximum row number per sheet (row_counts) rather than the full list of row IDs,
    keeping state size O(sheets) instead of O(rows) to support large files without hitting
    Fivetran's state size limit.
    For sheets that shrunk: deletes rows from (new_count + 1) to prev_count.
    For sheets removed entirely: new_count defaults to 0, so all rows are deleted.
    Args:
        file_id: the Graph API item ID of the modified file.
        previous_row_counts: sheet_key → previous max row number from last sync state.
        new_row_counts: sheet_key → current max row number from this sync.
    """
    for sheet_key, prev_count in previous_row_counts.items():
        sheet_name = None if sheet_key == __CSV_SHEET_KEY else sheet_key
        new_count = new_row_counts.get(sheet_key, 0)
        for n in range(new_count + 1, prev_count + 1):
            op.delete("file_rows", {"row_id": build_row_id(file_id, sheet_name, n)})


def sync_one_file(
    configuration: dict,
    state: dict,
    site_id: str,
    site_name: str,
    drive_id: str,
    item: dict,
) -> None:
    """
    Sync a single SharePoint file: upsert its metadata and all extracted row records.
    Skips the file when lastModifiedDateTime is unchanged since the last sync.
    After re-syncing a changed file, deletes any rows that no longer exist.
    State is updated in-place under state["file_states"]["{site_id}:{item_id}"].
    Args:
        configuration: connector configuration.
        state: mutable sync state dict shared across all files in this sync run.
        site_id: Graph API site ID the file belongs to.
        site_name: human-readable site display name.
        drive_id: Graph API drive ID.
        item: Graph API drive item dict for the file to sync.
    """
    file_states = state.setdefault("file_states", {})
    state_key = f"{site_id}:{item['id']}"
    previous = file_states.get(state_key, {})

    last_modified = item.get("lastModifiedDateTime", "")
    if previous.get("last_modified") == last_modified:
        log.fine(f"Skipping unchanged file: {item.get('name')}")
        return

    # Upsert file metadata record into the 'files' table
    op.upsert("files", flatten_file_record(item, drive_id, site_id, site_name))

    content_bytes = graph_download(configuration, drive_id, item["id"])
    delimiter = configuration.get("delimiter", "").strip() or None
    skip_rows = int(configuration.get("skip_rows", "0") or "0")

    new_row_counts: Dict[str, int] = {}
    row_count = 0

    # Upsert each extracted row into 'file_rows'; track max row number per sheet
    for sheet_name, source_row_number, row_data in parse_file_rows(
        item["name"], content_bytes, delimiter, skip_rows
    ):
        row_id = build_row_id(item["id"], sheet_name, source_row_number)
        sheet_key = __CSV_SHEET_KEY if sheet_name is None else sheet_name
        new_row_counts[sheet_key] = source_row_number
        row_count += 1

        op.upsert(
            "file_rows",
            {
                "row_id": row_id,
                "file_id": item["id"],
                "drive_id": drive_id,
                "site_id": site_id,
                "site_name": site_name,
                "file_name": item["name"],
                "sheet_name": sheet_name,
                "source_row_number": source_row_number,
                "data": row_data,
                "last_modified_date_time": last_modified,
            },
        )

    # Delete rows that disappeared because the file shrank or lost sheets
    delete_orphaned_rows(
        item["id"],
        previous.get("row_counts", {}),
        new_row_counts,
    )

    file_states[state_key] = {
        "last_modified": last_modified,
        "row_counts": new_row_counts,
        "file_id": item["id"],
        "drive_id": drive_id,
    }

    log.info(f"Synced {row_count} row(s) from file '{item['name']}' in site '{site_name}'")


def handle_deleted_files_for_site(
    site_id: str,
    current_file_ids: set,
    state: dict,
) -> None:
    """
    Delete all destination records for files removed from SharePoint since the last sync.
    Removes all row data and the file metadata record for each deleted file,
    then clears the corresponding state entry.
    Args:
        site_id: Graph API site ID whose state entries should be checked.
        current_file_ids: set of item IDs currently found in SharePoint for this site.
        state: mutable sync state dict; entries for deleted files are removed in place.
    """
    file_states = state.setdefault("file_states", {})
    delete_keys = [
        state_key for state_key, _ in file_states.items()
        if state_key.startswith(f"{site_id}:") and state_key.split(":", 1)[1] not in current_file_ids
    ]

    for state_key in delete_keys:
        file_state = file_states.pop(state_key)
        # Delete all row records for the removed file
        for sheet_key, row_count in file_state.get("row_counts", {}).items():
            sheet_name = None if sheet_key == __CSV_SHEET_KEY else sheet_key
            for n in range(1, row_count + 1):
                op.delete(
                    "file_rows",
                    {"row_id": build_row_id(file_state["file_id"], sheet_name, n)},
                )
        # Delete file metadata record using the composite primary key
        op.delete(
            "files",
            {"file_id": file_state["file_id"], "drive_id": file_state["drive_id"]},
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "files",
            "primary_key": ["file_id", "drive_id"],
            "columns": {
                "file_id": "STRING",
                "drive_id": "STRING",
                "site_id": "STRING",
                "site_name": "STRING",
                "file_name": "STRING",
                "web_url": "STRING",
                "size_bytes": "LONG",
                "mime_type": "STRING",
                "parent_id": "STRING",
                "parent_path": "STRING",
                "created_date_time": "UTC_DATETIME",
                "last_modified_date_time": "UTC_DATETIME",
                "etag": "STRING",
            },
        },
        {
            "table": "file_rows",
            "primary_key": ["row_id"],
            "columns": {
                "row_id": "STRING",
                "file_id": "STRING",
                "drive_id": "STRING",
                "site_id": "STRING",
                "site_name": "STRING",
                "file_name": "STRING",
                "sheet_name": "STRING",
                "source_row_number": "LONG",
                "data": "JSON",
                "last_modified_date_time": "UTC_DATETIME",
            },
        },
    ]


# ---------------------------------------------------------------------------
# Main update
# ---------------------------------------------------------------------------

def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details (tenant_id, client_id,
            client_secret, and site_ids or site_urls). Optional keys: folder_path,
            sync_subfolders, file_pattern, delimiter, skip_rows.
        state: A dictionary containing state information from previous runs.
            The state dictionary is empty for the first sync or for any full re-sync.
    """
    validate_configuration(configuration=configuration)

    sites = resolve_sites(configuration)
    folder_path = configuration.get("folder_path", "").strip()
    recurse = configuration.get("sync_subfolders", "false").lower() == "true"
    file_pattern = configuration.get("file_pattern", "").strip() or None

    log.info(f"Starting sync for {len(sites)} site(s)")

    for index, (site_id, site_name) in enumerate(sites, start=1):
        log.info(f"Syncing site {index}/{len(sites)}: {site_name}")

        drive = get_default_drive(configuration, site_id)
        drive_id = drive["id"]

        files = list_files_in_folder(
            configuration=configuration,
            drive_id=drive_id,
            folder_path=folder_path,
            recurse=recurse,
            file_pattern=file_pattern,
        )
        files.sort(key=lambda item: item.get("lastModifiedDateTime", ""))

        current_file_ids: set = set()
        for item in files:
            current_file_ids.add(item["id"])
            sync_one_file(
                configuration=configuration,
                state=state,
                site_id=site_id,
                site_name=site_name,
                drive_id=drive_id,
                item=item,
            )
            # Checkpoint after each file to preserve progress on interruption.
            # This caps re-work to a single file rather than an entire site on restart.
            op.checkpoint(state)

        # Handle files removed from SharePoint since the last sync
        handle_deleted_files_for_site(site_id, current_file_ids, state)

        # Checkpoint to persist any deletion state changes before moving to the next site
        op.checkpoint(state)

        log.info(f"Completed site {index}/{len(sites)}: {site_name}")

    log.info("Sync complete")


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
    # Open the configuration.json file and load its contents into the configuration variable
    with open("configuration.json", "r") as config_file:
        configuration = json.load(config_file)
    # Test the connector locally
    connector.debug(configuration=configuration)
