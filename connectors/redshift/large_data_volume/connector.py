"""
This connector demonstrates how to fetch data from Redshift source and upsert it into destination using redshift_connector library.
It supports both FULL and INCREMENTAL replication strategies, with automatic schema detection and column typing.
This example also ensures that large datasets are handled efficiently by batching fetches and checkpointing progress periodically.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

from concurrent.futures import ThreadPoolExecutor, as_completed  # For parallel execution
from redshift_client import (
    _ConnectionPool,
    get_table_plans,
    run_single_worker_sync,
    _run_plan_with_pool,
)  # Redshift client utilities


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = [
        "redshift_host",
        "redshift_port",
        "redshift_database",
        "redshift_user",
        "redshift_password",
        "redshift_schema",
        "batch_size",
        "auto_schema_detection",
        "enable_complete_resync",
    ]
    missing = [k for k in required_configs if k not in configuration]
    if missing:
        raise ValueError(f"Missing required configuration value(s): {', '.join(missing)}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # build table plans from configuration and Redshift metadata
    # This will use the TABLE_SPECS defined in table_specs.py if auto_schema_detection is false,
    # otherwise it will discover tables and primary keys from Redshift.
    plans = get_table_plans(configuration=configuration)
    schema_list = []
    # Build the schema list
    for plan in plans:
        table = {"table": plan.stream, "primary_key": plan.primary_keys}
        if plan.explicit_columns:
            # If there are any explicitly typed columns, include them in the schema
            table["columns"] = plan.explicit_columns
        schema_list.append(table)
    return schema_list


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
    log.warning("Example: Source Examples - Redshift - Large Data Volume")

    # Build table plans from configuration and Redshift metadata
    plans = get_table_plans(configuration=configuration)

    # Get max parallel workers from configuration
    # If the value is greater than the number of tables to sync, it will be capped at the number of tables to sync
    # Ensure that you do not set this to a high value. Recommended value is between 2 and 4.
    # Setting a high value may degrade the performance instead of improving it
    max_parallel_workers = min(int(configuration.get("max_parallel_workers")), len(plans))

    if not plans:
        log.warning(
            "No tables defined to sync. Either define TABLE_SPECS or enable auto_schema_detection."
        )
        return

    if max_parallel_workers <= 1:
        # Run sync sequentially using a single connection
        run_single_worker_sync(plans=plans, configuration=configuration, state=state)
    else:
        # Run sync in parallel using a connection pool
        pool = _ConnectionPool(configuration=configuration, size=max_parallel_workers)
        try:
            with ThreadPoolExecutor(max_workers=max_parallel_workers) as executor:
                # Submit tasks to the executor for each table plan
                futures = [
                    executor.submit(_run_plan_with_pool, plan, pool, configuration, state)
                    for plan in plans
                ]
                for future in as_completed(futures):
                    stream = future.result()
                    log.info(f"{stream}: Sync Finished.")
        finally:
            # Close all connections in the pool after all tasks are completed
            pool.close_all()
            log.info("All connections in the pool have been closed.")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
