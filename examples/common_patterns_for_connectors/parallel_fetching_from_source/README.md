# Parallel Fetching from Source Example

This example demonstrates how to fetch data from multiple files in an AWS S3 bucket in parallel using ThreadPoolExecutor, and stream the data efficiently without loading entire files into memory at once.

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns_for_connectors/parallel_fetching_from_source
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

### Configuration

The connector requires the following configuration parameters in `configuration.json`:

```json
{
  "aws_access_key_id": "<YOUR_AWS_ACCESS_KEY_ID>",
  "aws_secret_access_key": "<YOUR_AWS_SECRET_ACCESS_KEY>",
  "region_name": "<YOUR_AWS_REGION_NAME>",
  "bucket_name": "<YOUR_AWS_BUCKET_NAME>",
  "prefix": "<YOUR_AWS_FOLDER_NAME>",
  "parallelism": "<NUMBER_OF_THREADS>"
}
```

- `aws_access_key_id` and `aws_secret_access_key`: AWS credentials with read access to your S3 bucket
- `region_name`: AWS region where your bucket is located
- `bucket_name`: Name of the S3 bucket containing your CSV files
- `prefix`: Folder path in the bucket where CSV files are stored (optional, defaults to root "/" if not specified)
- `parallelism`: Number of threads to use (optional, defaults to 4 if not specified)

### Key Functions

1. `create_s3_client(configuration)`
Creates an S3 client using boto3. Validates required configuration parameters.

2. `get_file_table_pairs(s3_client, bucket_name, prefix)`
Retrieves all CSV files from the specified S3 location and maps them to table names. You can modify this function to filter specific files or implement custom table naming logic beyond simply removing the `.csv` extension.

3. `process_file_get_stream(s3_client, bucket_name, file_key, table_name)`
Processes a single file using streaming (not loading the entire file into memory). You can modify this function to handle different file formats or add additional data transformation logic for your specific use case.

### Important Performance Considerations

- Avoid loading entire files into memory before processing, as this can cause Out of Memory errors with large files.
- A maximum of 4-8 worker threads is recommended for production environments. The connector defaults to 4 threads, which is suitable for most workloads.
- While increasing threads might show performance improvements during local testing, this doesn't translate to production environments where other constraints apply.

> IMPORTANT : Do not set `parallelism` too high. Higher number of threads are not always better and can actually degrade performance.