"""
This is an example connector syncing Google Trends data for the entire configured time period on every sync.
Each sync creates a complete snapshot of the trends data, allowing you to track how
Google Trends data changes over time.

Strategy:
- Pull ENTIRE timeframe each sync (e.g., "2024-01-01 today" or "today 12-m")
- No cursor tracking - full refresh every time
- Use exponential backoff retry with randomization (60-90s, 120-150s, 180-210s)
- Append-only design with sync_timestamp tracks historical changes
- search_id groups keywords from same search (results are relative to each other)

See the Technical Reference documentation: https://fivetran.com/docs/connectors/connector-sdk/technical-reference
See the Best Practices documentation: https://fivetran.com/docs/connectors/connector-sdk/best-practices
"""

# Used for generating unique hash-based identifiers for search configurations
import hashlib

# Used for parsing JSON configuration strings
import json

# Used for adding random jitter to retry delays to prevent thundering herd
import random

# Used for sleep delays between retries and API rate limiting
import time

# Used for timestamp generation and timezone handling
from datetime import datetime, timezone

# Used for type hints in function signatures
from typing import List

# Used for detailed error logging and debugging
import traceback

# Used for catching specific HTTP and network exceptions from pytrends
import requests.exceptions

# Import required classes  from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import pytrends for Google Trends API access
# Main class for making requests to Google Trends
from pytrends.request import TrendReq

# Data manipulation library used by pytrends for returning data
import pandas as pd

# Default searches constant defined in config.py
from config import SEARCHES

# Suppress pandas FutureWarning from pytrends
# Used to filter out unwanted warning messages
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="pytrends")
pd.set_option("future.no_silent_downcasting", True)

__MAX_RETRIES = 5  # Number of retry attempts
__RETRY_BASE_DELAY = 60  # Base delay in seconds for exponential backoff (1 minute)
__RETRY_JITTER = 30  # Random jitter to add on top of base delay (30 seconds)
__INTER_REGION_DELAY = 5  # Delay in seconds between regions to avoid rate limiting


def get_searches(configuration: dict):
    """
    Retrieve search configurations from either the connector configuration or the Python config file.

    This function provides flexibility by allowing searches to be defined either in the Fivetran
    connector configuration (as JSON) or in the local config.py file. This is useful for
    development and testing without needing to update the Fivetran configuration.

    Args:
        configuration: A dictionary containing the connector configuration settings.

    Returns:
        A list of search configuration dictionaries, each containing keywords, regions, and timeframe.
    """
    # Get searches from configuration or use Python config
    if "searches" in configuration:
        searches_raw = configuration.get("searches")
        searches = json.loads(searches_raw) if isinstance(searches_raw, str) else searches_raw
        log.info("Using searches from configuration.json")
    else:
        # Use searches from Python config file
        searches = SEARCHES
        log.info("Using searches from config.py")
    return searches


def _validate_region(region: dict, search_idx: int, region_idx: int) -> None:
    """
    Validate that a region configuration has the required structure and fields.

    A valid region must be a dictionary with 'name' and 'code' fields. The code can be
    an empty string for worldwide searches.

    Args:
        region: The region configuration dictionary to validate.
        search_idx: Index of the parent search (for error messages).
        region_idx: Index of this region within the search (for error messages).

    Raises:
        ValueError: If the region is not a dictionary or is missing required fields.
    """
    if not isinstance(region, dict):
        raise ValueError(
            f"Search {search_idx}, Region {region_idx}: must be an object with 'name' and 'code'"
        )
    if "name" not in region or "code" not in region:
        raise ValueError(
            f"Search {search_idx}, Region {region_idx}: missing 'name' or 'code' field"
        )


