# HubSpot Events API Connector Example

## Connector overview
This connector demonstrates how to sync event analytics data from HubSpot using the Fivetran Connector SDK. It authenticates using an API token, supports incremental syncs via date-based filtering, and creates one destination table per event type. This example specifically syncs `e_visited_page` events.

You can modify it to:
- Sync multiple event types to separate tables.
- Consolidate all event types into a single table.
- Customize fields and event filtering logic.

This connector uses:
- occurredAfter and occurredBefore parameters to define sync windows.
- after (pagination cursor) to iterate through large result sets.

Refer to [HubSpot’s Event Analytics API documentation](https://developers.hubspot.com/docs/reference/api/analytics-and-events/event-analytics) for more information.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/hubspot
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Authenticates to HubSpot using Bearer Token (`api_token`).
- Syncs only one event type (`e_visited_page`), configurable via `EVENT_TYPE_NAMES`.
- Uses date-based windowing with `occurredAfter` and `occurredBefore`.
- Handles pagination using HubSpot's `after` cursor.
- Transforms nested or list data into JSON strings using `flatten_json` and `list_to_json`.


## Configuration file
The connector requires the following configuration parameters:

```json
{
    "api_token": "<your_hubspot_api_token>",
    "initial_sync_start_date": "2025-01-01T00:00:00.000Z"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled via HubSpot Private App token, passed as a Bearer token in the request headers.


## Pagination
Pagination is handled using the `after` cursor returned in HubSpot’s `paging.next.after`.
- The connector loops until no `after` token is returned.
- Pages are requested in batches of 1,000 using `limit`.


## Data handling
- The connector flattens nested `dict` fields and converts any `list` values to JSON strings before sending to Fivetran.
- State is tracked using `start_date` to avoid duplicate syncs.
- The `schema()` method defines a single event table `E_VISITED_PAGE` with `id` as primary key.


## Error handling
- All API responses are checked with `raise_for_status()` to catch errors.
- The connector logs detailed request metadata (URL, params).
- Unrecognized response structures are gracefully handled with fallbacks.


## Tables created
The connector creates a `E_VISITED_PAGE` table:

```json
{
  "table": "e_visited_page",
  "primary_key": ["id"],
  "columns": "inferred"
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.