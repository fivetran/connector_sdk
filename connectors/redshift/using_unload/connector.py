"""
This connector demonstrates how to efficiently sync large tables from Amazon Redshift
by leveraging the UNLOAD command to export data to S3 in Parquet format, then reading
from S3 for ingestion. This approach is highly performant for large datasets as it:
1. Offloads data export to Redshift's native UNLOAD functionality
2. Uses Parquet format for efficient storage and fast reading
3. Supports parallel execution for multiple tables
4. Supports automatic schema detection
5. Supports both FULL and INCREMENTAL replication strategies

See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For concurrent execution
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import Redshift client utilities
from redshift_client import (
    _ConnectionPool,
    get_table_plans,
    run_single_worker_sync,
    _run_plan_with_pool,
)

# Import S3 client utilities
from s3_client import S3Client


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
        "s3_bucket",
        "s3_region",
        "iam_role",
        "aws_access_key_id",
        "aws_secret_access_key",
        "auto_schema_detection",
        "enable_complete_resync",
        "max_parallel_workers",
    ]

    missing = [k for k in required_configs if k not in configuration]
    if missing:
        raise ValueError(f"Missing required configuration value(s): {', '.join(missing)}")

    # Validate IAM role format
    iam_role = configuration.get("iam_role", "")
    if not iam_role.startswith("arn:aws:iam::"):
        raise ValueError(
            "Invalid IAM role format. Expected format: arn:aws:iam::<account-id>:role/<role-name>"
        )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
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
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Source Examples - Redshift - Using UNLOAD")

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

    # Create S3 client for reading exported data
    s3_client = S3Client(configuration=configuration)

    log.info(f"Starting sync for {len(plans)} table(s) with {max_parallel_workers} worker(s)")

    if max_parallel_workers <= 1:
        # Run sync sequentially using a single connection
        run_single_worker_sync(
            plans=plans,
            s3_client=s3_client,
            configuration=configuration,
            state=state,
        )
    else:
        # Run sync in parallel using a connection pool
        pool = _ConnectionPool(configuration=configuration, size=max_parallel_workers)
        try:
            with ThreadPoolExecutor(max_workers=max_parallel_workers) as executor:
                # Submit tasks to the executor for each table plan
                # Map futures to their corresponding plans for better error reporting
                future_to_plan = {
                    executor.submit(
                        _run_plan_with_pool,
                        plan,
                        pool,
                        s3_client,
                        configuration,
                        state,
                    ): plan
                    for plan in plans
                }

                # Collect errors from failed threads
                errors = []

                # Wait for all tasks to complete, allowing all threads to finish
                for future in as_completed(future_to_plan):
                    plan = future_to_plan[future]
                    try:
                        stream = future.result()
                        log.info(f"{stream}: Sync Finished.")
                    except Exception as e:
                        # Log the error but continue processing other threads
                        log.error(f"{plan.stream}: Error during sync: {e}")
                        errors.append((plan.stream, e))

                # After all threads complete, raise an error if any failed
                if errors:
                    failed_streams = [stream for stream, _ in errors]
                    error_messages = [f"{stream}: {str(e)}" for stream, e in errors]
                    raise RuntimeError(
                        f"Sync failed for {len(errors)} table(s): {', '.join(failed_streams)}. "
                        f"Errors: {'; '.join(error_messages)}"
                    )
        finally:
            # Close all connections in the pool after all tasks are completed
            pool.close_all()
            log.info("All connections in the pool have been closed.")

    log.info("Sync completed successfully.")


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
