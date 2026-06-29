# Redshift Using UNLOAD Connector Example

## Connector overview

This example connector demonstrates how to efficiently sync large tables from Amazon Redshift by leveraging the native `UNLOAD` command to export data to S3 in Parquet format, then reading from S3 for ingestion into Fivetran.


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
fivetran init <project-path> --template connectors/redshift/using_unload
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- UNLOAD-based export: Uses Redshift's native `UNLOAD` command for efficient data export
- Parquet format: Exports data in Parquet format with `SNAPPY` compression for optimal performance
- Memory-efficient reading: Uses `PyArrow S3FileSystem` to stream data row-group by row-group
- Incremental sync: Supports incremental synchronization using replication keys
- Automatic schema detection: Discovers tables and primary keys from Redshift automatically
- Automatic replication key inference: Infers replication keys based on timestamp column types and preferred naming conventions
- Parallel table sync: Syncs multiple tables concurrently using configurable parallel workers
- Automatic S3 cleanup: Removes all temporary files (including manifests) after sync
- Graceful fallback: Falls back to FULL sync when no suitable replication key is found


## Configuration file

The configuration file (`configuration.json`) contains the necessary parameters to connect to Amazon Redshift and S3:

```json
{
  "redshift_host": "<YOUR_REDSHIFT_HOST>",
  "redshift_port": "<YOUR_REDSHIFT_PORT>",
  "redshift_database": "<YOUR_REDSHIFT_DATABASE>",
  "redshift_user": "<YOUR_REDSHIFT_USER>",
  "redshift_password": "<YOUR_REDSHIFT_PASSWORD>",
  "redshift_schema": "<YOUR_REDSHIFT_SCHEMA>",
  "s3_bucket": "<YOUR_S3_BUCKET_NAME>",
  "s3_region": "<YOUR_S3_BUCKET_REGION>",
  "s3_prefix": "<YOUR_S3_BUCKET_PREFIX>",
  "iam_role": "<YOUR_REDSHIFT_IAM_ROLE_ARN>",
  "aws_access_key_id": "<YOUR_AWS_ACCESS_KEY>",
  "aws_secret_access_key": "<YOUR_AWS_SECRET_KEY>",
  "auto_schema_detection": "<ENABLE_OR_DISABLE_AUTO_SCHEMA_DETECTION>",
  "enable_complete_resync": "<ENABLE_OR_DISABLE_FULL_RESYNC_DURING_EACH_SYNC>",
  "max_parallel_workers": "<YOUR_MAX_PARALLEL_WORKERS>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

### Configuration parameters

#### Redshift connection
| Parameter | Description | Required |
|-----------|-------------|----------|
| `redshift_host` | The hostname of the Redshift cluster | Yes |
| `redshift_port` | The port number for the Redshift cluster | Yes |
| `redshift_database` | The name of the Redshift database | Yes |
| `redshift_user` | The username for Redshift authentication | Yes |
| `redshift_password` | The password for Redshift authentication | Yes |
| `redshift_schema` | The default schema to extract data from | Yes |

#### S3 configuration
| Parameter | Description | Required |
|-----------|-------------|----------|
| `s3_bucket` | S3 bucket name for UNLOAD output | Yes |
| `s3_region` | AWS region for S3 bucket | Yes |
| `s3_prefix` | Prefix path within the bucket for UNLOAD files (default: fivetran-unload) | No |
| `iam_role` | IAM role ARN for Redshift to access S3 (format: `arn:aws:iam::<account-id>:role/<role-name>`) | Yes |
| `aws_access_key_id` | AWS access key for connector to read/delete S3 files | Yes |
| `aws_secret_access_key` | AWS secret key for connector to read/delete S3 files | Yes |

The IAM role specified in `iam_role` must have `s3:PutObject` permission on the target S3 bucket. The AWS credentials provided in `aws_access_key_id` and `aws_secret_access_key` must have `s3:GetObject`, `s3:ListBucket`, and `s3:DeleteObject` permissions.

#### Sync behavior
| Parameter | Description | Required |
|-----------|-------------|----------|
| `auto_schema_detection` | Enable automatic table and schema discovery (`true`/`false`) | Yes |
| `enable_complete_resync` | Force FULL sync for all tables, ignoring incremental settings (`true`/`false`) | Yes |
| `max_parallel_workers` | Maximum concurrent table syncs | Yes |


## Requirements file

The connector requires the following packages, which should be listed in the `requirements.txt` file:

```
redshift_connector==2.1.8
boto3==1.35.0
pyarrow==17.0.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. Do not declare them in your `requirements.txt` to avoid dependency conflicts.


## Authentication
The connector uses username and password authentication to connect to the Redshift database. The credentials are provided in the `configuration.json` file. Ensure that the Redshift user has the necessary permissions to read data from the specified schema and tables.

The connector also requires an IAM role for Redshift to write `UNLOAD` output to S3, as well as AWS credentials for the connector to read and delete files from S3.


## Pagination
The connector handles large datasets by leveraging Redshift's `UNLOAD` command to export data in Parquet format to `S3`. This approach allows efficient handling of large tables without the need for traditional pagination. The connector reads the Parquet files from `S3` in a memory-efficient manner using PyArrow's `S3FileSystem`, streaming data row-group by row-group.


## Data handling

The connector uses the following workflow:

1. Schema discovery: Connects to Redshift and discovers tables and columns (or uses predefined `TABLE_SPECS`)
2. Table plan building: Builds sync plans for each table including primary keys, replication strategy, and column selection
3. `UNLOAD` execution: For each table, executes UNLOAD command to export data to S3 as Parquet files
4. S3 reading: Reads Parquet files from S3 using PyArrow S3FileSystem for memory-efficient streaming
5. Data sync: Upserts records using the connector SDK
6. Checkpointing: Periodically saves sync progress (every `CHECKPOINT_EVERY_ROWS` rows)
7. Cleanup: Deletes all temporary S3 files after successful sync


## Error handling
The connector includes robust error handling mechanisms to manage potential issues during data extraction and processing. Key strategies include:
- Connection errors: Retries Redshift and S3 connections with exponential backoff
- UNLOAD failures: Catches and logs `UNLOAD` command errors, aborting syncs if necessary
- S3 read errors: Handles S3 read failures and retries as needed


## Tables created
The connector creates tables in the destination based on the source schema. Table names and structures are derived from the Redshift schema specified in the `configuration.json` file. The connector creates a table for each table found in the specified Redshift schema with the name format `<schema_name>.<table_name>`.

The connector automatically detects the schema of each table and creates corresponding tables in the destination with appropriate data types. If automatic schema detection is disabled, the connector uses the schema defined in the `table_spec.py` file.


## Additional files
The connector includes the following additional files:
- `table_spec.py` - This file defines the schema for each table in the Redshift database. The connector uses it when automatic schema detection is disabled. You can customize this file to specify the exact schema for each table, including column names and data types.
- `redshift_client.py` - This file contains the logic for connecting to the Redshift database and executing SQL queries. It encapsulates the connection handling, query execution, and data fetching logic.
- `s3_client.py` - This file contains the logic for interacting with S3, including reading Parquet files and deleting temporary files after sync.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
