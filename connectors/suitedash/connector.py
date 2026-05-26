"""This is an example to show how to sync CRM data from SuiteDash's API by using Connector SDK. You need to provide your SuiteDash Public ID and Secret Key for this example to work.
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

# Import requests for making HTTP API calls to SuiteDash
import requests

# Import json for configuration file handling
import json

# Import time for implementing retry delays
import time

# Import Any for type hinting
from typing import Any

__BASE_URL = "https://app.suitedash.com/secure-api"  # Base URL for SuiteDash API
__COMPANIES_ENDPOINT = "/companies"  # Endpoint for fetching companies
__CONTACTS_ENDPOINT = "/contacts"  # Endpoint for fetching contacts
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__RETRY_DELAY = 1  # Base retry delay in seconds


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters for SuiteDash API
    required_configs = ["public_id", "secret_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def flatten_nested_object(obj: dict, prefix: str = "") -> dict:
    """
    Flatten nested dictionary objects into a flat structure with prefixed keys.
    Converts nested dictionaries like {"contact": {"name": "John"}} to {"contact_name": "John"}.
    Args:
        obj (dict): The nested dictionary to flatten
        prefix (str): The prefix to add to the flattened keys
    Returns:
        dict: A flattened dictionary with prefixed keys
    """
    flattened = {}
    if not obj:
        return flattened

    for key, value in obj.items():
        new_key = f"{prefix}_{key}" if prefix else key
        if isinstance(value, dict) and value:
            flattened.update(flatten_nested_object(value, new_key))
        else:
            flattened[new_key] = value
    return flattened


def process_company_record(company: dict) -> dict:
    """
    Process a company record by flattening nested objects and handling arrays.
    Transforms raw SuiteDash company data into a flat structure suitable for database storage.
    Args:
        company (dict): Raw company record from SuiteDash API
    Returns:
        dict: Processed company record ready for upsert operation
    """
    processed = {}

    # Copy basic fields from company record
    basic_fields = [
        "uid",
        "role",
        "name",
        "phone",
        "home_phone",
        "work_phone",
        "shop_phone",
        "full_address",
        "website",
        "background_info",
        "created",
    ]
    for field_name in basic_fields:
        processed[field_name] = company.get(field_name)

    # Flatten primaryContact object
    primary_contact = company.get("primaryContact", {})
    if primary_contact:
        flattened_contact = flatten_nested_object(primary_contact, "primaryContact")
        processed.update(flattened_contact)

    # Flatten category object
    category = company.get("category", {})
    if category:
        flattened_category = flatten_nested_object(category, "category")
        processed.update(flattened_category)

    # Flatten address object
    address = company.get("address", {})
    if address:
        flattened_address = flatten_nested_object(address, "address")
        processed.update(flattened_address)

    # Convert tags array to comma-separated string
    tags = company.get("tags", [])
    processed["tags"] = ",".join(tags) if tags else None

    return processed


def process_contact_record(contact: dict) -> dict:
    """
    Process a contact record by flattening nested objects and handling arrays.
    Transforms raw SuiteDash contact data into a flat structure suitable for database storage.
    Args:
        contact (dict): Raw contact record from SuiteDash API
    Returns:
        dict: Processed contact record ready for upsert operation
    """
    processed = {}

    # Copy basic fields from contact record
    basic_fields = [
        "uid",
        "first_name",
        "last_name",
        "email",
        "name_prefix",
        "home_email",
        "work_email",
        "phone",
        "home_phone",
        "work_phone",
        "shop_phone",
        "title",
        "active",
        "role",
        "full_address",
        "website",
        "background_info",
        "created",
    ]
    for field_name in basic_fields:
        processed[field_name] = contact.get(field_name)

    # Flatten address object
    address = contact.get("address", {})
    if address:
        flattened_address = flatten_nested_object(address, "address")
        processed.update(flattened_address)

    # Convert tags and circles arrays to comma-separated strings
    tags = contact.get("tags", [])
    processed["tags"] = ",".join(tags) if tags else None

    circles = contact.get("circles", [])
    processed["circles"] = (
        ",".join([circle.get("name", "") for circle in circles if isinstance(circle, dict)])
        if circles
        else None
    )

    return processed


def extract_contact_company_relationships(contact: dict, op) -> int:
    """
    Extract contact-company relationships from a contact record and upsert them directly.
    Creates separate relationship records for each company associated with a contact and upserts them immediately.
    Args:
        contact (dict): Contact record from SuiteDash API
        op: Operations object for upserting data
    Returns:
        int: Number of relationships processed
    """
    relationships_processed = 0
    contact_uid = contact.get("uid")
    companies = contact.get("companies", [])

    for company in companies:
        if isinstance(company, dict):
            relationship = {
                "contact_uid": contact_uid,
                "company_uid": company.get("uid"),
                "company_name": company.get("name"),
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table="contact_company_relationship", data=relationship)
            relationships_processed += 1

    return relationships_processed


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
            "table": "company",  # Company table from /companies endpoint
            "primary_key": ["uid"],  # Primary key is the unique company ID
        },
        {
            "table": "contact",  # Contact table from /contacts endpoint
            "primary_key": ["uid"],  # Primary key is the unique contact ID
        },
        {
            "table": "contact_company_relationship",  # Junction table for contact-company relationships
            "primary_key": ["contact_uid", "company_uid"],  # Composite primary key
        },
    ]


def get_api_headers(configuration: dict) -> dict:
    """
    Build authentication headers required for SuiteDash API requests.
    Creates headers with public ID and secret key for API authentication.
    Args:
        configuration (dict): Configuration dictionary containing API credentials
    Returns:
        dict: Headers dictionary for API requests including authentication
    """
    return {
        "X-Public-ID": configuration["public_id"],
        "X-Secret-Key": configuration["secret_key"],
        "Content-Type": "application/json",
    }


def make_api_request(url: str, headers: dict, params=None) -> Any:
    """
    Make an authenticated HTTP GET request to the SuiteDash API with retry logic and error handling.
    Handles HTTP errors, rate limiting, and transient failures with exponential backoff.
    Args:
        url (str): The API endpoint URL to request
        headers (dict): Authentication headers for the request
        params (dict, optional): Query parameters for the request
    Returns:
        dict: JSON response parsed as dictionary
    Raises:
        RuntimeError: If the API request fails after all retry attempts
    """
    for attempt in range(__MAX_RETRIES):
        try:
            log.info(f"Making API call to: {url} with params: {params}")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            if attempt == __MAX_RETRIES - 1:  # Last attempt
                log.error(f"API request failed after {__MAX_RETRIES} attempts", e)
                raise RuntimeError(f"Failed to fetch data from SuiteDash API: {str(e)}")

            # Calculate delay with exponential backoff
            delay = __RETRY_DELAY * (2**attempt)
            log.warning(
                f"API request failed (attempt {attempt + 1}/{__MAX_RETRIES}), retrying in {delay}s: {str(e)}"
            )
            time.sleep(delay)

    return None


def process_and_upsert_records(
    records: list,
    table_name: str,
    record_processor_func,
    relationship_processor_func=None,
) -> tuple[int, int]:
    """
    Processes and upserts a batch of records from a single API page.

    This helper function iterates through a list of records, applies the necessary
    transformations, upserts the main record, and optionally processes any
    defined relationships.

    Args:
        records (list): A list of record dictionaries to be processed.
        table_name (str): The destination table name for the upsert operation.
        record_processor_func (callable): Function to process an individual record.
        relationship_processor_func (callable, optional): Function to process relationships.

    Returns:
        tuple[int, int]: A tuple containing the count of processed records and
                         the count of processed relationships for the given batch.
    """
    records_in_page = 0
    relationships_in_page = 0
    for record in records:
        # Process main record data
        processed_record = record_processor_func(record)

        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table=table_name, data=processed_record)

        records_in_page += 1

        # Process relationships if function provided
        if relationship_processor_func:
            relationships_in_page += relationship_processor_func(record, op)

    return records_in_page, relationships_in_page


def sync_endpoint_with_pagination(
    state: dict,
    configuration: dict,
    endpoint: str,
    endpoint_name: str,
    table_name: str,
    record_processor_func,
    relationship_processor_func=None,
) -> dict:
    """
    Generic function to sync data from SuiteDash API endpoints with pagination support.
    Handles pagination, processing, and upserting records.
    Args:
        state (dict): State dictionary to manage sync progress
        configuration (dict): Configuration dictionary containing API credentials
        endpoint (str): API endpoint path (e.g., "/companies", "/contacts")
        endpoint_name (str): Human-readable endpoint name for logging
        table_name (str): Destination table name for upserting records
        record_processor_func (callable): Function to process individual records
        relationship_processor_func (callable, optional): Function to process relationships (for contacts)
    Returns:
        dict: Summary of processing results
    """
    log.info(f"Starting {endpoint_name} sync")
    headers = get_api_headers(configuration)
    page = 1
    more_data = True
    total_records_processed = 0
    total_relationships_processed = 0

    while more_data:
        url = f"{__BASE_URL}{endpoint}"
        params = {"page": page}

        response_data = make_api_request(url, headers, params)

        if not response_data.get("success", False):
            log.error(f"API returned error: {response_data.get('message', 'Unknown error')}")
            break

        records = response_data.get("data", [])
        if not records:
            log.info(f"No more {endpoint_name} to process")
            break

        # Process the batch of records from the current page
        page_records, page_relationships = process_and_upsert_records(
            records,
            table_name,
            record_processor_func,
            relationship_processor_func,
        )

        total_records_processed += page_records
        total_relationships_processed += page_relationships

        log_message = (
            f"Processed page {page} of {endpoint_name}, total processed: {total_records_processed}"
        )

        if relationship_processor_func:
            log_message += f", relationships: {total_relationships_processed}"

        log.info(log_message)

        # Check pagination metadata to determine if more pages exist
        pagination = response_data.get("meta", {}).get("pagination", {})
        next_page_url = pagination.get("nextPage")

        if next_page_url:
            page += 1
        else:
            more_data = False

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    # Build and write final summary log
    summary_message = f"{endpoint_name.capitalize()} sync completed. Total {endpoint_name} processed: {total_records_processed}"

    if relationship_processor_func:
        summary_message += f", relationships: {total_relationships_processed}"

    log.info(summary_message)

    return {
        "records_processed": total_records_processed,
        "relationships_processed": total_relationships_processed,
    }


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

    log.warning("Example: Source Examples : SuiteDash")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    try:
        # Sync companies data from /companies endpoint
        companies_result = sync_endpoint_with_pagination(
            state=state,
            configuration=configuration,
            endpoint=__COMPANIES_ENDPOINT,
            endpoint_name="companies",
            table_name="company",
            record_processor_func=process_company_record,
        )

        # Sync contacts data from /contacts endpoint
        contacts_result = sync_endpoint_with_pagination(
            state=state,
            configuration=configuration,
            endpoint=__CONTACTS_ENDPOINT,
            endpoint_name="contacts",
            table_name="contact",
            record_processor_func=process_contact_record,
            relationship_processor_func=extract_contact_company_relationships,
        )

        log.info(
            f"SuiteDash sync completed successfully. Companies: {companies_result['records_processed']}, "
            f"Contacts: {contacts_result['records_processed']}, "
            f"Relationships: {contacts_result['relationships_processed']}"
        )

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data from SuiteDash: {str(e)}")


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
