"""
This connector fetches export metadata from Oktopost BI Export API and downloads
the associated CSV files for data synchronization.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading CSV files
import csv

# For reading and writing files
import io

# For handling regular expressions
import re

# For handling time delays
import time

# For handling ZIP files
import zipfile

# For handling date and time operations
from datetime import datetime, timezone

# For type hints
from typing import Dict, List, Any

# For handling URLs
from urllib.parse import urlparse

# For making HTTP requests
import requests

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Configuration constants
__BASE_URL = "https://api.oktopost.com/v2"
__API_TIMEOUT_SECONDS = 30
__MAX_RETRIES = 3
__RETRY_DELAY_SECONDS = 1  # Base delay for exponential backoff


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.

    Args:
        configuration: A dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: If any required configuration parameter is missing or invalid.
    """
    # Validate required configuration parameters
    required_configs = ["account_id", "api_key"]
    for key in required_configs:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate base_url format if provided
    base_url = configuration.get("base_url")
    if base_url:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid base_url format: {base_url}. Must start with 'http://' or 'https://'"
            )

        # Basic URL validation
        try:
            parsed = urlparse(base_url)
            if not parsed.netloc:
                raise ValueError(
                    f"Invalid base_url format: {base_url}. Must include a valid domain"
                )
        except Exception as e:
            raise ValueError(f"Invalid base_url format: {base_url}. {str(e)}")


def _should_retry_status_code(status_code: int) -> bool:
    """Check if a status code should trigger a retry."""
    return status_code == 429 or 500 <= status_code < 600


def _is_client_error(status_code: int) -> bool:
    """Check if a status code represents a client error that shouldn't be retried."""
    return 400 <= status_code < 500 and status_code != 429


def _handle_retry_delay(attempt: int) -> None:
    """Handle retry delay with exponential backoff."""
    if attempt > 0:
        delay = __RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
        log.info(f"Retrying after {delay:.1f}s (attempt {attempt + 1})")
        time.sleep(delay)


def _handle_retryable_error(attempt: int, error: Exception) -> None:
    """Handle retryable errors (timeout, connection)."""
    if attempt < __MAX_RETRIES:
        log.warning(f"{type(error).__name__} on attempt {attempt + 1}, retrying")
    else:
        raise RuntimeError(f"{type(error).__name__} after {__MAX_RETRIES + 1} attempts")


def _handle_http_error(attempt: int, error: requests.exceptions.HTTPError) -> None:
    """Handle HTTP errors with appropriate retry logic."""
    status_code = error.response.status_code

    if _is_client_error(status_code):
        raise RuntimeError(f"Client error {status_code}: {error.response.text}")

    if attempt < __MAX_RETRIES:
        log.warning(f"HTTP {status_code} on attempt {attempt + 1}, retrying")
    else:
        raise RuntimeError(f"HTTP {status_code} after {__MAX_RETRIES + 1} attempts")


def make_api_request_with_retry(
    url: str, headers: Dict[str, str], auth: tuple = None
) -> requests.Response:
    """Make API request with exponential backoff retry logic."""
    for attempt in range(__MAX_RETRIES + 1):
        try:
            _handle_retry_delay(attempt)

            response = requests.get(url, headers=headers, auth=auth, timeout=__API_TIMEOUT_SECONDS)

            # Check if we should retry based on status code
            if _should_retry_status_code(response.status_code):
                if attempt < __MAX_RETRIES:
                    log.warning(f"HTTP {response.status_code} on attempt {attempt + 1}, retrying")
                    continue
                else:
                    raise RuntimeError(
                        f"HTTP {response.status_code} after {__MAX_RETRIES + 1} attempts"
                    )

            response.raise_for_status()
            return response

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            _handle_retryable_error(attempt, e)
            continue

        except requests.exceptions.HTTPError as e:
            _handle_http_error(attempt, e)
            continue

    raise RuntimeError(f"Request failed after {__MAX_RETRIES + 1} attempts")


