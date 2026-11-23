"""This connector syncs the semantic layer of Omni (https://omni.co): models, views, dimensions,
measures, topics and the topic join graph, plus the workbooks, dashboards and apps built on them.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete(), truncate() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For building the setup form shown to users when configuring the connector in Fivetran
from fivetran_connector_sdk import ConfigurationForm

# For defining the fields of the setup form
from fivetran_connector_sdk import form_field

# For returning success or failure from the setup form's connection test
from fivetran_connector_sdk import Test

# For calling the Omni REST API with retries
import omni_api

# For turning Omni's YAML model files and document records into destination rows
import omni_model_parser

# Every table this connector writes. The model table comes first so it is populated before the
# tables whose rows refer to it.
__TABLES = ["model", "views", "dimension", "measure", "topic", "topic_join", "document"]
__SEMANTIC_LAYER_TABLES = ["views", "dimension", "measure", "topic", "topic_join"]
__REQUIRED_CONFIGURATION_KEYS = ["base_url", "api_token"]


def configuration_form():
    """
    Define the setup form shown to users when configuring this connector in Fivetran.
    Fivetran calls this method when rendering the connector setup UI.
    Returns:
        ConfigurationForm: the completed form with fields and the connection test.
    """
    config_form = ConfigurationForm()
    config_form.add_field(
        form_field.TextField(
            name="base_url",
            label="Omni URL",
            description="The host you sign in to, with or without https://. A custom domain works too.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="acme.omniapp.co",
        )
    )
    # Omni authenticates every API request with "Authorization: Bearer <token>". An Organization API
    # key is recommended: a Personal Access Token inherits its creator's permissions, so models that
    # user cannot see would be silently missing from the synced metadata.
    config_form.add_field(
        form_field.TextField(
            name="api_token",
            label="Organization API key",
            description="Create one in Omni under Settings > API access > Organization keys. A Personal"
            " Access Token also works, but only syncs the models its creator can access.",
            required=True,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_test(label="Connecting to Omni API", func=connection_test)
    return config_form


def connection_test(configuration: dict):
    """
    Confirm the Omni URL and token together by listing the models the connector will sync.
    The test uses a fail-fast budget of one attempt and a 10 second timeout, so a blocked host or a
    wrong URL is reported in seconds rather than leaving the form spinning through the sync budget.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
    test = Test()
    try:
        validate_configuration(configuration=configuration)
        client = omni_api.create_client(
            configuration["base_url"],
            configuration["api_token"],
            timeout_seconds=omni_api.SETUP_TEST_TIMEOUT_SECONDS,
            max_attempts=omni_api.SETUP_TEST_MAX_ATTEMPTS,
        )
        # The first page is enough to prove the URL and token work.
        next(omni_api.model_pages(client))
    except (ValueError, omni_api.OmniApiError) as error:
        log.warning(f"Omni connection test failed: {error}")
        return test.failure(f"Unable to connect to the Omni API: {error}")
    log.info("Omni connection test passed")
    return test.success()


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or the Omni URL is not http or https.
    """
    for key in __REQUIRED_CONFIGURATION_KEYS:
        if not str(configuration.get(key, "")).strip():
            raise ValueError(f"Missing required configuration value: {key}")
    # Raises ValueError for a URL with a scheme other than http or https.
    omni_api.api_base_url(configuration["base_url"])


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "model", "primary_key": ["id"]},
        # Named views rather than view: VIEW is a restricted identifier on destinations that enforce
        # the SQL standard, so queries against a table of that name would need quoting.
        {"table": "views", "primary_key": ["model_id", "view_name"]},
        {
            "table": "dimension",
            "primary_key": ["model_id", "view_name", "field_name"],
            "columns": {"is_primary_key": "BOOLEAN"},
        },
        {"table": "measure", "primary_key": ["model_id", "view_name", "measure_name"]},
        {"table": "topic", "primary_key": ["model_id", "topic_name"]},
        {
            "table": "topic_join",
            "primary_key": ["model_id", "topic_name", "from_view", "to_view"],
        },
        {
            "table": "document",
            "primary_key": ["id"],
            "columns": {
                "has_dashboard": "BOOLEAN",
                "has_app": "BOOLEAN",
                "is_deleted": "BOOLEAN",
                "visits": "INT",
                "last_viewed_at": "UTC_DATETIME",
                "updated_at": "UTC_DATETIME",
            },
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: QuickStart Examples - Omni")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    client = omni_api.create_client(configuration["base_url"], configuration["api_token"])

    # Omni returns the model and the documents as full listings rather than a change feed, so every
    # sync re-reads everything and nothing needs to carry across syncs in the state.
    populated_tables = set()
    sync_models(client, state, populated_tables)
    sync_documents(client, state, populated_tables)

    for table in __TABLES:
        if table not in populated_tables:
            log.warning(
                f"Omni returned no rows for {table}; leaving existing rows in place rather than "
                "marking them deleted"
            )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)
    log.info("Omni sync completed")


def sync_models(client, state: dict, populated_tables: set):
    """
    Sync every shared model and the views, dimensions, measures, topics and joins parsed from its
    YAML files, checkpointing after each model.
    Args:
        client: the Omni API client.
        state: the connector state, checkpointed unchanged.
        populated_tables: names of the tables that have received rows in this sync.
    """
    for models in omni_api.model_pages(client):
        for model in models:
            upsert_row("model", model, populated_tables)
            sync_model_contents(client, model["id"], populated_tables)

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state)


def sync_model_contents(client, model_id: str, populated_tables: set):
    """
    Fetch one model's YAML files and upsert the rows parsed from them.
    The YAML endpoint returns the whole model in a single response, so it cannot be paged; on a
    large real instance the shared model came to about 68,000 rows.
    Args:
        client: the Omni API client.
        model_id: the model to sync.
        populated_tables: names of the tables that have received rows in this sync.
    """
    files, view_names = omni_api.fetch_model_yaml(client, model_id)
    rows_by_table = omni_model_parser.parse_model(model_id, files, view_names)
    row_counts = ", ".join(
        f"{len(rows_by_table[table])} {table}" for table in __SEMANTIC_LAYER_TABLES
    )
    log.info(f"Model {model_id}: {row_counts}")
    for table in __SEMANTIC_LAYER_TABLES:
        for row in rows_by_table[table]:
            upsert_row(table, row, populated_tables)


def sync_documents(client, state: dict, populated_tables: set):
    """
    Sync every workbook, dashboard and app, checkpointing after each page.
    Args:
        client: the Omni API client.
        state: the connector state, checkpointed unchanged.
        populated_tables: names of the tables that have received rows in this sync.
    """
    document_count = 0
    for page_records in omni_api.document_pages(client):
        for record in page_records:
            row = omni_model_parser.document_row(record)
            if row is not None:
                upsert_row("document", row, populated_tables)
                document_count += 1

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)
    log.info(f"Synced {document_count} Omni document(s)")


def upsert_row(table: str, row: dict, populated_tables: set):
    """
    Upsert one row. Before the first row of each table in a sync, request a deferred truncate.
    A deferred truncate marks the rows synced before the call as deleted only after the sync
    completes successfully, so a definition removed in Omni is marked deleted downstream while a
    failed sync leaves the table untouched. Truncating only tables that receive rows protects
    against a listing that comes back empty without failing, for example after a token loses sight
    of the shared model: emptying the semantic layer on such a sync would not be recoverable.
    Args:
        table: the destination table.
        row: the row to upsert.
        populated_tables: names of the tables that have received rows in this sync.
    """
    if table not in populated_tables:
        op.truncate(table=table, deferred=True)
        populated_tables.add(table)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table, data=row)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema, configuration_form=configuration_form)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
