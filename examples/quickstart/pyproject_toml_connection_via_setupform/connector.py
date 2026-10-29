from __future__ import annotations

import json
import os
import re

import requests
from fivetran_connector_sdk import ConfigurationForm
from fivetran_connector_sdk import Connector, Operations as op, Logging as log
from fivetran_connector_sdk import Test
from fivetran_connector_sdk import form_field

DATA_RANGE_LIMITS = {
    "last_7_days": 7,
    "last_30_days": 30,
    "all_time": None,
}


def configuration_form():
    """Define the setup form shown to users when configuring this connector in Fivetran."""
    config_form = ConfigurationForm()

    config_form.add_field(
        form_field.TextField(
            name="api_base_url",
            label="API Base URL",
            description="The base URL for your REST API endpoint.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="https://jsonplaceholder.typicode.com",
        )
    )

    config_form.add_field(
        form_field.TextField(
            name="api_key",
            label="API Key",
            description="Your API authentication key. This value is stored securely.",
            required=True,
            field_type=form_field.TextField.password,
            placeholder="your_api_key_here",
        )
    )

    config_form.add_field(
        form_field.TextField(
            name="my_host",
            label="My Host",
            description="Your target host for the proxy tunnel.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="myhost.com:1234",
        )
    )

    config_form.add_field(
        form_field.DropdownField(
            name="batch_size",
            label="Batch Size",
            description="Number of records to fetch per API request.",
            fields=[
                form_field.DropdownFieldParam(value=10),
                form_field.DropdownFieldParam(value=100),
                form_field.DropdownFieldParam(value=500),
            ],
            required=True,
        )
    )

    config_form.add_field(
        form_field.ToggleField(
            name="enable_metrics",
            label="Enable Metrics",
            description="Log extraction volume metrics during each sync.",
        )
    )

    config_form.add_field(
        form_field.DropdownField(
            name="data_range",
            label="Data Range",
            fields=[
                form_field.DropdownFieldParam(
                    value="last_7_days",
                    label="Last 7 Days",
                    description="Fetch records created or updated in the last 7 days.",
                ),
                form_field.DropdownFieldParam(
                    value="last_30_days",
                    label="Last 30 Days",
                    description="Fetch records created or updated in the last 30 days.",
                ),
                form_field.DropdownFieldParam(
                    value="all_time",
                    label="All Time",
                    description="Fetch all available historical records.",
                ),
            ],
        )
    )

    config_form.add_test(label="Test connection", func=connection_test)
    return config_form


def connection_test(configuration: dict):
    """Validate that the API credentials are correct and the endpoint is reachable."""
    test = Test()
    api_base_url = configuration.get("api_base_url", "").rstrip("/")
    api_key = configuration.get("api_key", "")

    if not api_base_url:
        return test.failure("api_base_url is required.")
    if not re.match(r"^https?://", api_base_url):
        return test.failure("api_base_url must start with http:// or https://.")
    if not api_key:
        return test.failure("api_key is required.")

    try:
        response = requests.get(
            api_base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if response.status_code == 200:
            log.info("Connection test passed: API returned 200")
            return test.success()
        log.warning(f"Connection test failed: API returned status {response.status_code}")
        return test.failure(f"API returned status code: {response.status_code}")
    except requests.exceptions.Timeout:
        return test.failure("Connection timed out. Verify your api_base_url is reachable.")
    except requests.exceptions.ConnectionError as exc:
        log.warning(f"Request failed: {exc}")
        return test.failure("Could not connect to the API. Check your api_base_url.")
    except requests.exceptions.RequestException as exc:
        return test.failure(f"Request failed: {exc}")


def schema(configuration: dict):
    """Return a schema describing the destination table for the connector."""
    return [{"table": "post", "primary_key": ["id"]}]


def validate_configuration(configuration: dict):
    """Ensure the configuration contains the required values before syncing."""
    required_keys = ["api_base_url", "api_key", "my_host"]
    for key in required_keys:
        if key not in configuration or not configuration[key]:
            raise ValueError(f"Missing required configuration value: '{key}'")


def update(configuration: dict, state: dict):
    """Fetch sample posts from the configured API and load them into the destination."""
    log.warning("Example: QuickStart : pyproject_toml_connection_via_setupform")
    validate_configuration(configuration)

    api_base_url = configuration.get("api_base_url", "").rstrip("/")
    api_key = configuration.get("api_key", "")
    batch_size = int(configuration.get("batch_size", 100))
    is_metrics_enabled = str(configuration.get("enable_metrics", "false")).lower() == "true"
    data_range = configuration.get("data_range", "all_time")
    max_records = DATA_RANGE_LIMITS.get(data_range)

    cursor = 0
    total_records = 0

    while True:
        if max_records is None:
            remaining_records = None
        else:
            remaining_records = max_records - total_records

        if remaining_records is not None and remaining_records <= 0:
            break

        if remaining_records is None:
            current_batch_size = batch_size
        else:
            current_batch_size = min(batch_size, remaining_records)

        response = requests.get(
            f"{api_base_url}/posts",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"_start": cursor, "_limit": current_batch_size},
            timeout=30,
        )
        response.raise_for_status()
        posts = response.json()

        if not posts:
            break

        for post in posts:
            op.upsert(table="post", data=post)

        total_records += len(posts)
        cursor += len(posts)
        op.checkpoint({"cursor": cursor})

        if len(posts) < current_batch_size:
            break

    if is_metrics_enabled:
        log.info(f"Sync complete for data_range={data_range}: {total_records} records extracted")


connector = Connector(update=update, schema=schema, configuration_form=configuration_form)


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configuration.json")
    with open(config_path, "r") as file:
        configuration = json.load(file)
    connector.debug(configuration=configuration)
