# Hashed Primary Key Connector Example

## Connector overview
This connector demonstrates how to generate hashed primary keys using field-level data when the source records lack a natural unique identifier. It simulates a data source returning user profiles and applies a SHA-1 hash over each row to derive a synthetic key `hash_id` for use as a primary key in the destination table.

This is a recommended practice in cases where:
- Source systems do not provide a stable primary key
- Data structure may change over time (e.g., columns added or removed)
- Upserts need to be deterministic and idempotent

Refer to the [Fivetran SDK Best Practices documentation](https://fivetran.com/docs/connector-sdk/best-practices#declareprimarykeys) for more details on why primary keys are critical for sync performance and integrity.


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
fivetran init <project-path> --template examples/common_patterns/hashes
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates how to generate a SHA-1 hash from record fields.
- Uses the hash as a synthetic primary key for upserts.
- Illustrates impact of null or missing fields on hash identity.
- Handles diverse data quality scenarios (e.g. null email, missing fields).
- Ensures data deduplication and repeatability in syncs.


## Configuration file
This example does not require any configuration inputs.

In a real-world scenario, `configuration.json` may include source API credentials, filters, or fields to include in the hash.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any external dependencies, it uses the following internal libraries:

```
hashlib
json
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is used, as the connector operates on hardcoded sample data. You can extend this to fetch records from an API or file system with auth tokens as needed.


## Pagination
Not applicable — this example syncs static data only. To support pagination, you could modify `update()` to loop through pages of records.


## Data handling
- Each row is serialized as a sorted JSON string.
- The SHA-1 hash of this string is calculated via `hashlib.sha1()`.
- The resulting `hash_id` is added to the row before upserting.
- Changes in any field, including null values, result in a new hash and row version.

This pattern ensures repeatable, deterministic hashing and row tracking, even without an explicit `id` field in the source.


## Error handling
- The example does not simulate failures, but hash generation is robust to missing fields and null values.
- Schema drift (e.g., added/removed columns) will result in a different `hash_id`, which creates a new row instead of updating the existing one.


## Tables created
The connector creates the `USER` table:

```
{
  "table": "user",
  "primary_key": ["hash_id"],
  "columns": {
    "first_name": "STRING",
    "last_name": "STRING",
    "email": "STRING",
    "updated_at": "UTC_DATETIME"
  }
}
```


## Additional considerations
- Make sure to sort and consistently structure the row data before hashing to avoid unintended duplicates.
- This approach works best when data volume is low-to-moderate. For large datasets, consider using UUIDs or hashing only key columns for better performance.
- Use sha256 if cryptographic strength is a concern. sha1 is used here for simplicity.


The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.