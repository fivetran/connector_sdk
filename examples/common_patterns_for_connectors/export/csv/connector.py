# This is a simple example of how to work with CSV file response for a REST API of export type.
# It defines a simple `update` method, which upserts retrieved data to a table named "item".
# THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
# (https://pypi.org/project/fivetran-api-playground/) TO RUN.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.


# Import requests to make HTTP calls to API.
import requests as rq

# Import CSV for parsing CSV data.
import csv

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op
from io import StringIO


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
            "table": "user",
            "primary_key": ["id"],
            "columns": {
                "id": "STRING",
                "name": "STRING",
                "email": "STRING",
                "address": "STRING",
                "company": "STRING",
                "job": "STRING",
                "updatedAt": "UTC_DATETIME",
                "createdAt": "UTC_DATETIME",
            },
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Handling CSV Response - Syncing data from CSV Export API")

    print(
        "RECOMMENDATION: Please ensure the base url is properly set, you can also use "
        "https://pypi.org/project/fivetran-api-playground/ to start mock API on your local machine."
    )
    base_url = "http://127.0.0.1:5001/export/csv"

    # Call the sync_csv_data function to process the CSV data.
    sync_csv_data(base_url, state)


def sync_csv_data(base_url, state):
    """
    The sync_csv_data function handles retrieving and processing CSV data from the API.
    Args:
        base_url: The base URL of the API endpoint to fetch CSV data.
        state: The state dictionary containing information about the last sync.
    """
    # Get response from API call.
    response_page = get_csv_response(base_url, {})

    # Parse the CSV content and process rows.
    items = parse_csv(response_page)
    if not items:
        return  # No data to sync

    # Process each row in the CSV response.
    log.info("Syncing CSV contents...")
    for item in items:
        op.upsert(table="user", data=item)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def get_csv_response(base_url, params):
    """
    The get_csv_response function sends an HTTP GET request and returns the raw CSV response as text.
    Args:
        base_url: The base URL of the API endpoint to fetch CSV data.
        params: A dictionary of query parameters to include in the request.
    Returns:
        str: The raw CSV response as a string.
    """
    log.info(f"Making API call to url: {base_url} with params: {params}")
    response = rq.get(base_url, params=params)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    return response.text


def parse_csv(csv_content):
    """
    The parse_csv function converts the raw CSV string into a list of dictionaries.
    Args:
        csv_content: The raw CSV content as a string.
    Returns:
        list: A list of dictionaries where each dictionary represents a row in the CSV.
    """
    log.info("Parsing CSV content.")
    csv_reader = csv.DictReader(StringIO(csv_content))
    return [row for row in csv_reader]


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    connector.debug()

# Resulting table:
# ┌───────────────────────────────────────┬───────────────┬───────────────────────────┬─────────────────────────────────┬───────────────────────────┬──────────────────────────────┬────────────────────────────┬──────────────────────────────┐
# │                 id                    │      name     │         email             │         address                 │        company            │           job                │        updatedAt           │        createdAt             │
# │               string                  │     string    │        string             │          string                 │        string             │          string              │      timestamp with UTC    │      timestamp with UTC      │
# ├───────────────────────────────────────┼───────────────┼───────────────────────────┼─────────────────────────────────┼───────────────────────────┼──────────────────────────────┼────────────────────────────┼──────────────────────────────┤
# │ a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6  │ John Doe      │ john.doe@example.com      │ 123 Elm Street, Springfield, IL │      Acme Corp            │ Software Engineer            │ 2024-12-01T10:15:30Z       │ 2024-12-01T09:50:00Z         │
# │ p6o7p8q9-r0s1t2u3-v4w5x6y7z8a9b0c1d2  │ Jane Smith    │ jane.smith@example.com    │ 456 Oak Avenue, Springfield, IL │      Tech Solutions       │ Data Scientist               │ 2024-12-01T11:10:45Z       │ 2024-12-01T10:30:20Z         │
# │ 12345678-9abc-def0-1234-56789abcdef0  │ Michael Green │ michael.green@example.com │ 789 Pine Road, Springfield, IL  │      Innovate Inc.        │ Product Manager              │ 2024-12-01T12:05:22Z       │ 2024-12-01T11:45:55Z         │
# └───────────────────────────────────────┴───────────────┴───────────────────────────┴─────────────────────────────────┴───────────────────────────┴──────────────────────────────┴────────────────────────────┴──────────────────────────────┘
# │  3 rows                                                                                                                                                                                                                          8 columns │
# └────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
