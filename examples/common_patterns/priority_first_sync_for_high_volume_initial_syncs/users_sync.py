from datetime import timezone

from fivetran_connector_sdk import (
    Operations as op,
)  # For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
import mock_api
import connector


def sync_users(base_url, params, state, is_historical_sync):
    more_data = True
    last_updated_at = params["updated_since"]

    while more_data:
        # Get response page from mock API call.
        response_page = mock_api.get_api_response(base_url, last_updated_at)

        # Process the items.
        items = response_page.get("data", [])
        if not items:
            break  # End pagination if there are no records in response.

        for user in items:
            op.upsert(table="user", data=user)
            last_updated_at = user[
                "updated_at"
            ]  # Assuming the API returns the data in ascending order

        # for historical sync, check if last_updated_at is greater than historical_cursor, if true break
        # as it means data fetch in the range from params['updated_since'] until historical_cursor is complete.
        # Next range will be fetched in next sync_users method call.
        if is_historical_sync and connector.get_datetime_object(
            last_updated_at
        ) >= connector.get_datetime_object(
            connector.get_pfs_historical_cursor_for_endpoint(state, "user")
        ).astimezone(
            timezone.utc
        ):
            break

        more_data = mock_api.should_continue_pagination(response_page)

    if is_historical_sync:
        # move the historical cursor backwards
        connector.set_pfs_historical_cursor_for_endpoint(state, "user", params["updated_since"])
    else:
        # move the incremental cursor forwards
        connector.set_pfs_incremental_cursor_for_endpoint(state, "user", last_updated_at)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)
