# This is an example for how to work with the fivetran_connector_sdk module.
# It defines a simple 'update' method, which upserts GitHub repo traffic data from GitHub's API into a Fivetran connector.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import required libraries
import time
from datetime import datetime, timezone
import requests
import json

# Constants
__MAX_RETRIES = 3
__TIMESTAMP_POSTFIX = "+00:00"


# Define the schema function which lets you configure the schema your connector delivers.
# See the technical reference documentation for more details on the schema function:
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
# The schema function takes one parameter:
# - configuration: a dictionary that holds the configuration settings for the connector.
def schema(configuration: dict):
    return [
        {
            "table": "repository_views",
            "primary_key": ["repository", "timestamp"],
            "columns": {
                "repository": "STRING",
                "timestamp": "UTC_DATETIME",
                "count": "INT",
                "uniques": "INT",
            },
        },
        {
            "table": "repository_clones",
            "primary_key": ["repository", "timestamp"],
            "columns": {
                "repository": "STRING",
                "timestamp": "UTC_DATETIME",
                "count": "INT",
                "uniques": "INT",
            },
        },
        {
            "table": "repository_referrers",
            "primary_key": ["repository", "referrer", "fetch_date"],
            "columns": {
                "repository": "STRING",
                "referrer": "STRING",
                "count": "INT",
                "uniques": "INT",
                "fetch_date": "NAIVE_DATE",
            },
        },
        {
            "table": "repository_paths",
            "primary_key": ["repository", "path", "fetch_date"],
            "columns": {
                "repository": "STRING",
                "path": "STRING",
                "title": "STRING",
                "count": "INT",
                "uniques": "INT",
                "fetch_date": "NAIVE_DATE",
            },
        },
    ]


# Define the update function, which is a required function, and is called by Fivetran during each sync.
# See the technical reference documentation for more details on the update function
# https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
# The function takes two parameters:
# - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
# - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
# The state dictionary is empty for the first sync or for any full re-sync
def update(configuration: dict, state: dict):
    log.warning("Example: Source Examples - GitHub Traffic")

    # Get configuration values
    token = configuration.get("personal_access_token")
    repositories = configuration.get("repositories")

    if not token:
        raise ValueError("Personal access token is required")

    if not repositories:
        raise ValueError("Repository must be specified")

    # Set up authentication headers
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    now = datetime.now(timezone.utc).isoformat().replace(__TIMESTAMP_POSTFIX, "Z")

    repo_list = [repo.strip() for repo in repositories.split(",")]
    print(repo_list)

    for repository in repo_list:
        owner, repo_name = repository.split("/")
        base_url = f"https://api.github.com/repos/{owner}/{repo_name}/traffic"

        # Sync repository views
        sync_views(base_url, headers, repository, state)

        # Sync repository clones
        sync_clones(base_url, headers, repository, state)

        # Sync repository referrers
        sync_referrers(base_url, headers, repository, now, state)

        # Sync repository paths
        sync_paths(base_url, headers, repository, now, state)

        # Checkpoint after processing each repository
        op.checkpoint(state)


def sync_views(base_url, headers, repository, state):
    """Sync the repository views data"""
    url = f"{base_url}/views"
    response = make_api_request(url, headers)

    if not response:
        return

    for view in response.get("views", []):
        data = {
            "repository": repository,
            "timestamp": view.get("timestamp"),
            "count": view.get("count"),
            "uniques": view.get("uniques"),
        }
        op.upsert("repository_views", data)

    # Update state with last sync time
    state_key = f"{repository}_views_last_sync"
    state[state_key] = datetime.now(timezone.utc).isoformat().replace(__TIMESTAMP_POSTFIX, "Z")


def sync_clones(base_url, headers, repository, state):
    """Sync the repository clones data"""
    url = f"{base_url}/clones"
    response = make_api_request(url, headers)

    if not response:
        return

    for clone in response.get("clones", []):
        data = {
            "repository": repository,
            "timestamp": clone.get("timestamp"),
            "count": clone.get("count"),
            "uniques": clone.get("uniques"),
        }
        op.upsert("repository_clones", data)

    # Update state with last sync time
    state_key = f"{repository}_clones_last_sync"
    state[state_key] = datetime.now(timezone.utc).isoformat().replace(__TIMESTAMP_POSTFIX, "Z")


def sync_referrers(base_url, headers, repository, sync_time, state):
    """Sync the repository referrers data"""
    url = f"{base_url}/popular/referrers"
    response = make_api_request(url, headers)

    if not response:
        return

    for referrer in response:
        data = {
            "repository": repository,
            "referrer": referrer.get("referrer"),
            "count": referrer.get("count"),
            "uniques": referrer.get("uniques"),
            "fetch_date": datetime.now(timezone.utc).date(),
        }
        op.upsert("repository_referrers", data)

    # Update state with last sync time
    state_key = f"{repository}_referrers_last_sync"
    state[state_key] = sync_time


def sync_paths(base_url, headers, repository, sync_time, state):
    """Sync the repository paths data"""
    url = f"{base_url}/popular/paths"
    response = make_api_request(url, headers)

    if not response:
        return

    for path_data in response:
        data = {
            "repository": repository,
            "path": path_data.get("path"),
            "title": path_data.get("title"),
            "count": path_data.get("count"),
            "uniques": path_data.get("uniques"),
            "fetch_date": datetime.now(timezone.utc).date(),
        }
        op.upsert("repository_paths", data)

    # Update state with last sync time
    state_key = f"{repository}_paths_last_sync"
    state[state_key] = sync_time


def make_api_request(url, headers):
    """Make an API request with retries and handle errors"""
    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            log.info(f"Making API request to: {url} (Attempt {attempt})")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"API request failed on attempt {attempt}", e)
            if hasattr(e.response, "status_code") and e.response.status_code == 403:
                log.error("Access forbidden. Ensure your token has the proper access.")
                return None
            if attempt < __MAX_RETRIES:
                delay_seconds = 2**attempt
                log.info(f"Retrying in {delay_seconds} seconds...")
                time.sleep(delay_seconds)
            else:
                log.error("Maximum retry attempts reached. Request aborted.")
    return None


# Create connector instance
connector = Connector(update=update, schema=schema)

# For local testing
if __name__ == "__main__":
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    connector.debug(configuration=configuration)