def _validate_search(search: dict, search_idx: int) -> None:
    """
    Validate that a search configuration has the required structure and fields.

    A valid search must contain:
    - keywords: Non-empty list of 1-5 keywords (Google Trends API limit)
    - regions: Non-empty list of region dictionaries
    - timeframe: Non-empty string in supported format

    Args:
        search: The search configuration dictionary to validate.
        search_idx: Index of this search (for error messages).

    Raises:
        ValueError: If the search is invalid or missing required fields.
    """
    if not isinstance(search, dict):
        raise ValueError(f"Search {search_idx}: must be an object")

    keywords = search.get("keywords")
    if not keywords or not isinstance(keywords, list) or len(keywords) == 0:
        raise ValueError(f"Search {search_idx}: 'keywords' must be a non-empty list")
    if len(keywords) > 5:
        raise ValueError(
            f"Search {search_idx}: Google Trends supports maximum 5 keywords per search"
        )

    regions = search.get("regions")
    if not regions or not isinstance(regions, list) or len(regions) == 0:
        raise ValueError(f"Search {search_idx}: 'regions' must be a non-empty list")
    for region_idx, region in enumerate(regions):
        _validate_region(region, search_idx, region_idx)

    timeframe = search.get("timeframe")
    if not timeframe or not isinstance(timeframe, str):
        raise ValueError(
            f"Search {search_idx}: 'timeframe' must be a non-empty string (e.g., '2024-01-01 today' or 'today 12-m')"
        )

    search_name = search.get("name", f"Search {search_idx + 1}")
    log.info(
        f"Validated search '{search_name}': {len(keywords)} keyword(s), "
        f"{len(regions)} region(s), timeframe: {timeframe}"
    )


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector
    has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    searches = get_searches(configuration)

    if not isinstance(searches, list) or len(searches) == 0:
        raise ValueError("'searches' must be a non-empty list")

    for search_idx, search in enumerate(searches):
        _validate_search(search, search_idx)


def generate_search_id(search_name: str, keywords: List[str], timeframe: str) -> str:
    """
    Generate a unique, human-readable search ID.

    The search_id groups keywords from the same search together since Google Trends
    results are relative to each other. This allows proper analysis of comparative trends.

    Format: {readable_name}_{timeframe_sanitized}_{hash}
    Example: etl_tools_comparison_2024-01-01_2026-01-27_a1b2c3d4

    Args:
        search_name: Name of the search from configuration
        keywords: List of keywords in this search
        timeframe: Timeframe string (e.g., "2024-01-01 today" or "today 12-m")

    Returns:
        A unique, human-readable search identifier
    """
    # Sanitize search name for use in identifier
    readable_part = search_name.lower().replace(" ", "_").replace("/", "_")
    # Remove non-alphanumeric characters except underscore
    readable_part = "".join(c for c in readable_part if c.isalnum() or c == "_")

    # Sanitize timeframe for readability
    timeframe_sanitized = timeframe.replace(" ", "_").replace("/", "_")

    # Create hash of the full search configuration for uniqueness
    # Sort keywords for consistency
    config_string = f"{sorted(keywords)}_{timeframe}"
    hash_digest = hashlib.md5(config_string.encode()).hexdigest()[:8]

    # Combine into search_id
    search_id = f"{readable_part}_{timeframe_sanitized}_{hash_digest}"

    return search_id


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
            "table": "google_trends",
            "primary_key": [
                "search_id",
                "keyword",
                "date",
                "region_code",
                "sync_timestamp",
            ],
            "columns": {
                "search_id": "STRING",
                "keyword": "STRING",
                "date": "UTC_DATETIME",
                "region_name": "STRING",
                "region_code": "STRING",
                "sync_timestamp": "UTC_DATETIME",
                "interest": "INT",
                "timeframe": "STRING",
                "is_partial": "BOOLEAN",
            },
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A Dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Connectors - Google trends example")

    # Validate the configuration
    validate_configuration(configuration)

    # Get searches from configuration or use Python config
    searches = get_searches(configuration)

    # Capture sync timestamp for this run
    sync_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    log.info(f"Starting Google Trends sync with {len(searches)} search group(s)")
    log.info(f"  Sync timestamp: {sync_timestamp}")

    # Initialize pytrends with custom headers
    pytrends = initialize_pytrends()

    # Track statistics
    total_records_synced = 0
    sync_start_time = time.time()
    failed_regions = []
    total_regions = 0  # Track total regions attempted

    try:
        # Process each search group
        for search_idx, search in enumerate(searches):
            total_records_synced, total_regions = process_search_group(
                search_idx,
                search,
                sync_timestamp,
                pytrends,
                failed_regions,
                total_records_synced,
                total_regions,
            )

        # Calculate sync duration
        sync_duration = time.time() - sync_start_time

        # Check if sync should be considered a failure
        if total_regions > 0 and len(failed_regions) == total_regions:
            # All regions failed
            log.error(
                f"Sync failed: All {total_regions} region(s) failed after {__MAX_RETRIES} retry attempts"
            )
            log.error(f"Failed regions: {', '.join(failed_regions)}")
            raise RuntimeError(
                f"All {total_regions} regions failed. No data was synced successfully."
            )

        if total_records_synced == 0:
            # No records synced at all
            log.error(f"Sync failed: 0 records synced from {total_regions} region(s)")
            if failed_regions:
                log.error(f"Failed regions: {', '.join(failed_regions)}")
            raise RuntimeError(
                f"Sync failed: 0 records synced. {len(failed_regions)}/{total_regions} regions failed."
            )

        # Update state with sync metadata
        new_state = {
            "last_sync_timestamp": sync_timestamp,
            "total_records_synced": total_records_synced,
            "failed_regions": failed_regions,
        }

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(new_state)

        if failed_regions:
            log.warning(
                f"Sync completed with partial failures. {len(failed_regions)}/{total_regions} "
                f"region(s) failed: {', '.join(failed_regions)}"
            )
            log.info(
                f"Successfully synced {total_records_synced} records from "
                f"{total_regions - len(failed_regions)}/{total_regions} regions "
                f"in {sync_duration:.2f} seconds"
            )
        else:
            log.info("Sync completed successfully!")
            log.info(
                f"Synced {total_records_synced} records from {total_regions} region(s) in {sync_duration:.2f} seconds"
            )

    except RuntimeError as e:
        log.error(f"Fatal error during sync: {str(e)}")
        # Re-raise RuntimeError without wrapping to avoid nested exception messages
        raise
    except Exception as e:
        log.error(f"Fatal error during sync: {str(e)}")
        # Wrap unexpected exceptions in a RuntimeError to provide a consistent error surface
        raise RuntimeError(f"Failed to sync Google Trends data: {str(e)}")


