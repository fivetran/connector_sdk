"""
This is an example of a Fivetran Connector SDK implementation that simulates various error scenarios
to demonstrate how to handle errors gracefully and follow best practices.
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

import time  # For time-related operations
import random  # For generating random data


def handle_critical_error(error_message, error_details=None):
    """
    Handle critical errors by logging them as error and stopping Connector SDK execution.
    Args:
        error_message (str): The main error message to log.
        error_details (str, optional): Additional details about the error, if available.
    """
    log.error(f"CRITICAL ERROR: {error_message}")
    if error_details:
        log.error(f"Error details: {error_details}")
    raise Exception(f"CRITICAL ERROR: {error_message}")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    return [{"table": "demo_response_test", "primary_key": ["key"]}]


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
    if "error_simulation_type" not in configuration:
        raise ValueError("Missing required configuration value: 'error_simulation_type'}")


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    """
    log.warning("Example: Common Patterns for Connectors - Error Simulation Example")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Get error simulation type from configuration
    error_simulation_type = str(configuration.get("error_simulation_type", "0"))
    log.info(f"Error simulation type: {error_simulation_type}")

    if error_simulation_type == "0":
        log.info("Running in normal mode - no error simulation")

    # If error_simulation_type is not "0", we will simulate various errors to demonstrate error handling
    start = time.time()

    # Handle configuration section and extract demo_config
    # If error_simulation_type is "1", we will simulate a missing configuration error.
    demo_config = handle_configuration_section(
        configuration=configuration, error_simulation_type=error_simulation_type
    )

    # Handle state section to manage the current state of the connector
    # If error_simulation_type is "2", we will simulate an invalid state format error
    handle_state_section(state=state, error_simulation_type=error_simulation_type)

    # Generate simulated data based on the demo_config
    # If error_simulation_type is "3", we will simulate a data generation error.
    simulated_data = handle_data_generation(
        demo_config=demo_config, error_simulation_type=error_simulation_type
    )

    # Process the generated data and prepare new state
    # If error_simulation_type is "4", we will simulate a data processing error.
    processed_data, new_state = handle_data_processing(
        start=start,
        demo_config=demo_config,
        simulated_data=simulated_data,
        error_simulation_type=error_simulation_type,
    )

    # Upsert processed data to the destination
    # If error_simulation_type is "5", we will simulate a database operation error.
    handle_data_upsertion(
        processed_data=processed_data, error_simulation_type=error_simulation_type
    )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(new_state)


def handle_configuration_section(configuration: dict, error_simulation_type: str):
    """Handle configuration validation and extraction"""
    try:
        # ERROR SIMULATION 1: Missing Configuration
        if error_simulation_type == "1":
            log.info("Simulating missing configuration error")
            log.info("BEST PRACTICE: Always validate required configuration parameters early")
            raise KeyError("demo_config missing from configuration")

        demo_config = configuration.get("demo_config", "default")
        log.info(f"Demo configuration: {demo_config}")
        return demo_config
    except KeyError as e:
        handle_critical_error("Missing required configuration", str(e))
    except Exception as e:
        handle_critical_error("Unexpected error during configuration validation", str(e))


def handle_state_section(state: dict, error_simulation_type: str):
    """Handle state management"""
    # Get current cursor from state
    current_cursor = state.get("cursor", None)
    log.info(f"Current cursor: {current_cursor}")

    # ERROR SIMULATION 2: Invalid State Format
    if error_simulation_type == "2":
        log.info("Simulating invalid state format error")
        log.info("BEST PRACTICE: Validate state format before using it")
        handle_critical_error("Invalid state format detected")


def handle_data_generation(demo_config: str, error_simulation_type: str):
    """Generate simulated data based on configuration"""
    try:
        log.info("Generating simulated data")

        # ERROR SIMULATION 3: Data Generation Error
        if error_simulation_type == "3":
            log.info("Simulating data generation error")
            log.info("BEST PRACTICE: Handle errors during data generation")
            handle_critical_error("Failed to generate data", "Simulated data generation error")

        # Simulate data generation
        simulated_data = {
            "response": f"Simulated response for config: {demo_config}",
            "timestamp": time.time(),
            "random_value": random.randint(1, 100),
        }
        log.info("Successfully generated simulated data")
        return simulated_data
    except Exception as e:
        handle_critical_error("Error during data generation", str(e))


def handle_data_processing(
    start: float, demo_config: str, simulated_data: dict, error_simulation_type: str
):
    """Process the generated data and prepare new state"""
    try:
        # Process the simulated data
        processed_data = {
            "key": start,
            "request": demo_config,
            "result": simulated_data["response"],
            "metadata": json.dumps(
                {
                    "timestamp": simulated_data["timestamp"],
                    "random_value": simulated_data["random_value"],
                }
            ),
        }
        # ERROR SIMULATION 4: Processing Error
        if error_simulation_type == "4":
            log.info("Simulating data processing error")
            log.info("BEST PRACTICE: Validate data before processing")
            handle_critical_error("Data processing error", "Simulated error during processing")

        log.info(f'Processed data: {processed_data["result"][:30]}...')

        # Create new state
        new_cursor = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        new_state = {"cursor": new_cursor}
        log.info(f"Generated new cursor: {new_cursor}")

        return processed_data, new_state
    except Exception as e:
        handle_critical_error("Error processing data", str(e))


def handle_data_upsertion(processed_data: dict, error_simulation_type: str):
    """Upsert processed data to the destination"""
    try:
        # ERROR SIMULATION 5: Database Operation Error
        if error_simulation_type == "5":
            log.info("Simulating database operation error")
            log.info("BEST PRACTICE: Handle database operation errors gracefully")
            handle_critical_error("Database operation failed", "Simulated database error")
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="demo_response_test", data=processed_data)
        log.info("Data successfully upserted to target database")
    except Exception as e:
        handle_critical_error("Error during upsert operation", str(e))


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
