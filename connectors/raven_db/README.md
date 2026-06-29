# RavenDB Connector Example

## Connector overview

This connector integrates RavenDB with Fivetran, syncing data from RavenDB collections to your destination. It connects to a RavenDB cluster, efficiently retrieves data using pagination, and handles incremental updates based on the `@last-modified` metadata field.

The connector is designed to handle large datasets efficiently through streaming and pagination, making it suitable for production environments with high data volumes.

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
fivetran init <project-path> --template connectors/raven_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connect to RavenDB clusters with certificate-based authentication
- Incremental updates based on `@last-modified` metadata tracking
- Memory-efficient data processing with pagination
- Checkpoint state management for reliable syncs
- Support for large datasets through pagination techniques
- Detailed logging for monitoring and troubleshooting
- Multi-node cluster support with comma-separated URLs
- Automatic flattening of nested document structures

## Configuration file

```json
{
  "ravendb_urls": "<YOUR_RAVENDB_CLOUD_URL>",
  "database_name": "<YOUR_DATABASE_NAME>",
  "certificate_base64": "<YOUR_BASE64_ENCODED_CERTIFICATE>"
}
```

### Configuration parameters
- `ravendb_urls` (required): Your RavenDB Cloud URLs. For clusters, provide comma-separated URLs
- `database_name` (required): Name of the RavenDB database to sync from
- `certificate_base64` (required): Base64-encoded client certificate (PEM format)

Important: You must provide the certificate as a base64-encoded PEM certificate string.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the RavenDB Python client:

```
ravendb
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses certificate-based authentication with RavenDB. The `certificate_base64` parameter contains a base64-encoded client certificate (PEM format), which is decoded at runtime and written to a temporary file for the RavenDB client.

To obtain your certificate:
1. Log in to your [RavenDB Cloud portal](https://cloud.ravendb.net/).
2. Navigate to your instance.
3. Download the client certificate package.
4. Convert the certificate to base64 format:

    - **macOS/Linux:**
      ```sh
      base64 -i certificate.pem
      ```
    - **Windows:**
      ```cmd
      certutil -encode certificate.pem certificate.b64
      ```
      The base64-encoded certificate is saved to `certificate.b64`.
5. Add the base64 string to your configuration file.

## Pagination

The connector implements efficient pagination when retrieving data from RavenDB:
- Uses RavenDB's `skip/take` pagination with configurable batch sizes
- Default batch size is set to 100 documents, but can be adjusted
- Performs upserts one document at a time, avoiding excessive memory usage
- Handles checkpointing after each batch to maintain state during long-running syncs

## Data handling

The connector processes data with the following approach:
- Connects to the specified RavenDB database and collection
- Retrieves documents incrementally based on the `@last-modified` metadata field
- Orders results by `@last-modified` ascending for consistent incremental sync
- Flattens nested document structures into key-value pairs for relational storage
- Skips RavenDB internal metadata fields (those starting with @)
- Converts arrays to JSON strings for storage
- Maintains state between runs by tracking the latest `@last-modified` timestamp
- Delivers data with automatic type inference (except primary key)

## Error handling

The connector implements the following error-handling strategies:
- Validates configuration parameters before attempting connection (refer to `validate_configuration()` function)
- Provides detailed error messages for connection and certificate failures (refer to `create_document_store()` function)
- Implements retry logic with exponential backoff for transient failures (ConnectionError, TimeoutError, RavenException) in `fetch_documents_batch()` function
- Wraps data fetching operations in try/except blocks with informative error messages
- Implements regular checkpointing to minimize data loss in case of failures
- Proper resource cleanup with DocumentStore closure and temporary certificate file removal in the finally block

## Tables created

This connector creates tables in your destination based on the collections you sync. The table structure follows this pattern:

### Example: `ORDERS` table (if syncing an Orders collection)
- Primary Key: `Id` (STRING - RavenDB document ID)
- Columns:
    - `Id` (STRING): Document unique identifier
    - `OrderNumber` (STRING): Order number
    - `CustomerName` (STRING): Customer name
    - `TotalAmount` (FLOAT): Order total
    - `Status` (STRING): Order status
    - `Items` (JSON): Order items as JSON array
    - `ShippingAddress_Street` (STRING): Flattened nested field
    - `ShippingAddress_City` (STRING): Flattened nested field
    - `LastModified` (UTC_DATETIME): Document last update timestamp from metadata

Note: The actual schema depends on your document structure. Nested objects are flattened with underscore separators, and arrays are stored as JSON strings.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.