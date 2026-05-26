# Truncate Operation Connector Example

## Connector overview
This connector demonstrates the [`truncate()` operation](https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-operations#truncate) in the Fivetran Connector SDK, showing how it interacts with `upsert()`, `update()`, and `delete()` on a single table.

`truncate()` soft-deletes all rows that exist in the destination at the point it is called by setting `_fivetran_deleted = true`. Rows emitted after `truncate()` within the same sync are not affected. This makes it useful for full-refresh patterns where the source replaces its entire dataset each sync.

The connector uses a hardcoded product catalog to walk through six stages. The resulting destination table state after each stage is shown as inline comments in `connector.py`.

**Key behaviors illustrated:**

- `truncate(table)` — soft-deletes every row in the table at the time of the call.
- `delete(table, keys)` — soft-deletes a single row identified by its primary key; unlike `truncate()`, it targets a single row.
- Rows upserted after `truncate()` in the same sync land with `_fivetran_deleted = false`.
- Upserting a row whose primary key was previously truncated or deleted sets `_fivetran_deleted = false` and applies the new column values.


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/truncate_operation
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Shows destination table state after each operation as inline comments in `connector.py`.
- Uses hardcoded realistic data — no external APIs or configuration required.
- Covers key soft-delete behaviors: bulk truncate, post-truncate inserts, and row revival.


## Configuration file
No configuration file is required for this example.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
No external dependencies are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is needed. This connector runs standalone for demonstration purposes.


## Pagination
Not applicable. This connector emits a static hardcoded dataset.


## Data handling
Each sync walks through six stages on the `PRODUCTS` table:

- **Stage 1 — upsert:** Inserts 3 products; all active (`_fivetran_deleted = false`).
- **Stage 2 — update:** Patches Laptop price only; other columns unchanged.
- **Stage 3 — truncate:** All 3 existing rows soft-deleted (`_fivetran_deleted = true`).
- **Stage 4 — upsert after truncate:** Inserts 2 new products; not soft-deleted because they are emitted after `truncate()`.
- **Stage 5 — revive:** Upserting a previously truncated primary key sets `_fivetran_deleted = false` and applies new values.
- **Stage 6 — delete:** Soft-deletes a product by primary key using `op.delete()`.


## Tables created

The connector creates the `PRODUCTS` table:

| Column | Type | Description |
|--------|------|-------------|
| `product_id` | INT | Primary key |
| `name` | STRING | Product name |
| `category` | STRING | Product category |
| `price` | FLOAT | Product price |
| `in_stock` | BOOLEAN | Whether product is currently in stock |


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
