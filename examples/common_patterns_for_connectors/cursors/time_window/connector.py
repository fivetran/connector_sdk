# This is an example for how to work with the fivetran_connector_sdk module.
# It defines a "from" and "to" timestamp that can be sent to an API, and limits the time range to DAYS_PER_SYNC days at a time for an initial sync.
# It does not sync any data from a source.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details


from datetime import datetime, timezone, timedelta

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__INITIAL_SYNC_START = "2024-06-01T00:00:00.000Z"
__DAYS_PER_SYNC = 30


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    The function takes two parameters:
     - configuration: dictionary contains any secrets or payloads you configure when deploying the connector
     - state: a dictionary contains whatever state you have chosen to checkpoint during the prior sync
    The state dictionary is empty for the first sync or for any full re-sync
    """

    log.warning("Example: Common Patterns For Connectors - Cursor - Time Window")

    # save the current time for starting the sync
    start_timestamp = format_iso_timestamp(datetime.now(timezone.utc))
    # get a start and end timestamp that could be used with an API
    from_timestamp, to_timestamp = set_timeranges(state, start_timestamp)
    # this "fine" log will only appear during debugging
    log.debug(f"start: {from_timestamp} end: {to_timestamp}, until we reach {start_timestamp}")

    more_data = True
    while more_data:

        # save the end of the current time range to the state
        state["to_timestamp"] = to_timestamp
        # The 'upsert' operation inserts the data into the destination.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into, in this case, "timestamps".
        # - The second argument is a dictionary containing the data to be upserted.
        op.upsert(table="timestamps", data={"message": f"from {from_timestamp} to {to_timestamp}"})

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        if to_timestamp < start_timestamp:
            # if we haven't reached the start of the sync yet
            from_timestamp, to_timestamp = set_timeranges(state, start_timestamp)
        else:
            more_data = False


def set_timeranges(state, start_timestamp):
    """
    Takes in current state and start timestamp of current sync.
    from_timestamp is always either the end of the last sync or the initialSyncStart found in the config file.
    If from_timestamp is more than __DAYS_PER_SYNC days ago, then set a to_timestamp that is __DAYS_PER_SYNC days later than from_timestamp.
    Otherwise, to_timestamp is the time that this sync was triggered.
    :param state:
    :param start_timestamp:
    :return: from_timestamp, to_timestamp
    """
    if "to_timestamp" in state:
        from_timestamp = state["to_timestamp"]
    else:
        from_timestamp = __INITIAL_SYNC_START

    if is_older_than_n_days(from_timestamp):
        """
        if the timerange from the last sync ended more than __DAYS_PER_SYNC days ago,
        get an ending timestamp for the new range that is __DAYS_PER_SYNC days later than that.
        """
        from_timestamp_dt = parse_iso_timestamp(from_timestamp)
        to_timestamp = format_iso_timestamp(from_timestamp_dt + timedelta(days=__DAYS_PER_SYNC))
    else:
        """otherwise the timerange for the next range can end when the sync started"""
        to_timestamp = start_timestamp

    return from_timestamp, to_timestamp


def is_older_than_n_days(date_to_check):
    """
    Checks whether date_to_check is older than __DAYS_PER_SYNC days.
    Is time-zone aware and handles date_to_check being a string and not a datetime
    :param date_to_check:
    :return: boolean based on whether date is older than __DAYS_PER_SYNC days
    """
    now = datetime.now(timezone.utc)  # Timezone-aware UTC datetime

    # Convert to datetime if input is a string
    if isinstance(date_to_check, str):
        date_to_check = parse_iso_timestamp(date_to_check)

    return date_to_check < now - timedelta(days=__DAYS_PER_SYNC)


def format_iso_timestamp(dt: datetime) -> str:
    """
    Formats a datetime object to ISO format with 'Z' timezone indicator.
    :param dt: datetime object to format
    :return: ISO formatted string with 'Z' timezone
    """
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso_timestamp(timestamp: str) -> datetime:
    """
    Parses an ISO format timestamp string with 'Z' timezone to a datetime object.
    :param timestamp: ISO formatted string with 'Z' timezone
    :return: datetime object
    """
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


# This creates the connector object that will use the update function defined in this connector.py file.
# This example does not use the schema() function. If it did, it would need to be included in the connector object definition.
connector = Connector(update=update)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE:
    connector.debug()