def initialize_pytrends():
    """
    Initialize a PyTrends request object with custom headers and configuration.

    This function creates a TrendReq instance configured with:
    - Custom browser headers to mimic a real browser request
    - UTC timezone (tz=0) for consistent timestamp handling
    - Custom timeout values (10s connection, 25s read)
    - Manual retry handling (retries=0) since we implement our own exponential backoff

    Returns:
        TrendReq: An initialized PyTrends request object ready to make API calls.
    """
    # Initialize pytrends with custom headers
    custom_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://trends.google.com/",
    }

    pytrends = TrendReq(
        hl="en-US",
        tz=0,
        timeout=(10, 25),
        retries=0,  # We handle retries manually
        requests_args={"headers": custom_headers},
    )
    return pytrends


def process_search_group(
    search_idx,
    search,
    sync_timestamp,
    pytrends,
    failed_regions,
    total_records_synced,
    total_regions,
):
    """
    Process a single search group by fetching data for all its regions.

    A search group represents a set of keywords that should be compared against each other,
    along with the regions and timeframe for the comparison. All keywords in a search group
    are fetched together to ensure their relative interest scores are comparable.

    Args:
        search_idx: Index of this search in the searches list.
        search: Dictionary containing keywords, regions, timeframe, and name.
        sync_timestamp: ISO timestamp for this sync run.
        pytrends: Initialized TrendReq instance for making API calls.
        failed_regions: List to accumulate names of regions that failed.
        total_records_synced: Running count of records synced so far.
        total_regions: Running count of total regions attempted.

    Returns:
        Tuple of (total_records_synced, total_regions) with updated counts.
    """
    search_name = search.get("name", f"Search {search_idx + 1}")
    keywords = search.get("keywords")
    regions = search.get("regions")
    timeframe = search.get("timeframe")

    # Convert "today" keyword to actual date if present in timeframe
    # Google Trends only accepts:
    # - Relative format: "today 12-m", "today 3-m"
    # - Absolute format: "2024-01-01 2026-01-21" (both as actual dates)
    # NOT: "2024-01-01 today" (mixing absolute with "today" keyword)
    if " today" in timeframe:
        # Replace "today" with actual current date
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        timeframe = timeframe.replace(" today", f" {today_str}")
        log.info(f"Search '{search_name}': Converted timeframe to: {timeframe}")

    # Generate unique search_id for this search configuration
    search_id = generate_search_id(search_name, keywords, timeframe)

    log.info(f"Processing search '{search_name}'")
    log.info(f"  Search ID: {search_id}")
    log.info(f"  Keywords: {keywords}")
    log.info(f"  Regions: {len(regions)}")
    log.info(f"  Timeframe: {timeframe}")

    # Process each region for this search
    for region in regions:
        total_records_synced, total_regions = process_region(
            region,
            search_name,
            search_id,
            keywords,
            timeframe,
            sync_timestamp,
            pytrends,
            failed_regions,
            total_records_synced,
            total_regions,
        )

    return total_records_synced, total_regions


