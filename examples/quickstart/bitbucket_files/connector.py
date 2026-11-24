"""This connector syncs a single Bitbucket Cloud repository: its metadata, the file listing of its
default branch, and each file's raw content as an unstructured file in the destination.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For stamping each file row with the sync start time
from datetime import datetime, timezone

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete(), truncate() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For streaming each file's raw bytes to the destination's file stage
from fivetran_connector_sdk import FileUpload

# For building the setup form shown to users when configuring the connector in Fivetran
from fivetran_connector_sdk import ConfigurationForm

# For defining the fields of the setup form
from fivetran_connector_sdk import form_field

# For returning success or failure from the setup form's connection test
from fivetran_connector_sdk import Test

# For calling the Bitbucket Cloud REST API with retries
import bitbucket_api

__REPOSITORY_TABLE = "repository"
__REPOSITORY_FILE_TABLE = "repository_file"
__CHECKPOINT_INTERVAL = 100
__REQUIRED_CONFIGURATION_KEYS = ["workspace", "repository_slug", "email", "api_token"]
__HTTP_UNAUTHORIZED = 401
__HTTP_FORBIDDEN = 403
__HTTP_NOT_FOUND = 404


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
            name="workspace",
            label="Workspace",
            description="Your Bitbucket workspace ID. If you access it at"
            ' https://bitbucket.org/my-team, then the workspace is "my-team".',
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="my-team",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="repository_slug",
            label="Repository",
            description="The slug of the repository to sync. If you access it at"
            ' https://bitbucket.org/my-team/my-repo, then the repository is "my-repo".',
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="my-repo",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="email",
            label="Atlassian account email",
            description="The email of the Atlassian account that owns the API token.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="you@example.com",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="api_token",
            label="API token",
            required=True,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="include_path_pattern",
            label="Include path pattern",
            description="Only sync files whose path matches this glob. Leave blank to sync all files.",
            required=False,
            field_type=form_field.TextField.plain_text,
            placeholder="*.py",
        )
    )
    config_form.add_test(label="Connecting to Bitbucket", func=connection_test)
    return config_form


def connection_test(configuration: dict):
    """
    Verify the credentials by fetching the configured repository, with a single attempt.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
    test = Test()
    try:
        validate_configuration(configuration=configuration)
    except ValueError as error:
        return test.failure(str(error))
    workspace = configuration["workspace"]
    repository_slug = configuration["repository_slug"]
    session = bitbucket_api.create_session(configuration["email"], configuration["api_token"])
    try:
        bitbucket_api.fetch_repository(
            session, workspace, repository_slug, bitbucket_api.SETUP_TEST_MAX_ATTEMPTS
        )
    except bitbucket_api.BitbucketApiError as error:
        return test.failure(connection_failure_message(error, workspace, repository_slug))
    finally:
        session.close()
    log.info("Bitbucket connection test passed")
    return test.success()


def connection_failure_message(error, workspace: str, repository_slug: str):
    """
    Turn a failed repository fetch into the message shown by the connection test.
    Args:
        error: the BitbucketApiError raised by the fetch.
        workspace: the configured workspace ID.
        repository_slug: the configured repository slug.
    Returns:
        The failure message.
    """
    if error.status_code in (__HTTP_UNAUTHORIZED, __HTTP_FORBIDDEN):
        return "Authentication failed. Check the account email and API token."
    if error.status_code == __HTTP_NOT_FOUND:
        return f'Repository "{workspace}/{repository_slug}" was not found or is not accessible.'
    return f"Unable to reach Bitbucket: {error}"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    for key in __REQUIRED_CONFIGURATION_KEYS:
        if not str(configuration.get(key, "")).strip():
            raise ValueError(f"Missing required configuration value: {key}")


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
            "table": __REPOSITORY_TABLE,
            "primary_key": ["uuid"],
            "columns": {
                "is_private": "BOOLEAN",
                "size": "LONG",
                "created_on": "UTC_DATETIME",
                "updated_on": "UTC_DATETIME",
            },
        },
        {
            # Each file's raw bytes are uploaded to the destination's file stage, and the
            # _fivetran_file_path column that points to them is added automatically.
            "table": __REPOSITORY_FILE_TABLE,
            "primary_key": ["repository_uuid", "path"],
            "columns": {"size": "LONG", "modified_at": "UTC_DATETIME"},
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
    log.warning("Example: QuickStart Examples - Bitbucket Files")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Every sync re-reads the repository's current state, so no cursor is kept in the state.
    sync_start = datetime.now(timezone.utc).isoformat()
    session = bitbucket_api.create_session(configuration["email"], configuration["api_token"])
    try:
        repository = sync_repository(session, configuration)
        sync_files(session, configuration, repository, sync_start, state)
    finally:
        session.close()

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def sync_repository(session, configuration: dict):
    """
    Fetch the configured repository and upsert its row.
    Args:
        session: the authenticated HTTP session.
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        The repository row.
    Raises:
        ValueError: if the repository has no default branch to sync.
    """
    repository = repository_row(
        bitbucket_api.fetch_repository(
            session, configuration["workspace"], configuration["repository_slug"]
        )
    )

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=__REPOSITORY_TABLE, data=repository)

    if not repository["full_name"] or not repository["default_branch"]:
        raise ValueError(
            f'Repository "{repository["full_name"]}" has no default branch to sync. The repository'
            " must have at least one commit on its default branch."
        )
    return repository


