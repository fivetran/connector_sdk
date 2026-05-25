"""
This example shows how to pull activity and participant data from the People.ai API
and load it into a destination using the Fivetran Connector SDK.

This Fivetran Connector uses the People.ai service to retrieve records from the
`/v0/public/activities` and `/v0/public/activities/{type}` endpoints. This connector demonstrates:
- OAuth2 authentication using the client credentials flow to retrieve an access token.
- Automatic token refresh (reauthentication) when a 401 Unauthorized error is encountered.
- Resilient API calls with exponential backoff and retries for transient network or 5xx server errors.
- Incremental data ingestion using pagination and upserts into destination tables.
- Schema definition with two destination tables (`activity` and `participants`) using composite keys.

The connector defines a robust retry strategy with reauthentication support, ensuring consistent
data delivery even under intermittent API failures. It also renames fields such as `subject` to
`api_subject` to prevent naming conflicts within destination schemas.

Refer to People.ai API documentation (https://api-docs.people.ai/) for more details.
See the Fivetran Connector SDK Technical Reference
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and Best Practices
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for implementation guidance.
"""

from __future__ import annotations

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# The unused imports 'Sequence' and 'Literal' have been removed.
from typing import Any, Dict, List, Callable, Optional

# Import time module to handle time-related tasks, such as delays.
import time

# Import requests to make HTTP calls to API
import requests


# --- Configuration ---
__API_BASE = "https://api.people.ai"

__ACTIVITY_TABLE = "activity"
__ACTIVITY_TYPES = ["participants"]

__MAX_RETRIES = 5
__INITIAL_DELAY_SECONDS = 2
__REAUTH_RETRY_COUNT = 1
# --- End Configuration ---


def schema(configuration: dict) -> List[Dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema
    your connector delivers.
    See the technical reference documentation
    for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "activity",  # Name of the table in the destination, required.
            "primary_key": ["uid"],  # Primary key column(s) for the table, optional.
        },
        {
            "table": "participants",  # Name of the table in the destination, required.
            "primary_key": ["uid", "email"],  # Primary key column(s) for the table, optional.
        },
    ]


