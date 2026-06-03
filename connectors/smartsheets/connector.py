"""
This is an example for syncing data from Smartsheet.
It hits the getSheet endpoint and gets data from pre-defined sheets and reports in Smartsheets.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for details.
"""

# For generating MD5 hashes of row IDs as primary keys
import hashlib

# For reading configuration from a JSON file
import json

# For normalizing column names and table names
import re

# For rate limiting and retry backoff delays
import time

# For flattening nested dictionaries
from collections.abc import MutableMapping

# For creating configuration and state classes
from dataclasses import dataclass

# For datetime operations and timezone handling
from datetime import datetime, timedelta, timezone

# For precise numeric calculations without floating point errors
from decimal import Decimal

# For defining column type constants
from enum import Enum

# For type hints and annotations
from typing import Any, Dict, List, Optional, Union

# For making HTTP requests to the Smartsheet API
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For implementing retry logic with exponential backoff
from requests.adapters import HTTPAdapter

# For configuring retry strategy for failed requests
from urllib3.util.retry import Retry

# Private constants
_TEST_MODE = False  # Set to True to limit row processing during development
_TEST_ROW_LIMIT = 10  # Number of rows to process in test mode
_DEFAULT_PAGE_SIZE = 100  # Smartsheet API default page size
_DEFAULT_REQUESTS_PER_MINUTE = 60  # Default rate limit for Smartsheet API
_MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
_BACKOFF_FACTOR = 1  # Base delay factor for exponential backoff
_RETRY_STATUS_CODES = [429, 500, 502, 503, 504]  # HTTP status codes that trigger retry


class StateManager:
    def __init__(self, initial_state: Dict[str, Any]):
        """
        Initialize the StateManager with the current sync state.

        Args:
            initial_state (Dict[str, Any]): The current state dictionary from
                the previous sync run. Contains last_modified timestamps and
                sheet-specific state information.

        The state structure is:
            {
                "last_modified": "ISO8601 timestamp",
                "sheet_states": {
                    "sheet_id": {
                        "last_modified": "ISO8601 timestamp",
                        "row_ids": ["row_1", "row_2", "row_3"]
                    },
                    ...
                },
                "report_states": {
                    "report_id": {
                        "row_ids": ["row_1", "row_2", "row_3"]
                    },
                    ...
                }
            }
        """
        self.state = initial_state
        self.sheet_states = self.state.get("sheet_states", {})
        self.report_states = self.state.get("report_states", {})

    def get_sheet_state(self, sheet_id: str) -> Dict[str, Any]:
        """
        Get state for a specific sheet.

        Args:
            sheet_id (str): The unique identifier of the sheet

        Returns:
            Dict[str, Any]: State information for the sheet containing:
                - last_modified: ISO8601 timestamp of the last sync, or None for new sheets
                - row_ids: List of row IDs from the previous sync
                If no state exists for the sheet, returns a default state
                with last_modified set to None to fetch all rows on first sync.

        Note:
            This method provides a default state for new sheets, ensuring
            that the first sync will fetch all available data by passing
            None for modified_since.
        """
        return self.sheet_states.get(
            sheet_id,
            {
                "last_modified": None,
                "row_ids": [],
            },
        )

    def get_report_state(self, report_id: str) -> Dict[str, Any]:
        """
        Get state for a specific report.

        Args:
            report_id (str): The unique identifier of the report

        Returns:
            Dict[str, Any]: State information for the report containing:
                - row_ids: List of row IDs from the previous sync
                If no state exists for the report, returns a default state
                with empty row_ids list.
        """
        return self.report_states.get(
            report_id,
            {"row_ids": []},
        )

    def update_sheet_state(self, sheet_id: str, last_modified: str, row_ids: List[str]):
        """
        Update state for a specific sheet after successful sync.

        Args:
            sheet_id (str): The unique identifier of the sheet
            last_modified (str): ISO8601 timestamp of the latest modification
                found during the current sync
            row_ids (List[str]): List of current row IDs in the sheet

        This method is called after processing a sheet to record the latest
        modification timestamp and current row IDs, which will be used for
        the next incremental sync and deletion detection.
        """
        self.sheet_states[sheet_id] = {
            "last_modified": last_modified,
            "row_ids": row_ids,
        }

    def update_report_state(self, report_id: str, row_ids: List[str]):
        """
        Update state for a specific report after successful sync.

        Args:
            report_id (str): The unique identifier of the report
            row_ids (List[str]): List of current row IDs in the report

        This method is called after processing a report to record the current
        row IDs, which will be used for deletion detection in the next sync.
        """
        self.report_states[report_id] = {"row_ids": row_ids}

    def get_latest_modified(self) -> str:
        """
        Get the latest modified timestamp across all sheets for consistency.

        Returns:
            str: ISO8601 timestamp of the latest modification across
                all processed sheets. If no sheet states exist, returns
                the global last_modified timestamp or defaults to 24 hours ago.

        This method uses the latest timestamp to ensure consistent incremental syncs
        and prevent state corruption issues.
        """
        if not self.sheet_states:
            default_time = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=1)
            return self.state.get(
                "last_modified",
                default_time.isoformat() + "Z",
            )
        return max(state["last_modified"] for state in self.sheet_states.values())

    def get_state(self) -> Dict[str, Any]:
        """
        Get the complete state for checkpointing.

        Returns:
            Dict[str, Any]: Complete state dictionary containing:
                - last_modified: Latest modification timestamp across all sheets
                - sheet_states: Per-sheet state information for incremental syncs
                - report_states: Per-report state information for deletion tracking

        This method is called at the end of a successful sync to save the
        current state for the next sync run. The returned state is used
        by Fivetran for checkpointing and resuming incremental syncs.
        """
        return {
            "last_modified": self.get_latest_modified(),
            "sheet_states": self.sheet_states,
            "report_states": self.report_states,
        }