def convert_timestamp_to_iso(date_index) -> str:
    """
    Convert pandas Timestamp to ISO format string with UTC timezone.

    This function handles timezone conversion for pandas Timestamp objects returned by
    PyTrends. It ensures all timestamps are in UTC and properly formatted as ISO strings.

    Args:
        date_index: A pandas Timestamp object or similar date/time object.

    Returns:
        ISO-formatted datetime string with UTC timezone.
    """
    if not hasattr(date_index, "tz_localize"):
        return str(date_index)

    if date_index.tz is None:
        return date_index.tz_localize("UTC").isoformat()

    return date_index.isoformat()


def process_region(
    region,
    search_name,
    search_id,
    keywords,
    timeframe,
    sync_timestamp,
    pytrends,
    failed_regions,
    total_records_synced,
    total_regions,
):
    """
    Process a single region within a search group by fetching and upserting its data.

    This function:
    1. Fetches interest over time data for the region using exponential backoff retry
    2. Transforms the data into individual records for each keyword/date combination
    3. Upserts each record to the google_trends table
    4. Handles errors and tracks failed regions

    Args:
        region: Dictionary with 'name' and 'code' for this region.
        search_name: Human-readable name of the parent search.
        search_id: Unique identifier grouping keywords from the same search.
        keywords: List of keywords to fetch data for.
        timeframe: Time period to query (e.g., "2024-01-01 2026-02-03").
        sync_timestamp: ISO timestamp for this sync run.
        pytrends: Initialized TrendReq instance for making API calls.
        failed_regions: List to accumulate names of regions that failed.
        total_records_synced: Running count of records synced so far.
        total_regions: Running count of total regions attempted.

    Returns:
        Tuple of (total_records_synced, total_regions) with updated counts.
    """
    region_name = region["name"]
    region_code = region["code"] or "WORLDWIDE"
    total_regions += 1

    region_display = region_code if region_code != "WORLDWIDE" else "Worldwide"
    log.info(f"  Processing region: {region_name} ({region_display})")

    try:
        df = fetch_region_data_with_retry(pytrends, keywords, timeframe, region["code"])

        if df is None or df.empty:
            log.warning(f"  No data returned for region {region_name} ({region_code})")
            return total_records_synced, total_regions

        has_partial_column = "isPartial" in df.columns
        records_in_region = 0

        for date_index, row in df.iterrows():
            is_partial = bool(row.get("isPartial", False)) if has_partial_column else False
            date_str = convert_timestamp_to_iso(date_index)

            for keyword in keywords:
                if keyword not in row:
                    continue

                record = {
                    "search_id": search_id,
                    "keyword": keyword,
                    "date": date_str,
                    "region_name": region_name,
                    "region_code": region_code,
                    "sync_timestamp": sync_timestamp,
                    "interest": int(row[keyword]),
                    "timeframe": timeframe,
                    "is_partial": is_partial,
                }

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="google_trends", data=record)
                records_in_region += 1
                total_records_synced += 1

        log.info(f"  Region {region_name}: Synced {records_in_region} records")

        # Save the progress by checkpointing the state. This is important for ensuring that
        # the sync process can resume from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
        # it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(
            {
                "last_sync_timestamp": sync_timestamp,
                "total_records_synced": total_records_synced,
                "failed_regions": failed_regions,
            }
        )

        time.sleep(__INTER_REGION_DELAY)

    except Exception as e:
        # Unexpected exceptions should be logged and tracked as regional failures so that
        # other regions/searches can continue. The overall sync logic will decide whether
        # to fail the sync based on how many regions succeeded vs. failed.
        error_type = type(e).__name__
        error_msg = str(e)
        log.error(f"  Unexpected error for region {region_name} ({region_code})")
        log.error(f"  Error type: {error_type}, Message: {error_msg}")
        log.error(f"  Traceback:\n{traceback.format_exc()}")
        failed_regions.append(f"{search_name}/{region_name}")

    return total_records_synced, total_regions


