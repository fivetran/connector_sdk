# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to fetch data from an OData API version 4 and sync it to a destination using python_odata.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
# python_odata is a library that provides a simple way to interact with OData services version 4
# For more information on python_odata refer to the documentation (https://tuomur-python-odata.readthedocs.io/en/latest/)
from odata import ODataService
import requests
from datetime import datetime, timezone


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [
        {
            "table": "Customers",  # Name of the table in the destination, required.
            "primary_key": ["CustomerID"],  # Primary key column(s) for the table, optional.
            "columns": {},  # Definition of columns and their types, optional.  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        },
        {
            "table": "Filtered_Customers",
            "primary_key": ["CustomerID"],
            "columns": {},
        },
        {
            "table": "Orders",
            "primary_key": ["OrderID"],
            "columns": {},
        },
    ]


# sets up northwind version 4 public odata service
# This function sets up the python_odata client that will be needed to interact with the OData service.
# For your own connector, you will need to replace the service_url with the URL of your OData service.
# You can also add any authentication headers or other configurations needed for your service to the session object
def setup_odata_service():
    service_url = "https://services.odata.org/v4/northwind/northwind.svc/"
    # Initialize the session object to be used by the pyOdata
    # This maintains connection state, headers, and authentication across requests
    # For more information on requests session object refer to the documentation
    # https://requests.readthedocs.io/en/latest/user/advanced
    session = requests.Session()
    service = ODataService(service_url, reflect_entities=True, session=session)

    log.info("OData service connection established")
    return service


# Fetches all the data present in the Customers entity
# The service parameter is the OData service object and table is the destination table name
# For your own connector, you will need to modify the service query to match the structure of your OData service.
def upsert_all_customers(service, table):
    log.info("Fetching all the data from Customers entity")

    # Access the entity and fetch all records
    # Modify the entity name to match the structure of your OData service
    entity = service.entities["Customers"]
    query = service.query(entity)
    results = list(query)

    # Obtained result needs to be converted to dictionary which can be upserted to the destination
    results = [data.__odata__ for data in results]
    for data in results:
        # Upsert the data to the destination
        op.upsert(table=table, data=data.data)

    log.info(f"upserted {len(results)} records to the destination")


# uses filter to get the customers whose name starts with 'S'
# The service parameter is the OData service object and table is the destination table name
# This method shows the usage of filter and select with the python_odata client.
# Modify the logic in the function to match your OData service to filter the data.
def upsert_customer_name_starting_with_s(service, table):
    log.info("Fetching Customer whose name start with S")

    # Access the entity
    # Modify the entity name to match the structure of your OData service
    entity = service.entities["Customers"]
    query = service.query(entity)

    # Filtering only the data where Name starts with 'S' or
    # Modify the filter condition to match your requirements
    query = query.filter(entity.ContactName.startswith("S"))

    # Selecting only the required columns
    # Modify this with the columns you want to select
    query = query.select(
        entity.CustomerID, entity.CompanyName, entity.ContactName, entity.ContactTitle
    )
    results = list(query)

    # No need to convert the data to dictionaries as select query statement does that
    for data in results:
        # Upsert the data to the destination
        op.upsert(table=table, data=data)

    log.info(f"upserted {len(results)} records to the destination")


# Helper function to parse the ISO datetime string to datetime object
def parse_iso_date(date_string):
    if not isinstance(date_string, str):
        return date_string

    dateformat = "%Y-%m-%dT%H:%M:%S"
    try:
        if date_string.endswith("Z"):
            date_string = date_string[:-1]  # Remove Z
        return datetime.strptime(date_string, dateformat).replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise RuntimeError(f"Invalid date format: {e}")


# Fetched the orders after the specified state value
# The service parameter is the OData service object, table is the destination table name, initial_state_value is the state value to start from
# This method shows how to use select with the pyodata client to select specific properties from the OData service.
# This method also shows how to use filter to implement incremental sync.
def query_orders(service, initial_date):
    # Access the entity
    entity = service.entities["Orders"]
    query = service.query(entity)
    # Selecting only the required columns
    query = query.select(
        entity.OrderID,
        entity.CustomerID,
        entity.EmployeeID,
        entity.OrderDate,
        entity.RequiredDate,
        entity.ShippedDate,
    )
    # Filtering only the data where OrderDate is greater than the initial date
    query = query.filter(entity.OrderDate > initial_date)
    return list(query)


# Processes the order results and upserts and tracks the latest date
# The results parameter is the list of order data, table is the destination table name, track_column is the column to track the latest date
# initial_max_date is the initial max date to start with
# This method upserts the data to the destination and gets the last date from the fetched data.
# This is a helper function to update the state to simulate the incremental sync.
def process_order_results(results, table, track_column, initial_max_date):
    max_date = initial_max_date
    count = 0

    for data in results:
        count += 1
        op.upsert(table=table, data=data)

        # Track the latest date
        current_date = data.get(track_column)
        if isinstance(current_date, datetime):
            if current_date > max_date:
                max_date = current_date
        elif isinstance(current_date, str):
            parsed_date = parse_iso_date(current_date)
            if parsed_date and parsed_date > max_date:
                max_date = parsed_date

    log.info(f"Upserted {count} records to the destination")
    return max_date


# Fetches all the orders after the initial state value and upserts them to the destination
# The service parameter is the OData service object, table is the destination table name, initial_state_value is the state value to start from
# track_column is the column to track the latest date
# This method performs an incremental sync by fetching orders after the initial_state_value.
# For your own connector, you will need to modify the logic to match the structure of your OData service.
def upsert_all_orders(service, table, initial_state_value, track_column):
    log.info(f"Fetching all the orders after the {initial_state_value}")

    initial_date = parse_iso_date(initial_state_value)
    results = query_orders(service, initial_date)
    max_date = process_order_results(results, table, track_column, initial_date)

    # Return datetime as string in ISO format for updating the state
    dateformat = "%Y-%m-%dT%H:%M:%S"
    if isinstance(max_date, datetime):
        return max_date.strftime(dateformat)
    return max_date


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    log.warning("Example: OData Data fetching and syncing using python-odata and pyodata library")

    odata_service = setup_odata_service()

    # Upserting all the customer data to the destination
    upsert_all_customers(odata_service, table="Customers")
    op.checkpoint(state)

    # Upserting selected data from customer to the destination
    upsert_customer_name_starting_with_s(odata_service, table="Filtered_Customers")
    op.checkpoint(state)

    # Upserting all the orders data to the destination while maintaining the state
    last_order_date = state.get("latestOrderDate", "1990-01-01T00:00:00")
    final_state_value = upsert_all_orders(
        odata_service,
        table="Orders",
        initial_state_value=last_order_date,
        track_column="OrderDate",
    )
    state["latestOrderDate"] = final_state_value
    op.checkpoint(state)


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug()
