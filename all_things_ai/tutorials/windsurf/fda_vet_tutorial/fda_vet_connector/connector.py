"""
FDA Veterinary Adverse Event Reporting System (FAERS) Connector

This connector demonstrates how to fetch veterinary adverse event data from the FDA API
and upsert it into destination using the Fivetran Connector SDK.
"""

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import (
    Connector,
)  # For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Logging as log  # For enabling Logs in your connector code
from fivetran_connector_sdk import (
    Operations as op,
)  # For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()

# Source-specific imports
import json  # For JSON data processing
import requests  # For making HTTP API calls to FDA
from datetime import datetime  # For timestamp handling
from utils import flatten_dict  # For flattening nested JSON structures


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    # FDA API doesn't require authentication for public endpoints
    # Configuration validation is minimal for this public API
    log.info("Configuration validation passed - FDA API is public")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Returns:
        list: Schema definition with table name and primary key
    """
    return [
        {
            "table": "events",  # Name of the table in the destination
            "primary_key": ["unique_aer_id_number"],  # Primary key column for the table
        }
    ]


def fetch_fda_data(params: dict):
    """
    Fetch data from the FDA Veterinary API.

    Args:
        params: Dictionary containing API parameters

    Returns:
        dict: API response data

    Raises:
        requests.RequestException: If API request fails
    """
    base_url = "https://api.fda.gov/animalandveterinary/event.json"

    log.info(f"Fetching data from {base_url} with params: {params}")

    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        log.error("Failed to fetch data from FDA API", e)
        raise


def process_event_data(event_data: list, state: dict):
    """
    Process and upsert event data into the destination.

    Args:
        event_data: List of event records from FDA API
        state: Current state dictionary

    Returns:
        dict: Updated state dictionary
    """
    processed_count = 0

    for event in event_data:
        try:
            # Flatten the nested dictionary structure
            flattened_event = flatten_dict(event)

            # Upsert the flattened data - direct operation call without yield
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table="events", data=flattened_event)

            processed_count += 1

            # Log progress every 10 records
            if processed_count % 10 == 0:
                log.info(f"Processed {processed_count} records")

        except Exception as e:
            log.error("Error processing event record", e)
            # Continue processing other records even if one fails
            continue

    # Update state with processing statistics
    state["total_processed"] = state.get("total_processed", 0) + processed_count
    state["last_processed"] = datetime.now().isoformat()

    log.info(
        f"Successfully processed {processed_count} records. Total processed: {state['total_processed']}"
    )

    return state


def update(configuration: dict, state: dict = None):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
               The state dictionary is empty for the first sync or for any full re-sync
    """
    log.info("Starting FDA Veterinary Adverse Event data sync")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Initialize state if not provided
    if state is None:
        state = {}

    # Initialize or update state with default values
    state.setdefault("last_processed", datetime.now().isoformat())
    state.setdefault("total_processed", 0)

    try:
        # Configure API parameters
        # Start with a reasonable limit for initial testing
        params = {"limit": configuration.get("batch_size", "100")}  # Configurable batch size

        # Add date filtering if specified in configuration
        if configuration.get("start_date"):
            params["search"] = f"receivedate:[{configuration['start_date']} TO *]"

        # Fetch data from FDA API
        api_data = fetch_fda_data(params)

        # Extract results from API response
        events = api_data.get("results", [])

        if not events:
            log.warning("No events found in API response")
            return

        log.info(f"Retrieved {len(events)} events from FDA API")

        # Process and upsert the event data
        updated_state = process_event_data(events, state)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state=updated_state)

        log.info("FDA Veterinary data sync completed successfully")

    except Exception as e:
        # In case of an exception, log the error and raise a runtime error
        log.error("Failed to sync FDA Veterinary data", e)
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
