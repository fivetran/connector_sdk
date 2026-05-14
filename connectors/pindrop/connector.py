"""Pindrop Connector for Fivetran
This connector fetches nightly reports from Pindrop API and syncs them to the destination.
It supports multiple report types: blacklist, calls, audit, cases, account_risk, enrollment, removal_list.
On initial sync, it fetches the last month's worth of data. On incremental syncs, it looks back based on the configured days.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# json: For parsing configuration files and JSON responses
import json

# requests: For making HTTP API calls to Pindrop
import requests

# datetime: For date/time operations and report date calculations
from datetime import datetime, timedelta

# time: For rate limiting and retry delays
import time

# csv: For parsing CSV report data from Pindrop API
import csv

# io: For handling CSV data as file-like objects
import io

# Configuration constants needed for the connector
__LOOKBACK_DAYS = 1  # Number of days to look back for reports (set to 1 for most recent day only)
__INITIAL_SYNC_START_DATE = "2025-07-07"  # Start date for initial sync
__REPORT_TYPES = [
    "blacklist",
    "calls",
    "audit",
    "cases",
    "account_risk",
    "enrollment",
]  # All available report types
__BASE_URL = "https://api.pindrop.com"  # Base URL for Pindrop API
__RATE_LIMIT_DELAY = 1  # Rate limit delay in seconds between requests
__MAX_RETRIES = 3  # Maximum number of retries for API requests


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    required_configs = ["client_id", "client_secret"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


class OAuth2TokenManager:
    """
    OAuth2 token management class for handling authentication with Pindrop API.
    Manages token lifecycle including requesting, storing, and refreshing access tokens.
    """

    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.token_url = "https://auth.us2.pindrop.com/oauth2/token"
        self.access_token = None
        self.token_expires_at = None

    def get_access_token(self, max_retries: int) -> str:
        """Get a valid access token, refreshing if necessary"""
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token

        return self._request_new_token(max_retries=max_retries)

    def _request_new_token(self, max_retries: int) -> str:
        """Request a new access token using client credentials flow with retry logic"""
        log.info("Requesting new OAuth2 access token")

        token_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        for attempt in range(max_retries):
            try:
                log.info(f"OAuth2 token request attempt {attempt + 1}/{max_retries}")

                response = requests.post(
                    self.token_url, data=token_data, headers=headers, timeout=30
                )

                if response.status_code == 200:
                    token_response = response.json()
                    self.access_token = token_response["access_token"]

                    # Calculate expiration time (subtract 60 seconds for buffer)
                    expires_in = token_response.get("expires_in", 3600)  # Default to 1 hour
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

                    log.info(
                        f"Successfully obtained access token, expires at {self.token_expires_at}"
                    )
                    return self.access_token
                else:
                    error_msg = f"Failed to obtain access token. Status: {response.status_code}, Response: {response.text}"
                    log.warning(f"Attempt {attempt + 1}/{max_retries}: {error_msg}")

                    if attempt < max_retries - 1:
                        # Exponential backoff: wait 2^attempt seconds
                        wait_time = 2**attempt
                        log.info(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        log.error(
                            f"OAuth2 token request failed after {max_retries} attempts: {error_msg}"
                        )
                        raise RuntimeError(
                            f"Failed to obtain access token after {max_retries} attempts. Final error: {error_msg}"
                        )

            except requests.exceptions.RequestException as e:
                error_msg = f"OAuth2 token request failed: {str(e)}"
                log.warning(f"Attempt {attempt + 1}/{max_retries}: {error_msg}")

                if attempt < max_retries - 1:
                    # Exponential backoff: wait 2^attempt seconds
                    wait_time = 2**attempt
                    log.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    log.error(
                        f"OAuth2 token request failed after {max_retries} attempts: {error_msg}"
                    )
                    raise RuntimeError(
                        f"Failed to obtain access token after {max_retries} attempts. Final error: {error_msg}"
                    )

        # This should never be reached due to the logic above, but included for completeness
        raise RuntimeError(f"Failed to obtain access token after {max_retries} attempts")


def _process_response(response, expect_csv: bool):
    """
    Process API response based on status code and expected format.
    Args:
        response: HTTP response object
        expect_csv: Whether to expect CSV response
    Returns:
        Processed response data (JSON dict or CSV text)
    Raises:
        RuntimeError: If authentication fails or other error occurs
    """
    if response.status_code == 200:
        return response.text if expect_csv else response.json()
    elif response.status_code == 404:
        log.warning(f"No data found for URL: {response.url}")
        return {"data": []} if not expect_csv else ""
    elif response.status_code == 401:
        raise RuntimeError("Authentication failed (401). Token may be expired.")
    else:
        raise RuntimeError(
            f"API request failed with status {response.status_code}: {response.text}"
        )


def make_api_request(url: str, headers: dict, max_retries: int = 3, expect_csv: bool = False):
    """
    Make API request with retry logic and error handling.
    Implements exponential backoff for failed requests and handles various HTTP status codes.
    Args:
        url: API endpoint URL
        headers: Request headers
        max_retries: Maximum number of retry attempts
        expect_csv: Whether to expect CSV response
    Returns:
        API response as dictionary or raw text for CSV
    Raises:
        RuntimeError: if API request fails after all retries
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            return _process_response(response, expect_csv)
        except (requests.exceptions.RequestException, RuntimeError) as e:
            log.warning(f"Request attempt {attempt + 1} failed: {str(e)}")

            if attempt < max_retries - 1:
                wait_time = 2**attempt
                log.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)  # Exponential backoff
                continue
            else:
                if isinstance(e, RuntimeError) and "Authentication failed" in str(e):
                    # Let caller handle authentication errors
                    raise
                else:
                    raise RuntimeError(
                        f"API request failed after {max_retries} attempts: {str(e)}"
                    )

    raise RuntimeError(f"API request failed after {max_retries} attempts")


