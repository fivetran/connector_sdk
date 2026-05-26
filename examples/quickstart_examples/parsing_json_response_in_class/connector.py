"""
This is an example for how to work with the fivetran_connector_sdk module.
It demonstrates how to parse a JSON response into a POJO-style class and use it in the update function.
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

# Import requests to make HTTP calls to API.
import requests

# Import dataclass for creating POJO-style classes
from dataclasses import dataclass

# Import time for implementing exponential backoff
import time

# Constants
__API_URL = "https://jsonplaceholder.typicode.com/posts"
__MAX_RETRIES = 3  # Maximum number of retries for failed requests
__BASE_DELAY = 2  # Base delay for exponential backoff in seconds


# POJO-style response class
@dataclass
class Post:
    """
    A class representing a post from the JSONPlaceholder API.
    """

    userId: int
    id: int
    title: str
    body: str


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    :param configuration: a dictionary that holds the configuration settings for the connector.
    :return: a list of tables with primary keys and any datatypes that we want to specify
    """
    return [
        {
            "table": "posts",
            "primary_key": ["id"],
            "columns": {"id": "INT", "userId": "INT", "title": "STRING", "body": "STRING"},
        }
    ]


def update(configuration: dict, state: dict):
    """
    # Define the update function, which is a required function, and is called by Fivetran during each sync.
    # See the technical reference documentation for more details on the update function
    # https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    # The state dictionary is empty for the first sync or for any full re-sync
    :param configuration: a dictionary that holds the configuration settings for the connector.
    :param state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
    """
    log.warning("Example: Quickstart Examples - Parsing JSON Response in Class")
    log.info("Fetching posts from JSONPlaceholder")

    post_list = []
    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            response = requests.get(__API_URL)
            response.raise_for_status()
            post_list = response.json()
            break  # Exit retry loop on success
        except requests.RequestException as e:
            log.warning(f"Request attempt {attempt} failed: {e}")
            if attempt < __MAX_RETRIES:
                delay = __BASE_DELAY**attempt
                log.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                log.error("Maximum retry attempts reached. Request aborted.")
                return

    for post_dict in post_list:
        try:
            post = Post(**post_dict)  # Deserialize into a POJO

            # Perform upsert operation, to sync the post data
            op.upsert(
                "posts",
                {"id": post.id, "userId": post.userId, "title": post.title, "body": post.body},
            )

        except Exception as e:
            log.warning(f"Failed to process post: {post_dict.get('id', 'unknown')} - {e}")

    log.info(f"Synced {len(post_list)} posts")


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration={})
