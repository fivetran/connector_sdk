# This example shows how to call a native C library from a Connector SDK connector using ctypes.
# It bundles a precompiled copy of libm, the C standard math library, as native/libm.so, built
# for Linux x86_64 (the Fivetran Connector SDK hosted production environment), and loads it from
# a fixed path at import time. The same ctypes pattern applies to any other compiled, proprietary,
# or third-party C library you need to bundle. See native_wrapper.py for details.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Thin ctypes wrapper around the bundled libm library (see native_wrapper.py)
import native_wrapper

# Name of the destination table this connector syncs to.
__TABLE_NAME = "calculations"

# Sample source rows. In a real connector, these inputs would come from your API or database;
# here they only illustrate how the native library's result gets upserted alongside the inputs.
__SAMPLE_ROWS = [
    {"id": 1, "base": 2.0, "exponent": 10.0},
    {"id": 2, "base": 3.0, "exponent": 4.0},
    {"id": 3, "base": 5.0, "exponent": 0.5},
]


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
            "table": __TABLE_NAME,
            "primary_key": ["id"],
            "columns": {
                "id": "LONG",
                "base": "DOUBLE",
                "exponent": "DOUBLE",
                "power_result": "DOUBLE",  # Computed by libm's native `pow` function.
                "sqrt_result": "DOUBLE",  # Computed by libm's native `sqrt` function.
            },
        }
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    # This example requires no configuration values; validation is a no-op but kept for consistency
    # with the standard connector structure and to make future configuration additions easy.
    return


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
    log.warning("Example: common_patterns : native_c_library_integration")

    validate_configuration(configuration)

    for row in __SAMPLE_ROWS:
        power_result = native_wrapper.power(row["base"], row["exponent"])
        sqrt_result = native_wrapper.square_root(row["base"])
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(
            table=__TABLE_NAME,
            data={
                "id": row["id"],
                "base": row["base"],
                "exponent": row["exponent"],
                "power_result": power_result,
                "sqrt_result": sqrt_result,
            },
        )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


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
