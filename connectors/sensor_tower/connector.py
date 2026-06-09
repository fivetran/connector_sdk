# This example details how to pull data from SensorTower, which is a market intelligence and analytics platform
# that provides insights into mobile apps, app store trends, and digital advertising
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# This SDK is pulling from the Sensor Tower Connector API for three specific tables sales_report_estimates, active_users and retention
# You can change the app IDs to those of your choosing to gather the necessary information

# Import requests to make HTTP calls to API
import requests

# Import the json module to handle JSON data.
import json

# Import datetime and relativedelta to handle date calculations.
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Constants
COUNTRY_CODE = "Country Code"
APP_ID = "App ID"

# Mapping used later for the sales_report_estimates table to provide more helpful column names
KEY_MAPPING = {
    "sales_report_estimates_key": {
        "ios": {
            "aid": APP_ID,
            "cc": COUNTRY_CODE,
            "d": "Date",
            "iu": "iPhone Downloads",
            "ir": "iPhone Revenue",
            "au": "iPad Downloads",
            "ar": "iPad Revenue",
        },
        "android": {
            "aid": APP_ID,
            "c": COUNTRY_CODE,
            "d": "Date",
            "u": "Android Downloads",
            "r": "Android Revenue",
        },
    }
}

# App IDs that have unique values in Sensor Tower application - can be changed for specific applications of interest
IOS_APP_IDS = []  # Add the iOS app IDs you want to track here
ANDROID_APP_IDS = []  # Add the Android app IDs you want to track here

BASE_URL = "https://api.sensortower.com/v1/"

# Additional parameters for endpoint filters
OS = ["ios", "android"]
ENDPOINTS = ["active_users", "sales_report_estimates", "retention"]
TIME_PERIOD = ["day", "week", "month"]
COUNTRY_CODES = ["US", "AU", "FR", "DE", "GB", "IT", "CA", "KR", "JP", "BR", "IN", "ES"]


# The schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.


def schema(configuration: dict):
    return [
        {
            "table": "sales_report_estimates",  # Name of the table in the destination.
            "primary_key": [APP_ID, "Date", COUNTRY_CODE],  # Primary key columns for the table.
            "columns": {APP_ID: "STRING"},  # Specify as a string due to data type mismatch issues
        },
        {
            "table": "active_users",
            "primary_key": ["app_id", "date", "time_period", "country"],
            "columns": {"app_id": "STRING"},
        },
        {
            "table": "retention",
            "primary_key": ["app_id", "date", "country"],
            "columns": {"app_id": "STRING"},
        },
    ]


# The get_data function, which is a helper function that run API calls to get the records from each endpoint
# The function takes 5 parameters
# - params: dictionary defining the standard params that will be used in all API call
# - os: the operating system (ios or Android) for the application
# - endpoint: each table has their own API endpoint we need to call to populate
# - time_period: aggregation period for the data (examples: "day", "week", "month")
# - country_code: a required parameter of the API calls is country_code, which you need to change to gather data for different locations


def get_data(params: dict, os, endpoint, time_period, country_code):
    f_params = params.copy()

    if os == "ios":
        f_params["app_ids"] = IOS_APP_IDS
    else:
        f_params["app_ids"] = ANDROID_APP_IDS

    # Each endpoint has their own specific URL and parameters

    if endpoint == "sales_report_estimates":
        url = BASE_URL + os + "/" + endpoint
        f_params["date_granularity"] = "daily"

    elif endpoint == "active_users":
        url = BASE_URL + os + "/usage/" + endpoint
        f_params["time_period"] = time_period

    else:
        url = BASE_URL + os + "/usage/" + endpoint
        f_params["date_granularity"] = "all_time"
        f_params["country"] = country_code

    response = requests.get(url, params=f_params)
    records = response.json()

    return records


# The process_active_users function handles data processing for the active_users endpoint
# The function takes 2 parameters:
# - params: dictionary containing API parameters
# - system: the operating system to fetch data for (ios/android)
# Upsert operations for each processed record with time period information


def process_active_users(params, system):
    for period in TIME_PERIOD:
        records = get_data(params, system, "active_users", period, None)
        for record in records:
            record["time_period"] = period
            op.upsert(table="active_users", data=record)


# The process_sales_report function handles data processing for sales report estimates
# The function takes 2 parameters:
# - params: dictionary containing API parameters
# - system: the operating system to fetch data for (ios/android)
# Upsert operations for each processed record with mapped column names


def process_sales_report(params, system):
    """Process sales report estimates endpoint data."""
    records = get_data(params, system, "sales_report_estimates", None, None)
    for record in records:
        mapping = KEY_MAPPING["sales_report_estimates_key"][
            "android" if system == "android" else "ios"
        ]
        record = {mapping.get(k, k): v for k, v in record.items()}
        op.upsert(table="sales_report_estimates", data=record)


# The process_retention function handles data processing for retention data
# The function takes 2 parameters:
# - params: dictionary containing API parameters
# - system: the operating system to fetch data for (ios/android)
# Upsert operations for each processed record with JSON-encoded retention data


def process_retention(params, system):
    """Process retention endpoint data."""
    for country in COUNTRY_CODES:
        raw_data = get_data(params, system, "retention", None, country)
        records = raw_data["app_data"]
        for record in records:
            record["corrected_retention"] = json.dumps(record["corrected_retention"])
            op.upsert(table="retention", data=record)


# The process_endpoints function orchestrates data processing across all endpoints
# The function takes 2 parameters:
# - endpoints: list of endpoints to process
# - params: dictionary containing API parameters
# Upsert operations from the appropriate endpoint processor for each endpoint/system combination


def process_endpoints(endpoints, params):
    for endpoint in endpoints:
        for system in OS:
            if endpoint == "active_users":
                process_active_users(params, system)
            elif endpoint == "sales_report_estimates":
                process_sales_report(params, system)
            else:  # retention endpoint
                process_retention(params, system)


# The update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync


def update(configuration: dict, state: dict):
    log.warning("Example: Source Examples - Sensor Tower")
    # Pull in the auth token from the configuration file in the project

    auth_token = configuration["auth_token"]

    # If no cursor exists, go through a historical sync

    if "look_back" not in state:
        look_back = (datetime.now() - relativedelta(months=3)).strftime(
            "%Y-%m-%d"
        )  # Change timeframe to suit requirements
    else:
        # For incremental syncs, do a one week lookback

        look_back = (datetime.now() - relativedelta(weeks=1)).strftime(
            "%Y-%m-%d"
        )  # Change timeframe to suit requirements

    current_date = (datetime.now()).strftime("%Y-%m-%d")

    # Set params that will be stable for all API calls

    params = {
        "start_date": look_back,
        "end_date": current_date,
        "auth_token": auth_token,
    }

    # Call the process_endpoints function to get the data from each endpoint

    process_endpoints(ENDPOINTS, params)

    # Set new cursor
    # Since we are doing the incremental pulls based on the current date, this is mostly used as a boolean here to see if a cursor exists or not

    op.checkpoint(state={"look_back": look_back})


# This creates the connector object that will use the update function defined in this connector.py file

connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.

if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.

    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.

    connector.debug(configuration=configuration)
