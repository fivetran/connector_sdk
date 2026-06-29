# AWS DocumentDB Connector Example

## Connector overview

This connector integrates AWS DocumentDB with Fivetran, syncing data from DocumentDB collections to your destination. It connects to a DocumentDB cluster, efficiently retrieves data using pagination, and handles incremental updates based on the `updated_at` timestamp field. 

Note: Fivetran already provides a native Java-based DocumentDB connector that supports SaaS deployment models. This Python-based connector is specifically intended for Hybrid Deployment (HD) scenarios, as the native connector does not support Hybrid Deployment. For SaaS deployments, we recommend using the native DocumentDB connector available at https://fivetran.com/docs/connectors/databases/documentdb.

Important Network Consideration: DocumentDB clusters are typically deployed in private subnets and do not allow direct connections from outside the VPC. If you need to connect from outside the VPC (such as from your local development environment), you can set up an EC2 instance in the same VPC as your DocumentDB cluster using the [AWS automatic connectivity guide](https://docs.aws.amazon.com/documentdb/latest/developerguide/connect-ec2-auto.html#auto-connect-ec2.process). Once the EC2 instance is set up, you can create a TCP tunnel using socat: `socat TCP-LISTEN:27017,fork TCP:<documentDBHost>:27017` to forward traffic from your local machine to the DocumentDB cluster through the EC2 instance.

The connector is designed to handle large datasets efficiently through streaming and pagination techniques, making it suitable for production environments with significant data volumes. It supports MongoDB-compatible operations since DocumentDB is MongoDB-compatible.

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
fivetran init <project-path> --template connectors/documentdb
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Connect to AWS DocumentDB clusters with SSL authentication
- Incremental updates based on timestamp tracking
- Memory-efficient data processing with pagination and generators
- Checkpoint state management for reliable syncs
- Support for large datasets through pagination techniques
- Detailed logging for monitoring and troubleshooting
- MongoDB-compatible operations for DocumentDB

## Configuration file

The connector requires the following configuration parameters:

```
{
  "hostname": "<YOUR_DOCUMENTDB_HOSTNAME>",
  "username": "<YOUR_DOCUMENTDB_USERNAME>",
  "password": "<YOUR_DOCUMENTDB_PASSWORD>",
  "database": "<YOUR_DOCUMENTDB_DATABASE>",
  "port": "<YOUR_DOCUMENTDB_PORT>"
}
```

- hostname: The DocumentDB cluster endpoint hostname
- username: Username for authentication
- password: Password for authentication
- database: The DocumentDB database name to connect to
- port: The port number for the DocumentDB cluster (default: 27017)

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the PyMongo driver and dateutil for timestamp parsing:

```
pymongo
python-dateutil
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses SSL authentication with DocumentDB. Provide the following credentials in the configuration: 

- username: A valid DocumentDB user with read permissions on the specified database
- password: The corresponding password for the user

The connector automatically configures SSL settings required for DocumentDB connections.

## Pagination

The connector implements efficient pagination when retrieving data from DocumentDB:  
- Uses MongoDB cursor-based pagination with batch_size parameter
- Default batch size is set to 100 documents but can be adjusted
- Performs upserts one document at a time, avoiding excessive memory usage
- Handles checkpointing every 1000 records to maintain state during long-running syncs

## Data handling

The connector processes data with the following approach:  
- Connects to the specified DocumentDB database
- Retrieves documents incrementally based on the `updated_at` timestamp
- Transforms DocumentDB documents into dictionaries for Fivetran
- Handles timezone-aware datetime objects consistently across queries and comparisons
- Uses MongoDB query syntax with `$gt` operator for efficient incremental querying
- Maintains state between runs by tracking the latest timestamp processed
- Delivers data with the following schema mapping:
  - _id (ObjectId → STRING)
  - name (string → STRING)
  - email (string → STRING)
  - status (string → STRING)
  - created_at (datetime → UTC_DATETIME)
  - updated_at (datetime → UTC_DATETIME)
  - metadata (object → JSON)

## Error handling

The connector implements the following error handling strategies:  
- Validates configuration parameters before attempting connection
- Provides detailed error messages for connection failures
- Handles timezone-related errors by ensuring consistent timezone awareness
- Wraps data fetching operations in try/except blocks with informative error messages
- Gracefully handles pagination issues that may occur with large datasets
- Implements regular checkpointing to minimize data loss in case of failures
- Handles SSL connection issues specific to DocumentDB

## Tables created

This connector creates the following tables in your destination:

### USERS
- Primary Key: `_id`
- Columns: 
  - `_id` (STRING): Document unique identifier
  - `created_at` (UTC_DATETIME): Document creation timestamp
  - `updated_at` (UTC_DATETIME): Document last update timestamp
  - `metadata` (JSON): Additional user metadata as JSON object

### ORDERS
- Primary Key: `_id`
- Columns:
  - `_id` (STRING): Document unique identifier
  - `created_at` (UTC_DATETIME): Order creation timestamp
  - `updated_at` (UTC_DATETIME): Order last update timestamp
  - `items` (JSON): Order items as JSON array


## Prerequisites

This connector requires that the following prerequisites exist in your DocumentDB instance:

- A database named as specified in your configuration
- Collections with documents containing the following fields:
   - `_id` (ObjectId): Primary key
   - `updated_at` (datetime): Document update timestamp for incremental sync
   - Other fields as defined in your schema

Example document structure:
```json
{
  "_id": ObjectId("..."),
  "created_at": ISODate("2023-01-01T00:00:00Z"),
  "updated_at": ISODate("2023-01-01T00:00:00Z"),
  "metadata": {"source": "web"}
}
```

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

## DocumentDB-specific notes

- DocumentDB is MongoDB-compatible, so this connector uses the PyMongo driver
- SSL is required for DocumentDB connections and is automatically configured
- The connector uses `retryWrites=false` in the connection string as required by DocumentDB
- DocumentDB has some limitations compared to MongoDB, but this connector works within those constraints
