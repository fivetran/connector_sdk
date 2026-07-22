# Data Handling Patterns Connector Example
## Connector overview

This example demonstrates three common techniques for handling nested data structures returned by an API source. A single API call fetches all user records, and each of the three sync functions applies a different data handling pattern to the same response:

- Flatten into columns – when the source returns a single nested object alongside top-level fields, its fields are promoted to individual columns on the parent table.
- Break out into child tables – when the source returns a list of nested objects inside a parent record, each list item is written to a separate child table.
- Write as a JSON blob – when the source returns nested structures that may vary between records, the entire structure is stored as a single JSON column.


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
fivetran init <project-path> --template examples/common_patterns/data_handling_patterns
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features

- Demonstrates three distinct data handling patterns for nested API responses in a single connector.
- Flattens all nested structures into a single flat table – refer to `sync_flattened()`.
- Splits a nested orders list into a parent table and a child table with a composite primary key – refer to `sync_parent_child()`.
- Stores the nested orders as a JSON blob column – refer to `sync_json_blob()`.
- Uses a mock API to simulate source data with randomized values and a fixed schema, enabling local testing without credentials or configuration.
- Checkpoints state after every table sync and at a configurable interval (`__CHECKPOINT_INTERVAL`) to support safe resumption after interruptions.

## Configuration file
This example does not require a configuration file.

In production, a `configuration.json` might contain API tokens, initial cursors, or filters to narrow down API results.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The `requirements.txt` file lists the Python libraries required by the connector. 
This example uses the `faker` library in `mock_api.py` to randomize the values in the simulated source data during local testing.

```
faker==40.5.1
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication

This example does not use any authentication. It connects to a mock API (`mock_api.py`) that generates synthetic data locally. When building your own connector, replace the mock API calls with authenticated requests to your real data source.


## Pagination

This example does not implement pagination. The mock API returns all records in a single response. When building your own connector, add pagination if your source returns results across multiple pages. Refer to the [pagination examples](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/pagination) for common patterns such as offset-based, page-number, keyset, and next-page-URL pagination.


## Data handling

A single call to `get_users()` in `mock_api.py` returns a list of user records, each containing all nested structures. The three sync functions in `connector.py` each process this same list and apply a different pattern.

Source shape returned by `get_users()`:
```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Alice",
  "orders": [
    {"order_id": "ORD-1", "amount": 20.5},
    {"order_id": "ORD-2", "amount": 35.0}
  ]
}
```

### Flatten into columns

When the source returns a single nested object alongside top-level fields, each field in the nested object can be promoted to a top-level column on the parent table. 
Destination — `users_flattened` (composite primary key: `user_id` + `order_id`):

| user_id | name  | order_id | amount |
|---------|-------|----------|--------|
| 1       | Alice | ORD-1    | 20.5   |
| 1       | Alice | ORD-2    | 35.0   |

Refer to `sync_flattened()`.

### Break out into child tables

The nested orders list is split into a parent table and a child table. All non-nested fields are written to the parent `users` table. Each order becomes its own row in the child `orders` table.

Order IDs in this example are sequential per user (`ORD-1`, `ORD-2` ...) and are not globally unique. A composite primary key (`user_id`, `order_id`) is therefore required to uniquely identify each order row.

Destination — `users` (parent):

| user_id | name  |
|---------|-------|
| 1       | Alice |

Destination — `orders` (child, composite primary key: `user_id` + `order_id`):

| user_id | order_id | amount |
|---------|----------|--------|
| 1       | ORD-1    | 20.5   |
| 1       | ORD-2    | 35.0   |

Refer to `sync_parent_child()`.

### Write as a JSON blob

The nested `orders` list is stored as a single JSON blob in the `orders` column. This avoids frequent schema changes and preserves the full structure for downstream consumers. The Connector SDK accepts the Python list directly; no manual serialization is required. Only the `order_id` and `amount` fields from each order are written into the blob.

Destination — `users_data`:

| user_id | name  | orders                                             |
|---------|-------|----------------------------------------------------|
| 1       | Alice | [{"order_id": "ORD-1", "amount": 20.5}, ...]       |

Refer to `sync_json_blob()`.


## Error handling

- Checkpointing – the connector checkpoints state after every table sync completes and at every `__CHECKPOINT_INTERVAL` upserts within a table. If a sync is interrupted, Fivetran resumes from the last checkpoint rather than replaying the entire sync from the beginning.


## Tables created

This connector creates four destination tables across the three data handling patterns.

`users_flattened` — pattern 1, flatten into columns (composite primary key: `user_id` + `order_id`):

| Column | Type | Description |
|--------|------|-------------|
| user_id (primary key) | STRING | User identifier; part of composite primary key |
| order_id (primary key) | STRING | Sequential order identifier per user (ORD-1, ORD-2 ...); part of composite primary key |
| name | STRING | User's full name, repeated on every order row |
| amount | DOUBLE | Order total amount |

`users` — pattern 2, parent table:

| Column | Type | Description |
|--------|------|-------------|
| user_id (primary key) | STRING | Unique user identifier |
| name | STRING | User's full name |

`orders` — pattern 2, child table (composite primary key):

| Column | Type | Description |
|--------|------|-------------|
| user_id (primary key) | STRING | Foreign key referencing `users.user_id`; part of composite primary key |
| order_id (primary key) | STRING | Sequential order identifier per user (ORD-1, ORD-2 ...); part of composite primary key |
| amount | DOUBLE | Order total amount |

`users_data` — pattern 3, JSON blob:

| Column | Type | Description |
|--------|------|-------------|
| user_id (primary key) | STRING | Unique user identifier |
| name | STRING | User's full name |
| orders | JSON | Nested orders stored as a JSON blob |


## Additional files

- `mock_api.py` – A simulated API that returns a list of user records with randomized values and a fixed schema, each containing a nested orders list used by the connector.


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
