"""
This is an example for how to work with parent-child relationship between tables from incremental API endpoints.
It defines a simple `update` method, which upserts retrieved data to respective 'company' and 'department' tables.
THIS EXAMPLE IS TO HELP YOU UNDERSTAND CONCEPTS USING DUMMY DATA. IT REQUIRES THE FIVETRAN-API-PLAYGROUND PACKAGE
(https://pypi.org/project/fivetran-api-playground/) TO RUN.
See the Technical Reference documentation
(https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# Import requests to make HTTP calls to API
import requests as rq

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__COMPANY_URL = "http://127.0.0.1:5001/cursors/companies"


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
            "table": "company",
            "primary_key": ["company_id"],
            "columns": {
                "company_id": "STRING",
                "company_name": "STRING",
                "updatedAt": "UTC_DATETIME",
                "createdAt": "UTC_DATETIME",
            },
        },
        {
            "table": "department",
            "primary_key": ["department_id", "company_id"],
            "columns": {
                "department_id": "STRING",
                "company_id": "STRING",
                "department_name": "STRING",
                "updatedAt": "UTC_DATETIME",
                "createdAt": "UTC_DATETIME",
            },
        },
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
    log.warning("Example: Common Patterns For Connectors - Cursors - Multiple Tables With Cursors")

    company_cursor = (
        state["company_cursor"] if "company_cursor" in state else "0001-01-01T00:00:00Z"
    )
    department_cursor = state["department_cursor"] if "department_cursor" in state else {}

    # Fetch and process the companies
    for company in fetch_companies(company_cursor):
        op.upsert(table="company", data=company)
        company_id = str(company["company_id"])

        # Update Cursor for Companies
        state["company_cursor"] = company["updatedAt"]

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

        # Fetch departments for a company
        department_data = fetch_departments_for_company(department_cursor, company_id)
        for department in department_data:
            op.upsert(table="department", data=department)

            # Update Cursor for a Department in department_cursor
            department_cursor[company_id] = department["updatedAt"]
            state["department_cursor"] = department_cursor

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)

    # State at the end of sync for the records
    # {"company_cursor": "2024-08-14T01:00:00Z",
    # "department_cursor": {"1": "2024-08-14T01:00:00Z", "2": "2024-08-14T01:00:00Z",
    # "3": "2024-08-14T01:00:00Z", "4": "2024-08-14T01:00:00Z"}}


def fetch_companies(company_cursor):
    """
    The fetch_companies function makes API call to fetch recently updated companies
    Api response looks like:
        {
          "data": [
            {"company_id": "1", "company_name": "Mark Taylor", ... },
            {"company_id": "2", "company_name": "Alan Taylor", ... }
            ...
          ],
          "total_items": 10
        }
    Args:
        company_cursor: The cursor for companies which is a UTC_DATETIME
    Returns:
        data: A list of dictionary containing the companies received from the API.
    """

    # Actual data fetch from API
    params = {"order_by": "updatedAt", "order_type": "asc", "updated_since": company_cursor}
    response_page = get_api_response(__COMPANY_URL, params)
    data = response_page.get("data", [])

    return data


def fetch_departments_for_company(department_cursor, company_id):
    """
    The fetch_departments_for_company function makes API call to fetch recently updated departments for a specified
    company id and cursor
    Api response looks like:
        {
          "data": [
            {"company_id": "1", "department_name": "Engineering", "department_id": "1" ... },
            {"company_id": "1", "department_name": "Sales", "department_id": "2" ... }
            ...
          ],
          "total_items": 8
        }
    Args:
        department_cursor: The department_cursor dict which looks like
       {"company_id 1": "UTC_DATETIME", "company_id 2": "UTC_DATETIME", ... }
        company_id: The id of the company for which departments are to be fetched
    Returns:
        data: A dictionary containing the departments received from the API.
    """
    # Fetch each company_id's cursor in department_cursor dict, if key is not present use default start value
    cursor = (
        department_cursor[company_id]
        if company_id in department_cursor
        else "0001-01-01T00:00:00Z"
    )
    log.info(f"Fetching departments for company_id: {company_id} with cursor: {cursor}")

    department_url = f"http://127.0.0.1:5001/cursors/{company_id}/departments"

    # Actual data fetch from API
    params = {"order_by": "updatedAt", "order_type": "asc", "updated_since": cursor}

    response_page = get_api_response(department_url, params)
    data = response_page.get("data", [])

    return data


def get_api_response(endpoint_path, params):
    """
    The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
    It performs the following tasks:
        1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
        2. Makes the API request using the 'requests' library, passing the URL and parameters.
        3. Parses the JSON response from the API and returns it as a dictionary.
    Args:
        endpoint_path: The URL to which the API request is made.
        params: A dictionary of query parameters to be included in the API request.
    Returns:
        response_page: A dictionary containing the parsed JSON response from the API.
    """
    log.info(f"Making API call to url: {endpoint_path} with params: {params}")
    response = rq.get(endpoint_path, params=params)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    return response_page


# Create the connector object using the schema and update functions.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Test your connector by running your file directly from your IDE.
    connector.debug()

# Resulting tables:
# Table "company":
# ┌─────────────┬──────────────┬─────────────────────────┐─────────────────────────┐
# │ company_id  │ company_name │      created_at         │      updated_at         │
# ├─────────────┼──────────────┼─────────────────────────┤─────────────────────────┤
# │      1      │   ABC Inc    │  2024-08-14T00:00:00Z   │  2024-08-14T01:00:00Z   │
# │      2      │   XYZ Inc    │  2024-08-14T00:01:00Z   │  2024-08-14T01:00:00Z   │
# └─────────────┴──────────────┴─────────────────────────┘─────────────────────────┘
#
# Table "department":
# ┌───────────────┬────────────┬─────────────────┬─────────────────────────┐─────────────────────────┐
# │ department_id │ company_id │ department_name │      created_at         │      updated_at         │
# ├───────────────┼────────────┼─────────────────┼─────────────────────────┤─────────────────────────┤
# │      1        │      1     │   Engineering   │    2024-08-14T00:00:00Z │    2024-08-14T01:00:00Z │
# │      2        │      1     │       HR        │    2024-08-14T00:01:00Z │    2024-08-14T01:00:00Z │
# │      3        │      1     │     Finance     │    2024-08-14T00:02:00Z │    2024-08-14T01:00:00Z │
# │      4        │      1     │      Sales      │    2024-08-14T00:03:00Z │    2024-08-14T01:00:00Z │
# │      1        │      2     │   Engineering   │    2024-08-14T00:04:00Z │    2024-08-14T01:00:00Z │
# │      2        │      2     │       HR        │    2024-08-14T00:05:00Z │    2024-08-14T01:00:00Z │
# │      3        │      2     │     Finance     │    2024-08-14T00:06:00Z │    2024-08-14T01:00:00Z │
# │      4        │      2     │      Sales      │    2024-08-14T00:07:00Z │    2024-08-14T01:00:00Z │
# └───────────────┴────────────┴─────────────────┴─────────────────────────┘─────────────────────────┘