def parse_csv_data(csv_data: str, report_type: str, report_date: str):
    """
    Parse CSV data into list of dictionaries.
    Converts raw CSV string data into structured records with metadata.
    Args:
        csv_data: Raw CSV string
        report_type: Type of report
        report_date: Date of report
    Returns:
        List of record dictionaries
    """
    if not csv_data or csv_data.strip() == "":
        log.info(f"Empty CSV data for {report_type} report on {report_date}")
        return []

    try:
        # Use StringIO to treat the string as a file-like object
        csv_file = io.StringIO(csv_data)
        csv_reader = csv.DictReader(csv_file)

        records = []
        for i, row in enumerate(csv_reader):
            # Convert the row to a regular dictionary and clean up
            record = dict(row)

            # Add metadata to each record
            record["report_date"] = report_date
            record["report_type"] = report_type.lower()
            record["_fivetran_synced"] = datetime.now().isoformat()

            # Ensure we have an ID field for primary key
            if "id" not in record:
                record["id"] = f"{report_type.lower()}_{report_date}_{i}"

            # Clean up any None values or empty strings
            cleaned_record = {}
            for key, value in record.items():
                if value is None:
                    cleaned_record[key] = ""
                elif isinstance(value, str):
                    cleaned_record[key] = value.strip()
                else:
                    cleaned_record[key] = value

            records.append(cleaned_record)

        log.info(
            f"Successfully parsed {len(records)} records from CSV for {report_type} on {report_date}"
        )
        return records

    except Exception as e:
        log.error(f"Failed to parse CSV data for {report_type} on {report_date}", e)
        return []