def extract_csv_from_zip(zip_content: bytes) -> List[Dict[str, Any]]:
    """
    Extract CSV files from a ZIP archive.

    Returns:
        List of dictionaries with keys "filename" and "content" for each CSV file found in the archive.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
            return [
                {
                    "filename": file_info.filename,
                    "content": zip_file.read(file_info.filename).decode("utf-8"),
                }
                for file_info in zip_file.filelist
                if file_info.filename.lower().endswith(".csv") and not file_info.is_dir()
            ]
    except Exception as e:
        log.error("Error extracting ZIP file", e)
        raise


def normalize_table_name(filename: str) -> str:
    """
    Normalize filename to generate consistent table names.

    Removes file extension, strips date prefix (YYYY-MM-DD-), replaces hyphens with underscores,
    converts to lowercase, and removes trailing underscores.
    """
    # Remove file extension
    name_without_ext = re.sub(r"\.[^.]*$", "", filename)
    return (
        re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name_without_ext).replace("-", "_").lower().rstrip("_")
    )


def process_csv_data(csv_content: str, filename: str, export_id: str) -> List[Dict[str, Any]]:
    """
    Process CSV content and return rows for upserting.

    Args:
        csv_content: CSV data as string.
        filename: Original filename for tracking.
        export_id: Export identifier.

    Returns:
        List of dictionaries with normalized column names and added export_id/source_filename fields.
    """
    try:
        return [
            {
                **{
                    key.strip()
                    .replace(" ", "_")
                    .replace('"', "")
                    .lower(): value.strip() if isinstance(value, str) else value
                    for key, value in row.items()
                },
                "export_id": export_id,
                "source_filename": filename,
            }
            for row in csv.DictReader(io.StringIO(csv_content))
        ]
    except Exception as e:
        log.error(f"Error processing CSV content from {filename}", e)
        raise


def _get_exports_to_process(
    configuration: Dict[str, str],
    base_url: str,
    auth: tuple,
    headers: Dict[str, str],
    current_sync: str,
) -> List[Dict[str, Any]]:
    """Get the list of exports to process, either from test mode or API."""
    test_export_id = configuration.get("test_export_id")

    if test_export_id:
        log.info(f"Testing with specific export ID: {test_export_id}")
        return [{"Id": test_export_id}]

    # Fetch exports from API
    response = make_api_request_with_retry(f"{base_url}/bi-export", headers, auth)
    exports_data = response.json()

    if not exports_data.get("Result"):
        log.warning("API returned Result=false for export list")
        return []

    exports = exports_data.get("Exports", [])
    log.info(f"Found {len(exports)} total exports")

    # Store export list metadata
    for export in exports:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="export_list_metadata", data={**export, "sync_timestamp": current_sync})

    active_exports = [export for export in exports if export.get("Status") == "active"]
    log.info(f"Found {len(active_exports)} active exports")
    return active_exports


def _process_export_metadata(
    export: Dict[str, Any], base_url: str, headers: Dict[str, str], auth: tuple, current_sync: str
) -> dict[str, str | None | Any] | None:
    """Process export metadata and return export details."""
    export_id = export.get("Id")
    if not export_id:
        log.warning("Export missing ID, skipping")
        return None

    log.info(f"Processing export {export_id}")

    # Fetch detailed export information
    detail_url = f"{base_url}/bi-export/{export_id}"
    try:
        detail_response = make_api_request_with_retry(detail_url, headers, auth)
        detail_data = detail_response.json()
    except Exception as e:
        log.warning(f"Failed to fetch details for export {export_id}: {str(e)}, skipping")
        return None

    if not detail_data.get("Result"):
        log.warning(f"API returned Result=false for export {export_id}")
        return None

    export_detail = detail_data.get("Export", {})

    # Store export metadata
    file_url = export_detail.get("LastRunFile")
    source_filename = urlparse(file_url).path.split("/")[-1] if file_url else None
    op.upsert(
        table="active_export_metadata",
        data={
            **export_detail,
            "sync_timestamp": current_sync,
            "source_filename": source_filename,
        },
    )

    return {"export_id": export_id, "file_url": file_url, "source_filename": source_filename}


def _process_zip_file(file_response: requests.Response, export_id: str) -> None:
    """Process a ZIP file by extracting and processing CSV files."""
    original_filename = urlparse(file_response.url).path.split("/")[-1]

    log.info(f"File {original_filename} is a ZIP archive, extracting CSV files")
    csv_files = extract_csv_from_zip(file_response.content)

    if not csv_files:
        log.warning(f"No CSV files found in ZIP archive {original_filename}")
        return

    for csv_file in csv_files:
        table_name = normalize_table_name(original_filename)
        log.info(f"Processing CSV data from {csv_file['filename']} into table: {table_name}")

        rows = process_csv_data(csv_file["content"], original_filename, export_id)

        for row in rows:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted,
            op.upsert(table=table_name, data=row)
        log.info(f"Processed {len(rows)} rows for table {table_name} from {csv_file['filename']}")


def _process_csv_file(file_response: requests.Response, export_id: str) -> None:
    """Process a single CSV file."""
    original_filename = urlparse(file_response.url).path.split("/")[-1]
    table_name = normalize_table_name(original_filename)
    log.info(f"Processing CSV data into table: {table_name}")

    rows = process_csv_data(file_response.text, original_filename, export_id)

    for row in rows:
        op.upsert(table=table_name, data=row)
    log.info(f"Processed {len(rows)} rows for table {table_name}")


def _process_export_file(export_info: Dict[str, Any]) -> None:
    """Process the file associated with an export."""
    export_id = export_info["export_id"]
    file_url = export_info["file_url"]

    if not file_url:
        return

    log.info(f"Downloading file for export {export_id}")

    try:
        file_response = make_api_request_with_retry(file_url, {})
        original_filename = urlparse(file_url).path.split("/")[-1]

        if original_filename.lower().endswith(".zip"):
            _process_zip_file(file_response, export_id)
        else:
            _process_csv_file(file_response, export_id)

    except Exception as e:
        log.error(f"Error processing file for export {export_id}", e)


def update(configuration: Dict[str, str], state: Dict[str, Any]):
    """
     Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Source Examples - Oktopost")
    try:
        # Validate configuration first
        validate_configuration(configuration=configuration)

        # Setup configuration and authentication
        account_id = configuration.get("account_id")
        api_key = configuration.get("api_key")
        base_url = configuration.get("base_url", __BASE_URL)
        auth = (account_id, api_key)
        headers = {"Content-Type": "application/json"}
        current_sync = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        log.info(f"Starting sync. Current sync: {current_sync}")

        # Get exports to process
        exports_to_process = _get_exports_to_process(
            configuration, base_url, auth, headers, current_sync
        )

        if not exports_to_process:
            log.info("No exports to process")
            return

        # Process each export
        for export in exports_to_process:
            export_info = _process_export_metadata(export, base_url, headers, auth, current_sync)

            if export_info:
                _process_export_file(export_info)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state={"last_sync_timestamp": current_sync})
        log.info("Sync completed successfully")

    except Exception as e:
        log.error("Error in update function", e)
        raise


def schema(configuration: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [{"table": "active_export_metadata"}, {"table": "export_list_metadata"}]


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
