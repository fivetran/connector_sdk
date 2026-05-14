# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import requests to make HTTP calls to API
import requests as rq
import traceback
import datetime
import json

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):

    if not ("topic" in configuration):
        raise ValueError("Could not find 'topic' in configuration.json")

    return [
        {
            "table": "article",
            "primary_key": ["source", "published_at"],
            "columns": {
                "source": "STRING",
                "published_at": "UTC_DATETIME",
            },
        }
    ]


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):

    try:
        conf = configuration
        base_url = "https://newsapi.org/v2/everything"

        # Default value can be set 1 day ago
        from_ts = (
            state["to_ts"]
            if "to_ts" in state
            else datetime.datetime.now() - datetime.timedelta(days=1)
        )
        now = datetime.datetime.now()
        to_ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        headers = {"Authorization": "Bearer " + conf["API_KEY"], "accept": "application/json"}

        params = {
            "from": from_ts,
            "to": to_ts,
            "page": "1",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": conf["pageSize"],
        }

        topics = json.loads(conf["topic"])

        for t in topics:
            params["q"] = t
            params["page"] = "1"
            sync_items(base_url, headers, params, state, t)

        # Update the state with the new cursor position, incremented by 1.
        new_state = {"to_ts": to_ts}
        log.debug(f"state updated, new state: {repr(new_state)}")

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state=new_state)

    except Exception as e:
        # Return error response
        exception_message = str(e)
        stack_trace = traceback.format_exc()
        detailed_message = f"Error Message: {exception_message}\nStack Trace:\n{stack_trace}"
        raise RuntimeError(detailed_message)


# The function takes five parameters:
# - base_url: The URL to the API endpoint.
# - headers: Authentication headers
# - state: State dictionary
# - topic: current topic to search
# - params: A dictionary of query parameters to be sent with the API request.
def sync_items(base_url, headers, params, state, topic):
    more_data = True

    while more_data:
        # Get response from API call.
        response_page = get_api_response(base_url, headers, params)

        log.info(str(response_page["totalResults"]) + " results for topic " + topic)

        # Process the items.
        items = response_page.get("articles", [])
        if not items:
            break  # End pagination if there are no records in response.

        # Iterate over each user in the 'items' list and performs an upsert operation.
        # The 'upsert' operation inserts the data into the destination.
        # Update the state with the 'updatedAt' timestamp of the current item.
        for a in items:
            op.upsert(
                table="article",
                data={
                    "topic": topic,
                    "source": a["source"]["name"],
                    "published_at": a["publishedAt"],
                    "author": a["author"],
                    "title": a["title"],
                    "description": a["description"],
                    "content": a["content"],
                    "url": a["url"],
                },
            )

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        # Determine if we should continue pagination based on the total items and the current offset.
        more_data, params = should_continue_pagination(params, response_page)


# The get_api_response function sends an HTTP GET request to the provided URL with the specified parameters.
# It performs the following tasks:
# 1. Logs the URL and query parameters used for the API call for debugging and tracking purposes.
# 2. Makes the API request using the 'requests' library, passing the URL and parameters.
# 3. Parses the JSON response from the API and returns it as a dictionary.
#
# The function takes two parameters:
# - base_url: The URL to which the API request is made.
# - params: A dictionary of query parameters to be included in the API request.
#
# Returns:
# - response_page: A dictionary containing the parsed JSON response from the API.
def get_api_response(endpoint_path, headers, params):
    response = rq.get(endpoint_path, headers=headers, params=params)
    response.raise_for_status()  # Ensure we raise an exception for HTTP errors.
    response_page = response.json()
    return response_page


# The should_continue_pagination function determines whether pagination should continue based on the
# current page number and the total number of results in the API response.
# It performs the following tasks:
# 1. Calculates the number of pages needed to retrieve all results based on pageSize parameter specified in
# configuration.json.
# 2. If the current page number is less than the total, updates the parameters with the new offset
# for the next API request.
# 3. If the current offset + current_page_size is greater than or equal to the total, or the next page will exceed the
# API result limit of 100 results per call, sets the flag to end the pagination process.
#
# Parameters:
# - params: A dictionary of query parameters used in the API request. It will be updated with the new offset.
# - response_page: A dictionary representing the parsed JSON response from the API.
#
# Returns:
# - has_more_pages: A boolean indicating whether there are more pages to retrieve.
# - params: The updated query parameters for the next API request.
#
def should_continue_pagination(params, response_page):
    has_more_pages = True

    # Determine if there are more pages to continue the pagination
    current_page = int(params["page"])
    total_pages = divmod(int(response_page["totalResults"]), int(params["pageSize"]))[0] + 1

    # 100 results is a temporary limit for dev API -- this limit can be removed if you have a paid API key
    page_check = current_page and total_pages
    page_check = page_check and current_page < total_pages
    page_check = page_check and current_page * int(params["pageSize"]) < 100

    if page_check:
        # Increment the page number for the next request in params
        params["page"] = current_page + 1
    else:
        has_more_pages = False  # End pagination if there is no more pages pending.

    return has_more_pages, params


# This creates the connector object that will use the update function defined in this connector.py file.
# This example does not use the schema() function. If it did, it would need to be included in the connector object definition.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "main":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
