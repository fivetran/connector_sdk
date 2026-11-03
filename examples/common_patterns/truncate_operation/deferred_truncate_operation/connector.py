"""Using Deferred Truncate example for Fivetran Connector SDK.
This example compares a regular truncate() with a deferred truncate (truncate(..., deferred=True)) on two identical tables.
A regular truncate() soft-deletes the existing rows at the next checkpoint, before the replacement rows have arrived.
A deferred truncate soft-deletes the existing rows only after update() returns successfully.

See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details.
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete(), truncate() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Table that uses a regular truncate: existing rows are soft-deleted at the next checkpoint.
__IMMEDIATE_TABLE = "products_immediate_truncate"

# Table that uses a deferred truncate: existing rows are soft-deleted after update() returns.
__DEFERRED_TABLE = "products_deferred_truncate"

# Both tables receive the same data so that the only difference is the type of truncate.
__TABLES = [__IMMEDIATE_TABLE, __DEFERRED_TABLE]

# Simulated rows already present in the destination from a previous sync.
__OLD_CATALOG = [
    {"product_id": 1, "name": "Laptop", "price": 999.99},
    {"product_id": 2, "name": "Wireless Mouse", "price": 29.99},
    {"product_id": 3, "name": "Desk Chair", "price": 349.99},
]

# Simulated replacement rows delivered by the current full refresh.
__NEW_CATALOG = [
    {"product_id": 4, "name": "Mechanical Keyboard", "price": 129.99},
    {"product_id": 5, "name": "Standing Desk", "price": 599.99},
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
        {"table": __IMMEDIATE_TABLE, "primary_key": ["product_id"]},
        {"table": __DEFERRED_TABLE, "primary_key": ["product_id"]},
    ]


def upsert_products(table: str, products: list):
    """
    Upsert a list of products into the given table.
    Args:
        table: the name of the destination table.
        products: a list of product dictionaries to upsert.
    """
    for product in products:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table, data=product)


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
    log.warning("Example: Common Patterns For Connectors - Using Deferred Truncate")

    # Stage 1: Load the old catalog into both tables, simulating rows from a previous sync.
    log.info("Stage 1: loading the old catalog into both tables")
    for table in __TABLES:
        upsert_products(table=table, products=__OLD_CATALOG)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)

    # Destination after Stage 1 (identical for both tables):
    # ┌────────────┬────────────────┬─────────┬───────────────────┐
    # │ product_id │      name      │  price  │ _fivetran_deleted │
    # ├────────────┼────────────────┼─────────┼───────────────────┤
    # │          1 │ Laptop         │  999.99 │ false             │
    # │          2 │ Wireless Mouse │   29.99 │ false             │
    # │          3 │ Desk Chair     │  349.99 │ false             │
    # └────────────┴────────────────┴─────────┴───────────────────┘

    # Stage 2: Start a full refresh by truncating both tables.
    log.info("Stage 2: truncating both tables")
    # A regular truncate soft-deletes all existing rows at the next checkpoint.
    op.truncate(table=__IMMEDIATE_TABLE)
    # A deferred truncate captures the truncate timestamp now, but soft-deletes the rows that existed before
    # that timestamp only after update() returns successfully. Rows upserted after this call are never affected.
    # Calling it again for the same table in the same sync replaces the earlier call with the latest timestamp.
    op.truncate(table=__DEFERRED_TABLE, deferred=True)
    # Checkpoint applies the regular truncate. The deferred truncate is not applied yet.
    op.checkpoint(state)

    # Destination after Stage 2 - the replacement rows have not arrived yet:
    # products_immediate_truncate: old rows are already soft-deleted
    # ┌────────────┬────────────────┬─────────┬───────────────────┐
    # │ product_id │      name      │  price  │ _fivetran_deleted │
    # ├────────────┼────────────────┼─────────┼───────────────────┤
    # │          1 │ Laptop         │  999.99 │ true              │
    # │          2 │ Wireless Mouse │   29.99 │ true              │
    # │          3 │ Desk Chair     │  349.99 │ true              │
    # └────────────┴────────────────┴─────────┴───────────────────┘
    # products_deferred_truncate: old rows are still active
    # ┌────────────┬────────────────┬─────────┬───────────────────┐
    # │ product_id │      name      │  price  │ _fivetran_deleted │
    # ├────────────┼────────────────┼─────────┼───────────────────┤
    # │          1 │ Laptop         │  999.99 │ false             │
    # │          2 │ Wireless Mouse │   29.99 │ false             │
    # │          3 │ Desk Chair     │  349.99 │ false             │
    # └────────────┴────────────────┴─────────┴───────────────────┘

    # Stage 3: Load the replacement rows into both tables.
    log.info("Stage 3: loading the replacement catalog into both tables")
    for table in __TABLES:
        upsert_products(table=table, products=__NEW_CATALOG)
    # Checkpoint saves the new rows. The deferred truncate is still pending.
    op.checkpoint(state)

    # Destination after Stage 3:
    # products_immediate_truncate: only the new rows are active.
    # ┌────────────┬─────────────────────┬─────────┬───────────────────┐
    # │ product_id │        name         │  price  │ _fivetran_deleted │
    # ├────────────┼─────────────────────┼─────────┼───────────────────┤
    # │          1 │ Laptop              │  999.99 │ true              │
    # │          2 │ Wireless Mouse      │   29.99 │ true              │
    # │          3 │ Desk Chair          │  349.99 │ true              │
    # │          4 │ Mechanical Keyboard │  129.99 │ false             │
    # │          5 │ Standing Desk       │  599.99 │ false             │
    # └────────────┴─────────────────────┴─────────┴───────────────────┘
    # products_deferred_truncate: old and new rows are both active.
    # ┌────────────┬─────────────────────┬─────────┬───────────────────┐
    # │ product_id │        name         │  price  │ _fivetran_deleted │
    # ├────────────┼─────────────────────┼─────────┼───────────────────┤
    # │          1 │ Laptop              │  999.99 │ false             │
    # │          2 │ Wireless Mouse      │   29.99 │ false             │
    # │          3 │ Desk Chair          │  349.99 │ false             │
    # │          4 │ Mechanical Keyboard │  129.99 │ false             │
    # │          5 │ Standing Desk       │  599.99 │ false             │
    # └────────────┴─────────────────────┴─────────┴───────────────────┘

    # update() returns here. The SDK now applies the deferred truncate and commits it with a final checkpoint.
    # If update() had raised an error before returning, the deferred truncate would not have been applied.
    #
    # Final destination for products_deferred_truncate, identical to products_immediate_truncate:
    # ┌────────────┬─────────────────────┬─────────┬───────────────────┐
    # │ product_id │        name         │  price  │ _fivetran_deleted │
    # ├────────────┼─────────────────────┼─────────┼───────────────────┤
    # │          1 │ Laptop              │  999.99 │ true              │  <- soft-deleted when update() returned
    # │          2 │ Wireless Mouse      │   29.99 │ true              │  <- soft-deleted when update() returned
    # │          3 │ Desk Chair          │  349.99 │ true              │  <- soft-deleted when update() returned
    # │          4 │ Mechanical Keyboard │  129.99 │ false             │
    # │          5 │ Standing Desk       │  599.99 │ false             │
    # └────────────┴─────────────────────┴─────────┴───────────────────┘


# Create the connector object using the schema and update functions.
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