class ColumnType(Enum):
    """Smartsheet column types"""

    TEXT_NUMBER = "TEXT_NUMBER"
    DATE = "DATE"
    DATETIME = "DATETIME"
    CHECKBOX = "CHECKBOX"
    NUMBER = "NUMBER"
    CURRENCY = "CURRENCY"
    PERCENT = "PERCENT"
    PICKLIST = "PICKLIST"


@dataclass
class SmartsheetConfig:
    """Configuration for Smartsheet connector"""

    access_token: str
    sheet_ids: Optional[List[str]] = None
    report_ids: Optional[List[str]] = None
    requests_per_minute: int = _DEFAULT_REQUESTS_PER_MINUTE


def hash_value(data):
    """
    Generate an MD5 hash for the given data.

    Note: This function uses hashlib.md5(usedforsecurity=False), which requires Python 3.9+.
    The usedforsecurity parameter explicitly indicates that MD5 is used for non-security
    purposes (generating consistent primary keys), not for cryptographic security.

    :param data: The data to hash
    :return: The MD5 hash as a hexadecimal string
    """
    dhash = hashlib.md5(usedforsecurity=False)
    dhash.update(data.encode())
    return dhash.hexdigest()


def normalize_key(key):
    """
    Normalize the key by replacing spaces and special characters with underscores and converting to lowercase.
    """
    key = re.sub(r"[^\w]", "_", key)  # Replace non-word characters with underscores
    return key.lower()


def flatten(dictionary, parent_key=False, separator="_"):
    """
    Turn a nested dictionary into a flattened dictionary with normalized keys.
    :param dictionary: The dictionary to flatten
    :param parent_key: The string to prepend to dictionary's keys
    :param separator: The string used to separate flattened keys
    :return: A flattened dictionary
    """
    items = []
    for key, value in dictionary.items():
        new_key = (
            normalize_key(str(parent_key) + separator + key) if parent_key else normalize_key(key)
        )
        if isinstance(value, MutableMapping):
            if not value.items():
                items.append((new_key, None))
            else:
                items.extend(flatten(value, new_key, separator).items())
        elif isinstance(value, list):
            items.append((new_key, json.dumps(value)))
        else:
            items.append((new_key, value))
    return dict(items)