# The 'update' function will now need to pass a reauth function to get_page
def get_page(
    access_token: str,
    reauth_func: Callable[[], str],  # Added reauth function for 401 handling
    activity_type: Optional[str] = None,  # Made optional for base endpoint
    limit: int = 50,
    offset: int = 0,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """
    Fetches a page of data from an API endpoint, handling potential
    reauthentication on 401 errors.

    Args:
        access_token (str): The authentication token required for API access.
        reauth_func (Callable[[], str]): A function that, when called,
            performs reauthentication and returns a new access token. Used on 401 errors.
        activity_type (Optional[str]): Specifies the type of activity to fetch.
            Set to None for the base endpoint.
        limit (int): The maximum number of items to return in a single page.
        offset (int): The starting position (offset) for the query, used for pagination.
        timeout (int): The request timeout in seconds.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary
            represents a data item (e.g., activity record).
    """

    current_token = access_token

    # Construct the URL: /activities or /activities/{type}
    url = f"{__API_BASE}/v0/public/activities"
    if activity_type:
        url += f"/{activity_type}"

    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    # Outer loop for re-authentication attempt on 401
    for reauth_attempt in range(__REAUTH_RETRY_COUNT + 1):

        # Inner loop for exponential backoff on server errors (5xx)
        for attempt in range(__MAX_RETRIES + 1):

            headers = {"Authorization": f"Bearer {current_token}"}

            try:
                r = requests.get(url, headers=headers, params=params, timeout=timeout)
                r.raise_for_status()
                payload = r.json()

                # Success, return the data
                if isinstance(payload, dict):
                    return payload.get("data", [])
                return payload

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code

                # --- Handle 401 (Unauthorized) ---
                if status_code == 401:
                    log.warning(f"Received 401 Client Error at offset {offset}.")
                    break  # Break inner loop to trigger re-auth attempt

                # --- Handle 502/5xx (Server/Gateway Errors) ---
                elif 500 <= status_code <= 599:
                    if attempt < __MAX_RETRIES:
                        # Exponential backoff calculation:
                        # BASE_DELAY * (2^attempt)
                        delay = __INITIAL_DELAY_SECONDS * (2**attempt)
                        log.warning(f"Received {status_code}. Retrying... ")
                        time.sleep(delay)
                        continue  # Continue inner loop for another request
                    else:
                        # Max retries reached
                        log.severe(
                            f"Failed to fetch page after {__MAX_RETRIES + 1} "
                            f"due to {status_code} error."
                        )
                        raise e

                # --- Handle other HTTP errors (e.g., 400, 404) ---
                else:
                    log.severe(f"Received unrecoverable HTTP error {status_code}")
                    raise e

            except requests.exceptions.RequestException as e:
                # Handle connection/timeout errors
                if attempt < __MAX_RETRIES:
                    delay = __INITIAL_DELAY_SECONDS * (2**attempt)
                    time.sleep(delay)
                    continue
                else:
                    # Max retries reached
                    log.severe(
                        f"Failed to fetch page after {__MAX_RETRIES + 1} "
                        "retries due to connection issues."
                    )
                    raise e

        # --- 401 Handling Logic ---
        # This point is reached only if a 401 error
        # caused the inner loop to 'break'
        if reauth_attempt < __REAUTH_RETRY_COUNT:
            log.info("Attempting to refresh access token...")
            try:
                # Call the passed re-authentication function
                current_token = reauth_func()
                log.info("Token refreshed successfully. Retrying request.")
                continue  # Continue outer loop with new token
            except Exception as e:
                log.severe(f"Failed to refresh token: {e}")
                raise e  # If re-auth fails, raise the exception
        else:
            # If 401 and max reauth retries reached
            log.severe(
                f"Authentication failed after {__REAUTH_RETRY_COUNT + 1}"
                " re-authentication attempts."
            )
            raise requests.exceptions.HTTPError(
                "401 Client Error: Unauthorized (Max re-auth retries reached)"
            )
    return []


def sync_base_activities(
    access_token: str, state: dict, reauth_func: Callable[[], str], op: op, *, limit: int = 50
) -> int:
    """
    Handles the full pagination and upsert logic for the base /activities endpoint.
    Passes the reauth_func to get_page.

    Args:
        access_token (str): The authentication token required for API access.
        state (dict): A dictionary containing state information from previous runs.
               The state dictionary is empty for the first sync or for any
               full re-sync.
        reauth_func (Callable[[], str]): A function that, when called,
            performs reauthentication and returns a new access token. Used on 401 errors.
        op (op): A database or storage operation object used to perform
            the upsert (update or insert) of the fetched data.
        limit (int): The maximum number of items to fetch per page in each
            API call (default is 50).

    Returns:
        int: The total number of records successfully processed (upserted).
    """
    offset = 0
    total = 0

    while True:
        try:
            # Pass the reauth_func
            page = get_page(
                access_token,
                reauth_func,
                activity_type=None,
                limit=limit,
                offset=offset,
            )
        except requests.exceptions.HTTPError as e:
            # The retry logic is now inside get_page,
            # so an error here means it failed permanently
            log.severe(f"Permanent failure fetching base activities" f" at offset {offset}: {e}")
            break

        if not page:
            break

        for rec in page:
            data_to_upsert = rec.copy()

            # The base endpoint may contain the 'subject' field too
            # so we rename it
            if "subject" in data_to_upsert:
                data_to_upsert["api_subject"] = data_to_upsert.pop("subject")

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=__ACTIVITY_TABLE, data=data_to_upsert)

        total += len(page)
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        state["activity_offset"] = offset + len(page)
        op.checkpoint(state)

        if len(page) < limit:
            break

        offset += limit

    return total


