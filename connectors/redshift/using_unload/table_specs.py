"""
This file contains table specifications and constants for the Redshift UNLOAD connector.
Each table specification includes details such as table name, primary keys,
replication strategy, replication key, and columns to include or exclude.
You can modify the lists to add or change table configurations as needed.
"""

# Preferred timestamp column names for inferring replication keys
# If your tables have any of these column names, they will be prioritized when automatically selecting a replication key
# You can add or modify these names based on your database schema conventions
PREFERRED_TS_COLUMN_NAMES = [
    "updated_at",
    "last_updated",
    "last_update",
    "last_modified",
    "modified_at",
    "modified_on",
    "updated_on",
    "update_time",
    "updated",
]

# Set of Redshift data types that represent timestamps or dates
# These are used to identify potential replication key columns if not explicitly specified
# This is only used when replication_key is not set in table spec and strategy is INCREMENTAL
TIMESTAMP_TYPE_NAMES = {
    "timestamp",
    "timestamp without time zone",
    "timestamp with time zone",
    "timestamptz",
    "date",
}

# Number of rows after which to checkpoint progress
# This ensures that the connector can resume from the last successful sync in case of interruptions
# Adjust this value based on your data volume and performance considerations
CHECKPOINT_EVERY_ROWS = 50000

# Mapping of Redshift data types to Fivetran semantic types
# This is used to properly type columns in the destination schema
REDSHIFT_TO_FIVETRAN_TYPE_MAP = {
    "date": "NAIVE_DATE",
    "timestamp": "NAIVE_DATETIME",
    "timestamp without time zone": "NAIVE_DATETIME",
    "timestamp with time zone": "UTC_DATETIME",
    "timestamptz": "UTC_DATETIME",
    "super": "JSON",
}

# List of table specifications for the Redshift connector
# Each dictionary in the list defines a table and its sync configuration
# You can modify this list to add or change table configurations as needed
# Each table spec includes:
# - name: The name of the table in the format "schema.table"
# - primary_keys: List of primary key columns for the table
# - strategy: Replication strategy, either "FULL" or "INCREMENTAL"
# - replication_key: Column used for incremental replication (if applicable)
# - include: List of columns to include in the sync (empty list means all columns)
# - exclude: List of columns to exclude from the sync (empty list means no exclusions)
TABLE_SPECS = [
    {
        "name": "tickit.users",  # Name of the table from the Redshift database
        "primary_keys": [
            "userid"
        ],  # Primary key column(s) for the table. If None, the connector will fetch the primary key(s) from the source database.
        "strategy": "FULL",  # Replication strategy: FULL or INCREMENTAL
        "replication_key": None,  # Column used for incremental replication. If None, the connector will attempt to infer it for INCREMENTAL sync strategy.
        "include": [],  # List of columns to include in the sync. An empty list means all columns are included.
        "exclude": [],  # List of columns to exclude from the sync. An empty list means no columns are excluded.
    },
    {
        "name": "tickit.category",
        "primary_keys": ["catid"],
        "strategy": "FULL",
        "include": [],
        "exclude": [],
    },
    {
        "name": "tickit.date",
        "primary_keys": ["dateid"],
        "strategy": "INCREMENTAL",
        "replication_key": None,
        "include": [],
        "exclude": [],
    },
    {
        "name": "tickit.event",
        "primary_keys": ["eventid", "venueid"],
        "strategy": "INCREMENTAL",
        "replication_key": None,
        "include": [],
        "exclude": [],
    },
    {
        "name": "tickit.listing",
        "primary_keys": ["sellerid", "listid", "eventid"],
        "strategy": "FULL",
        "replication_key": None,
        "include": [],
        "exclude": [],
    },
    {
        "name": "tickit.sales",
        "primary_keys": ["buyerid", "sellerid", "salesid", "listid"],
        "strategy": "FULL",
        "replication_key": None,
        "include": [],
        "exclude": [],
    },
    {
        "name": "tickit.venue",
        "primary_keys": ["venueid"],
        "strategy": "FULL",
        "replication_key": None,
        "include": [],
        "exclude": [],
    },
]
