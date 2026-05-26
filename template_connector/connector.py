"""ADD ONE LINE DESCRIPTION OF YOUR CONNECTOR HERE.
For example: This connector demonstrates a working starter template that syncs simple user data.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

""" ADD YOUR SOURCE-SPECIFIC IMPORTS HERE
Example: import pandas, boto3, etc.
Add comment for each import to explain its purpose for users to follow.
"""


"""
GUIDELINES TO FOLLOW WHILE WRITING A CONNECTOR:
- Import only the necessary modules and libraries to keep the code clean and efficient.
- Use clear, consistent and descriptive names for your functions and variables.
- For constants and global variables, use uppercase letters with underscores (e.g. CHECKPOINT_INTERVAL, TABLE_NAME).
- Keep constants as private by default, unless they are meant to be used outside the module (e.g. __CHECKPOINT_INTERVAL).
- Add comments to explain the purpose of each function in the docstring.
- Add comments to explain the purpose of complex logic within functions, wherever necessary. Ideally try to split the main logic into smaller functions to avoid too many comments.
- Add comments to highlight where users can make changes to the code to suit their specific use case.
- Split your code into smaller functions to improve readability and maintainability where required.
- Use logging to provide useful information about the connector's execution. Do not log excessively.
- Implement error handling to catch exceptions and log them appropriately. Catch specific exceptions where possible.
- Add retry for API requests to handle transient errors. Use exponential backoff strategy for retries.
- Define the complete data model with primary key and data types in the schema function.
- Ensure that the connector does not load all data into memory at once. This can cause memory overflow errors. Use pagination or streaming where possible.
- Add comments to explain pagination or streaming logic to help users understand how to handle large datasets.
- Add comments for upsert, update and delete to explain the purpose of upsert, update and delete. This will help users understand the upsert, update and delete processes.
- Checkpoint your state at regular intervals to ensure that the connector can resume from the last successful sync in case of interruptions.
- Add comments for checkpointing to explain the purpose of checkpoint. This will help users understand the checkpointing process.
- Refer to the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices)
"""


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    # Validate required configuration parameters
    # No configuration required for this starter connector.
    # When building your own connector, uncomment and modify the example below:
    #
    # required_configs = ["api_key", "base_url"]
    # for key in required_configs:
    #     if key not in configuration:
    #         raise ValueError(f"Missing required configuration value: {key}")
    pass


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
            "table": "users",  # Name of the table in the destination, required.
            "primary_key": [
                "id"
            ],  # Primary key column(s) for the table. We recommend defining a primary_key for each table. If not provided, fivetran computes _fivetran_id from all column values.
            "columns": {  # Definition of columns and their types, optional.
                "id": "STRING",  # Example: defining the id column type. You can define column types when needed.
                # For any columns whose names are not provided here, their data types will be inferred based on the data provided during upsert.
                # We recommend not defining all columns here to allow for schema evolution.
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

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as needed
    # TODO: Extract your configuration parameters here
    # Example: api_key = configuration.get("api_key")

    # Get the state variable for the sync, if needed
    # This is useful for incremental syncs to keep track of the last synced record or timestamp.
    # For example, you might want to track the last updated timestamp to fetch only new or updated records since the last sync.
    # For the first sync, state will be empty JSON object: {}
    # You can modify this logic based on your specific use case.
    # For more information on state management, refer to: https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#workingwithstatejsonfile
    last_updated_at = state.get("last_updated_at")
    new_updated_at = last_updated_at

    try:
        # Fetch data from your source
        # TODO: Replace get_data() with your actual data fetching logic
        data = get_data(last_updated_at)

        if not data:
            log.info("No new data to sync")
            return

        log.info(f"Processing {len(data)} record(s)")

        for record in data:
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="users", data=record)

            # Update state tracking for incremental syncs
            record_updated_at = record.get("updated_at")

            # Update only if record_updated_time is greater than current new_sync_time
            if new_updated_at is None or (
                record_updated_at and record_updated_at > new_updated_at
            ):
                new_updated_at = (
                    record_updated_at  # Assuming the API returns the data in ascending order
                )

        # Update state with the current sync time for the next run
        new_state = {"last_updated_at": new_updated_at}

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(new_state)
        log.info(f"Data synced successfully. Last updated at: {new_updated_at}")

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def get_data(last_sync_time=None):
    """
    This function simulates fetching data from a source.
    In a real-world scenario, this would involve making API calls or database queries.

    TODO: Replace this with your actual data fetching logic.
    - Add pagination if your source supports it
    - Filter by last_sync_time for incremental syncs
    - Add retry logic for API calls
    - Handle rate limiting

    Args:
        last_sync_time: The last sync time to fetch data from (for incremental syncs).
                        None for full syncs.
    Returns:
        A list of dictionaries representing the data to be upserted.
    """
    # Simulate data fetching logic
    # For starter template, return simple user test data
    # In production, replace this with actual API calls or database queries
    return [
        {
            "id": "1",
            "name": "Alice",
            "email": "alice@example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        {
            "id": "2",
            "name": "Bob",
            "email": "bob@example.com",
            "created_at": "2024-01-01T01:00:00Z",
            "updated_at": "2024-01-01T01:00:00Z",
        },
    ]


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
