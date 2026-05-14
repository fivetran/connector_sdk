# Priority-first sync, pfs for short, is very helpful for high volume historical syncs. It is a sync strategy
# which prioritises fetching the most recent data first so that fresh data is ready for you to use more quickly.
# This is a simple example of how you could implement the Priority-first sync strategy in a `connector.py` file for your connection.
# There is 1 table/endpoint in the example,i.e. "user".
# The `update` method is the starting point for the sync strategy.
# See the Technical Reference documentation
# (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

from datetime import datetime, timedelta, timezone
import traceback

# Import required classes from fivetran_connector_sdk.
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

import users_sync

base_url = "http://example.com/pagination/keyset"
sync_start = datetime.now().astimezone(timezone.utc)

# Constants
PFS_CURSORS = "pfs_cursors"
INCREMENTAL_SYNC_CURSOR = "incremental_cursor"
HISTORICAL_SYNC_CURSOR = "historical_cursor"
HISTORICAL_SYNC_LIMIT = "historical_limit"
IS_INCREMENTAL_SYNC = "is_incremental_sync"
SYNC_DURATION_THRESHOLD_IN_HOURS = 6
HISTORICAL_SYNC_BATCH_DURATION_IN_HOURS = 1


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
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
                "updated_at": "UTC_DATETIME",
                "created_at": "UTC_DATETIME",
            },
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning(
        "Example: Common Patterns For Connectors - Priority First Sync For High Volume Initial Syncs"
    )

    try:
        # list of endpoints for pfs flow mapped from table names
        endpoints = []
        for table_schema in schema(configuration):
            endpoints.append(table_schema["table"])

        # initializes pfs cursors in state for new endpoints
        initialize_pfs_cursors_for_each_endpoint(state, endpoints)

        # perform incremental sync based on `is_incremental_sync` state field and also checking
        # if all historical syncs have completed else perform historical sync and finally
        # switch value of `is_incremental_sync` state field to try alternate incremental and
        # historical sync
        if is_pfs_incremental_sync(state) or is_historical_data_completely_synced(
            state, endpoints
        ):
            log.info("starting incremental syncs")
            run_incremental_sync_for_endpoints(state, endpoints)
            # try running historical sync in the next sync
            set_pfs_incremental_sync(state, False)
        else:
            log.info("starting historical syncs")
            run_historical_syncs_for_endpoints(state, endpoints)
            # try running incremental sync in the next sync
            set_pfs_incremental_sync(state, True)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)
    except Exception:
        # logs stack trace
        log.error(traceback.format_exc())


def is_historical_data_completely_synced(state, endpoints):
    for endpoint in endpoints:
        # if historical_cursor is after the historical_limit for any endpoint, it means historical sync is not complete
        if get_datetime_object(
            get_pfs_historical_cursor_for_endpoint(state, endpoint)
        ) > get_datetime_object(get_pfs_historical_limit_for_endpoint(state, endpoint)):
            return False
    return True


def run_incremental_sync_for_endpoints(state, endpoints):
    for endpoint in endpoints:
        log.info("starting incremental sync for " + endpoint + " endpoint")
        incremental_sync_for_endpoint(state, endpoint)


def run_historical_syncs_for_endpoints(state, endpoints):
    for endpoint in endpoints:
        log.info("starting historical sync for " + endpoint + " endpoint")
        while get_datetime_object(
            get_pfs_historical_cursor_for_endpoint(state, endpoint)
        ) > get_datetime_object(get_pfs_historical_limit_for_endpoint(state, endpoint)):
            historical_sync_for_endpoint(state, endpoint)
            if is_sync_duration_threshold_breached():
                log.info(
                    "Sync duration breached sync_duration_threshold. Stopping sync to flush data to destination..."
                )
                return


def is_sync_duration_threshold_breached():
    if (
        (datetime.now().astimezone(timezone.utc) - sync_start).total_seconds() / 60 / 60
    ) >= SYNC_DURATION_THRESHOLD_IN_HOURS:
        return True
    return False


