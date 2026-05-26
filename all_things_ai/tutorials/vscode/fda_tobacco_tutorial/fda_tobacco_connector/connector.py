# This connector fetches data from the FDA Tobacco Problem Reports API and upserts it into destination using Fivetran Connector SDK.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import (
    Connector,
)  # For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Logging as log  # For enabling Logs in your connector code
from fivetran_connector_sdk import (
    Operations as op,
)  # For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()

# Add your source-specific imports here
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional

# Constants for configuration
DEFAULT_BASE_URL = "https://api.fda.gov/tobacco/problem.json"
DEFAULT_RATE_LIMIT = 240  # requests per minute
DEFAULT_PAGE_SIZE = 1000  # maximum records per API call
CHECKPOINT_INTERVAL = 100  # checkpoint every 100 rows
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


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
    required_configs = ["base_url", "rate_limit", "page_size", "checkpoint_interval"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate optional parameters if provided
    if "api_key" in configuration and configuration["api_key"]:
        log.info("Using API key authentication for higher rate limits")
    else:
        log.warning("No API key provided - using limited rate limits (1,000 requests/day)")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "fda_tobacco_problem_reports",  # Name of the table in the destination, required.
            "primary_key": ["report_id"],  # Primary key column(s) for the table, required.
        },
    ]