def log_http_response_details(e: Exception):
    """
    Log HTTP response details if available in the exception.

    When an HTTP request fails, this function extracts and logs diagnostic information
    from the response object if it exists. This helps debug API failures by showing
    status codes, headers, and response body content.

    Args:
        e: The exception that was raised, potentially containing an HTTP response object.
    """
    if not hasattr(e, "response") or e.response is None:
        return

    log.error(f"[DEBUG] HTTP Status Code: {getattr(e.response, 'status_code', 'N/A')}")
    try:
        headers_dict = dict(getattr(e.response, "headers", {}))
        log.error(f"[DEBUG] Response Headers: {headers_dict}")
    except Exception as header_error:
        log.error(
            f"[DEBUG] Failed to log response headers: {type(header_error).__name__}: {header_error}"
        )
    response_text = getattr(e.response, "text", "")
    if response_text:
        log.error(f"[DEBUG] Response Text (first 500 chars): {response_text[:500]}")


def log_error_details(
    e: Exception, retry: int, region_code: str, keywords: List[str], timeframe: str
):
    """
    Log comprehensive error information for debugging API failures.

    This function logs all relevant context about a failed API request, including:
    - Which retry attempt failed
    - Exception type and message
    - Request parameters (region, keywords, timeframe)
    - HTTP response details if available
    - Full stack trace

    Args:
        e: The exception that was raised.
        retry: Current retry attempt number (0-indexed).
        region_code: The region code being queried.
        keywords: List of keywords in the request.
        timeframe: The timeframe string being queried.

    Returns:
        Tuple of (error_type, error_msg) for use in retry logic.
    """
    error_msg = str(e)
    error_type = type(e).__name__

    log.error(f"[DEBUG] Attempt {retry + 1}/{__MAX_RETRIES} failed")
    log.error(f"[DEBUG] Exception Type: {error_type}")
    log.error(f"[DEBUG] Exception Message: {error_msg}")
    log.error(f"[DEBUG] Region: {region_code}, Keywords: {keywords}, Timeframe: {timeframe}")

    log_http_response_details(e)

    log.error(f"[DEBUG] Traceback:\n{traceback.format_exc()}")

    return error_type, error_msg


def calculate_retry_delay(retry: int) -> tuple[float, float, float]:
    """
    Calculate exponential backoff delay with random jitter for retry attempts.

    The delay increases exponentially with each retry:
    - Retry 0: 60s base + 0-30s jitter = 60-90s total
    - Retry 1: 120s base + 0-30s jitter = 120-150s total
    - Retry 2: 240s base + 0-30s jitter = 240-270s total
    - And so on...

    Random jitter helps prevent thundering herd problems when multiple processes retry.

    Args:
        retry: Current retry attempt number (0-indexed).

    Returns:
        Tuple of (total_wait_time, base_delay, jitter) in seconds.
    """
    base_delay = __RETRY_BASE_DELAY * (2**retry)
    jitter = random.uniform(0, __RETRY_JITTER)
    wait_time = base_delay + jitter
    return wait_time, base_delay, jitter