def incremental_sync_for_endpoint(state, endpoint):
    params = {"updated_since": get_pfs_incremental_cursor_for_endpoint(state, endpoint)}

    if endpoint == "user":
        users_sync.sync_users(base_url, params, state, False)


def historical_sync_for_endpoint(state, endpoint):
    # set updated_since to historical cursor minus 1 day. If updated_since is before historical_limit, sets it to historical limit
    # data is fetched for time range updated_since until historical cursor
    updated_since = get_datetime_object(
        get_pfs_historical_cursor_for_endpoint(state, endpoint)
    ) - timedelta(days=HISTORICAL_SYNC_BATCH_DURATION_IN_HOURS)
    if updated_since < get_datetime_object(get_pfs_historical_limit_for_endpoint(state, endpoint)):
        updated_since = get_datetime_object(get_pfs_historical_limit_for_endpoint(state, endpoint))
    params = {"updated_since": updated_since.isoformat()}

    if endpoint == "user":
        users_sync.sync_users(base_url, params, state, True)


def initialize_pfs_cursors_for_each_endpoint(state, endpoints):
    if PFS_CURSORS not in state:
        state[PFS_CURSORS] = {}
    for endpoint in endpoints:
        if endpoint not in state[PFS_CURSORS]:
            state[PFS_CURSORS][endpoint] = {}
            # incremental_cursor is used in incremental syncs
            # historical_cursor is used in historical syncs
            # historical_limit is the earliest timestamp upto which to fetch for historical syncs
            # historical_limit may be EPOCH in actual usage. 5 days is used here.
            state[PFS_CURSORS][endpoint][INCREMENTAL_SYNC_CURSOR] = (
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat()
            state[PFS_CURSORS][endpoint][HISTORICAL_SYNC_CURSOR] = state[PFS_CURSORS][endpoint][
                INCREMENTAL_SYNC_CURSOR
            ]
            state[PFS_CURSORS][endpoint][HISTORICAL_SYNC_LIMIT] = (
                datetime.now(timezone.utc) - timedelta(days=5)
            ).isoformat()
    if IS_INCREMENTAL_SYNC not in state[PFS_CURSORS]:
        set_pfs_incremental_sync(state, True)


def is_pfs_incremental_sync(state):
    return state[PFS_CURSORS][IS_INCREMENTAL_SYNC]


def set_pfs_incremental_sync(state, value):
    state[PFS_CURSORS][IS_INCREMENTAL_SYNC] = value


def set_pfs_incremental_cursor_for_endpoint(state, endpoint, value):
    state[PFS_CURSORS][endpoint][INCREMENTAL_SYNC_CURSOR] = value


def set_pfs_historical_cursor_for_endpoint(state, endpoint, value):
    state[PFS_CURSORS][endpoint][HISTORICAL_SYNC_CURSOR] = value


def set_pfs_historical_limit_for_endpoint(state, endpoint, value):
    state[PFS_CURSORS][endpoint][HISTORICAL_SYNC_LIMIT] = value


def get_pfs_incremental_cursor_for_endpoint(state, endpoint):
    return state[PFS_CURSORS][endpoint][INCREMENTAL_SYNC_CURSOR]


def get_pfs_historical_cursor_for_endpoint(state, endpoint):
    return state[PFS_CURSORS][endpoint][HISTORICAL_SYNC_CURSOR]


def get_pfs_historical_limit_for_endpoint(state, endpoint):
    return state[PFS_CURSORS][endpoint][HISTORICAL_SYNC_LIMIT]


def format_datetime(date_time):
    return date_time.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_datetime_object(date_time_str):
    return datetime.fromisoformat(date_time_str)


# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module. This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button. This is useful for debugging while you write your code.
# Note this method is not called by Fivetran when executing your connector in production. Please test using the
# Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from
    # your IDE.
    connector.debug()
