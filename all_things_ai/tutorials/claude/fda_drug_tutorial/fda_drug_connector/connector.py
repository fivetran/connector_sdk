"""
FDA Drug API Fivetran Connector
Dynamically discovers and syncs data from FDA Drug API endpoints with incremental sync support.
This connector follows Fivetran Connector SDK best practices without using yield statements.
"""

import json
import requests
import time
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urljoin
import base64

from fivetran_connector_sdk import Connector, Logging as log, Operations as op


class FDADrugConnector:
    """FDA Drug API Connector with endpoint discovery and incremental sync."""

    BASE_URL = "https://api.fda.gov/drug/"

    # Known FDA Drug endpoints - can be extended
    KNOWN_ENDPOINTS = ["ndc", "event", "label", "enforcement"]

    # Endpoint-specific date fields for incremental sync
    ENDPOINT_DATE_FIELDS = {
        "ndc": "listing_expiration_date",
        "event": "receivedate",  # Date FDA received the report
        "label": "effective_time",  # Label effective date
        "enforcement": "report_date",  # Enforcement report date
    }

    def __init__(self, configuration: Dict[str, str]):
        self.config = configuration
        self.api_key = configuration.get("api_key", "").strip()
        self.base_url = configuration.get("base_url", self.BASE_URL).rstrip("/") + "/"
        self.requests_per_checkpoint = int(configuration.get("requests_per_checkpoint", "10"))
        self.rate_limit_delay = float(
            configuration.get("rate_limit_delay", "0.25")
        )  # 250ms between requests
        self.flatten_nested = configuration.get("flatten_nested", "true").lower() == "true"
        self.create_child_tables = (
            configuration.get("create_child_tables", "false").lower() == "true"
        )
        self.max_api_calls_per_endpoint = int(configuration.get("max_api_calls_per_endpoint", "2"))

        # Rate limiting
        self.last_request_time = 0
        self.request_count = 0

        log.info(
            f"Initialized FDA Drug Connector with {self.requests_per_checkpoint} requests per checkpoint"
        )
        log.info(f"Maximum API calls per endpoint: {self.max_api_calls_per_endpoint}")
        log.info(f"Endpoint date fields: {self.ENDPOINT_DATE_FIELDS}")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers if API key is provided."""
        headers = {"User-Agent": "Fivetran-FDA-Connector/1.0", "Accept": "application/json"}

        if self.api_key:
            # FDA API supports basic auth with API key as username
            auth_string = base64.b64encode(f"{self.api_key}:".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
            log.info("Using API key authentication")
        else:
            log.info("Running without API key - limited to 1000 requests/day")

        return headers

    def _rate_limit(self):
        """Implement rate limiting to respect API limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(self, url: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Make rate-limited API request with error handling."""
        self._rate_limit()

        try:
            headers = self._get_auth_headers()

            # Add API key to params if provided
            if self.api_key and params:
                params["api_key"] = self.api_key
            elif self.api_key:
                params = {"api_key": self.api_key}

            log.info(f"Making request to: {url}")
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 429:
                log.warning("Rate limit hit, waiting 60 seconds")
                time.sleep(60)
                return self._make_request(url, params)

            response.raise_for_status()
            self.request_count += 1

            return response.json()

        except requests.exceptions.RequestException as e:
            log.error("API request failed", e)
            return None

    def discover_endpoints(self) -> List[str]:
        """Discover available drug endpoints by testing known endpoints."""
        available_endpoints = []

        log.info("Discovering available FDA Drug API endpoints...")

        for endpoint in self.KNOWN_ENDPOINTS:
            test_url = urljoin(self.base_url, f"{endpoint}.json")
            params = {"limit": 1}  # Minimal request to test availability

            response = self._make_request(test_url, params)
            if response and "results" in response:
                available_endpoints.append(endpoint)
                log.info(f"Discovered endpoint: {endpoint}")
            else:
                log.warning(f"Endpoint not available or accessible: {endpoint}")

        log.info(f"Discovered {len(available_endpoints)} available endpoints")
        return available_endpoints

    def _flatten_dict(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flatten nested dictionaries with prefixed keys."""
        flattened = {}

        for key, value in data.items():
            new_key = f"{prefix}_{key}" if prefix else key

            if isinstance(value, dict):
                flattened.update(self._flatten_dict(value, new_key))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Handle array of objects by creating indexed flat keys
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        flattened.update(self._flatten_dict(item, f"{new_key}_{i}"))
                    else:
                        flattened[f"{new_key}_{i}"] = item
            elif isinstance(value, list):
                # Handle simple arrays
                flattened[new_key] = json.dumps(value) if value else None
            else:
                flattened[new_key] = value

        return flattened

    def _extract_child_tables(
        self, data: Dict[str, Any], parent_key: str
    ) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        """Extract nested objects into separate child tables."""
        main_record = {}
        child_tables = {}

        for key, value in data.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                # Create child table
                table_name = f"{parent_key}_{key}"
                child_records = []

                for i, item in enumerate(value):
                    child_record = {"_parent_id": parent_key, "_index": i}
                    if isinstance(item, dict):
                        child_record.update(item)
                    else:
                        child_record["value"] = item
                    child_records.append(child_record)

                child_tables[table_name] = child_records
                main_record[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                # Flatten sub-objects into main record
                flattened = self._flatten_dict(value, key)
                main_record.update(flattened)
            else:
                main_record[key] = value

        return main_record, child_tables

    def sync_endpoint(self, endpoint: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Sync data from a specific endpoint with incremental support."""
        table_name = f"fda_drug_{endpoint}"
        endpoint_state_key = f"{endpoint}_cursor"

        # Get endpoint-specific date field
        date_field = self.ENDPOINT_DATE_FIELDS.get(endpoint)
        if not date_field:
            log.warning(f"No date field defined for endpoint {endpoint}, using full sync only")

        # Get cursor from state
        cursor = state.get(endpoint_state_key)
        if cursor:
            log.info(f"Resuming {endpoint} sync from cursor: {cursor} (field: {date_field})")
        else:
            log.info(f"Starting full sync for {endpoint} (date field: {date_field})")

        url = urljoin(self.base_url, f"{endpoint}.json")
        skip = 0
        limit = 100  # API maximum
        total_records = 0
        checkpoint_counter = 0
        api_call_count = 0  # Track API calls per endpoint
        latest_date = cursor

        log.info(f"Processing up to {self.max_api_calls_per_endpoint} API calls for {endpoint}")

        while api_call_count < self.max_api_calls_per_endpoint:
            params = {"limit": limit, "skip": skip}

            # Add incremental filter if cursor exists and date field is available
            if cursor and date_field:
                # Different endpoints may need different date formats
                if endpoint == "ndc":
                    # NDC uses YYYYMMDD format
                    params["search"] = f"{date_field}:[{cursor} TO 99991231]"
                elif endpoint == "event":
                    # Event uses YYYYMMDD format
                    params["search"] = f"{date_field}:[{cursor} TO 99991231]"
                elif endpoint in ["label", "enforcement"]:
                    # Label and enforcement may use different formats, try both
                    params["search"] = f"{date_field}:[{cursor} TO 9999-12-31]"

                log.info(f"Using incremental search: {params.get('search')}")

            response = self._make_request(url, params)
            api_call_count += 1

            if not response or "results" not in response:
                log.warning(
                    f"No more data available for {endpoint} after {api_call_count} API calls"
                )
                break

            results = response["results"]
            if not results:
                log.info(f"No more records found for {endpoint} after {api_call_count} API calls")
                break

            # Process records
            child_table_data = {}

            for record in results:
                # Determine primary key based on endpoint
                if endpoint == "ndc":
                    primary_key = record.get("product_id") or record.get("product_ndc")
                elif endpoint == "event":
                    primary_key = record.get("safetyreportid") or record.get("receiptdate")
                elif endpoint == "label":
                    primary_key = record.get("id") or record.get("set_id")
                elif endpoint == "enforcement":
                    primary_key = record.get("recall_number") or record.get("product_description")
                else:
                    primary_key = record.get("id", f"{endpoint}_{skip + results.index(record)}")

                # Ensure we have a primary key
                if not primary_key:
                    primary_key = f"{endpoint}_{api_call_count}_{results.index(record)}"

                if self.create_child_tables:
                    main_record, child_tables = self._extract_child_tables(record, primary_key)

                    # Collect child table data
                    for child_table, child_records in child_tables.items():
                        if child_table not in child_table_data:
                            child_table_data[child_table] = []
                        child_table_data[child_table].extend(child_records)

                    processed_record = main_record
                else:
                    # Flatten everything into main table
                    processed_record = (
                        self._flatten_dict(record) if self.flatten_nested else record
                    )

                # Add primary key
                processed_record["_primary_key"] = primary_key

                # Track latest date for cursor using endpoint-specific field
                if date_field and date_field in processed_record:
                    record_date = processed_record[date_field]
                    if record_date and (not latest_date or record_date > latest_date):
                        latest_date = record_date
                elif date_field:
                    # Try flattened field names for nested data
                    flattened_field_candidates = [
                        date_field,
                        f"{date_field}_0",
                        f"patient_{date_field}",
                        f"meta_{date_field}",
                    ]
                    for candidate in flattened_field_candidates:
                        if candidate in processed_record and processed_record[candidate]:
                            record_date = processed_record[candidate]
                            if not latest_date or record_date > latest_date:
                                latest_date = record_date
                            break

                # Direct operation call without yield - easier to adopt
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted,
                op.upsert(table=table_name, data=processed_record)
                total_records += 1

            # Upsert child table data if enabled
            if self.create_child_tables:
                for child_table, child_records in child_table_data.items():
                    for child_record in child_records:
                        op.upsert(table=child_table, data=child_record)

            checkpoint_counter += 1

            # Checkpoint after configured number of requests
            if checkpoint_counter >= self.requests_per_checkpoint:
                # Only update cursor if we found a valid date
                if latest_date and latest_date != cursor:
                    state[endpoint_state_key] = latest_date
                    log.info(f"Checkpointed {endpoint} at cursor: {latest_date}")
                else:
                    log.info(f"Checkpointed {endpoint} - no date progression")

                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state=state)
                checkpoint_counter = 0
                log.info(
                    f"Checkpoint complete for {endpoint}, total records: {total_records}, API calls: {api_call_count}"
                )

            # Check if we've reached the end of available data
            total_available = response.get("meta", {}).get("results", {}).get("total", 0)
            if skip + limit >= total_available:
                log.info(f"Reached end of {endpoint} data with {api_call_count} API calls")
                break

            skip += limit

        # Log completion with API call summary
        if api_call_count >= self.max_api_calls_per_endpoint:
            log.info(
                f"Reached maximum API calls ({self.max_api_calls_per_endpoint}) for {endpoint}"
            )

        # Final checkpoint - only update cursor if we found valid dates
        if latest_date and latest_date != cursor:
            state[endpoint_state_key] = latest_date
            op.checkpoint(state=state)
            log.info(f"Final checkpoint for {endpoint} at cursor: {latest_date}")
        else:
            log.info(f"No cursor update for {endpoint} - no valid dates found")

        log.info(
            f"Completed sync for {endpoint}: {total_records} records processed, {api_call_count} API calls used"
        )

        return state


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
    required_configs = ["api_key", "base_url", "requests_per_checkpoint", "rate_limit_delay"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def schema(configuration: dict) -> List[Dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    log.info("Generating schema for FDA Drug API")

    # Initialize connector to discover endpoints
    connector = FDADrugConnector(configuration)
    endpoints = connector.discover_endpoints()

    tables = []

    # Create main tables for each endpoint
    for endpoint in endpoints:
        table_name = f"fda_drug_{endpoint}"
        tables.append({"table": table_name, "primary_key": ["_primary_key"]})

        # Add child tables if enabled
        if connector.create_child_tables:
            # Common child table patterns for FDA data
            child_tables = [
                f"{table_name}_active_ingredients",
                f"{table_name}_packaging",
                f"{table_name}_openfda",
                f"{table_name}_route",
            ]

            for child_table in child_tables:
                tables.append({"table": child_table, "primary_key": ["_parent_id", "_index"]})

    log.info(f"Generated schema with {len(tables)} tables")
    return tables


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
    log.info("Starting FDA Drug API sync")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    connector = FDADrugConnector(configuration)
    endpoints = connector.discover_endpoints()

    if not endpoints:
        log.error("No available endpoints discovered")
        return

    total_api_calls = 0
    max_calls_per_endpoint = connector.max_api_calls_per_endpoint

    log.info(
        f"Processing {len(endpoints)} endpoints with max {max_calls_per_endpoint} API calls each"
    )
    log.info(f"Total estimated API calls: {len(endpoints) * max_calls_per_endpoint}")

    try:
        for endpoint in endpoints:
            log.info(
                f"Starting sync for endpoint: {endpoint} (max {max_calls_per_endpoint} API calls)"
            )

            try:
                endpoint_start_calls = connector.request_count
                state = connector.sync_endpoint(endpoint, state)
                endpoint_calls = connector.request_count - endpoint_start_calls
                total_api_calls += endpoint_calls

                log.info(f"Completed {endpoint}: {endpoint_calls} API calls used")

            except Exception as e:
                log.error(f"Error syncing endpoint {endpoint}", e)
                continue

        log.info(f"FDA Drug API sync completed - Total API calls used: {total_api_calls}")

        # Log quota usage summary
        if connector.api_key:
            remaining_daily = 120000 - total_api_calls
            log.info(f"API quota usage: {total_api_calls}/120,000 daily calls (with API key)")
            log.info(remaining_daily)
        else:
            remaining_daily = 1000 - total_api_calls
            log.info(f"API quota usage: {total_api_calls}/1,000 daily calls (no API key)")
            if total_api_calls > 500:
                log.warning(
                    "Approaching daily API limit - consider getting an API key for higher limits"
                )

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync FDA Drug API data: {str(e)}")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open(
        "/Users/elijah.davis/Documents/code/sdk/customer/ai_customer/FDA_drug_claude_no_yield/configuration.json",
        "r",
    ) as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
