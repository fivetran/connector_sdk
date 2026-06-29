"""
Apache Druid Client for PyDruid library integration.
This module provides the DruidPyDruidClient class for connecting to and querying Apache Druid.
"""

# Used for sleep delays between retries and batch requests
import time
import random  # Used for jitter in retry delays

# Used for parsing timestamps for safe comparison
from datetime import datetime, timezone, timedelta

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# PyDruid imports
try:
    from pydruid.client import PyDruid

    _PYDRUID_AVAILABLE = True
except ImportError:
    PyDruid = None
    _PYDRUID_AVAILABLE = False

# Constants for retry logic
__MAX_RETRIES = 3  # Maximum number of retries for failed requests
__INITIAL_RETRY_DELAY = 2  # Initial retry delay in seconds
__MAX_RETRY_DELAY = 60  # Maximum retry delay in seconds


def retry_with_exponential_backoff(max_retries=__MAX_RETRIES):
    """
    Decorator that implements retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed, re-raise the exception
                        raise

                    # Calculate exponential backoff delay with jitter
                    delay = min(__INITIAL_RETRY_DELAY * (2**attempt), __MAX_RETRY_DELAY)
                    # Add random jitter (±25% of delay)
                    jitter = delay * 0.25 * (2 * random.random() - 1)
                    actual_delay = max(0.1, delay + jitter)

                    log.warning(
                        f"Attempt {attempt + 1} failed: {str(e)}. "
                        f"Retrying in {actual_delay:.2f} seconds..."
                    )
                    time.sleep(actual_delay)

            # This should never be reached due to the raise in the loop
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def _parse_iso_timestamp(ts: str) -> datetime:
    """
    Parse an ISO timestamp string, handling Z suffix properly.

    Args:
        ts: ISO timestamp string (may have Z suffix)

    Returns:
        datetime object with timezone info
    """
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class DruidPyDruidClient:
    """
    Apache Druid client using pydruid package for native Druid queries.

    This client provides direct access to Druid's native query APIs including:
    - GroupBy queries for aggregation with grouping
    - Timeseries queries for time-based aggregation
    - TopN queries for finding top values
    - Scan queries for raw data extraction
    - Search queries for dimension value discovery
    """

    def __init__(self, configuration: dict):
        """
        Initialize the PyDruid client.

        Args:
            configuration: Dictionary containing connection parameters
                - host: Druid broker hostname
                - port: Druid broker port
                - protocol: http or https (optional, defaults to https)
                - username: Basic auth username (optional)
                - password: Basic auth password (optional)
        """
        if not _PYDRUID_AVAILABLE:
            raise ImportError(
                "pydruid package is required. Please install it with: pip install pydruid==0.6.5"
            )

        self.host = configuration.get("host")
        self.port = int(configuration.get("port", 8080))
        self.protocol = configuration.get(
            "protocol", "https"
        )  # Default to https for secure connections
        self.username = configuration.get("username")
        self.password = configuration.get("password")

        # Validate required parameters
        if not self.host:
            raise ValueError("host is required in configuration")

        # Build endpoint URL using specified or default protocol
        self.endpoint = f"{self.protocol}://{self.host}:{self.port}"

        # Initialize pydruid client
        self._initialize_client()

        log.info(f"Initialized PyDruid client for {self.endpoint}")

    def _initialize_client(self):
        """Initialize the pydruid Client instance."""
        try:
            # Create pydruid client
            self.client = PyDruid(self.endpoint, "druid/v2/")

            # Handle authentication if provided
            if self.username and self.password:
                # PyDruid supports basic authentication via set_basic_auth_credentials
                self.client.set_basic_auth_credentials(self.username, self.password)
                log.info(
                    f"PyDruid client initialized with basic authentication for user: {self.username}"
                )
            else:
                log.info("PyDruid client initialized without authentication")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize PyDruid client: {str(e)}")

    def _execute_query_with_retry(self, query_func, *args, **kwargs):
        """Execute a PyDruid query with retry logic."""

        # Apply retry decorator to handle transient network/server failures
        # Provides exponential backoff with jitter for reliable Druid connectivity
        @retry_with_exponential_backoff()
        def execute():
            return query_func(*args, **kwargs)

        return execute()

    def scan_datasource(
        self,
        datasource: str,
        intervals: list[str],
        columns: list[str] | None = None,
        filters=None,
        limit: int | None = None,
        batch_size: int = 1000,  # __SCAN_BATCH_SIZE
    ):
        """
        Scan a datasource for raw data using Druid's scan query.

        Args:
            datasource: Name of the datasource to scan
            intervals: List of ISO intervals (e.g., ["2023-01-01/2023-02-01"])
            columns: Specific columns to retrieve (optional, gets all if None)
            filters: List of filter dictionaries (optional)
            limit: Maximum number of records to retrieve
            batch_size: Number of records per batch request

        Yields:
            Individual records as dictionaries
        """
        try:
            total_fetched = 0

            # Build scan query - Druid scan queries don't support offset-based pagination
            # Instead, we use the limit parameter and handle pagination through result processing
            scan_params = {
                "datasource": datasource,
                "intervals": intervals,
            }

            # Set a high limit to ensure we get all records (PyDruid may have internal defaults)
            # Use a very large number instead of None to avoid PyDruid defaults
            if limit is not None:
                scan_params["limit"] = limit
            else:
                scan_params["limit"] = 100000000  # 100 million - effectively unlimited

            # Add columns if specified
            if columns:
                scan_params["columns"] = columns

            # Add filter if provided (note: singular 'filter', not 'filters')
            if filters:
                scan_params["filter"] = filters

            effective_limit = scan_params["limit"]
            if limit is not None:
                log.info(f"Starting scan of datasource {datasource} with limit {limit}")
            else:
                log.info(
                    f"Starting unlimited scan of datasource {datasource} (effective limit: {effective_limit})"
                )
            if filters:
                log.info(f"Applying filter: {filters}")

            # Execute query with proper error handling for filter issues
            try:
                query = self._execute_query_with_retry(self.client.scan, **scan_params)
            except Exception as e:
                if "'dict' object has no attribute 'filter'" in str(e):
                    # Fallback: remove filter and rely on interval filtering only
                    log.warning(
                        f"Filter not supported in this PyDruid version, falling back to interval filtering: {e}"
                    )
                    if "filter" in scan_params:
                        del scan_params["filter"]
                    query = self._execute_query_with_retry(self.client.scan, **scan_params)
                else:
                    raise

            if not hasattr(query, "result") or not query.result:
                log.info(f"No data found in datasource {datasource}")
                return

            batch_data = query.result

            # Handle PyDruid scan result structure: list of segments, each with events
            events = []
            if isinstance(batch_data, list):
                for segment in batch_data:
                    if isinstance(segment, dict) and "events" in segment:
                        events.extend(segment["events"])
                    elif isinstance(segment, dict):
                        # Handle case where segment itself is an event
                        events.append(segment)
            else:
                log.warning(f"Unexpected result format: {type(batch_data)}")
                return

            # Process events and yield them
            for event in events:
                if isinstance(event, dict):
                    yield event
                    total_fetched += 1

                    # Log progress periodically
                    if total_fetched % batch_size == 0:
                        log.info(f"Processed {total_fetched} records from {datasource}")

                    # Only break if we have a limit and have reached it
                    if limit is not None and total_fetched >= limit:
                        break
                else:
                    log.warning(f"Unexpected event format: {type(event)} - {event}")

            log.info(f"Completed scan of {datasource}. Total records: {total_fetched}")

        except Exception as e:
            log.error(f"Failed to scan datasource {datasource}: {str(e)}")
            raise RuntimeError(f"Failed to scan datasource {datasource}: {str(e)}")

    def incremental_scan(
        self,
        datasource: str,
        timestamp_column: str = "__time",
        since: str | None = None,
        batch_size: int = 10000,  # __BATCH_SIZE
    ):
        """
        Perform incremental scan of a datasource based on timestamp.

        Args:
            datasource: Name of the datasource
            timestamp_column: Name of the timestamp column
            since: ISO timestamp to start from (None for full scan)
            batch_size: Number of records per batch

        Yields:
            Individual records as dictionaries
        """
        try:
            # Determine the interval based on since parameter - use interval filtering for incremental sync
            if since:
                # For incremental sync, we need to get records AFTER the since timestamp
                try:
                    since_dt = _parse_iso_timestamp(since)
                    # Add 1 millisecond to ensure we only get records AFTER the last processed record
                    since_dt = since_dt + timedelta(milliseconds=1)
                    start_time = since_dt.isoformat().replace("+00:00", "Z")
                    log.info(f"Starting incremental scan from {start_time} (excluding {since})")
                except Exception as e:
                    log.warning(f"Could not parse since timestamp {since}, using as-is: {e}")
                    # If we can't parse, add a small buffer to avoid re-processing the same record
                    start_time = since
                    # Try to add a small time buffer if it looks like an ISO timestamp
                    if "T" in since and ("Z" in since or "+" in since):
                        try:
                            since_dt = _parse_iso_timestamp(since) + timedelta(milliseconds=1)
                            start_time = since_dt.isoformat().replace("+00:00", "Z")
                            log.info(f"Applied 1ms buffer to unparseable timestamp: {start_time}")
                        except Exception:
                            pass
            else:
                start_time = "1970-01-01T00:00:00.000Z"
                log.info("Starting full scan from epoch")

            # Use a wide end time to capture all data - intervals are inclusive in Druid
            end_time = "2100-01-01T00:00:00.000Z"
            intervals = [f"{start_time}/{end_time}"]

            # For incremental sync, we need additional client-side filtering to ensure precise exclusion
            # since Druid intervals are inclusive and we need to exclude records AT the exact 'since' timestamp
            last_processed_time = None
            if since:
                try:
                    last_processed_time = _parse_iso_timestamp(since)
                except Exception:
                    pass

            for record in self.scan_datasource(
                datasource=datasource,
                intervals=intervals,
                filters=None,
                limit=None,
                batch_size=batch_size,
            ):
                # Client-side filtering for precise incremental sync
                if last_processed_time and since:
                    record_time = record.get("__time") or record.get("timestamp")
                    if record_time:
                        try:
                            # Parse record timestamp
                            if isinstance(record_time, (int, float)):
                                record_dt = datetime.fromtimestamp(
                                    record_time / 1000, tz=timezone.utc
                                )
                            elif isinstance(record_time, str):
                                record_dt = _parse_iso_timestamp(str(record_time))
                            else:
                                record_dt = record_time

                            if record_dt.tzinfo is None:
                                record_dt = record_dt.replace(tzinfo=timezone.utc)

                            # Skip records that are <= the last processed timestamp
                            if record_dt <= last_processed_time:
                                continue
                        except Exception:
                            # If we can't parse the timestamp, include the record to be safe
                            pass

                yield record

        except Exception as e:
            log.error(f"Failed to perform incremental scan: {str(e)}")
            raise RuntimeError(f"Failed to perform incremental scan: {str(e)}")

    def close(self):
        """Close the connection (cleanup if needed)."""
        # pydruid doesn't require explicit connection closing
        log.info("PyDruid client closed")
