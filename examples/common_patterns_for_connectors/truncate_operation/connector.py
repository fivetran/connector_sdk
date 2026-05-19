"""Using Truncate example for Fivetran Connector SDK.
This example demonstrates the truncate operation combined with upsert(), update(), and delete()
on a single table, showing how each operation affects the destination.
truncate() soft-deletes all rows that exist in the destination before the call (_fivetran_deleted = true).
Rows upserted after truncate() in the same sync are not affected.

See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details.
"""

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Simulated product catalog - initial batch loaded into the destination.
__INITIAL_CATALOG = [
    {
        "product_id": 1,
        "name": "Laptop",
        "category": "Electronics",
        "price": 999.99,
        "in_stock": True,
    },
    {
        "product_id": 2,
        "name": "Wireless Mouse",
        "category": "Electronics",
        "price": 29.99,
        "in_stock": True,
    },
    {
        "product_id": 3,
        "name": "Desk Chair",
        "category": "Furniture",
        "price": 349.99,
        "in_stock": False,
    },
]

# Replacement catalog loaded after truncate.
__NEW_CATALOG = [
    {
        "product_id": 4,
        "name": "Mechanical Keyboard",
        "category": "Electronics",
        "price": 129.99,
        "in_stock": True,
    },
    {
        "product_id": 5,
        "name": "Standing Desk",
        "category": "Furniture",
        "price": 599.99,
        "in_stock": True,
    },
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
            "table": "products",
            "primary_key": ["product_id"],
            "columns": {
                "product_id": "INT",
                "name": "STRING",
                "category": "STRING",
                "price": "FLOAT",
                "in_stock": "BOOLEAN",
            },
        }
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
    log.warning("Example: Common Patterns For Connectors - Using Truncate")

    # Stage 1: Upsert initial product catalog.
    # All 3 rows land as active rows (_fivetran_deleted = false).
    log.info("Stage 1: upserting initial product catalog")
    for product in __INITIAL_CATALOG:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="products", data=product)
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)

    # Destination after Stage 1 — upsert (initial load):
    # ┌────────────┬────────────────┬─────────────┬────────┬──────────┬───────────────────┐
    # │ product_id │      name      │  category   │ price  │ in_stock │ _fivetran_deleted │
    # ├────────────┼────────────────┼─────────────┼────────┼──────────┼───────────────────┤
    # │          1 │ Laptop         │ Electronics │ 999.99 │ true     │ false             │
    # │          2 │ Wireless Mouse │ Electronics │  29.99 │ true     │ false             │
    # │          3 │ Desk Chair     │ Furniture   │ 349.99 │ false    │ false             │
    # └────────────┴────────────────┴─────────────┴────────┴──────────┴───────────────────┘

    # Stage 2: Patch a single column on an existing row.
    # op.update() modifies only the supplied columns; all other columns are unchanged.
    log.info("Stage 2: updating Laptop price")
    op.update(table="products", modified={"product_id": 1, "price": 799.99})
    # Checkpoint flushes the update to the destination.
    op.checkpoint(state)

    # Destination after Stage 2 — update (Laptop price patched):
    # ┌────────────┬────────────────┬─────────────┬────────┬──────────┬───────────────────┐
    # │ product_id │      name      │  category   │ price  │ in_stock │ _fivetran_deleted │
    # ├────────────┼────────────────┼─────────────┼────────┼──────────┼───────────────────┤
    # │          1 │ Laptop         │ Electronics │ 799.99 │ true     │ false             │  <- price updated
    # │          2 │ Wireless Mouse │ Electronics │  29.99 │ true     │ false             │
    # │          3 │ Desk Chair     │ Furniture   │ 349.99 │ false    │ false             │
    # └────────────┴────────────────┴─────────────┴────────┴──────────┴───────────────────┘

    # Stage 3: Truncate the table.
    # Marks ALL rows that exist in the destination up to this point as soft-deleted
    # (_fivetran_deleted = true). Rows inserted after this call in the same sync are NOT affected.
    log.info("Stage 3: truncating products table")
    # The 'truncate' operation soft-deletes all rows currently in the destination table.
    # The first argument is the name of the destination table.
    # Rows upserted after this call in the same sync are not affected.
    op.truncate(table="products")
    # Checkpoint flushes the truncate to the destination.
    op.checkpoint(state)

    # Destination after Stage 3 — truncate (all existing rows soft-deleted):
    # ┌────────────┬────────────────┬─────────────┬────────┬──────────┬───────────────────┐
    # │ product_id │      name      │  category   │ price  │ in_stock │ _fivetran_deleted │
    # ├────────────┼────────────────┼─────────────┼────────┼──────────┼───────────────────┤
    # │          1 │ Laptop         │ Electronics │ 799.99 │ true     │ true              │  <- soft-deleted
    # │          2 │ Wireless Mouse │ Electronics │  29.99 │ true     │ true              │  <- soft-deleted
    # │          3 │ Desk Chair     │ Furniture   │ 349.99 │ false    │ true              │  <- soft-deleted
    # └────────────┴────────────────┴─────────────┴────────┴──────────┴───────────────────┘

    # Stage 4: Upsert new catalog rows after truncate.
    # These rows are emitted after op.truncate(), so they are not soft-deleted.
    log.info("Stage 4: upserting new catalog after truncate")
    for product in __NEW_CATALOG:
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="products", data=product)
    # Checkpoint flushes the new rows to the destination.
    op.checkpoint(state)

    # Destination after Stage 4 — upsert (new catalog added post-truncate, not soft-deleted):
    # ┌────────────┬─────────────────────┬─────────────┬────────┬──────────┬───────────────────┐
    # │ product_id │        name         │  category   │ price  │ in_stock │ _fivetran_deleted │
    # ├────────────┼─────────────────────┼─────────────┼────────┼──────────┼───────────────────┤
    # │          1 │ Laptop              │ Electronics │ 799.99 │ true     │ true              │
    # │          2 │ Wireless Mouse      │ Electronics │  29.99 │ true     │ true              │
    # │          3 │ Desk Chair          │ Furniture   │ 349.99 │ false    │ true              │
    # │          4 │ Mechanical Keyboard │ Electronics │ 129.99 │ true     │ false             │  <- new, not deleted
    # │          5 │ Standing Desk       │ Furniture   │ 599.99 │ true     │ false             │  <- new, not deleted
    # └────────────┴─────────────────────┴─────────────┴────────┴──────────┴───────────────────┘

    # Stage 5: Revive a truncated row by upserting it again.
    # Upserting a previously soft-deleted row sets _fivetran_deleted = false and applies new values.
    log.info("Stage 5: reviving Laptop with updated details")
    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(
        table="products",
        data={
            "product_id": 1,
            "name": "Laptop Pro",
            "category": "Electronics",
            "price": 1249.99,
            "in_stock": True,
        },
    )
    # Checkpoint flushes the revived row to the destination.
    op.checkpoint(state)

    # Destination after Stage 5 — upsert on previously truncated PK (row revived with new values):
    # ┌────────────┬─────────────────────┬─────────────┬─────────┬──────────┬───────────────────┐
    # │ product_id │        name         │  category   │  price  │ in_stock │ _fivetran_deleted │
    # ├────────────┼─────────────────────┼─────────────┼─────────┼──────────┼───────────────────┤
    # │          1 │ Laptop Pro          │ Electronics │ 1249.99 │ true     │ false             │  <- revived + updated
    # │          2 │ Wireless Mouse      │ Electronics │   29.99 │ true     │ true              │
    # │          3 │ Desk Chair          │ Furniture   │  349.99 │ false    │ true              │
    # │          4 │ Mechanical Keyboard │ Electronics │  129.99 │ true     │ false             │
    # │          5 │ Standing Desk       │ Furniture   │  599.99 │ true     │ false             │
    # └────────────┴─────────────────────┴─────────────┴─────────┴──────────┴───────────────────┘

    # Stage 6: Delete a specific row by primary key.
    # op.delete() soft-deletes a single row identified by its primary key. This is different from
    # op.truncate(), which soft-deletes ALL rows in the table at the time of the call.
    # Use op.delete() when you know exactly which row to remove; use op.truncate() for a full reset.
    log.info("Stage 6: deleting Standing Desk by primary key")
    # The 'delete' operation soft-deletes a single row by its primary key.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the primary key column(s) identifying the row.
    op.delete(table="products", keys={"product_id": 5})
    # Checkpoint flushes the delete to the destination.
    op.checkpoint(state)

    # Destination after Stage 6 — delete (Standing Desk soft-deleted by primary key):
    # ┌────────────┬─────────────────────┬─────────────┬─────────┬──────────┬───────────────────┐
    # │ product_id │        name         │  category   │  price  │ in_stock │ _fivetran_deleted │
    # ├────────────┼─────────────────────┼─────────────┼─────────┼──────────┼───────────────────┤
    # │          1 │ Laptop Pro          │ Electronics │ 1249.99 │ true     │ false             │
    # │          2 │ Wireless Mouse      │ Electronics │   29.99 │ true     │ true              │
    # │          3 │ Desk Chair          │ Furniture   │  349.99 │ false    │ true              │
    # │          4 │ Mechanical Keyboard │ Electronics │  129.99 │ true     │ false             │
    # │          5 │ Standing Desk       │ Furniture   │  599.99 │ true     │ true              │  <- soft-deleted by delete()
    # └────────────┴─────────────────────┴─────────────┴─────────┴──────────┴───────────────────┘


# Create the connector object using the schema and update functions.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    connector.debug()
