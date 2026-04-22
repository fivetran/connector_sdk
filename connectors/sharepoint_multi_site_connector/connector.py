import csv
import io
import json
import time
from typing import Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

import openpyxl
import requests
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xlsm"}

_access_token = ""
_token_expiry = 0.0


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_access_token(configuration: dict) -> str:
    global _access_token, _token_expiry

    if _access_token and time.time() < _token_expiry - 60:
        return _access_token

    response = requests.post(
        f"https://login.microsoftonline.com/{configuration['tenant_id']}/oauth2/v2.0/token",
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
    _access_token = payload["access_token"]
    _token_expiry = time.time() + payload.get("expires_in", 3600)

    log.info("Access token obtained/refreshed")
    return _access_token


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def graph_get(configuration: dict, url: str, params: dict = None) -> dict:
    global _token_expiry

    for _ in range(4):
        token = get_access_token(configuration)
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=60,
        )

        if response.status_code == 401:
            _token_expiry = 0
            continue

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 30))
            log.warning(f"Rate limited; retrying in {retry_after}s")
            time.sleep(retry_after)
            continue

        if response.status_code in (503, 504):
            log.warning(f"Service unavailable ({response.status_code}); retrying in 30s")
            time.sleep(30)
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError(f"Failed after retries: GET {url}")


def graph_download(configuration: dict, drive_id: str, item_id: str) -> bytes:
    global _token_expiry
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"

    for _ in range(4):
        token = get_access_token(configuration)
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
            allow_redirects=True,
        )

        if response.status_code == 401:
            _token_expiry = 0
            continue

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 30))
            log.warning(f"Rate limited during file download; retrying in {retry_after}s")
            time.sleep(retry_after)
            continue

        if response.status_code in (503, 504):
            log.warning(f"File download unavailable ({response.status_code}); retrying in 30s")
            time.sleep(30)
            continue

        response.raise_for_status()
        return response.content

    raise RuntimeError(f"Failed after retries: download drive_id={drive_id}, item_id={item_id}")


def paginate(configuration: dict, url: str, params: dict = None) -> Iterator[dict]:
    while url:
        payload = graph_get(configuration, url, params)
        params = None
        for item in payload.get("value", []):
            yield item
        url = payload.get("@odata.nextLink")


# ---------------------------------------------------------------------------
# Config + site helpers
# ---------------------------------------------------------------------------

def validate_configuration(configuration: dict) -> None:
    required = ["tenant_id", "client_id", "client_secret"]
    missing = [k for k in required if not configuration.get(k, "").strip()]
    if missing:
        raise ValueError(f"Missing required configuration key(s): {', '.join(missing)}")

    if not configuration.get("site_ids", "").strip() and not configuration.get("site_urls", "").strip():
        raise ValueError("Provide at least one of: site_ids or site_urls")


def resolve_sites(configuration: dict) -> List[Tuple[str, str]]:
    site_ids_raw = configuration.get("site_ids", "").strip()
    site_urls_raw = configuration.get("site_urls", "").strip()

    if site_ids_raw:
        sites = []
        for site_id in [x.strip() for x in site_ids_raw.split(",") if x.strip()]:
            payload = graph_get(configuration, f"{GRAPH_BASE}/sites/{site_id}")
            sites.append((payload["id"], payload.get("displayName") or payload.get("name") or site_id))
        return sites

    sites = []
    for raw_url in [x.strip() for x in site_urls_raw.split(",") if x.strip()]:
        parsed = urlparse(raw_url)
        hostname = parsed.netloc
        path = parsed.path.rstrip("/")
        payload = graph_get(configuration, f"{GRAPH_BASE}/sites/{hostname}:{path}")
        sites.append((payload["id"], payload.get("displayName") or payload.get("name") or raw_url))
    return sites


def get_default_drive(configuration: dict, site_id: str) -> dict:
    return graph_get(configuration, f"{GRAPH_BASE}/sites/{site_id}/drive")


def get_children_url(drive_id: str, folder_path: str) -> str:
    clean_path = folder_path.strip("/")
    if clean_path:
        return f"{GRAPH_BASE}/drives/{drive_id}/root:/{clean_path}:/children"
    return f"{GRAPH_BASE}/drives/{drive_id}/root/children"


def get_extension(file_name: str) -> str:
    file_name = (file_name or "").lower()
    for ext in SUPPORTED_EXTENSIONS:
        if file_name.endswith(ext):
            return ext
    return ""


def file_matches(item: dict, file_pattern: Optional[str]) -> bool:
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
    start_url = get_children_url(drive_id, folder_path)
    files: List[dict] = []

    def walk(url: str) -> None:
        for item in paginate(configuration, url):
            if "folder" in item:
                if recurse:
                    child_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item['id']}/children"
                    walk(child_url)
            elif file_matches(item, file_pattern):
                files.append(item)

    walk(start_url)
    return files


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_csv_rows(content_bytes: bytes, delimiter: Optional[str]) -> Iterator[Tuple[Optional[str], int, Dict]]:
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
            stream.seek(0)
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


