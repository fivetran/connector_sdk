"""This connector fetches healthcare provider data from the NPPES NPI Registry API and syncs it to the destination.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to the NPI Registry API
import requests

# For implementing exponential backoff retry logic
import time

# Constants for API configuration
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__BASE_DELAY = 1  # Base delay in seconds for API request retries
__CHECKPOINT_INTERVAL = 500  # Checkpoint after processing this many records
__MAX_SKIP = 1000  # Maximum skip value allowed by the API
__REQUEST_TIMEOUT = 30  # Timeout in seconds for API requests


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate that the API URL is provided
    if "api_url" not in configuration:
        raise ValueError(
            "api_url is required. Please provide the complete API URL from https://npiregistry.cms.hhs.gov/demo-api"
        )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    return [
        {"table": "provider", "primary_key": ["number"]},
        {"table": "address", "primary_key": ["number", "address_purpose"]},
        {"table": "taxonomy", "primary_key": ["number", "code"]},
        {"table": "identifier", "primary_key": ["number", "identifier"]},
        {"table": "endpoint", "primary_key": ["number", "endpoint"]},
        {"table": "other_name", "primary_key": ["number", "code", "type"]},
        {"table": "practice_location", "primary_key": ["number", "address_1"]},
    ]


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

    log.warning("Example:Source Examples - NPPES NPI Registry")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Get the current skip offset from state (for pagination)
    current_skip = state.get("skip", 0)

    # Get the base API URL from configuration
    base_api_url = configuration["api_url"]

    log.info(f"Starting sync from skip offset: {current_skip}")

    records_processed = 0

    try:
        # Continue fetching data until no more results are returned or max skip reached
        # Note: API limits skip to 1000, so maximum 1,200 records can be retrieved (6 pages of 200)
        while current_skip <= __MAX_SKIP:
            # Fetch a page of results from the API
            results, total_results = fetch_npi_data(base_api_url, current_skip)

            if not results:
                log.info("No more results found. Sync complete.")
                break

            log.info(
                f"Processing {len(results)} providers (skip: {current_skip}, total: {total_results})"
            )

            # Process each provider record
            for result in results:
                process_provider_record(result)
                records_processed += 1

            # Check if we've reached the end of results before incrementing skip
            if current_skip + len(results) >= total_results:
                log.info(f"Reached end of results. Total records processed: {records_processed}")
                break

            # Move to next page
            current_skip += len(results)

            # Checkpoint periodically to save progress
            if records_processed % __CHECKPOINT_INTERVAL == 0:
                new_state = {"skip": current_skip}
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(new_state)
                log.info(f"Checkpoint saved at skip offset: {new_state['skip']}")

            # Warn if approaching API limit
            if __MAX_SKIP < current_skip + len(results) < total_results:
                log.warning(
                    f"API limit will be reached on the next iteration. Maximum skip value is {__MAX_SKIP}. Retrieved {records_processed} of {total_results} total records. Refine your search criteria to get specific records."
                )

        # Final checkpoint at the end of sync
        final_state = {"skip": 0}  # Reset for next full sync
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(final_state)
        log.info(f"Sync completed successfully. Total records processed: {records_processed}")

    except requests.exceptions.RequestException as e:
        # Handle API request errors
        log.error(f"API request failed: {str(e)}")
        raise RuntimeError(f"Failed to fetch data from NPI Registry API: {str(e)}")
    except Exception as e:
        # In case of an exception, raise a runtime error
        log.error(f"Unexpected error during sync: {str(e)}")
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def fetch_npi_data(base_url: str, skip: int):
    """
    Fetch data from the NPI Registry API with pagination support.

    Note: Each page contains a maximum of 200 records (API limit), which is
    safe to load into memory. Records are processed immediately upon return
    in the update() function, ensuring efficient memory usage through streaming
    pagination rather than accumulating all records.

    Args:
        base_url: The complete API URL from configuration
        skip: Number of records to skip (for pagination)

    Returns:
        Tuple of (results list, total result count)
    """
    # Add skip parameter to the URL
    separator = "&" if "?" in base_url else "?"
    url_with_skip = f"{base_url}{separator}skip={skip}"

    # Make API request with retry logic
    response_data = make_api_request_with_retry(url_with_skip)

    results = response_data.get("results", [])
    result_count = response_data.get("result_count", 0)

    return results, result_count


def make_api_request_with_retry(url: str):
    """
    Make an API request with exponential backoff retry logic.
    Args:
        url: The complete API URL with all parameters
    Returns:
        JSON response data
    Raises:
        requests.exceptions.RequestException: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, timeout=__REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == __MAX_RETRIES - 1:
                raise
            delay = __BASE_DELAY * (2**attempt)
            log.warning(
                f"API request failed (attempt {attempt + 1}/{__MAX_RETRIES}): {str(e)}. Retrying in {delay}s..."
            )
            time.sleep(delay)

    # This should never be reached due to the raise in the exception handler,
    # but added for completeness to avoid implicit None return
    raise RuntimeError("API request failed after all retry attempts")


def process_provider_record(result: dict):
    """
    Process a single provider record and upsert data into multiple tables.
    Args:
        result: A provider result dictionary from the API
    """
    number = result.get("number")

    if not number:
        log.warning("Skipping record without NPI number")
        return

    # Upsert main provider data
    provider_data = flatten_provider_basic(result)
    # The 'upsert' operation is used to insert or update data in the destination table.
    # The op.upsert method is called with two arguments:
    # - The first argument is the name of the table to upsert the data into.
    # - The second argument is a dictionary containing the data to be upserted,
    op.upsert(table="provider", data=provider_data)

    # Upsert child records using generic flattening
    upsert_child_records(number, result.get("addresses", []), "address")
    upsert_child_records(number, result.get("taxonomies", []), "taxonomy")
    upsert_child_records(number, result.get("identifiers", []), "identifier")
    upsert_child_records(number, result.get("endpoints", []), "endpoint")
    upsert_child_records(number, result.get("other_names", []), "other_name")
    upsert_child_records(number, result.get("practiceLocations", []), "practice_location")


def flatten_provider_basic(result: dict):
    """
    Flatten the basic provider information from the result.
    Args:
        result: Provider result dictionary
    Returns:
        Flattened dictionary with provider basic information
    """
    basic = result.get("basic", {})

    provider_data = {
        "number": result.get("number"),
        "enumeration_type": result.get("enumeration_type"),
        "created_epoch": result.get("created_epoch"),
        "last_updated_epoch": result.get("last_updated_epoch"),
    }

    # Flatten all basic fields
    for key, value in basic.items():
        provider_data[f"basic_{key}"] = value

    return provider_data


def upsert_child_records(number: str, records: list, table_name: str):
    """
    Generic function to flatten and upsert child records for any child table.
    Args:
        number: NPI number (foreign key)
        records: List of child records to process
        table_name: Name of the destination table
    """
    if not records:
        return

    for record in records:
        flattened = {"number": number}
        # Rename 'desc' to 'description' to avoid SQL reserved keyword conflict
        for key, value in record.items():
            if key == "desc":
                flattened["description"] = value
            else:
                flattened[key] = value

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table=table_name, data=flattened)


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