def sync_files(session, configuration: dict, repository: dict, sync_start: str, state: dict):
    """
    Upsert a row for every file on the default branch and upload its raw bytes, checkpointing
    every 100 files.
    Before the first file, a deferred truncate is requested for repository_file. When the sync
    completes successfully, every file row not upserted in this sync is marked deleted, so files
    removed from the repository, including the old path of a renamed file, are marked deleted
    downstream. If the sync fails, nothing is marked deleted.
    Args:
        session: the authenticated HTTP session.
        configuration: a dictionary that holds the configuration settings for the connector.
        repository: the repository row.
        sync_start: the ISO 8601 time the sync started.
        state: the connector state, checkpointed unchanged.
    """
    op.truncate(table=__REPOSITORY_FILE_TABLE, deferred=True)
    files_since_checkpoint = 0
    pages = bitbucket_api.file_pages(
        session,
        repository["full_name"],
        repository["default_branch"],
        configuration.get("include_path_pattern"),
    )
    for page_files in pages:
        for file in page_files:
            row = repository_file_row(file, repository["uuid"], sync_start)
            upsert_file(session, repository, row)
            files_since_checkpoint += 1
            if files_since_checkpoint >= __CHECKPOINT_INTERVAL:
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state)
                files_since_checkpoint = 0


def upsert_file(session, repository: dict, row: dict):
    """
    Upsert one file's row together with its raw bytes. If the file's content cannot be fetched,
    the row is still upserted with the same _fivetran_file_path, so the bytes staged by an earlier
    sync stay in place, and the sync continues. A failure while the bytes are being uploaded is
    not caught and fails the sync.
    Args:
        session: the authenticated HTTP session.
        repository: the repository row.
        row: the file row to upsert.
    """
    try:
        response = bitbucket_api.open_file_content(
            session, repository["full_name"], repository["default_branch"], row["path"]
        )
    except bitbucket_api.BitbucketApiError as error:
        # The path is customer data, so it is left out of the log.
        log.warning(f"Skipping a Bitbucket file whose content could not be fetched: {error}")

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__REPOSITORY_FILE_TABLE, data={**row, "_fivetran_file_path": row["path"]})
        return

    with response:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        # The third argument (file) is the FileUpload object with file details associated with the metadata row.
        op.upsert(
            table=__REPOSITORY_FILE_TABLE,
            data=row,
            file=FileUpload(path=row["path"], stream=response.raw),
        )


def repository_row(repository: dict):
    """
    Map the repository response to a row, flattening mainbranch.name into default_branch.
    language is renamed main_language because LANGUAGE is a reserved SQL keyword.
    Args:
        repository: the repository response.
    Returns:
        The repository row.
    """
    mainbranch = repository.get("mainbranch") or {}
    return {
        "uuid": repository.get("uuid"),
        "name": repository.get("name"),
        "full_name": repository.get("full_name"),
        "slug": repository.get("slug"),
        "description": repository.get("description"),
        "is_private": repository.get("is_private"),
        "size": repository.get("size"),
        "created_on": repository.get("created_on"),
        "updated_on": repository.get("updated_on"),
        "main_language": repository.get("language"),
        "default_branch": mainbranch.get("name"),
    }


def repository_file_row(file: dict, repository_uuid: str, sync_start: str):
    """
    Map one entry of the file listing to a row, flattening commit.hash into commit_hash.
    file_id and modified_at are a stable per-file id and a modified-at cursor for the AI
    document-parse pipeline: the path and the sync start time.
    Args:
        file: one entry of the file listing.
        repository_uuid: the owning repository's uuid, which the listing does not carry.
        sync_start: the ISO 8601 time the sync started.
    Returns:
        The file row.
    """
    commit = file.get("commit") or {}
    return {
        "repository_uuid": repository_uuid,
        "path": file.get("path"),
        "type": file.get("type"),
        "size": file.get("size"),
        "mimetype": file.get("mimetype"),
        "file_id": file.get("path"),
        "modified_at": sync_start,
        "commit_hash": commit.get("hash"),
    }


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
