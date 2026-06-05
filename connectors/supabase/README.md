# Supabase Connector Example 

## Connector overview
This connector demonstrates how to fetch employee data from a Supabase database and sync it to Fivetran using the Fivetran Connector SDK with advanced batch processing capabilities. The connector retrieves employee records from a Supabase table using efficient batch processing with `.range(start, end)` method and performs incremental synchronization based on the hire_date field. It handles Supabase's 1000 record limit by using configurable batch sizes and processes each batch completely before requesting the next one. The connector connects to Supabase using the Python Supabase client library and handles data extraction, transformation, and loading into the destination with proper checkpointing strategies.


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
fivetran init <project-path> --template connectors/supabase
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Batch processing using Supabase's `.range(start, end)` method for efficient data retrieval
- Handles Supabase's record limit by using configurable batch sizes (default: 1000 records per batch)
- Processes each batch completely before requesting the next batch for optimal performance
- Smart checkpointing strategy that checkpoints every 1000 records to minimize overhead
- Progress tracking with total record count and batch-by-batch logging for monitoring large syncs
- Configurable schema and table names for flexibility
- Incremental syncs based on the `hire_date` field
- Automatic data type inference for all columns except for the primary key
- Checkpointing for large datasets to ensure resumable syncs
- Error handling and logging for debugging
- Connection to Supabase using official Python SDK with ClientOptions


## Configuration file
The configuration requires your Supabase project URL and API key to establish a connection to your Supabase database. Optionally, you can also specify the schema name and table name. Below is a breakdown of the available configuration parameters:

- `supabase_url` (required) - Your Supabase project URL.
- `supabase_key` (required) - Your Supabase anon/public API key.
- `schema_name` (optional) - Database schema name (defaults to `public` if not specified otherwise).
- `table_name` (optional) - Table name to sync (defaults to `employee` if not specified otherwise).
- `batch_size` (optional): Number of records to fetch per batch (defaults to `1000`)

```
{
"supabase_url": "<YOUR_SUPABASE_PROJECT_URL>",
"supabase_key": "<YOUR_SUPABASE_ANON_KEY>",
"schema_name": "<YOUR_SCHEMA_NAME>",
"table_name": "<YOUR_TABLE_NAME>",
"batch_size": "<YOUR_OPTIONAL_BATCH_SIZE>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The `requirements.txt` file specifies the Python libraries required by the connector. The main dependency is the Supabase Python client library.

```
supabase
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector uses API key authentication to access Supabase. To authenticate, you need to provide the following:
- Your Supabase project URL - Found in your Supabase project dashboard
- Supabase API key - Use the anon/public key for read-only access to your database

To obtain these credentials:
1. Log in to your Supabase dashboard.
2. Navigate to your project.
3. Go to **Settings > API**.
4. Make a note of the Project URL and anon public key. You will need it later to set up your Connector SDK connector.


## Pagination
The connector handles data retrieval using Supabase's built-in query capabilities with explicit ordering by `hire_date`. The connector fetches data in chronological order (ascending by `hire_date`) to ensure proper incremental sync behavior. 

For large datasets, the connector implements checkpointing every 1000 rows to ensure the sync can resume from the correct position if interrupted. The explicit sorting ensures that checkpoints always capture the correct state for resuming syncs.


## Data handling
The connector fetches data from the specified Supabase table and performs the following operations:
- Queries records where `hire_date` is greater than the last synced `hire_date`
- Explicitly orders results by `hire_date` ascending to ensure consistent incremental syncs
- Processes records sequentially in chronological order for accurate checkpointing
- Flattens any nested data structures into key-value pairs
- Upserts each record to the destination table (using configurable table name)
- Updates state with the latest `hire_date` for subsequent syncs


## Error handling
The connector implements comprehensive error handling strategies:
- Connection validation for Supabase client creation 
- Configuration validation to ensure required parameters are present 
- Data retrieval error handling with detailed logging 
- Runtime exception handling in the main update loop with proper error propagation


## Tables created
The connector creates a table in the destination based on your configuration:

- Table name - Configurable via `table_name` parameter
- Primary key - `id` (INT - maps to Supabase int8)
- Fields - All fields from the source table (e.g., `id`, `first_name`, `last_name`, `email`, `department`, `hire_date`)

Note: Data types are automatically inferred by Fivetran except for the primary key.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
