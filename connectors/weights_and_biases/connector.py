"""
Weights & Biases
This connector syncs data from Weights & Biases (W&B), including projects, runs, and artifacts.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For working with timestamps and timezone conversions
from datetime import datetime, timezone

# Weights & Biases Python SDK for accessing W&B API
import wandb

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Keep checkpoint constant outside (used for projects, runs, artifacts)
__CHECKPOINT_INTERVAL = 1000


def validate_configuration(configuration: dict) -> None:
    """
    Validate the configuration dictionary to ensure it contains all required parameters and that they have valid values.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or has an invalid value.
    """
    # Validate API key
    api_key = configuration.get("api_key")
    if api_key is None or api_key == "":
        raise ValueError("Missing required configuration value: api_key")
    if not isinstance(api_key, str):
        raise ValueError("Configuration 'api_key' must be a string.")

    # Validate entity
    entity = configuration.get("entity")
    if entity is None or entity == "":
        raise ValueError("Missing required configuration value: entity")
    if not isinstance(entity, str):
        raise ValueError("Configuration 'entity' must be a string.")


def _now_utc_iso() -> str:
    """
    Get the current UTC timestamp in ISO format.
    This is used for tracking when records were synced.
    Returns:
        A string representing the current UTC timestamp in ISO 8601 format.
    """
    return datetime.now(timezone.utc).isoformat()


def fetch_and_upsert_artifacts(run, state: dict, artifacts_synced: int) -> int:
    """
    Upsert all artifacts logged by a single W&B run.
    Artifacts are versioned data objects (models, datasets, etc.) logged during runs in W&B.
    Args:
        run: A W&B run object whose logged artifacts will be fetched.
        state: Fivetran state dictionary used for checkpointing.
        artifacts_synced: Running count of artifacts upserted so far (used for checkpointing).
    Returns:
        Updated count of artifacts upserted.
    """
    # Iterate through all artifacts logged by this run
    for artifact in run.logged_artifacts():
        artifact_object = {
            "artifact_id": artifact.id,
            "name": artifact.name,
            "type": artifact.type,
            "version": artifact.version,
            "state": artifact.state,
            "size": artifact.size,
            "created_at": str(getattr(artifact, "created_at", None)),
            "description": getattr(artifact, "description", None),
            "source_project": str(getattr(artifact, "source_project", None)),
            "run_id": run.id,
            "entity": run.entity,
            "synced_at": _now_utc_iso(),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="artifacts", data=artifact_object)
        # increment after each successful artifact upsert
        artifacts_synced += 1

        # Checkpoint at regular intervals
        if artifacts_synced % __CHECKPOINT_INTERVAL == 0:
            state["last_sync_time"] = _now_utc_iso()
            log.info(f"Checkpointing after {artifacts_synced} artifact upserts")
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)

    return artifacts_synced


def fetch_and_upsert_artifacts_and_runs(
    api: wandb.Api, entity: str, project, state: dict, runs_synced: int, artifacts_synced: int
) -> tuple:
    """
    Fetch all runs for a given W&B project, upsert them, and call fetch_artifacts() for each run.
    Args:
        api: An authenticated W&B API instance.
        entity: The W&B entity (username or team name).
        project: A W&B project object whose runs will be fetched.
        state: Fivetran state dictionary used for checkpointing.
        runs_synced: Running count of runs upserted so far (used for checkpointing).
        artifacts_synced: Running count of artifacts upserted so far (used for checkpointing).
    Returns:
        Tuple of (runs_synced, artifacts_synced).
    """
    log.info(f"Fetching runs for project: {project.name}")
    runs = api.runs(f"{entity}/{project.name}")
    log.info(f"Found {len(runs)} runs in project {project.name}")

    for run in runs:
        try:
            # Extract user information safely using getattr
            user = getattr(run, "user", None)
            username = getattr(user, "username", None) if user else None

            run_object = {
                "run_id": run.id,
                "name": run.name,
                "state": run.state,
                "tags": run.tags,
                "url": run.url,
                "entity": run.entity,
                "project": run.project,
                "path": f"{run.entity}/{run.project}/{run.id}",
                "created_at": str(run.created_at),
                "user": username,
            }

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="run_fields", data=run_object)
            runs_synced += 1

            # Checkpoint at regular intervals
            if runs_synced % __CHECKPOINT_INTERVAL == 0:
                state["last_sync_time"] = _now_utc_iso()
                log.info(f"Checkpointing after {runs_synced} run_fields upserts")
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)
        except Exception as e:
            log.warning(
                f"Failed to process run {getattr(run, 'id', 'unknown')}: "
                f"{type(e).__name__}: {str(e)}"
            )

        try:
            # Fetch and upsert artifacts for this run and update the artifacts_synced count
            artifacts_synced = fetch_and_upsert_artifacts(run, state, artifacts_synced)
        except Exception as e:
            log.warning(
                f"Failed to fetch artifacts for run {getattr(run, 'id', 'unknown')}: "
                f"{type(e).__name__}: {str(e)}"
            )

    # Checkpoint after completing all runs in the project to save progress
    state["last_sync_time"] = _now_utc_iso()
    op.checkpoint(state=state)

    return runs_synced, artifacts_synced


def fetch_and_upsert_data(api: wandb.Api, entity: str, state: dict) -> tuple:
    """
    Fetch all projects for a given W&B entity, upsert them, and call fetch_artifacts_and_runs()
    for each project.
    Projects are the top-level containers in W&B that group related runs and artifacts.
    Args:
        api: An authenticated W&B API instance.
        entity: The W&B entity (username or team name) to fetch projects from.
        state: Fivetran state dictionary used for checkpointing.
    Returns:
        Tuple of (projects_synced, runs_synced, artifacts_synced).
    """
    # tracks total number of projects upserted in this sync
    projects_synced = 0
    # tracks total number of run_fields upserted across all projects
    runs_synced = 0
    # tracks total number of artifacts upserted across all projects
    artifacts_synced = 0

    for project in api.projects(entity):
        project_record = {
            "project_id": f"{project.entity}/{project.name}",
            "entity": project.entity,
            "name": project.name,
            "url": getattr(project, "url", None),
            "synced_at": _now_utc_iso(),
        }

        # Upsert projects data to destination
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="projects", data=project_record)
        projects_synced += 1

        # Checkpoint at regular intervals
        if projects_synced % __CHECKPOINT_INTERVAL == 0:
            state["last_sync_time"] = _now_utc_iso()
            log.info(f"Checkpointing after {projects_synced} project upserts")
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)

        try:
            runs_synced, artifacts_synced = fetch_and_upsert_artifacts_and_runs(
                api, entity, project, state, runs_synced, artifacts_synced
            )
        except Exception as e:
            log.warning(f"Failed to fetch runs for project {project.name}: {str(e)}")

    return projects_synced, runs_synced, artifacts_synced


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
            "table": "projects",
            "primary_key": ["project_id"],
        },
        {
            "table": "run_fields",
            "primary_key": ["run_id"],
        },
        {
            "table": "artifacts",
            "primary_key": ["artifact_id"],
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
    log.warning("Example: Source Examples - Weights and Biases")

    # Validate the configuration
    validate_configuration(configuration)

    # Extract configuration parameters
    api_key = configuration["api_key"]
    entity = configuration["entity"]

    # Initialize API client with the provided API key
    api = wandb.Api(api_key=api_key)

    # Fetch and upsert projects, runs, and artifacts
    projects_count, runs_count, artifacts_count = fetch_and_upsert_data(api, entity, state)

    log.info(f"Upserted {projects_count} projects")
    log.info(f"Upserted {runs_count} run-fields")
    log.info(f"Upserted {artifacts_count} artifacts")

    # Update state with the current sync time for the next run
    state["last_sync_time"] = _now_utc_iso()
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state=state)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

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
