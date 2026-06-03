"""
This connector demonstrates how to fetch purchase order data from the SAP Ariba API and
upsert it into a Fivetran destination using the Connector SDK.

The sync is performed via full table replication using offset-based pagination.
Note: Incremental filtering is not supported by the current sandbox environment.

See the Fivetran Connector SDK documentation:
- Technical Reference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
- Best Practices: https://fivetran.com/docs/connectors/connector-sdk/best-practices
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to SAP Ariba
import requests

# For handling datetime parsing and formatting
from datetime import datetime, timezone

# For handling exponential backoff in retries
import time

# Constants
__MAX_RETRIES = 3
__RETRY_DELAY = 3  # seconds
__BASE_URL = "https://sandbox.api.sap.com/ariba/api/purchase-orders/v1/sandbox/"
__RECORDS_PER_PAGE = 100
__CHECKPOINT_INTERVAL = 1000
__PAGE_OFFSET = "$skip"

# Schema Definitions


def get_order_columns():
    """Return the column schema definition for the 'order' table."""
    return {
        "documentNumber": "STRING",
        "orderDate": "UTC_DATETIME",
        "supplierName": "STRING",
        "supplierANID": "STRING",
        "buyerANID": "STRING",
        "customerName": "STRING",
        "systemId": "STRING",
        "payloadId": "STRING",
        "revision": "STRING",
        "endpointId": "STRING",
        "created": "UTC_DATETIME",
        "status": "STRING",
        "documentStatus": "STRING",
        "amount": "DOUBLE",
        "numberOfInvoices": "INT",
        "invoiced_amount": "DOUBLE",
        "company_code": "STRING",
        "rowId": "INT",
    }


def get_item_columns():
    """Return the column schema definition for the 'item' table."""
    return {
        "documentNumber": "STRING",
        "lineNumber": "INT",
        "quantity": "DOUBLE",
        "unitOfMeasure": "STRING",
        "supplierPart": "STRING",
        "buyerPartId": "STRING",
        "manufacturerPartId": "STRING",
        "description": "STRING",
        "itemShipToName": "STRING",
        "itemShipToStreet": "STRING",
        "itemShipToCity": "STRING",
        "itemShipToState": "STRING",
        "itemShipToPostalCode": "STRING",
        "itemShipToCountry": "STRING",
        "isoCountryCode": "STRING",
        "itemShipToCode": "STRING",
        "itemLocation": "STRING",
        "requestedDeliveryDate": "UTC_DATETIME",
        "requestedShipmentDate": "UTC_DATETIME",
        "rowId": "INT",
    }


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
            "table": "order",
            "primary_key": ["payloadId", "revision", "rowId"],
            "columns": get_order_columns(),
        },
        {
            "table": "item",
            "primary_key": ["documentNumber", "lineNumber", "rowId"],
            "columns": get_item_columns(),
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    validate_configuration(configuration)
    log.warning("Example: Source Examples - SAP Ariba")

    # Store the sync start time in ISO format for the 'last_updated_at' column.
    sync_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {
        "APIKey": configuration.get("api_key"),
        "Accept": "application/json",
        "DataServiceVersion": "2.0",
    }
    params = {"$top": __RECORDS_PER_PAGE, "$count": True}

    # Execute sync for both tables.
    sync_table(params.copy(), "order", headers, state, sync_start)
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    sync_table(params.copy(), "item", headers, state, sync_start)
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info("SAP Ariba sync completed successfully.")


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required parameters are present.
    Args:
        configuration: Configuration dictionary.
    Raises:
        ValueError: If 'api_key' is missing.
    """
    if "api_key" not in configuration:
        raise ValueError("Missing required configuration: api_key")


def sync_table(params: dict, table: str, headers: dict, state: dict, sync_start: str):
    """
    Initiates a full sync for a table, either 'item' or the 'order' data.
    Args:
        params: API query parameters.
        table: The table/entity name.
        headers: HTTP headers.
        state: State dictionary.
        sync_start: Sync start timestamp string.
    """
    log.info(f"Starting full sync for table: {table}")

    # set variable for which columns to get when syncing rows
    if table == "order":
        columns = get_order_columns()
    elif table == "item":
        columns = get_item_columns()
    else:
        log.error(f"Table {table} is not supported for sync.")
        return

    # Reset offset to 0 for a full table sync.
    params[__PAGE_OFFSET] = 0
    if table not in state:
        state[table] = {}

    sync_rows(table, params, headers, state, columns, sync_start)