def make_api_request(
    url: str, params: Dict, api_key: Optional[str] = None, retry_count: int = 0
) -> Dict:
    """
    Make an API request to the FDA Tobacco Problem Reports API with retry logic and rate limiting.

    Args:
        url: The API endpoint URL
        params: Query parameters for the request
        api_key: Optional API key for authentication
        retry_count: Current retry attempt number

    Returns:
        Dictionary containing the API response

    Raises:
        RuntimeError: If the request fails after all retry attempts
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Rate limit exceeded
            if retry_count < MAX_RETRIES:
                wait_time = (2**retry_count) * RETRY_DELAY
                log.warning(
                    f"Rate limit exceeded, waiting {wait_time} seconds before retry {retry_count + 1}"
                )
                time.sleep(wait_time)
                return make_api_request(url, params, api_key, retry_count + 1)
            else:
                raise RuntimeError("Rate limit exceeded after maximum retries")
        else:
            response.raise_for_status()

    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES:
            log.warning(f"Request failed, retrying in {RETRY_DELAY} seconds: {str(e)}")
            time.sleep(RETRY_DELAY)
            return make_api_request(url, params, api_key, retry_count + 1)
        else:
            raise RuntimeError(f"API request failed after {MAX_RETRIES} retries: {str(e)}")


def process_ai_data_record(record: Dict) -> Dict:
    """
    Process and clean AI/ML data from FDA tobacco reports.
    Handles schema evolution, missing values, and nested JSON structures.

    Args:
        record: Raw record from FDA API

    Returns:
        Processed record optimized for AI/ML ingestion
    """
    # AI-specific data cleaning and feature engineering
    processed_record = {
        "report_id": record.get("report_id"),
        "date_submitted": record.get("date_submitted"),
        "nonuser_affected": record.get("nonuser_affected"),
        "reported_health_problems": json.dumps(record.get("reported_health_problems", [])),
        "number_health_problems": record.get("number_health_problems"),
        "reported_product_problems": json.dumps(record.get("reported_product_problems", [])),
        "number_product_problems": record.get("number_product_problems"),
        "number_tobacco_products": record.get("number_tobacco_products"),
        "tobacco_products": json.dumps(record.get("tobacco_products", [])),
        "sync_timestamp": datetime.now().isoformat(),
    }

    # Handle missing values for AI/ML processing
    for key, value in processed_record.items():
        if value is None:
            if key.startswith("number_"):
                processed_record[key] = 0
            elif key.endswith("_problems") or key.endswith("_products"):
                processed_record[key] = "[]"
            else:
                processed_record[key] = ""

    return processed_record


def process_batch_for_ai(data_batch: List[Dict]) -> List[Dict]:
    """
    Batch processing for large datasets optimized for AI/ML ingestion.

    Args:
        data_batch: List of raw records from API

    Returns:
        List of processed records ready for AI/ML processing
    """
    processed = []
    for record in data_batch:
        # AI-specific data cleaning
        cleaned = process_ai_data_record(record)
        # Feature engineering for AI/ML
        enriched = enrich_features_for_ai(cleaned)
        processed.append(enriched)
    return processed


def enrich_features_for_ai(record: Dict) -> Dict:
    """
    Enrich features for AI/ML processing by adding derived fields.

    Args:
        record: Cleaned record

    Returns:
        Record with enriched features
    """
    # Add derived features for AI/ML analysis
    record["total_problems"] = record.get("number_health_problems", 0) + record.get(
        "number_product_problems", 0
    )
    record["has_health_problems"] = record.get("number_health_problems", 0) > 0
    record["has_product_problems"] = record.get("number_product_problems", 0) > 0
    record["has_nonuser_affected"] = record.get("nonuser_affected", False)

    # Parse date for time-series analysis
    if record.get("date_submitted"):
        try:
            date_obj = datetime.strptime(record["date_submitted"], "%Y%m%d")
            record["date_submitted_parsed"] = date_obj.isoformat()
            record["year"] = date_obj.year
            record["month"] = date_obj.month
            record["day_of_week"] = date_obj.weekday()
        except ValueError:
            record["date_submitted_parsed"] = None
            record["year"] = None
            record["month"] = None
            record["day_of_week"] = None

    return record


def fetch_fda_data(configuration: dict, state: dict) -> List[Dict]:
    """
    Fetch data from the FDA Tobacco Problem Reports API with pagination and rate limiting.
    Optimized for AI/ML data ingestion patterns.

    Args:
        configuration: Configuration dictionary containing API settings
        state: State dictionary for incremental syncs

    Returns:
        List of processed records ready for AI/ML processing
    """
    base_url = configuration.get("base_url", DEFAULT_BASE_URL)
    page_size = int(configuration.get("page_size", DEFAULT_PAGE_SIZE))
    rate_limit = int(configuration.get("rate_limit", DEFAULT_RATE_LIMIT))
    api_key = configuration.get("api_key")
    test_mode = configuration.get("test_mode", "false").lower() == "true"
    test_limit = int(configuration.get("test_limit", "10"))

    # Calculate delay between requests to respect rate limits
    request_delay = 60.0 / rate_limit

    # Get last sync state for incremental syncs
    last_sync_date = state.get("last_sync_date")

    # Build search parameters
    search_params = {}
    if last_sync_date:
        # Format date for FDA API (YYYYMMDD)
        last_date = datetime.strptime(last_sync_date, "%Y-%m-%d")
        search_date = last_date.strftime("%Y%m%d")
        current_date = datetime.now().strftime("%Y%m%d")
        search_params["search"] = f"date_submitted:[{search_date}+TO+{current_date}]"
        log.info(f"Performing incremental sync from {last_sync_date}")
    else:
        log.info("Performing full sync - no previous sync date found")

    # Set page size and limit for test mode
    if test_mode:
        page_size = min(page_size, test_limit)
        log.info(f"Test mode enabled - limiting to {test_limit} records")

    search_params["limit"] = page_size
    offset = 0
    total_processed = 0
    all_records = []

    while True:
        # Add offset for pagination
        if offset > 0:
            search_params["skip"] = offset

        # Make API request with rate limiting
        log.info(f"Fetching data with offset {offset}, page size {page_size}")

        try:
            response_data = make_api_request(base_url, search_params, api_key)

            # Extract results and metadata
            results = response_data.get("results", [])
            meta = response_data.get("meta", {})
            total_count = meta.get("results", {}).get("total", 0)
            log.info(total_count)

            if not results:
                log.info("No more data to fetch")
                break

            # Process batch for AI/ML optimization
            processed_batch = process_batch_for_ai(results)
            all_records.extend(processed_batch)
            total_processed += len(processed_batch)

            log.info(f"Processed {len(processed_batch)} records in current batch")

            # Check if we've reached the end or test limit
            if test_mode and total_processed >= test_limit:
                log.info(f"Test mode: reached limit of {test_limit} records")
                break

            if len(results) < page_size:
                log.info("Reached end of data")
                break

            # Move to next page
            offset += page_size

            # Rate limiting delay
            time.sleep(request_delay)

        except Exception as e:
            log.error("Error fetching data", e)
            raise RuntimeError(f"Failed to fetch FDA data: {str(e)}")

    log.info(f"Total records fetched and processed: {total_processed}")
    return all_records


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
    log.info("FDA Tobacco Problem Reports API Connector: Starting AI/ML optimized sync")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters
    base_url = configuration.get("base_url", DEFAULT_BASE_URL)
    rate_limit = configuration.get("rate_limit", str(DEFAULT_RATE_LIMIT))
    page_size = configuration.get("page_size", str(DEFAULT_PAGE_SIZE))
    checkpoint_interval = configuration.get("checkpoint_interval", str(CHECKPOINT_INTERVAL))
    api_key = configuration.get("api_key", "")
    if len(api_key) > 2:
        masked_api_key = api_key[:2] + "*" * (len(api_key) - 2)
    else:
        masked_api_key = api_key  # too short to mask
    log.info(masked_api_key)
    test_mode = configuration.get("test_mode", "false")
    test_limit = configuration.get("test_limit", "10")

    # Log configuration details
    log.info(f"Base URL: {base_url}")
    log.info(f"Rate Limit: {rate_limit} requests/minute")
    log.info(f"Page Size: {page_size}")
    log.info(f"Checkpoint Interval: {checkpoint_interval}")
    log.info(f"Test Mode: {test_mode}")
    if test_mode == "true":
        log.info(f"Test Limit: {test_limit}")

    # Get the state variable for the sync, if needed
    last_sync_date = state.get("last_sync_date")
    last_report_id = state.get("last_report_id")

    if last_sync_date:
        log.info(f"Resuming from last sync date: {last_sync_date}")
    if last_report_id:
        log.info(f"Last processed report ID: {last_report_id}")

    try:
        # Fetch and process data from FDA API optimized for AI/ML
        all_records = fetch_fda_data(configuration, state)

        # Process records in batches for optimal performance
        batch_size = int(checkpoint_interval)
        total_processed = 0

        for i in range(0, len(all_records), batch_size):
            batch = all_records[i : i + batch_size]

            # Upsert batch of records without yield
            for record in batch:
                op.upsert(table="fda_tobacco_problem_reports", data=record)
                total_processed += 1

            # Checkpoint after each batch
            checkpoint_state = {
                "last_sync_date": datetime.now().strftime("%Y-%m-%d"),
                "last_report_id": batch[-1].get("report_id") if batch else None,
                "total_processed": total_processed,
                "offset": i + len(batch),
            }
            op.checkpoint(state=checkpoint_state)

            log.info(f"Processed batch of {len(batch)} records, total: {total_processed}")

        # Final checkpoint with updated state
        final_state = {
            "last_sync_date": datetime.now().strftime("%Y-%m-%d"),
            "total_processed": total_processed,
            "sync_completed": True,
            "last_sync_timestamp": datetime.now().isoformat(),
        }

        log.info(f"Sync completed successfully. Total records processed: {total_processed}")
        op.checkpoint(state=final_state)

    except Exception as e:
        # In case of an exception, raise a runtime error
        log.error("Failed to sync FDA tobacco data", e)
        raise RuntimeError(f"Failed to sync FDA tobacco data: {str(e)}")


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
