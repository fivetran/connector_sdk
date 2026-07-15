# Track Tables Example

This example demonstrates how to track and manage tables to sync using the Fivetran Connector SDK. It shows how to maintain a list of tables in the connector state and handle the addition of new tables over time.

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns/tracking_tables
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Overview

The connector implements a table tracking pattern where:

- It maintains a list of tables to sync in the `TABLES_TO_SYNC` constant
- It stores the list of previously synced tables in the connector state
- It detects new tables that need full historical syncs
- It syncs existing tables incrementally from the last checkpoint

## Key Components

### Configuration

- `initialSyncStart`: The starting timestamp for initial syncs (configured in configuration.json)
- `synced_tables`: Optional comma-separated list of previously synced tables (can be provided in configuration)

### Main Functions

- `update()`: The main sync function that:
  - Retrieves the list of previously synced tables from state or configuration
  - Compares with the current list of tables to sync
  - Syncs each table with appropriate time ranges
  - Checkpoints progress in state

- `sync_tables()`: Handles the syncing of each table, determining whether to:
  - Sync incrementally for previously synced tables
  - Sync full history for newly added tables

- `set_timeranges()`: Calculates the from/to timestamps for each sync

## Usage

### Running the Connector

The connector can be run locally for testing using:

```bash
fivetran debug --configuration configuration.json
```

### Adding New Tables

To observe how adding a new table works:

1. Run the connector with the initial configuration
2. Check `files/state.json` - it will contain `"synced_tables": ["A", "B", "C"]`
3. Add a new table to `TABLES_TO_SYNC` in `connector.py` (e.g., `TABLES_TO_SYNC = ["A", "B", "C", "D"]`)
4. Run the connector again
5. The log output will show `FINE: D is new, needs history from ...`
6. Check `files/state.json` - it will now include the new table
7. The new table will be synced for its full history

## Implementation Details

### State Management

- The connector maintains state using:
  - `to_timestamp`: Tracks the last successful sync point
  - `synced_tables`: List of tables that have been synced
- State is stored in the connector's state object and persisted between syncs

### Table Sync Logic

- New tables are detected by comparing `TABLES_TO_SYNC` with previously synced tables
- New tables are synced from the `initialSyncStart` timestamp
- Existing tables are synced incrementally from their last sync point

## Reference Documentation

For more information, refer to:
- [Fivetran Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
- [Fivetran Best Practices](https://fivetran.com/docs/connector-sdk/best-practices)