def sync_activity_type(
    access_token: str,
    state: dict,
    reauth_func: Callable[[], str],
    op: op,
    activity_type: str,
    *,
    limit: int = 50,
) -> int:
    """
    Handles the full pagination and upsert logic
    for a single specific activity type (/activities/{type}).
    Passes the reauth_func to get_page.

    Args:
        access_token (str): The authentication token required for API access.
        state: A dictionary containing state information from previous runs.
               The state dictionary is empty for the first sync or for any
               full re-sync.
        reauth_func (Callable[[], str]): A function that, when called,
            performs reauthentication and returns a new access token. Used on 401 errors.
        op (op): A database or storage operation object used to perform
            the upsert (update or insert) of the fetched data.
        activity_type (str): The specific type of activity to synchronize
            (e.g., 'runs', 'rides', 'swims'), which forms part of the API endpoint.
        limit (int): The maximum number of items to fetch per page in each
            API call (default is 50).

    Returns:
        int: The total number of records successfully processed (upserted) for
            the specified activity type.
    """
    offset = 0
    total = 0

    while True:
        try:
            # Pass the reauth_func
            page = get_page(access_token, reauth_func, activity_type, limit=limit, offset=offset)
        except requests.exceptions.HTTPError as e:
            # The retry logic is now inside get_page,
            # so an error here means it failed permanently
            log.severe(f"Permanent failure fetching {activity_type}" f" at offset {offset}: {e}")
            break

        if not page:
            break

        for rec in page:
            data_to_upsert = rec.copy()

            # The original logic for renaming 'subject'
            # for certain types is kept
            if "subject" in data_to_upsert and activity_type in [
                "meeting",
                "email",
                "call",
            ]:
                data_to_upsert["api_subject"] = data_to_upsert.pop("subject")

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=activity_type, data=data_to_upsert)

        total += len(page)
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        state["activity_offset"] = offset + len(page)
        op.checkpoint(state)

        if len(page) < limit:
            break

        offset += limit

    log.info(f"Completed sync for '{activity_type}'. Total records synced: {total}")
    return total


def get_access_token(api_key: str, api_secret: str) -> str:
    """
    Fetches the OAuth access token using client credentials.

    Args:
        api_key (str): The client ID or API key used to identify the application.
        api_secret (str): The client secret used to authenticate the application.

    Returns:
        str: The newly acquired OAuth access token.
    """
    url = f"{__API_BASE}/auth/v1/tokens"
    data = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": api_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(url, data=data, headers=headers)
    resp.raise_for_status()
    return resp.json()["access_token"]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_key", "api_secret"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure
    how your connector fetches data.
    See the technical reference documentation for more details
    on the update function: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

    Args:
        configuration: A dictionary containing connection details.
        state: A dictionary containing state information from previous runs.
               The state dictionary is empty for the first sync or for any
               full re-sync.
    """
    log.warning("Example: CONNECTORS : PEOPLE_AI")
    validate_configuration(configuration)

    # Define a closure function for re-authentication to pass to sync functions
    api_key = configuration["api_key"]
    api_secret = configuration["api_secret"]

    def reauthenticate():
        nonlocal access_token
        access_token = get_access_token(api_key, api_secret)
        return access_token

    # 1. Initial Authentication
    log.info("Starting initial authentication process.")
    try:
        access_token = get_access_token(api_key, api_secret)
    except requests.exceptions.RequestException as e:
        log.severe(f"FATAL: Initial authentication failed: {e}")
        return  # Stop the sync

    total_records_synced = 0

    # 2. Sync the base /activities endpoint to the 'activity' table
    log.info("\n--- Starting synchronization for activity table ---")
    count = sync_base_activities(
        access_token=access_token,
        state=state,
        reauth_func=reauthenticate,  # Pass the reauth function
        op=op,
        limit=1000,
    )
    total_records_synced += count

    # 3. Sync only the specific activity type
    # endpoints defined in __ACTIVITY_TYPES
    log.info(f"\nStarting sync for the {len(__ACTIVITY_TYPES)} " "specific activity type(s).")

    for activity_type in __ACTIVITY_TYPES:
        count = sync_activity_type(
            access_token=access_token,
            state=state,
            reauth_func=reauthenticate,  # Pass the reauth function
            op=op,
            activity_type=activity_type,
            limit=100000,
        )
        total_records_synced += count

    log.info(f"\n--- All tables synced. Total records processed: " f"{total_records_synced} ---")


# Create the connector object using the schema and update functions
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
