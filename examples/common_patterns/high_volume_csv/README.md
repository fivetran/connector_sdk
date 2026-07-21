# High Volume CSV Connector Example

## Connector overview
This example demonstrates efficient patterns for processing and ingesting high-volume CSV data using Fivetran's Connector SDK. It showcases three different approaches for handling large CSV files:

- Dask – Parallel processing with distributed dataframes for scalable batch processing
- Pandas with PyArrow – High-performance CSV reading with optimized data types
- Polars – Modern, memory-efficient dataframe library with streaming capabilities (recommended)

The connector fetches CSV data from an API endpoint, saves it locally, and processes it using each library to demonstrate their respective strengths. This example is ideal for scenarios involving large datasets where memory management and processing speed are critical.

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
fivetran init <project-path> --template examples/common_patterns/high_volume_csv
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Multiple CSV processing approaches – Demonstrates Dask, Pandas with PyArrow, and Polars for handling large CSV files
- Memory-efficient processing – Uses batching and streaming to handle large files without excessive memory usage
- Automatic retry logic – Implements exponential backoff for transient API failures
- Robust error handling – Handles connection errors, timeouts, and HTTP errors gracefully
- Incremental sync support – Maintains state between syncs for efficient data updates

## Configuration file
The connector requires the following configuration parameters:

```
{
  "api_url": "<YOUR_CSV_API_URL>",
  "api_key": "<YOUR_CSV_API_KEY>"
}
```

- `api_url` (required) – The endpoint URL that returns CSV data
- `api_key` (required) – Your API authentication key

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The connector requires the following Python libraries for CSV processing:

```
polars==1.35.2
dask==2025.11.0
pandas==2.3.3
pyarrow==22.0.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector uses API key authentication. The API key is passed in the Authorization header as follows:

```
Authorization: apiKey <YOUR_API_KEY>
```

To obtain your API key, refer to your data source's API documentation. You can modify the authentication as needed to fit your specific API requirements.


## Pagination
This example does not implement pagination as it processes a single CSV file fetched from the source API. For connectors that need to handle multiple pages of CSV data, implement pagination in the API request logic and process each page.


## Data handling
The connector demonstrates three different approaches for processing high-volume CSV data:

### Approach 1: Dask (function `upsert_with_dask`)
- Reads CSV in partitions using `blocksize="128MB"` for parallel processing. You can adjust the blocksize based on your data.
- Processes each partition sequentially.
- Defines explicit data types to avoid type inference overhead.
- Uses `itertuples()` for efficient row iteration.

### Approach 2: Pandas with PyArrow (function `upsert_with_pandas_pyarrow`)
- Uses PyArrow engine for faster CSV reading.
- Loads only necessary columns using `usecols`.
- Defines explicit PyArrow string types for better performance.

### Approach 3: Polars (Recommended) (function `upsert_with_polars`)
- Uses batched reading with `pl.read_csv_batched()` for memory efficiency.
- Reads specified columns only.
- Enables `low_memory=True` for minimal memory footprint.
- Processes batches in a streaming fashion.


## Error handling
The connector implements comprehensive error handling:

- Retries transient failures up to 3 times (`__MAX_RETRIES`).
- Uses exponential backoff starting at 1 second (`__INITIAL_RETRY_DELAY`).
- Maximum delay capped at 16 seconds (`__MAX_RETRY_DELAY`).
- Retries connection errors, timeouts, and HTTP `429`, `500`, `502`, `503`, `504` status codes.
- Fails immediately for permanent errors.
- Ensures all required configuration parameters are present before execution. Raises `ValueError` with descriptive messages for missing parameters.


## Tables created

The connector creates three tables demonstrating different processing approaches:

- `TABLE_USING_DASK` : Contains data processed using Dask's distributed dataframe approach.

- `TABLE_USING_PANDAS_PYARROW` : Contains data processed using Pandas with PyArrow engine.

- `TABLE_USING_POLARS` : Contains data processed using Polars in batched mode (recommended approach).


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