def sync_rows(
    table: str, params: dict, headers: dict, state: dict, allowed_columns: dict, sync_start: str
):
    """
    Iteratively fetch and upsert paginated data from the SAP Ariba API.

    Handles pagination, column filtering, and periodic checkpointing.
    Args:
        table (str): The table/entity name.
        params (dict): API query parameters (including page offset).
        headers (dict): HTTP headers.
        state (dict): State dictionary for checkpointing.
        allowed_columns (dict): Destination column schema.
        sync_start (str): Timestamp for 'last_updated_at'.
    """
    count = 0
    endpoint = table

    # Loop through all pages of data until no more data is returned.
    while True:
        data = make_api_request(endpoint, params=params, headers=headers)
        if not data:
            break

        # Determine total records count from the first page response.
        if data.get("firstPage"):
            total = data.get("count", 0)
            log.info(f"Total records to process for {table}: {total}")

        items = data.get("content", [])
        if not items:
            break

        for item in items:
            count += 1
            record = filter_columns(item, allowed_columns)
            record["rowId"] = count
            record["last_updated_at"] = sync_start

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=table, data=record)

        # Checkpoint the state periodically to save progress.
        if count % __CHECKPOINT_INTERVAL == 0:
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
            op.checkpoint(state)

        # Increment the offset parameter for the next page fetch.
        params[__PAGE_OFFSET] += __RECORDS_PER_PAGE


def make_api_request(
    endpoint: str, params: dict, headers: dict, retries=__MAX_RETRIES, delay=__RETRY_DELAY
):
    """
    Perform a GET request with retry logic and exponential backoff.

    Handles rate limiting (429) and server errors (5xx) by retrying.
    Args:
        endpoint (str): The specific API path.
        params (dict): Query parameters.
        headers (dict): HTTP headers.
        retries (int, optional): Max number of retries.
        delay (int, optional): Base delay for exponential backoff.
    Returns:
        dict: Parsed JSON content.
    Raises:
        requests.RequestException: If the request fails after all retries.
    """
    url = f"{__BASE_URL}{endpoint}"
    last_exception = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                wait = delay * attempt
                log.warning(f"Rate limit hit. Retrying in {wait}s...")
                time.sleep(wait)
            elif 400 <= response.status_code < 500:
                # Client errors (other than 429) should fail immediately without retry
                log.error(f"Client error {response.status_code}: {response.text}")
                response.raise_for_status()
            elif 500 <= response.status_code < 600:
                log.warning(f"Server error {response.status_code}, retrying...")
                last_exception = requests.HTTPError(
                    f"Server error {response.status_code} after {retries} retries",
                    response=response,
                )
                if attempt < retries:
                    time.sleep(delay * attempt)
                    continue
            else:
                raise requests.HTTPError(
                    f"Unexpected HTTP status code: {response.status_code}", response=response
                )
        except requests.RequestException as e:
            last_exception = e
            if attempt == retries:
                break
            log.error(f"Network error: {e}")
            time.sleep(delay * attempt)

    # Re-raise the last exception if all retries exhausted
    if last_exception:
        raise last_exception

    raise RuntimeError(f"API request to {endpoint} failed after {retries} retries")


def filter_columns(record: dict, allowed_columns: dict) -> dict:
    """
    Filter record fields and transform UTC_DATETIME fields to ISO 8601 format.
    Args:
        record: Raw record dictionary from the API.
        allowed_columns: Dictionary of allowed column names and their types.
    Returns:
        Filtered dictionary.
    """
    filtered = {}

    for col, col_type in allowed_columns.items():
        if col == "rowId":
            continue

        if col_type == "UTC_DATETIME":
            filtered[col] = convert_to_iso(record.get(col))

        elif col in record:
            filtered[col] = record[col]

    return filtered


def convert_to_iso(date_str: str) -> str | None:
    """
    Convert a common SAP Ariba date string format to ISO 8601 format.

    Parses 'DD Mon YYYY HH:MM:SS AM/PM' and outputs 'YYYY-MM-DDTHH:MM:SSZ'.
    Args:
        date_str (str): The SAP API date string.
    Returns:
        str or None: The ISO 8601 formatted string, None, or the original string.
    """
    if not date_str:
        return None

    try:
        dt = datetime.strptime(date_str, "%d %b %Y %I:%M:%S %p")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    except ValueError:
        log.warning(f"Unable to parse date string: {date_str}. Returning original value.")
        return date_str


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