def fetch_report_data(token_manager: OAuth2TokenManager, report_type: str, report_date: str):
    """
    Fetch data for a specific report using the new API endpoint structure (CSV format).
    Retrieves report data from Pindrop API and parses it into structured records.
    Args:
        token_manager: OAuth2 token manager
        report_type: Type of report to fetch
        report_date: Date for the report (YYYY-MM-DD)
    Returns:
        List of report records
    """
    # Use the new API endpoint structure
    url = f"https://api2.us2.pindrop.com/v1/nightly_reports/{report_type.lower()}/{report_date}"

    # Get fresh access token
    access_token = token_manager.get_access_token(max_retries=__MAX_RETRIES)

    # Simple headers matching the working Postman request
    headers = {"Authorization": f"Bearer {access_token}"}

    log.info(f"Fetching {report_type} report for {report_date}")

    try:
        # Fetch CSV data
        csv_data = make_api_request(url, headers, expect_csv=True)

        # Parse CSV data into records
        records = parse_csv_data(csv_data, report_type, report_date)

        log.info(f"Successfully fetched {len(records)} records for {report_type} on {report_date}")
        return records

    except RuntimeError as e:
        if "Authentication failed" in str(e):
            # Try to refresh token and retry once
            log.warning("Authentication failed, attempting to refresh token")
            try:
                access_token = token_manager._request_new_token(max_retries=__MAX_RETRIES)
                headers["Authorization"] = f"Bearer {access_token}"
                csv_data = make_api_request(url, headers, max_retries=1, expect_csv=True)

                # Parse CSV data into records
                records = parse_csv_data(csv_data, report_type, report_date)

                log.info(
                    f"Successfully fetched {len(records)} records for {report_type} on {report_date} after token refresh"
                )
                return records

            except Exception as retry_error:
                log.error(
                    f"Failed to fetch {report_type} report for {report_date} even after token refresh",
                    retry_error,
                )
                return []
        else:
            log.error(f"Failed to fetch {report_type} report for {report_date}", e)
            return []
    except Exception as e:
        log.error(f"Failed to fetch {report_type} report for {report_date}", e)
        return []


def generate_reports_to_process(state: dict, is_initial_sync: bool):
    """
    Generate all report combinations for the specified date range.
    Creates a list of reports to process based on sync type and existing state.
    Args:
        state: Current state dictionary
        is_initial_sync: Whether this is initial sync
    Returns:
        List of report dictionaries with date, report_type, and status
    """
    processed_reports = state.get("processed_reports", {})
    reports_to_process = []

    # Determine date range
    today = datetime.now().date()

    if is_initial_sync:
        # Parse the initial sync start date
        try:
            start_date = datetime.strptime(__INITIAL_SYNC_START_DATE, "%Y-%m-%d").date()
            log.info(f"Initial sync: generating reports from {start_date} to {today}")
        except ValueError as e:
            log.error(
                f"Invalid INITIAL_SYNC_START_DATE format: {__INITIAL_SYNC_START_DATE}. Expected YYYY-MM-DD",
                e,
            )
            return []
    else:
        # Incremental sync: lookback configured days
        start_date = today - timedelta(days=__LOOKBACK_DAYS)
        log.info(
            f"Incremental sync: generating reports from {start_date} to {today} ({__LOOKBACK_DAYS} days)"
        )

    # Generate all combinations of dates and report types
    current_date = start_date
    while current_date <= today:
        date_str = current_date.strftime("%Y-%m-%d")

        for report_type in __REPORT_TYPES:
            # Check if we've already processed this report type up to or beyond this date
            if report_type in processed_reports:
                last_processed_date = processed_reports[report_type].get("last_processed_date")
                if last_processed_date and date_str <= last_processed_date:
                    log.info(
                        f"Skipping {report_type} report for {date_str} - already processed up to {last_processed_date}"
                    )
                    continue

            # Create report dictionary
            report = {
                "date": date_str,
                "report_type": report_type.upper(),
                "status": "COMPLETE",  # Assume all reports are complete since we're generating them
            }

            reports_to_process.append(report)
            log.info(f"Will process {report_type} report for {date_str}")

        current_date += timedelta(days=1)

    log.info(f"Generated {len(reports_to_process)} reports to process")
    return reports_to_process


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    schemas = []
    for report_type in __REPORT_TYPES:
        schemas.append(
            {
                "table": f"{report_type}",  # Name of the table in the destination, required.
                "primary_key": (
                    ["report_date", "id"]
                    if report_type != "blacklist"
                    else ["report_date", "phone_number"]
                ),  # Primary key column(s) for the table, optional.
                # For any columns whose names are not provided here, their data types will be inferred
            }
        )

    return schemas