def handle_retry_sleep(retry: int, error_type: str, error_msg: str):
    """
    Handle the sleep delay and logging for retry attempts.

    This function calculates the appropriate delay using exponential backoff with jitter,
    logs the retry information for visibility, and then sleeps for the calculated duration.

    Args:
        retry: Current retry attempt number (0-indexed).
        error_type: Type of the exception that caused this retry.
        error_msg: Message from the exception.
    """
    wait_time, base_delay, jitter = calculate_retry_delay(retry)
    log.warning(f"Request failed (attempt {retry + 1}/{__MAX_RETRIES}): {error_type}: {error_msg}")
    log.info(f"Retrying in {wait_time:.1f} seconds ({base_delay}s base + {jitter:.1f}s jitter)...")

    time.sleep(wait_time)


def fetch_region_data_with_retry(
    pytrends: TrendReq, keywords: List[str], timeframe: str, region_code: str
):
    """
    Fetch Google Trends data for a specific region with exponential backoff retry and jitter.

    This implements retry strategy with exponential backoff + randomization:
    - Retry 1: wait 60-90 seconds (60s base + 0-30s random jitter)
    - Retry 2: wait 120-150 seconds (120s base + 0-30s random jitter)
    - Retry 3: wait 240-270 seconds (240s base + 0-30s random jitter)
    - Retry 4: wait 480-510 seconds (480s base + 0-30s random jitter)
    - Retry 5: wait 960-990 seconds (960s base + 0-30s random jitter)

    Args:
        pytrends: Initialized TrendReq instance
        keywords: List of keywords to search
        timeframe: Time period to fetch (e.g., "2024-01-01 today" or "today 12-m")
        region_code: Geographic region code (empty string for worldwide)

    Returns:
        DataFrame with interest over time data, or None if all retries fail
    """
    last_error = None

    for retry in range(__MAX_RETRIES):
        try:
            # Build payload for this timeframe
            pytrends.build_payload(
                kw_list=keywords, cat=0, timeframe=timeframe, geo=region_code, gprop=""
            )

            # Fetch interest over time
            df = pytrends.interest_over_time()

            # Success!
            return df

        # Catch specific exceptions for retry logic
        except (
            requests.exceptions.RequestException,
            ValueError,
            KeyError,
        ) as e:
            # HTTP/network errors, data parsing errors - these are expected and should be retried
            last_error = e
            error_type, error_msg = log_error_details(e, retry, region_code, keywords, timeframe)

            if retry < __MAX_RETRIES - 1:
                # Calculate exponential backoff delay with random jitter
                # Exponential: 60s, 120s, 240s, 480s, 960s + Random jitter: 0-30s
                handle_retry_sleep(retry, error_type, error_msg)
            else:
                log.error(f"All {__MAX_RETRIES} retry attempts exhausted for region {region_code}")
                log.error(f"[DEBUG] Final error type: {error_type}, message: {error_msg}")
        except Exception as e:
            # Catch other unexpected exceptions from pytrends library
            # Still retry these as they may be transient errors
            last_error = e
            error_type, error_msg = log_error_details(e, retry, region_code, keywords, timeframe)

            if retry < __MAX_RETRIES - 1:
                # Calculate exponential backoff delay with random jitter
                # Exponential: 60s, 120s, 240s, 480s, 960s + Random jitter: 0-30s
                handle_retry_sleep(retry, error_type, error_msg)
            else:
                log.error(f"All {__MAX_RETRIES} retry attempts exhausted for region {region_code}")
                log.error(f"[DEBUG] Final error type: {error_type}, message: {error_msg}")

    # All retries exhausted - re-raise the last error
    if last_error:
        raise last_error

    raise RuntimeError(
        f"Failed to fetch data for region {region_code} after {__MAX_RETRIES} retries"
    )


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
