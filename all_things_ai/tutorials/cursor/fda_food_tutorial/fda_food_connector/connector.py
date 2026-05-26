# FDA Food Enforcement API Connector
# This connector fetches data from the FDA Food Enforcement API and upserts it into the destination.
# The connector supports both API key and no API key authentication, configurable batch sizes, and incremental syncs.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

# Add your source-specific imports here
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any
import time

# Constants for configuration
BASE_URL = "https://api.fda.gov/food/enforcement.json"
DEFAULT_LIMIT = 1000  # FDA API maximum limit per request
CHECKPOINT_INTERVAL = 10  # Checkpoint every 10 rows as requested


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
    required_configs = ["max_records", "use_api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate numeric values
    try:
        int(configuration["max_records"])
    except ValueError:
        raise ValueError("max_records must be a valid integer")

    # Validate boolean value
    if configuration["use_api_key"] not in ["true", "false"]:
        raise ValueError("use_api_key must be 'true' or 'false'")


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
            "table": "fda_food_enforcement_reports",  # Name of the table in the destination, required.
            "primary_key": ["event_id"],  # Primary key column(s) for the table, required.
        },
    ]


def flatten_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten complex fields in the record to make them compatible with Fivetran Connector SDK.
    Args:
        record: The original record from FDA API
    Returns:
        Flattened record with complex fields converted to strings
    """
    flattened = {}

    for key, value in record.items():
        if isinstance(value, dict):
            # Convert nested objects to JSON strings
            if value:  # Only if not empty
                flattened[key] = json.dumps(value)
            else:
                flattened[key] = ""
        elif isinstance(value, list):
            # Convert arrays to comma-separated strings
            if value:
                flattened[key] = "; ".join(str(item) for item in value)
            else:
                flattened[key] = ""
        else:
            flattened[key] = value

    return flattened


def fetch_fda_food_data(configuration: dict, state: dict) -> List[Dict[str, Any]]:
    """
    Fetch data from the FDA Food Enforcement API with pagination and rate limiting.
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
    Returns:
        List of dictionaries containing the API response data
    """
    # Extract configuration parameters
    max_records = int(configuration.get("max_records", "10"))
    api_key = configuration.get("api_key", "")
    use_api_key = configuration.get("use_api_key", "false").lower() == "true"
    if len(api_key) > 2:
        masked_api_key = api_key[:2] + "*" * (len(api_key) - 2)
    else:
        masked_api_key = api_key  # too short to mask
    log.info(masked_api_key)
    lookback_days = int(configuration.get("lookback_days", "30"))
    use_date_filter = configuration.get("use_date_filter", "false").lower() == "true"

    # Prepare request parameters
    params = {"limit": min(max_records, DEFAULT_LIMIT), "skip": 0}

    # Add date filter only if requested and working
    if use_date_filter:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        date_range = f"[{start_date.strftime('%Y%m%d')}+TO+{end_date.strftime('%Y%m%d')}]"
        params["search"] = f"report_date:{date_range}"
        log.info(
            f"Using date filter: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )
    else:
        log.info("Fetching most recent records without date filtering")

    # Add API key if configured
    if use_api_key and api_key:
        params["api_key"] = api_key
        log.info("Using API key for authentication")
    else:
        log.info(
            "Using no API key authentication (limited to 240 requests/minute, 1000 requests/day)"
        )

    # Track processed records
    processed_count = 0
    total_to_process = min(max_records, DEFAULT_LIMIT)
    all_records = []

    log.info(f"Starting data fetch: max_records={max_records}, lookback_days={lookback_days}")

    while processed_count < total_to_process:
        try:
            # Make API request
            log.info(f"Fetching data: skip={params['skip']}, limit={params['limit']}")
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Check for API errors
            if "error" in data:
                log.error(f"API error: {data['error']}")
                raise RuntimeError(f"FDA API error: {data['error']['message']}")

            # Check if we have results
            if not data.get("results") or not data["results"]:
                log.info("No more results from API")
                break

            # Log API metadata
            if "meta" in data and "results" in data["meta"]:
                meta = data["meta"]["results"]
                log.info(
                    f"API returned {len(data['results'])} records (total available: {meta.get('total', 'unknown')})"
                )

            # Process results
            results = data["results"]
            for record in results:
                if processed_count >= total_to_process:
                    break

                # Flatten the record to handle nested objects
                flattened_record = flatten_record(record)

                # Add metadata fields
                flattened_record["_fivetran_synced"] = datetime.now().isoformat()
                flattened_record["_fivetran_batch_id"] = (
                    f"batch_{params['skip']}_{params['limit']}"
                )
                flattened_record["_data_source"] = "FDA_Food_Enforcement_API"

                all_records.append(flattened_record)
                processed_count += 1

            # Check if we have more data to fetch
            if len(results) < params["limit"] or processed_count >= total_to_process:
                break

            # Update skip for next page
            params["skip"] += params["limit"]

            # Rate limiting - FDA allows 240 requests per minute without API key
            if not use_api_key:
                time.sleep(0.25)  # 240 requests per minute = 0.25 seconds between requests

        except requests.exceptions.RequestException as e:
            log.error("API request failed", e)
            raise RuntimeError(f"Failed to fetch data from FDA API: {str(e)}")
        except Exception as e:
            log.error("Unexpected error during data fetch", e)
            raise RuntimeError(f"Unexpected error: {str(e)}")

    log.info(f"Completed data fetch. Total records processed: {processed_count}")
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
    log.info("FDA Food Enforcement API Connector: Starting sync")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters
    max_records = int(configuration.get("max_records", "10"))
    api_key = configuration.get("api_key", "")
    if len(api_key) > 2:
        masked_api_key = api_key[:2] + "*" * (len(api_key) - 2)
    else:
        masked_api_key = api_key  # too short to mask
    log.info(masked_api_key)
    lookback_days = int(configuration.get("lookback_days", "30"))

    # Get the state variable for the sync, if needed
    last_sync_time = state.get("last_sync_time")
    last_processed_count = state.get("last_processed_count", 0)

    if last_sync_time:
        log.info(
            f"Resuming from previous sync: {last_sync_time}, processed: {last_processed_count}"
        )
    else:
        log.info("Starting fresh sync")

    try:
        # Fetch data from FDA API
        records = fetch_fda_food_data(configuration, state)

        # Process records in batches for better performance
        batch_size = 100
        records_processed = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]

            # Process each record in the batch
            for record in batch:
                # Direct operation call without yield - easier to adopt
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted.
                op.upsert(table="fda_food_enforcement_reports", data=record)
                records_processed += 1

                # Exit gracefully after processing the configured number of records
                if records_processed >= max_records:
                    log.info(f"Reached maximum records limit ({max_records}), stopping sync")
                    break

            # Checkpoint after each batch for incremental syncs
            if i + batch_size < len(records):
                checkpoint_state = {
                    "last_processed_count": records_processed,
                    "last_sync_time": datetime.now().isoformat(),
                    "batch_completed": i + batch_size,
                }
                op.checkpoint(state=checkpoint_state)
                log.info(f"Checkpointed after processing {records_processed} records")

        # Final checkpoint with completion state
        final_state = {
            "last_sync_time": datetime.now().isoformat(),
            "last_processed_count": records_processed,
            "total_records_processed": records_processed,
            "sync_completed": True,
            "lookback_days": lookback_days,
        }

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state=final_state)

        log.info(f"Sync completed successfully. Total records processed: {records_processed}")

    except Exception as e:
        # In case of an exception, raise a runtime error
        log.error("Sync failed", e)
        raise RuntimeError(f"Failed to sync data: {str(e)}")


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
