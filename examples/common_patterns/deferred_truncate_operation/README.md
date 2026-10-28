# Deferred Truncate Operation Connector Example

## Connector overview
This connector demonstrates the deferred truncate operation for Fivetran Connector SDK. It compares a regular `op.truncate(table)` with a deferred `op.truncate(table, deferred=True)` on two identical tables, so you can see exactly when each one soft-deletes existing rows.

A regular `truncate()` soft-deletes the rows that already exist in the destination (`_fivetran_deleted = true`) at the first checkpoint after the call. This happens before the replacement rows have finished arriving. If the sync fails part way through, the table looks empty or nearly empty even though the refresh has not finished.

A deferred truncate captures the truncate timestamp when `op.truncate(table, deferred=True)` is called, but soft-deletes the rows synced before that timestamp only after `update()` returns successfully. The soft-delete is committed together with the final checkpoint, so the destination is never left with the old rows deleted and the replacement rows missing. Rows upserted after the call are never affected.

Use a deferred truncate when you replace a table through a full refresh that takes several checkpoints. Use a regular truncate when you want the existing rows soft-deleted immediately. For a walkthrough of the regular truncate with `upsert()`, `update()` and `delete()`, refer to the [truncate_operation](../truncate_operation) example.


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
fivetran init <project-path> --template examples/common_patterns/deferred_truncate_operation
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Compares a regular truncate and a deferred truncate side by side on two tables.
- Shows the destination state after each stage as inline comments in `connector.py`.
- Uses hardcoded data, so no external API or credentials are needed.


## Configuration file
No configuration keys are required. The `configuration.json` file contains an empty JSON object.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
No external dependencies are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is needed. This connector runs standalone for demonstration purposes.


## Pagination
Not applicable. This connector emits a small hardcoded dataset.


## Data handling
Each sync runs three stages on both tables. Refer to `def update(configuration: dict, state: dict)`.

- Stage 1 – The old catalog (products 1 to 3) is upserted into both tables and checkpointed. All rows are active.
- Stage 2 – `op.truncate(table)` is called on `products_immediate_truncate` and `op.truncate(table, deferred=True)` on `products_deferred_truncate`, followed by a checkpoint. The regular truncate soft-deletes products 1 to 3 at this checkpoint. The deferred truncate soft-deletes nothing yet, so products 1 to 3 stay active.
- Stage 3 – The replacement catalog (products 4 and 5) is upserted into both tables and checkpointed. The deferred table now holds the old and new rows as active rows.
- When `update()` returns – The Connector SDK applies the deferred truncate and soft-deletes products 1 to 3 in `products_deferred_truncate`. Both tables end with products 4 and 5 active.

The difference is between Stage 2 and the end of the sync:

| Point in the sync | `products_immediate_truncate` active rows | `products_deferred_truncate` active rows |
|-------------------|-------------------------------------------|------------------------------------------|
| After Stage 1 | 1, 2, 3 | 1, 2, 3 |
| After Stage 2 | none | 1, 2, 3 |
| After Stage 3 | 4, 5 | 1, 2, 3, 4, 5 |
| After `update()` returns | 4, 5 | 4, 5 |

Additional behaviors of a deferred truncate:
- Only rows synced before the truncate timestamp are soft-deleted. Rows upserted after the call stay active.
- Calling a deferred truncate more than once for the same table in one sync results in a single soft-delete, at the latest call's timestamp.
- If `update()` fails before returning, the deferred truncate is not applied. If a checkpoint was saved after the call, the next attempt applies it once its own `update()` succeeds, without calling `truncate()` again.
- `deferred` defaults to `False`, so existing `truncate()` calls behave as before.


## Tables created

The connector creates two tables with the same columns:

- `PRODUCTS_IMMEDIATE_TRUNCATE` – Uses a regular truncate.
- `PRODUCTS_DEFERRED_TRUNCATE` – Uses a deferred truncate.

| Column | Type | Description |
|--------|------|-------------|
| `product_id` | INT | Primary key |
| `name` | STRING | Product name |
| `price` | FLOAT | Product price |


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
