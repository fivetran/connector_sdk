# This is a simple example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to work with data frames.
# It also shows how to handle NaN values, as we do not support NaN inputs.
# Customers should convert NaN values to None before sending data.
# It shows the use of a requirements.txt file and a connector that calls a publicly available API to get random profile data
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import the requests module for making HTTP requests, aliased as rq.
import requests as rq
import pandas as pd
import numpy as np


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
            "table": "profile",
            "primary_key": ["id"],
            # Columns and data types will be inferred by Fivetran
        },
        {
            "table": "location",
            "primary_key": ["profileId"],
            # Columns and data types will be inferred by Fivetran
        },
        {
            "table": "login",
            "primary_key": ["profileId"],
            # Columns and data types will be inferred by Fivetran
        },
        {
            "table": "table_with_nan",
            "primary_key": ["id"],
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
    log.warning("Example: QuickStart Examples - User Profiles")

    # Retrieve the last processed profile ID from state or set it to 0 if not present
    profile_cursor = state["profile_cursor"] if "profile_cursor" in state else 0

    # Fetch new data and return DataFrames for profile, location, and login tables
    profile_df, location_df, login_df, cursor = get_data(profile_cursor)

    # Approaches to upsert the records from dataFrame
    upsert_dataframe_approach_1(profile_df=profile_df, state=state, cursor=cursor)

    upsert_dataframe_approach_2(location_df=location_df, state=state, cursor=cursor)

    upsert_dataframe_approach_3(login_df=login_df, state=state, cursor=cursor)

    # Approaches to handle NaN values in dataframes
    handle_tables_with_nan(state)


def get_data(cursor):
    """
    Function to fetch data from an API and process it into DataFrames
    Args:
        cursor: An integer representing the last processed profile ID, used to increment the primary key for new profiles.
    Returns:
        profile_df: DataFrame containing profile data.
        location_df: DataFrame containing location data.
        login_df: DataFrame containing login data.
    """
    # Initialize empty DataFrames for profile, location, and login tables
    profile_df = pd.DataFrame([])
    location_df = pd.DataFrame([])
    login_df = pd.DataFrame([])

    # Fetch data for 3 iterations, each with a new profile
    for i in range(2):
        # Increment primary key
        cursor += 1

        # Request data from an external API
        response = rq.get("https://randomuser.me/api/")
        data = response.json()
        data = data["results"][0]

        # Process and store profile data
        profile_data = {
            "id": cursor,
            "fullName": f"{data['name']['title']} {data['name']['first']} {data['name']['last']}",
            "gender": data["gender"],
            "email": data["email"],
            "age": data["dob"]["age"],
            "date": data["dob"]["date"],
            "mobile": data["cell"],
            "nationality": data["nat"],
            # Stores the JSON data e.g. {"large":"https://randomuser.me/api/portraits/women/67.jpg","medium":"https://randomuser.me/api/portraits/med/women/67.jpg","thumbnail":"https://randomuser.me/api/portraits/thumb/women/67.jpg"}
            "picture": data["picture"],
        }
        profile_df = pd.concat([profile_df, pd.DataFrame([profile_data])], ignore_index=True)

        # Process and store location data
        location_details = data["location"]
        location_data = {
            "profileId": cursor,
            "street": f"{location_details['street']['number']} {location_details['street']['name']}",
            "city": location_details["city"],
            "state": location_details["state"],
            "country": location_details["country"],
            "postcode": location_details["postcode"],
        }
        location_df = pd.concat([location_df, pd.DataFrame([location_data])], ignore_index=True)

        # Process and store login data
        login_details = data["login"]
        login_data = {
            "profileId": cursor,
            "uuid": login_details["uuid"],
            "username": login_details["username"],
            "password": login_details["password"],
        }
        login_df = pd.concat([login_df, pd.DataFrame([login_data])], ignore_index=True)

    return profile_df, location_df, login_df, cursor


def handle_tables_with_nan(state: dict):
    """
    Function to handle tables with NaN values by converting them to None before upserting.
    Args:
        state: A dictionary containing state information from previous runs.
    """
    # Upsert tables with NaN
    table_df_1 = generate_data_with_NaN()
    table_df_2 = generate_data_with_NaN()
    table_df_3 = generate_data_with_NaN()

    # Approaches to replace NaN with None

    # Approach 1: Convert NaN to None using the replace method
    table_df_1 = table_df_1.replace(np.nan, None)
    upsert_dataframe(table_df=table_df_1, state=state)

    # Approach 2: Convert NaN to None using the where method
    table_df_2 = table_df_2.astype(object).where(pd.notnull(table_df_2), None)
    upsert_dataframe(table_df=table_df_2, state=state)

    # Approach 3: Fill NaN values with np.nan and then replace any NaN with None.
    table_df_3 = table_df_3.fillna(np.nan).replace([np.nan], [None])
    upsert_dataframe(table_df=table_df_3, state=state)


def generate_data_with_NaN():
    """
    Function to generate a DataFrame with random numbers and NaN values.
    Returns:
        pd.DataFrame: A DataFrame with random numbers and some NaN values.
    """
    np.random.seed(0)

    # Create a DataFrame with 10 rows and 3 columns of random numbers
    data = np.random.rand(10, 3)

    # Randomly assign NaN values (e.g., 10% NaN)
    nan_mask = np.random.choice([True, False], size=data.shape, p=[0.1, 0.9])
    data[nan_mask] = np.nan

    # Create the DataFrame
    return pd.DataFrame(data, columns=["id", "column_1", "Column_2"])


def upsert_dataframe(table_df, state):
    """
    Function to upsert a DataFrame to the destination
    Args:
        table_df: pd.DataFrame: The DataFrame to be upserted.
        state: A dictionary containing state information from previous runs.
    """
    cursor = state["table_with_nan_cursor"] if "table_with_nan_cursor" in state else 0
    for row in table_df.to_dict("records"):
        op.upsert("table_with_nan", row)
        cursor += 1

    state["table_with_nan_cursor"] = cursor

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets)
    op.checkpoint(state)


def upsert_dataframe_approach_1(profile_df, state, cursor):
    # APPROACH 1: Gives you direct access to individual row values by column name, Slower approach, helpful for custom row handling
    # UPSERT all profile table data, checkpoint periodically to save progress. In this example every 5 records.
    for index, row in profile_df.iterrows():
        op.upsert("profile", {col: row[col] for col in profile_df.columns})
        if index % 5 == 0:
            state["profile_cursor"] = row["id"]

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)

    # Checkpointing at the end of the "profile" table data processing
    state["profile_cursor"] = cursor

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def upsert_dataframe_approach_2(location_df, state, cursor):
    # APPROACH 2: Generally faster and more memory-efficient, Simplifies the code since rows are already dictionaries and can be used directly
    # UPSERT all location table data.
    # Iterate over each row in the DataFrame, converting it to a dictionary
    for row in location_df.to_dict("records"):
        op.upsert("location", row)

    # Checkpointing at the end of the "location" table data processing
    state["location_cursor"] = cursor

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def upsert_dataframe_approach_3(login_df, state, cursor):
    # APPROACH 3: Faster approach, Keeps track of the original indices of the rows, which can be useful for certain operations that require indexing information.
    # UPSERT all login table data.
    # Iterate over the values of the dictionary (which are the DataFrame rows)
    for value in login_df.to_dict("index").values():
        op.upsert("login", value)

    # Checkpointing at the end of the "login" table data processing
    state["login_cursor"] = cursor

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the "fivetran debug" command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug()