def _process_report(
    token_manager: OAuth2TokenManager, report: dict, latest_dates_by_type: dict
) -> int:
    """
    Process a single report and upsert records to the destination.

    Args:
        token_manager: OAuth2 token manager for API authentication
        report: Dictionary containing report details (date, type)
        latest_dates_by_type: Dictionary to track latest processed dates

    Returns:
        Number of records processed for this report
    """
    report_date = report.get("date")
    report_type = report.get("report_type", "").lower()
    table_name = f"{report_type}"

    try:
        # Fetch data for this report
        records = fetch_report_data(token_manager, report_type, report_date)

        # Upsert records to destination
        for record in records:
            op.upsert(table=table_name, data=record)

        # Check if this is a newer date than what we have for this report type
        is_newer_report_type = report_type not in latest_dates_by_type
        is_newer_report_date = report_date > latest_dates_by_type[report_type]

        # Track the latest date for this report type
        if is_newer_report_date or is_newer_report_type:
            latest_dates_by_type[report_type] = report_date

        log.info(
            f"Completed processing {report_type} report for {report_date} - {len(records)} records"
        )

        # Rate limiting
        if __RATE_LIMIT_DELAY > 0:
            time.sleep(__RATE_LIMIT_DELAY)

        return len(records)

    except Exception as e:
        log.error(f"Error processing {report_type} for {report_date}", e)
        return 0


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

    log.info("Starting Pindrop connector sync")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    client_id = configuration["client_id"]
    client_secret = configuration["client_secret"]

    # Initialize OAuth2 token manager
    token_manager = OAuth2TokenManager(client_id, client_secret, __BASE_URL)

    # Get the state variable for the sync, if needed
    # Determine if this is initial sync
    is_initial_sync = not state or not state.get("last_sync_date")

    log.info(f"Sync type: {'Initial' if is_initial_sync else 'Incremental'}")

    try:
        # Generate reports to process based on date range and report types
        reports_to_process = generate_reports_to_process(state, is_initial_sync)

        if not reports_to_process:
            log.info("No new reports to process")
            return

        log.info(f"Processing {len(reports_to_process)} reports")

        total_records = 0
        processed_reports = state.get("processed_reports", {})

        # Track the latest date processed for each report type
        latest_dates_by_type = {}

        # Process each report
        for report in reports_to_process:
            records_processed = _process_report(token_manager, report, latest_dates_by_type)
            total_records += records_processed

        # Update processed_reports with only the latest date for each report type
        for report_type, latest_date in latest_dates_by_type.items():
            processed_reports[report_type] = {
                "last_processed_date": latest_date,
                "processed_at": datetime.now().isoformat(),
            }

        # Update state with the current sync time for the next run
        new_state = {
            "last_sync_date": datetime.now().date().strftime("%Y-%m-%d"),
            "last_sync_timestamp": datetime.now().isoformat(),
            "total_records_synced": total_records,
            "processed_reports": processed_reports,
            "sync_type": "initial" if is_initial_sync else "incremental",
        }

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state=new_state)

        log.info(f"Sync completed successfully. Total records synced: {total_records}")

    except Exception as e:
        # In case of an exception, raise a runtime error
        log.error("Sync failed with error", e)
        raise RuntimeError(f"Failed to sync Pindrop data: {str(e)}")


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


# Jul 08, 2025 03:34:38 PM: INFO Fivetran-Tester-Process: SYNC PROGRESS:
# Operation       | Calls
# ----------------+------------
# Upserts         | 44962
# Updates         | 0
# Deletes         | 0
# Truncates       | 0
# SchemaChanges   | 6
# Checkpoints     | 1

# Jul 08, 2025 03:34:38 PM: INFO Fivetran-Tester-Process: Sync SUCCEEDED
