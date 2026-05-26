# Toast Connector Example

## Connector overview

This connector extracts and syncs data from the [Toast POS API](https://doc.toasttab.com/) into a destination warehouse. Toast is a restaurant management platform providing point-of-sale, labor, menu, and operational data.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/toast
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Syncs data from multiple Toast endpoints, including orders, employees, shifts, menus, and more
- Automatically handles nested JSON structures and normalizes them into relational tables
- Includes incremental sync via time-based windowing and state checkpointing
- Graceful handling of rate limits, authentication, and API errors
- Supports voids, deletions, and nested child entities
- Uses Fernet encryption for token security in state

## Configuration file

```json
{
  "clientId": "<YOUR_CLIENT_ID>",
  "clientSecret": "<YOUR_CLIENT_SECRET>",
  "userAccessType": "<TOAST_MACHINE_CLIENT>",
  "domain": "<YOUR_DOMAIN>",
  "initialSyncStart": "<ISO_FORMAT_TIMESTAMP>",
  "key": "<BASE_64_ENCODED_FERNET_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The connector generates and caches a Toast access token using the `clientId`, `clientSecret`, and `userAccessType` credentials. The token is encrypted using the provided Fernet `key` and stored in state for reuse across syncs. For more information on Fernet encryption, see the [Fernet documentation](https://cryptography.io/en/latest/fernet/). Refer to `make_headers(configuration, base_url, state, key)`.

## Pagination

The connector syncs data in 30-day time windows, iterating from `initialSyncStart` to the current sync time. State is checkpointed after each window to allow resumption in case of interruption. Refer to `sync_items(base_url, headers, ts_from, ts_to, start_timestamp, state)` and `set_timeranges(state, configuration, start_timestamp)`.

## Data handling

- The connector flattens nested JSON objects and serializes list fields using `flatten_dict(parent_row, dict_field, prefix)`, `extract_fields(fields, row)`, and `stringify_lists(d)`.
- Records are written to the destination using `op.upsert()`, and deleted records are emitted using `op.delete()`. 
- State is updated after each 30-day window to enable incremental sync. Refer to `sync_items(base_url, headers, ts_from, ts_to, start_timestamp, state)`.
- Checkpointing: Updates state after each window to resume seamlessly


## Error handling

- 401 Unauthorized – Retries up to three times before logging an error and skipping the endpoint.
- 403 Forbidden – Skips the endpoint.
- 429 Too Many Requests – Backs off on rate limit response before retrying.
- 400 and 409 errors – Skips with logging.

## Tables created

The entity-relationship diagram (ERD) below shows how tables are linked in the Toast schema.

 <img src="https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/connectors/toast/Toast_ERD.png" alt="Fivetran Toast Connector ERD" width="100%">

### Core tables
- `restaurant`
- `job`, `employee`, `shift`, `break`, `time_entry`
- `orders`, `orders_check`, `payment`

### Configuration
- `menu`, `menu_item`, `menu_group`, `discounts`, `tables`, etc.

### Nested children
- `orders_check_payment`, `orders_check_selection`, `orders_check_selection_modifier`, etc.

### Cash management
- `cash_entry`, `cash_deposit`

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