class SmartsheetAPI:
    """Handles all Smartsheet API interactions"""

    BASE_URL = "https://api.smartsheet.com/2.0"

    def __init__(self, config: SmartsheetConfig):
        """
        Initialize the SmartsheetAPI client with configuration and session setup.

        Args:
            config (SmartsheetConfig): Configuration object containing API settings
                including access token, rate limits, and target resources.

        Sets up:
            - HTTP session with retry strategy
            - Authorization headers
            - Rate limiting tracking
        """
        self.config = config
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=_MAX_RETRIES,
            backoff_factor=_BACKOFF_FACTOR,
            status_forcelist=_RETRY_STATUS_CODES,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Authentication: Uses Bearer token authentication with Smartsheet API
        # To obtain an API token, log in to your Smartsheet account at https://app.smartsheet.com/
        self.headers = {"Authorization": f"Bearer {self.config.access_token}"}

        self.request_times = []

    def _check_rate_limit(self):
        """
        Implement rate limiting to stay within Smartsheet's API limits.

        This method tracks API request times and enforces a sliding window
        rate limit. If the rate limit is exceeded, it sleeps until enough
        time has passed to make another request.

        The rate limit is configured via config.requests_per_minute and
        defaults to 60 requests per minute.

        Side Effects:
            - May sleep the current thread if rate limit is exceeded
            - Updates internal request_times tracking
        """
        current_time = time.time()
        self.request_times = [t for t in self.request_times if current_time - t < 60]

        if len(self.request_times) >= self.config.requests_per_minute:
            sleep_time = 60 - (current_time - self.request_times[0])
            if sleep_time > 0:
                log.debug(f"Rate limit reached, sleeping for {sleep_time} seconds")
                time.sleep(sleep_time)

        self.request_times.append(current_time)

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """
        Make a GET request with rate limiting and retry logic.

        Args:
            endpoint (str): The API endpoint to call (e.g., 'sheets', 'sheets/123')
            params (Optional[Dict[str, Any]]): Query parameters to include in the request

        Returns:
            requests.Response: The HTTP response from the Smartsheet API

        Raises:
            requests.exceptions.HTTPError: If the request fails with a 4xx or 5xx status code
            requests.exceptions.RequestException: For other request-related errors

        Features:
            - Automatic rate limiting before each request
            - Retry logic for 429 (rate limit) responses
            - Automatic retry for 5xx server errors
            - Proper error handling and logging
        """
        self._check_rate_limit()
        url = f"{self.BASE_URL}/{endpoint}"
        response = self.session.get(url, headers=self.headers, params=params)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            log.debug(f"Rate limited, retrying after {retry_after} seconds")
            time.sleep(retry_after)
            return self.get(endpoint, params)

        response.raise_for_status()
        return response

    def get_sheets(self) -> List[Dict[str, Any]]:
        """
        Get all sheets or specific sheets based on configuration.

        If sheet_ids are configured, fetches only those specific sheets.
        Otherwise, fetches all sheets accessible to the API token.

        Returns:
            List[Dict[str, Any]]: List of sheet objects from the Smartsheet API.
                Each sheet object contains metadata like id, name, columns, etc.

        Raises:
            requests.exceptions.RequestException: If API requests fail

        Note:
            The returned sheets contain basic metadata. Use get_sheet_details()
            to fetch complete sheet data including rows and cell values.
        """
        if self.config.sheet_ids:
            sheets = []
            for sheet_id in self.config.sheet_ids:
                log.debug(f"Fetching specific sheet: {sheet_id}")
                response = self.get(f"sheets/{sheet_id}")
                sheets.append(response.json())
            return sheets
        else:
            log.debug("Fetching all accessible sheets")
            response = self.get("sheets")
            return response.json().get("data", [])

    def _fetch_paginated_data(
        self, endpoint: str, resource_id: str, modified_since: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch all data from a paginated endpoint with automatic pagination handling.

        Args:
            endpoint (str): The API endpoint (e.g., "sheets/{id}" or "reports/{id}")
            resource_id (str): The ID of the resource being fetched
            modified_since (Optional[str]): ISO 8601 timestamp to filter for
                rows modified after this time. If None, fetches all rows.

        Returns:
            Dict[str, Any]: Complete resource object with all rows from all pages

        Note:
            This method handles the common pagination pattern used by both
            sheets and reports. It automatically fetches all pages and
            combines the results into a single response object.
        """
        all_rows = []
        page = 1
        page_size = _DEFAULT_PAGE_SIZE

        while True:
            log.debug(f"Fetching page {page} for {endpoint.split('/')[0]} {resource_id}")
            params = {"page": page, "pageSize": page_size}
            if modified_since:
                params["modifiedSince"] = modified_since

            response = self.get(endpoint, params=params)
            data = response.json()

            rows = data.get("rows", [])
            if not rows:
                log.debug(f"No rows returned on page {page}, stopping pagination")
                break

            # Check for duplicate rows to prevent infinite loops
            new_row_ids = {row.get("id") for row in rows if row.get("id")}
            existing_row_ids = {row.get("id") for row in all_rows if row.get("id")}

            if new_row_ids.issubset(existing_row_ids):
                log.warning(f"Page {page} contains only duplicate rows, stopping pagination")
                break

            all_rows.extend(rows)
            log.debug(
                f"Retrieved {len(rows)} rows from page {page}, total so far: {len(all_rows)}"
            )

            # Check if we've reached the end (less rows than requested)
            if len(rows) < page_size:
                log.debug(
                    f"Received {len(rows)} rows (less than page size {page_size}), stopping pagination"
                )
                break

            page += 1

        # Update the data with all rows
        data["rows"] = all_rows
        resource_type = endpoint.split("/")[0].rstrip(
            "s"
        )  # "sheets" -> "sheet", "reports" -> "report"

        # Log unique row IDs to help debug pagination issues
        unique_row_ids = {row.get("id") for row in all_rows if row.get("id")}
        log.info(
            f"{resource_type.title()} {resource_id}: Retrieved {len(all_rows)} total rows ({len(unique_row_ids)} unique) across {page} pages"
        )

        return data

    def get_sheet_details(
        self, sheet_id: str, modified_since: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information for a specific sheet including rows and cell data.

        Args:
            sheet_id (str): The unique identifier of the sheet to fetch
            modified_since (Optional[str]): ISO 8601 timestamp to filter for
                rows modified after this time. If None, fetches all rows.

        Returns:
            Dict[str, Any]: Complete sheet object containing:
                - Sheet metadata (id, name, columns, etc.)
                - All rows with their cell values (with pagination)
                - Column definitions and types

        Raises:
            requests.exceptions.RequestException: If API request fails

        Note:
            This method fetches the complete sheet data including all rows,
            which can be large for sheets with many rows. The modified_since
            parameter helps reduce data transfer by only fetching recent changes.
            Uses pagination to ensure all rows are retrieved.
        """
        log.debug(f"Fetching sheet details for sheet ID: {sheet_id}")
        return self._fetch_paginated_data(f"sheets/{sheet_id}", sheet_id, modified_since)

    def get_reports(self) -> List[Dict[str, Any]]:
        """
        Get all reports based on configuration.

        If report_ids are configured, fetches only those specific reports.
        Otherwise, returns an empty list (reports must be explicitly specified).

        Returns:
            List[Dict[str, Any]]: List of report objects from the Smartsheet API.
                Each report object contains metadata like id, name, etc.
                Returns empty list if no report_ids are configured.

        Raises:
            requests.exceptions.RequestException: If API requests fail

        Note:
            Unlike sheets, reports must be explicitly specified by ID in the
            configuration. There is no "get all reports" endpoint available.
        """
        if self.config.report_ids:
            reports = []
            for report_id in self.config.report_ids:
                log.debug(f"Fetching specific report: {report_id}")
                response = self.get(f"reports/{report_id}")
                reports.append(response.json())
            return reports
        else:
            return []

    def get_report_details(self, report_id: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific report including rows and cell data.

        Args:
            report_id (str): The unique identifier of the report to fetch

        Returns:
            Dict[str, Any]: Complete report object containing:
                - Report metadata (id, name, etc.)
                - All rows with their cell values (with pagination)
                - Column definitions (may include virtual columns)

        Raises:
            requests.exceptions.RequestException: If API request fails

        Note:
            Reports have a similar structure to sheets but may include virtual
            columns and different column ID handling. This method fetches the
            complete report data including all rows using pagination.
        """
        log.debug(f"Fetching report details for report ID: {report_id}")
        return self._fetch_paginated_data(f"reports/{report_id}", report_id)


class DataTypeHandler:
    @staticmethod
    def parse_value(value: Any, column_type: Union[str, ColumnType]) -> Any:
        """
        Parse cell value based on column type from Smartsheet.

        Args:
            value (Any): The raw cell value from the Smartsheet API
            column_type (Union[str, ColumnType]): The type of the column
                (e.g., 'TEXT_NUMBER', 'DATE', 'NUMBER', etc.)

        Returns:
            Any: Parsed value with appropriate Python type:
                - None: For null/empty values
                - datetime: For DATE and DATETIME columns
                - bool: For CHECKBOX columns
                - Decimal: For NUMBER, CURRENCY, and PERCENT columns (maintains precision)
                - str: For all other column types

        Note:
            If parsing fails for a specific type, the original value is returned
            unchanged. This ensures data integrity even with unexpected values.
            Decimal is used for numeric types to avoid floating point precision issues
            in financial calculations.
        """
        if value is None:
            return None

        try:
            if isinstance(column_type, str):
                column_type = ColumnType(column_type)

            if column_type in [ColumnType.DATE, ColumnType.DATETIME]:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))

            if column_type == ColumnType.CHECKBOX:
                return bool(value)

            if column_type in [
                ColumnType.NUMBER,
                ColumnType.CURRENCY,
                ColumnType.PERCENT,
            ]:
                return Decimal(value)

            if column_type == ColumnType.PICKLIST:
                return str(value)

            return str(value)
        except (ValueError, TypeError):
            return value


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    if "api_token" not in configuration:
        raise ValueError("Missing required configuration value: api_token")

    if not configuration.get("api_token", "").strip():
        raise ValueError("Configuration value 'api_token' cannot be empty")

    if not configuration.get("sheets") and not configuration.get("reports"):
        raise ValueError("At least one of 'sheets' or 'reports' must be configured")


def _parse_config_items(config_string: str) -> Dict[str, str]:
    """
    Parse a comma-separated config string of 'id:name' pairs into a dictionary.

    Args:
        config_string: Comma-separated string of 'id:name' pairs
            (e.g., "123:Sheet1,456:Sheet2")

    Returns:
        Dict[str, str]: Dictionary mapping IDs to names
    """
    result = {}
    for item in config_string.split(","):
        if ":" in item:
            item_id, item_name = item.strip().split(":", 1)
            result[item_id.strip()] = item_name.strip()
    return result


def _make_table_name(prefix: str, configured_name: str) -> str:
    """
    Create a normalized table name from a prefix and configured name.

    Args:
        prefix: Table name prefix (e.g., "sheet" or "report")
        configured_name: The display name for the resource

    Returns:
        str: Normalized table name (e.g., "sheet_my_sheet_name")
    """
    return f"{prefix}_{configured_name.lower().replace(' ', '_').replace('-', '_')}"


def _delete_removed_rows(
    table_name: str, previous_row_ids: set, current_row_ids: set, resource_label: str
):
    """
    Detect and delete rows that existed previously but are no longer present.

    Args:
        table_name: Destination table name
        previous_row_ids: Set of row IDs from the previous sync
        current_row_ids: Set of row IDs from the current sync
        resource_label: Label for logging (e.g., "sheet 'My Sheet'")
    """
    deleted_row_ids = previous_row_ids - current_row_ids
    if deleted_row_ids:
        log.info(f"{resource_label}: Found {len(deleted_row_ids)} deleted rows")
        for deleted_row_id in deleted_row_ids:
            deleted_record_id = hash_value(str(deleted_row_id))
            log.debug(f"Deleting row for {resource_label}, row {deleted_row_id}")
            # The 'delete' operation is used to remove data from the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the primary key of the record to be deleted.
            op.delete(table_name, {"id": deleted_record_id})


def _process_sheet(
    sheet: Dict[str, Any],
    sheets_config: Dict[str, str],
    api: SmartsheetAPI,
    data_handler: DataTypeHandler,
    state_manager: StateManager,
):
    """
    Process a single sheet: fetch data, detect deletions, upsert rows, and checkpoint state.

    Args:
        sheet: Sheet metadata from the Smartsheet API
        sheets_config: Mapping of sheet IDs to configured display names
        api: SmartsheetAPI client instance
        data_handler: DataTypeHandler for parsing cell values
        state_manager: StateManager for tracking sync state
    """
    sheet_id = str(sheet["id"])
    sheet_name = sheet["name"]
    configured_name = sheets_config.get(sheet_id, sheet_name)
    table_name = _make_table_name("sheet", configured_name)

    try:
        sheet_state = state_manager.get_sheet_state(sheet_id)
        last_modified = sheet_state.get("last_modified")
        log.info(
            f"Sheet '{sheet_name}': State loaded - last_modified={last_modified or 'INITIAL_SYNC'}, row_count={len(sheet_state.get('row_ids', []))}"
        )
        sheet_data = api.get_sheet_details(sheet_id, last_modified)

        column_type_map = {col["id"]: col["type"] for col in sheet_data["columns"]}
        column_map = {col["id"]: col["title"] for col in sheet_data["columns"]}

        # For initial sync, start with a very old timestamp so any row is considered newer
        latest_sheet_modified = last_modified or "1970-01-01T00:00:00Z"

        sheet_rows = sheet_data.get("rows", [])
        if _TEST_MODE:
            sheet_rows = sheet_rows[:_TEST_ROW_LIMIT]
            log.debug(f"Test mode: Processing {len(sheet_rows)} rows for sheet '{sheet_name}'")

        log.info(f"Sheet '{sheet_name}': Found {len(sheet_rows)} total rows")
        log.info(
            f"Sheet '{sheet_name}': Using modifiedSince={last_modified or 'None (fetching all rows)'}"
        )

        current_row_ids = {str(row["id"]) for row in sheet_rows}
        previous_row_ids = set(sheet_state.get("row_ids", []))

        _delete_removed_rows(
            table_name, previous_row_ids, current_row_ids, f"Sheet '{sheet_name}'"
        )

        for row in sheet_rows:
            try:
                row_data = {
                    "row_id": str(row["id"]),
                    "sheet_id": sheet_id,
                    "sheet_name": sheet_name,
                }

                for cell in row["cells"]:
                    column_name = column_map.get(cell["columnId"], f"col_{cell['columnId']}")
                    column_type = column_type_map.get(cell["columnId"], ColumnType.TEXT_NUMBER)
                    value = cell.get("displayValue") or cell.get("value")
                    row_data[column_name] = data_handler.parse_value(value, column_type)

                row_record = flatten(row_data)
                row_record["id"] = hash_value(str(row["id"]))

                row_modified = row.get("modifiedAt", latest_sheet_modified)
                latest_sheet_modified = max(latest_sheet_modified, row_modified)

                log.debug(f"Upserting row for sheet '{sheet_name}', row {row['id']}")
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table_name, row_record)
            except Exception as e:
                log.warning(
                    f"Error processing row {row.get('id', 'unknown')} in sheet '{sheet_name}': {str(e)}"
                )
                continue

        current_row_id_list = list(current_row_ids)
        log.info(
            f"Sheet '{sheet_name}': Updating state - last_modified={latest_sheet_modified}, row_count={len(current_row_id_list)}"
        )
        state_manager.update_sheet_state(sheet_id, latest_sheet_modified, current_row_id_list)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state_manager.get_state())

    except requests.exceptions.RequestException as e:
        log.warning(f"Error processing sheet {sheet_name} ({sheet_id}): {str(e)}")


def _process_report(
    report: Dict[str, Any],
    reports_config: Dict[str, str],
    api: SmartsheetAPI,
    state_manager: StateManager,
):
    """
    Process a single report: fetch data, detect deletions, upsert rows, and checkpoint state.

    Args:
        report: Report metadata from the Smartsheet API
        reports_config: Mapping of report IDs to configured display names
        api: SmartsheetAPI client instance
        state_manager: StateManager for tracking sync state
    """
    report_id = str(report["id"])
    report_name = report["name"]
    configured_name = reports_config.get(report_id, report_name)
    table_name = _make_table_name("report", configured_name)

    try:
        report_data = api.get_report_details(report_id)
        column_map = {
            col.get("virtualId", col.get("id")): col["title"] for col in report_data["columns"]
        }

        log.info(f"Report '{report_name}': Found {len(report_data.get('rows', []))} total rows")

        report_rows = report_data.get("rows", [])
        current_row_ids = {str(row["id"]) for row in report_rows}
        report_state = state_manager.get_report_state(report_id)
        previous_row_ids = set(report_state.get("row_ids", []))

        _delete_removed_rows(
            table_name, previous_row_ids, current_row_ids, f"Report '{report_name}'"
        )

        for row in report_rows:
            row_data = {
                "row_id": str(row["id"]),
                "report_id": report_id,
                "report_name": report_name,
            }

            for cell in row["cells"]:
                column_name = column_map.get(
                    cell.get("virtualColumnId", cell.get("columnId")),
                    f"col_{cell.get('virtualColumnId', cell.get('columnId'))}",
                )
                value = cell.get("displayValue") or cell.get("value")
                row_data[column_name] = value

            row_record = flatten(row_data)
            row_record["id"] = hash_value(str(row["id"]))

            log.debug(f"Upserting row for report '{report_name}', row {row['id']}")
            op.upsert(table_name, row_record)

        current_row_id_list = list(current_row_ids)
        state_manager.update_report_state(report_id, current_row_id_list)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state_manager.get_state())

    except requests.exceptions.RequestException as e:
        log.warning(f"Error processing report {report_name} ({report_id}): {str(e)}")


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: Connectors : Smartsheet")

    # Validate configuration
    validate_configuration(configuration)

    # Parse configuration values from strings
    sheets_config = (
        _parse_config_items(configuration["sheets"]) if configuration.get("sheets") else {}
    )
    reports_config = (
        _parse_config_items(configuration["reports"]) if configuration.get("reports") else {}
    )

    requests_per_minute = int(
        configuration.get("requests_per_minute", str(_DEFAULT_REQUESTS_PER_MINUTE))
    )

    # Initialize configuration
    config = SmartsheetConfig(
        access_token=configuration["api_token"],
        sheet_ids=list(sheets_config.keys()) if sheets_config else None,
        report_ids=list(reports_config.keys()) if reports_config else None,
        requests_per_minute=requests_per_minute,
    )

    # Initialize components
    api = SmartsheetAPI(config)
    data_handler = DataTypeHandler()
    state_manager = StateManager(state)

    try:
        # Process sheets
        sheets = api.get_sheets()
        for sheet in sheets:
            _process_sheet(sheet, sheets_config, api, data_handler, state_manager)

        # Process reports
        reports = api.get_reports()
        for report in reports:
            _process_report(report, reports_config, api, state_manager)

        # Final checkpoint
        current_sync_time = datetime.now(timezone.utc).isoformat()
        final_state = state_manager.get_state()

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(final_state)

        log.debug(f"Sync completed successfully at {current_sync_time}")

    except Exception as e:
        log.error(f"Error during sync: {e}")
        raise


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    if "api_token" not in configuration:
        raise ValueError("Could not find 'api_token'")

    # Parse configuration values from strings
    sheets_config = (
        _parse_config_items(configuration["sheets"]) if configuration.get("sheets") else {}
    )
    reports_config = (
        _parse_config_items(configuration["reports"]) if configuration.get("reports") else {}
    )

    # Get sheet and report names to create dynamic schema
    config_obj = SmartsheetConfig(
        access_token=configuration["api_token"],
        sheet_ids=list(sheets_config.keys()) if sheets_config else None,
        report_ids=list(reports_config.keys()) if reports_config else None,
    )

    api = SmartsheetAPI(config_obj)
    schema_tables = []

    try:
        # Add schemas for sheets
        sheets = api.get_sheets()
        for sheet in sheets:
            sheet_id = str(sheet["id"])
            configured_name = sheets_config.get(sheet_id, sheet["name"])
            table_name = _make_table_name("sheet", configured_name)

            schema_tables.append(
                {
                    "table": table_name,
                    "primary_key": ["id"],
                    "columns": {
                        "id": "STRING",
                    },
                }
            )

        # Add schemas for reports
        reports = api.get_reports()
        for report in reports:
            report_id = str(report["id"])
            configured_name = reports_config.get(report_id, report["name"])
            table_name = _make_table_name("report", configured_name)

            schema_tables.append(
                {
                    "table": table_name,
                    "primary_key": ["id"],
                    "columns": {
                        "id": "STRING",
                    },
                }
            )

    except Exception as e:
        log.warning(f"Could not fetch dynamic schema, using default: {e}")
        # Fallback to default schema if API call fails
        schema_tables = [
            {
                "table": "sheet_default",
                "primary_key": ["id"],
                "columns": {
                    "id": "STRING",
                },
            }
        ]

    return schema_tables


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Test the connector locally
    connector.debug(configuration=configuration)
