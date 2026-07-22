from fivetran_connector_sdk import Logging as log  # For enabling Logs in your connector code
from faker import Faker
from datetime import datetime, timedelta, timezone

import connector

fake = Faker()


def get_api_response(base_url, from_cursor):
    log.info(f"Making API call to url: {base_url} with from_cursor: {from_cursor}")
    updated_since = connector.get_datetime_object(from_cursor)
    until = updated_since + timedelta(days=1)
    if until > datetime.now(timezone.utc):
        until = datetime.now(timezone.utc)
    response_page = {"data": []}
    while updated_since <= until:
        response_page["data"].append(
            {
                "id": fake.uuid4(),
                "name": fake.name(),
                "email": fake.email(),
                "address": fake.address(),
                "company": fake.company(),
                "job": fake.job(),
                "updated_at": updated_since.isoformat(),
                "created_at": updated_since.isoformat(),
            }
        )
        updated_since = updated_since + timedelta(hours=1)
    if updated_since < connector.sync_start:
        response_page["has_more"] = True
    return response_page


def should_continue_pagination(response_page):
    return response_page.get("has_more")
