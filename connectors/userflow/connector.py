# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

import requests  # HTTP client library used to send requests to external APIs (GET/POST, etc.)
import datetime as dt  # Standard datetime module (aliased as dt) for working with dates, times, and timestamps
import time  # For implementing retry delays with exponential backoff
from urllib.parse import urlparse  # For validating and parsing base_url

__USERFLOW_VERSION = "2020-01-03"
__MAX_LIMIT = 100
__MAX_RETRIES = 5


def build_headers(api_key: str):
    """
    Create headers for Userflow API requests.
    Args:
        api_key (str): The API key for authentication.
    Returns:
        dict: A dictionary of HTTP headers.
    """
    return {
        "Authorization": f"Bearer {api_key}",
        "Userflow-Version": __USERFLOW_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def timestamp():
    """
    Get the current UTC timestamp in ISO 8601 format.
    """
    return dt.datetime.now(dt.timezone.utc).isoformat()


def table_state(state, table):
    """
    Create or return per-table state.
    Args:
    state: The overall state dictionary.
    table: The name of the table.
    Returns: The state dictionary specific to the table.
    """
    if "bookmarks" not in state:
        state["bookmarks"] = {}
    if table not in state["bookmarks"]:
        state["bookmarks"][table] = {}
    return state["bookmarks"][table]


def schema(configuration):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "users",
            "primary_key": ["id"],
            "columns": {
                "id": "STRING",
                "email": "STRING",
                "name": "STRING",
                "created_at": "UTC_DATETIME",
                "signed_up_at": "UTC_DATETIME",
                "raw": "JSON",
                "_synced_at": "UTC_DATETIME",
            },
        }
    ]


def fetch_users(base_url, headers, limit, starting_after=None):
    """
    Fetch a single page of users from the Userflow API.
    Args:
        base_url: The base URL for the Userflow API.
        headers: HTTP headers including authorization.
        limit: Maximum number of users to fetch per page.
        starting_after: Cursor ID to start pagination from (optional).
    Returns:
        Tuple of (users list, has_more flag, next_page_url).
    """
    params = {"limit": limit}
    if starting_after:
        params["starting_after"] = starting_after

    url = base_url + "/users"
    resp = get_with_retry(url, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    return (
        payload.get("data", []),
        payload.get("has_more"),
        payload.get("next_page_url"),
    )


def validate_configuration(configuration):
    """
    Validate connector configuration.
    Args:
        configuration: The connector configuration dictionary
    """
    api_key = configuration.get("userflow_api_key")
    if api_key is None or not str(api_key).strip():
        raise ValueError("Missing required configuration field: 'userflow_api_key'")

    base_url = configuration.get("base_url", "https://api.userflow.com")
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid 'base_url' value: {base_url!r}")

    log.info("Configuration validation succeeded.")


def get_with_retry(url, headers=None, params=None, timeout=60):
    """
    Perform a GET request with retries for transient errors.
    Args:
        url: The URL to send the GET request to.
        headers: Optional HTTP headers.
        params: Optional query parameters.
        timeout: Request timeout in seconds.
    Returns:
        The HTTP response object.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp

        except (requests.Timeout, requests.ConnectionError) as e:
            # Network-level / timeout issues → retry if we have attempts left
            if attempt == __MAX_RETRIES - 1:
                log.severe(f"Network/timeout error on GET {url}", e)
                raise
            sleep_time = min(60, 2**attempt)
            log.warning(
                f"Network/timeout error on GET {url}: {e}. "
                f"Retrying {attempt + 1}/{__MAX_RETRIES} after {sleep_time}s"
            )
            time.sleep(sleep_time)

        except requests.HTTPError as e:
            status = e.response.status_code
            # Retry only transient HTTP errors (5xx, 429)
            if status in (429,) or 500 <= status < 600:
                if attempt == __MAX_RETRIES - 1:
                    log.severe(f"HTTP error {status} on GET {url}: {e.response.text}")
                    raise
                sleep_time = min(60, 2**attempt)
                log.warning(
                    f"Transient HTTP {status} on GET {url}. "
                    f"Retrying {attempt + 1}/{__MAX_RETRIES} after {sleep_time}s"
                )
                time.sleep(sleep_time)
            else:
                # Non-retryable: 4xx, etc.
                log.severe(f"Non-retryable HTTP {status} on GET {url}: {e.response.text}")
                raise

    raise RuntimeError(f"get_with_retry exhausted retries for {url}")


def update(configuration, state):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    base_url = configuration.get("base_url", "https://api.userflow.com")
    api_key = configuration["userflow_api_key"]
    limit = __MAX_LIMIT
    headers = build_headers(api_key)

    tb_state = table_state(state, "users")
    starting_after = tb_state.get("last_seen_id")

    total = 0
    has_more = True

    while has_more:
        users, has_more, next_page_url = fetch_users(base_url, headers, limit, starting_after)
        if not users:
            break

        for user in users:
            attrs = user.get("attributes", {})
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(
                table="users",
                data={
                    "id": user.get("id"),
                    "email": attrs.get("email"),
                    "name": attrs.get("name"),
                    "created_at": user.get("created_at"),
                    "signed_up_at": attrs.get("signed_up_at"),
                    "raw": user,
                    "_synced_at": timestamp(),
                },
            )
            # Incremental bookmark (keep the last ID seen)
            tb_state["last_seen_id"] = user.get("id")
            total += 1

        log.info(f"Fetched {len(users)} users (total {total}) so far...")

        # If using `next_page_url`, override base_url/params for next loop
        # The Userflow API returns `next_page_url` as either a full URL (e.g., "https://api.userflow.com/users?starting_after=abc")
        # or as a path (e.g., "/users?starting_after=abc"). Handle both cases below.
        if next_page_url:
            if next_page_url.startswith("http"):
                base_url = next_page_url
            elif next_page_url.startswith("/"):
                base_url = base_url.rstrip("/") + next_page_url
            else:
                log.warning(
                    f"Unexpected format for next_page_url: {next_page_url}. Skipping pagination."
                )
                has_more = False

        last_user_id = users[-1].get("id")
        starting_after = last_user_id

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
    log.info(f"Incremental sync completed: {total} users fetched")


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the "fivetran debug" command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug()
