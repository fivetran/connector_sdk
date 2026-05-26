"""This connector demonstrates how to fetch employee data from Supabase and upsert it into destination using the Supabase Python SDK.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Import the Supabase Python SDK for connecting to Supabase database
# The supabase-py library contains:
#   create_client: Factory function to create a Supabase client instance for database operations
#   Client: The main Supabase client class that provides methods for database queries, authentication, and real-time subscriptions
#   ClientOptions: Configuration class for customizing client behavior including timeouts, schema selection, and connection settings
from supabase import create_client, Client
from supabase.client import ClientOptions

# Constants for the connector
__CHECKPOINT_INTERVAL = 1000  # Checkpoint after processing every 1000 rows
__BATCH_SIZE = 1000  # Batch size for range queries, default Supabase's limit


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
    required_configs = ["supabase_url", "supabase_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # Get table name from configuration or use default
    table_name = configuration.get("table_name", "employee")

    return [
        {
            "table": table_name,  # Name of the table in the destination, required.
            "primary_key": ["id"],  # Primary key column(s) for the table, optional.
            "columns": {  # Definition of columns and their types, optional.
                "id": "INT",  # Contains a dictionary of column names and data types (int8 maps to INT)
            },  # For any columns whose names are not provided here, e.g. id, their data types will be inferred
        },
    ]


def create_supabase_client(configuration: dict):
    """
    Create a Supabase client using the provided configuration.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Client: A Supabase client instance.
    """
    supabase_url = configuration.get("supabase_url")
    supabase_key = configuration.get("supabase_key")
    schema_name = configuration.get("schema_name", "public")

    try:
        # Create Supabase client with schema configuration
        supabase_client: Client = create_client(
            supabase_url,
            supabase_key,
            options=ClientOptions(
                postgrest_client_timeout=10,
                storage_client_timeout=10,
                schema=schema_name,
            ),
        )
        log.info(f"Successfully created Supabase client for schema: {schema_name}")
        return supabase_client
    except Exception as e:
        log.error("Failed to create Supabase client", e)
        raise RuntimeError(f"Failed to create Supabase client: {str(e)}")


def fetch_employee_data_batch(
    supabase_client: Client,
    table_name: str,
    last_hire_date: str,
    offset: int = 0,
    limit: int = __BATCH_SIZE,
):
    """
    Fetch a batch of employee data from Supabase table where hire_date is greater than the last sync time.
    Uses range() method for pagination to handle Supabase's record limits efficiently.
    Data is explicitly ordered by hire_date to ensure consistent incremental sync.
    Args:
        supabase_client: The Supabase client instance.
        table_name: The name of the table to fetch data from.
        last_hire_date: The last hire date from the previous sync.
        offset: Starting position for the batch (0-based index).
        limit: Number of records to fetch in this batch.
    Returns:
        A tuple containing (list of employee records sorted by hire_date, has_more_data boolean).
    """
    try:
        # Calculate end position for range (Supabase range is inclusive)
        end_position = offset + limit - 1

        # Query employees with hire_date greater than last_hire_date using range for pagination
        # This ensures we process records in chronological order for proper checkpointing
        response = (
            supabase_client.table(table_name)
            .select("*")
            .gt("hire_date", last_hire_date)
            .order("hire_date", desc=False)  # Explicitly sort by hire_date ascending
            .range(offset, end_position)  # Use range for batch processing
            .execute()
        )

        if response.data:
            log.info(
                f"Fetched batch: {len(response.data)} records from table: {table_name}, "
                f"offset: {offset}, range: [{offset}, {end_position}], sorted by hire_date"
            )

            # Check if there might be more data
            # If we got exactly the limit, there might be more data
            has_more_data = len(response.data) == limit

            return response.data, has_more_data
        else:
            log.info(f"No new records found in table: {table_name} at offset: {offset}")
            return [], False

    except Exception as e:
        log.error(f"Failed to fetch batch from table {table_name} at offset {offset}", e)
        raise RuntimeError(
            f"Failed to fetch batch from table {table_name} at offset {offset}: {str(e)}"
        )


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

    log.warning("Example: Source Examples: Supabase Employee Sync")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Create Supabase client
    supabase_client = create_supabase_client(configuration)

    # Get configuration parameters
    table_name = configuration.get("table_name", "employee")
    batch_size = int(configuration.get("batch_size", __BATCH_SIZE))

    # Get the state variable for the sync, if needed
    last_hire_date = state.get("last_hire_date", "1990-01-01")
    new_hire_date = last_hire_date

    try:

        row_count = 0
        batch_count = 0
        offset = 0
        has_more_data = True

        log.info(f"Starting batch processing with batch size: {batch_size}")

        # Process data in batches using range-based pagination
        while has_more_data:
            batch_count += 1
            log.info(f"Processing batch {batch_count}, offset: {offset}")

            # Fetch employee data batch from Supabase
            employee_batch, has_more_data = fetch_employee_data_batch(
                supabase_client, table_name, last_hire_date, offset, batch_size
            )

            if not employee_batch:
                log.info("No more records to process")
                break

            # Process each record in the current batch
            batch_row_count = 0
            for record in employee_batch:
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted,
                op.upsert(table=table_name, data=record)
                row_count += 1
                batch_row_count += 1

                record_hire_date = record.get("hire_date")

                # Update new_hire_date with the current record's hire_date since data is sorted
                # This ensures we always have the latest processed hire_date for checkpointing
                if record_hire_date:
                    new_hire_date = record_hire_date

                if row_count % __CHECKPOINT_INTERVAL == 0:
                    save_state(new_hire_date)

            log.info(
                f"Completed batch {batch_count}: processed {batch_row_count} records, "
                f"total processed: {row_count}, last hire_date: {new_hire_date}"
            )

            # Update offset for next batch - increment by batch size for range-based pagination
            offset += batch_size

        # Final checkpoint
        save_state(new_hire_date)

        log.info(f"Successfully synced {row_count} employee records across {batch_count} batches")

    except Exception as e:
        # In case of an exception, raise a runtime error
        raise RuntimeError(f"Failed to sync data: {str(e)}")


def save_state(new_hire_date):
    new_state = {"last_hire_date": new_hire_date}
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(new_state)


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
