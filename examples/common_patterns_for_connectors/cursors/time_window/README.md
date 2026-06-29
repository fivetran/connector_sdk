# Time Window Cursor Example

## Connector overview

This connector demonstrates how to implement cursor-based pagination using time windows with the Fivetran Connector SDK. It shows how to handle large datasets by breaking them into smaller time-based chunks during the initial sync, which is particularly useful for APIs that support date range queries.

The connector implements a cursor-forward pattern that tracks the last synced timestamp in the state and processes data in configurable time windows. For initial syncs, it starts from a configured date and limits each sync chunk to a specified number of days, continuing forward until reaching the current time.

## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns_for_connectors/cursors/time_window
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features

* **Time-based cursor pagination**: Implements cursor-forward pattern using timestamps
* **Configurable time windows**: Limits each sync chunk to a specified number of days (default: 30 days)
* **State management**: Tracks sync progress using checkpointing
* **Initial sync handling**: Starts from a configured date for first-time syncs
* **Timezone awareness**: Handles UTC timestamps with proper ISO formatting
* **Incremental syncs**: Resumes from the last synced timestamp for subsequent syncs

## Configuration file

This example does not require external configuration as it uses hardcoded constants.

## Requirements file

This example does not require additional dependencies beyond the Fivetran Connector SDK, as it only uses Python's built-in datetime module.

## Authentication

This example does not implement authentication as it uses hard-coded values only.

## Pagination

This connector does not implement traditional pagination (such as page-based or offset-based pagination). Instead, it uses time-based chunking to process data in configurable time windows, as described in the Connector overview section.

## Data handling

**Refer to the `update()` function:**

The connector insert/update timestamp data to demonstrate the time window concept. 

**Refer to the `is_older_than_n_days()` function:**

The connector includes utility functions for timestamp handling:
- Timezone-aware date comparisons
- ISO timestamp parsing and formatting
- Automatic string-to-datetime conversion

## Error handling

This example includes basic error handling through the Fivetran Connector SDK's built-in logging system. The connector uses:

- **Warning logs**: For sync start notifications
- **Fine logs**: For detailed debugging information (only visible during debug mode)
- **State checkpointing**: Ensures sync progress is preserved even if errors occur

## Tables Created

The connector creates a single demonstration table:

**timestamps** - Contains messages showing the time ranges processed during each sync chunk

*Example data:*
```
message: "from 2024-06-01T00:00:00.000Z to 2024-07-01T00:00:00.000Z"
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

### Key constants

- `__INITIAL_SYNC_START`: Starting timestamp for initial syncs (2024-06-01T00:00:00.000Z)
- `__DAYS_PER_SYNC`: Maximum days per sync chunk (30)

### Testing

You can test this connector locally using:

```bash
fivetran debug
```

This will run the connector in debug mode, showing detailed logs and processing the time windows as configured. 