def parse_excel_rows(content_bytes: bytes, skip_rows: int) -> Iterator[Tuple[Optional[str], int, Dict]]:
    workbook = openpyxl.load_workbook(
        io.BytesIO(content_bytes),
        read_only=True,
        data_only=True,
    )

    try:
        worksheet = workbook.active
        row_iter = worksheet.iter_rows(values_only=True)

        for _ in range(skip_rows):
            next(row_iter, None)

        header_row = next(row_iter, None)
        if not header_row:
            return

        headers: List[str] = []
        for index, value in enumerate(header_row, start=1):
            if value is None or str(value).strip() == "":
                headers.append(f"col_{index}")
            else:
                headers.append(str(value).strip())

        for row_number, raw_row in enumerate(row_iter, start=1):
            record = {}
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
    ext = get_extension(file_name)

    if ext == ".csv":
        yield from parse_csv_rows(content_bytes, delimiter)
        return

    if ext in {".xlsx", ".xlsm"}:
        yield from parse_excel_rows(content_bytes, skip_rows)
        return


# ---------------------------------------------------------------------------
# Row sync helpers
# ---------------------------------------------------------------------------

def build_row_id(file_id: str, sheet_name: Optional[str], source_row_number: int) -> str:
    if sheet_name:
        return f"{file_id}::{sheet_name}::{source_row_number}"
    return f"{file_id}::{source_row_number}"


def flatten_file_record(item: dict, drive_id: str, site_id: str, site_name: str) -> dict:
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


def emit_delete_rows(previous_row_ids: Iterable[str]):
    for row_id in previous_row_ids:
        yield op.delete("file_rows", {"row_id": row_id})


def sync_one_file(
    configuration: dict,
    state: dict,
    site_id: str,
    site_name: str,
    drive_id: str,
    item: dict,
):
    file_states = state.setdefault("file_states", {})
    state_key = f"{site_id}:{item['id']}"
    previous = file_states.get(state_key, {})

    last_modified = item.get("lastModifiedDateTime", "")
    if previous.get("last_modified") == last_modified:
        log.fine(f"Skipping unchanged file: {item.get('name')}")
        return

    yield op.upsert("files", flatten_file_record(item, drive_id, site_id, site_name))

    content_bytes = graph_download(configuration, drive_id, item["id"])
    delimiter = configuration.get("delimiter", "").strip() or None
    skip_rows = int(configuration.get("skip_rows", "0") or "0")

    new_row_ids: List[str] = []
    row_count = 0

    for sheet_name, source_row_number, row_data in parse_file_rows(
        item["name"], content_bytes, delimiter, skip_rows
    ):
        row_id = build_row_id(item["id"], sheet_name, source_row_number)
        new_row_ids.append(row_id)
        row_count += 1

        yield op.upsert(
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

    previous_row_ids = set(previous.get("row_ids", []))
    current_row_ids = set(new_row_ids)

    for row_id in previous_row_ids - current_row_ids:
        yield op.delete("file_rows", {"row_id": row_id})

    file_states[state_key] = {
        "last_modified": last_modified,
        "row_ids": new_row_ids,
        "file_id": item["id"],
        "drive_id": drive_id,
    }

    log.info(f"Synced {row_count} row(s) from file '{item['name']}' in site '{site_name}'")


def handle_deleted_files_for_site(site_id: str, current_file_ids: set, state: dict):
    file_states = state.setdefault("file_states", {})
    delete_keys = []

    for state_key, file_state in file_states.items():
        if not state_key.startswith(f"{site_id}:"):
            continue

        _, file_id = state_key.split(":", 1)
        if file_id not in current_file_ids:
            delete_keys.append(state_key)

    for state_key in delete_keys:
        file_state = file_states.pop(state_key)
        yield from emit_delete_rows(file_state.get("row_ids", []))

        yield op.delete(
            "files",
            {
                "file_id": file_state["file_id"],
                "drive_id": file_state["drive_id"],
            },
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def schema(configuration: dict):
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
    validate_configuration(configuration)

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

        current_file_ids = set()

        for item in files:
            current_file_ids.add(item["id"])
            yield from sync_one_file(
                configuration=configuration,
                state=state,
                site_id=site_id,
                site_name=site_name,
                drive_id=drive_id,
                item=item,
            )

        yield from handle_deleted_files_for_site(site_id, current_file_ids, state)

        yield op.checkpoint(state=state)
        log.info(f"Completed site {index}/{len(sites)}: {site_name}")

    log.info("Sync complete")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    with open("configuration.json", "r") as config_file:
        configuration = json.load(config_file)
    connector.debug(configuration=configuration)