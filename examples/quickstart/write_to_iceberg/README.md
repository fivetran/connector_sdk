# Write to Iceberg Example

## Connector overview
This example shows how to upsert data from a Connector SDK connector into an Apache Iceberg destination. The connector sends 12 mock order rows to a table named `mock_orders`. The sample rows live in a separate file, `mock_data.py`, so you can swap in your own data without changing the sync logic.

The connector code is the same for any destination. To write to an Iceberg catalog, fill in the catalog settings in `destination.json` and run the connector with [`fivetran run`](https://fivetran.com/docs/connector-sdk/getting-started/connector-sdk-commands#fivetranrun). `fivetran run` reads `destination.json` and sends the data to that catalog. `fivetran debug` ignores `destination.json` and writes to a local DuckDB file instead. For the full walkthrough, see [Write to an Iceberg catalog](https://fivetran.com/docs/connector-sdk/testing/write-to-iceberg-catalog#writetoanicebergcatalog).

## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- An Iceberg catalog that Fivetran can reach.

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To create a new Connector SDK project from this example, run:

```bash
fivetran init --template examples/quickstart/write_to_iceberg
```

To test the connector locally, run:

```bash
fivetran debug
```

`fivetran debug` runs the sync on your machine and writes the results to `files/warehouse.db`. It does not write to Iceberg.

To write to your Iceberg catalog, fill in `destination.json` (see [Destination file](#destination-file)), then run:

```bash
fivetran run
```

To use a destination file stored elsewhere, pass its path:

```bash
fivetran run --destination-file <path-to-destination.json>
```

See [`fivetran run`](https://fivetran.com/docs/connector-sdk/getting-started/connector-sdk-commands#fivetranrun) for all flags, including `--configuration`, `--state`, and `--naming`.


## Features
- Implements `schema()` and `update()`.
- Declares `id` as the primary key and forces its type to `INT`. Other columns are inferred.
- Upserts 12 rows from `mock_data.py`.
- Uses `op.checkpoint()` to save state after the upserts.

## Configuration file
The connector requires no configuration parameters, so `configuration.json` is an empty object:

```json
{}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

Iceberg connection settings go in `destination.json`, described below.


## Requirements file
This connector requires no additional packages, so there is no `requirements.txt`.

Note: [Certain packages](https://fivetran.com/docs/connector-sdk/getting-started/how-to-install-connector-sdk#installconnectorsdk) are pre-installed in the Connector SDK runtime environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Destination file
`destination.json` holds the Iceberg catalog settings. It must sit beside `connector.py`, or you can point to it with `--destination-file`. Replace each placeholder with your own values. See our [Write to an Iceberg Catalog documentation](https://fivetran.com/docs/connector-sdk/testing/write-to-iceberg-catalog#writetoanicebergcatalog) for more information.

| Key | Description                                                                                                                                                                                                                       |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `uri` | URI of the Iceberg REST catalog endpoint. Must start with `http://` or `https://`.                                                                                                                                                |
| `warehouse` | Name of the catalog warehouse.                                                                                                                                                                                                    |
| `namespace` | Namespace for the tables. Use one reserved for this connector.                                                                                                                                                                    |
| `client_id` | Client ID for OAuth2 client-credentials sign-in.                                                                                                                                                                                  |
| `client_secret` | Client secret for OAuth2 client-credentials sign-in.                                                                                                                                                                              |
| `scope` | The scope to request. Goes with the client credentials.                                                                                                                                                                           |
| `header.X-Iceberg-Access-Delegation` | For this example, use `vended-credentials` so the catalog supplies storage credentials; only `s3.region` may be supplied alongside it. Non-vended storage authentication (`none`, or omitting this header) is outside the scope of this example. |
| `s3.region` | AWS region of the bucket that stores the Parquet files.                                                                                                                                                                           |

Note:
- Use a namespace that is used only for your connector. `fivetran run` does not ask for confirmation, and changes any table with the same name that is already in the namespace.
- On the first run, DuckDB downloads its Iceberg extension, so the machine needs internet access.


## Data handling
- `schema()` declares the `mock_orders` table with `id` as the primary key.
- `update()` upserts each row from `__MOCK_ORDERS` in `mock_data.py`. Running the sync again updates the same rows instead of adding duplicates.
- `op.checkpoint()` runs after the upserts in `update()`. This tells Fivetran it is safe to write the buffered rows to the destination.


## Error handling
`update()` has no error handling, because the example does not call an external system. For real connectors, catch specific exceptions in `update()`, log them, and retry transient failures.


## Tables created

The connector writes one table, `MOCK_ORDERS`, into the `namespace` set in `destination.json`.

| Column   | Type   | Primary key | Source                 |
|----------|--------|-------------|------------------------|
| `id`     | INT    | Yes         | Declared in `schema()` |
| `name`   | STRING | No          | Inferred from data     |
| `amount` | DOUBLE | No          | Inferred from data     |


## Additional files
The connector uses the following additional file:
- **`mock_data.py`** - Holds the `__MOCK_ORDERS` list of 12 sample rows that `update()` upserts into `mock_orders`.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
