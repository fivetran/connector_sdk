# This is a simple example for how to use ConfigurationForm, form_field, and Test
# with the fivetran_connector_sdk module to build a connector with a setup form.
# It shows all available field types (TextField, DropdownField, ToggleField)
# and how to register a setup test that Fivetran runs when the user clicks "Test Connection".
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For building the setup form shown to users when configuring the connector in Fivetran
from fivetran_connector_sdk import ConfigurationForm

# For defining individual form fields (text inputs, dropdowns, toggles, etc.)
from fivetran_connector_sdk import form_field

# For returning success/failure responses from setup test functions
from fivetran_connector_sdk import Test

# For reading configuration from the local configuration.json file during debug runs
import json
import os
import re

# For making HTTP requests to the example API in the connection test and sync logic
import requests


DATA_RANGE_LIMITS = {
    "last_7_days": 7,
    "last_30_days": 30,
    "all_time": None,
}


def configuration_form():
    """
    Define the setup form shown to users when configuring this connector in Fivetran.
    Add fields using add_field() and register connection tests using add_test().
    Fivetran calls this method when rendering the connector setup UI.
    Returns:
        ConfigurationForm: the completed form with fields and tests.
    """
    config_form = ConfigurationForm()

    log.info("Example: QuickStart Examples - Configuration Form start")

    # Plain text field — visible input, suitable for non-sensitive values like URLs
    config_form.add_field(
        form_field.TextField(
            name="api_base_url",
            label="API Base URL",
            description="The base URL for your REST API endpoint.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="https://api.example.com/v1",
        )
    )

    # Password field — masked input, suitable for secrets like API keys
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

    # Dropdown field — lets the user select one option from a fixed list
    config_form.add_field(
        form_field.DropdownField(
            name="batch_size",
            label="Batch Size",
            description="Number of records to fetch per API request.",
            fields=[form_field.DropdownFieldParam(value=10),
                    form_field.DropdownFieldParam(value=100),
                    form_field.DropdownFieldParam(value=500)
                    ],
            required=True,
        )
    )

    # Toggle field — boolean on/off switch
    config_form.add_field(
        form_field.ToggleField(
            name="enable_metrics",
            label="Enable Metrics",
            description="Log extraction volume metrics (record count and bytes) during each sync.",
        )
    )

    # Dropdown — like a dropdown but each option includes an explanation (label and description)
    config_form.add_field(
        form_field.DropdownField(
            name="data_range",
            label="Data Range",
            fields=[
                form_field.DropdownFieldParam(
                    value="last_7_days",
                    label="Last 7 Days",
                    description="Fetches records created or updated in the last 7 days."
                ),
                form_field.DropdownFieldParam(
                    value="last_30_days",
                    label="Last 30 Days",
                    description="Fetches records created or updated in the last 30 days."
                ),
                form_field.DropdownFieldParam(
                    value="all_time",
                    label="All Time",
                    description="Fetches all available historical records."
                )
            ]
        )
    )

    # Register a setup test — Fivetran calls connection_test() when the user clicks "Test Connection"
    config_form.add_test(label="Test connection", func=connection_test)

    return config_form


def connection_test(configuration: dict):
    """
    Validate that the API credentials are correct and the endpoint is reachable.
    Fivetran calls this function by its __name__ during connector setup.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
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
        else:
            log.warning(f"Connection test failed: API returned status {response.status_code}")
            return test.failure(f"API returned status code: {response.status_code}")
    except requests.exceptions.Timeout:
        return test.failure("Connection timed out. Verify your api_base_url is reachable.")
    except requests.exceptions.ConnectionError:
        return test.failure("Could not connect to the API. Check your api_base_url.")
    except requests.exceptions.RequestException as e:
        return test.failure(f"Request failed: {e}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "post",
            "primary_key": ["id"],
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
    log.warning("Example: QuickStart Examples - Configuration Form")

    api_base_url = configuration.get("api_base_url", "").rstrip("/")
    api_key = configuration.get("api_key", "")
    batch_size = int(configuration.get("batch_size", 100))
    is_metrics_enabled = str(configuration.get("enable_metrics", "false")).lower() == "true"
    data_range = configuration.get("data_range", "all_time")
    max_records = DATA_RANGE_LIMITS.get(data_range)
    cursor = 0

    total_records = 0

    while True:
        remaining_records = None if max_records is None else max_records - total_records
        if remaining_records is not None and remaining_records <= 0:
            break

        current_batch_size = (
            batch_size if remaining_records is None else min(batch_size, remaining_records)
        )

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
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="post", data=post)

        total_records += len(posts)
        cursor += len(posts)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint({"cursor": cursor})

        if len(posts) < current_batch_size:
            break

    if is_metrics_enabled:
        log.info(f"Sync complete for data_range={data_range}: {total_records} records extracted")


# This creates the connector object that will use the update, schema, and configuration_form
# functions defined in this connector.py file.
connector = Connector(update=update, schema=schema, configuration_form_fn=configuration_form)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configuration.json")
    with open(config_path, "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
