# Environment-Driven Connectivity Connector Example


## Connector overview
This example demonstrates how to build a connector that automatically selects API endpoints based on the deployment environment. It uses the Star Wars API (SWAPI) to showcase environment-driven connectivity patterns, switching between a production mirror and the direct API endpoint using the `FIVETRAN_DEPLOYMENT_MODEL` environment variable.

- **Production environment**: Uses a mirror (https://swapi.py4e.com/api) for improved reliability and performance
- **Local debug environment**: Uses the direct API endpoint (https://swapi.dev/api) for development and testing


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/environment_driven_connectivity
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Environment-aware endpoint selection: Automatically switches between production and debug API endpoints
- Comprehensive data coverage: Syncs all six SWAPI resource types (people, planets, films, species, starships, vehicles)
- Robust pagination handling: Efficiently processes paginated API responses
- Retry logic with exponential backoff: Handles transient failures with configurable retry attempts
- Rate limiting support: Respects HTTP 429 responses and Retry-After headers


## Configuration file
This connector does not require any configuration parameters in `configuration.json` as it uses a public API. You can add configuration parameters if needed for your specific use case.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This example does not require any additional Python packages beyond those pre-installed in the Fivetran environment. Therefore, no `requirements.txt` file is needed.


Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not require authentication as it uses SWAPI. The API is freely accessible without API keys or credentials.

The Fivetran platform automatically sets the `FIVETRAN_DEPLOYMENT_MODEL` environment variable based on the deployment context. See the [Working with Connector SDK documentation](https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#referencingenvironmentvariablesinyourcode) for details.

## Pagination
The connector handles pagination automatically using SWAPI's pagination structure:

- Makes an initial request to the resource endpoint (e.g., `/people/`)
- Extracts the results array from the response
- Yields each page of results to the caller for processing
- Follows the next URL from the response to fetch the next page
- Continues until the next field is null, indicating the end of data

Each page is processed immediately before fetching the next page, ensuring memory-efficient streaming of large datasets.


## Data handling
The connector processes data as follows:

- Resource discovery: Fetches all available resource types from the SWAPI root endpoint
- Streaming pagination: Processes each page of results immediately without loading all data into memory
- Data validation: Skips records without a required url field and logs warnings
- Upsert operations: Uses the url field as the primary key for inserting or updating records.


## Error handling
The connector implements comprehensive error handling:

- Retry logic: Attempts up to three retries for transient failures
- Exponential backoff: Doubles wait time between retries (1s, 2s, 4s), capped at 16 seconds
- Rate limiting: Handles HTTP 429 responses by respecting the Retry-After header
- Request timeout: 20-second timeout for all API requests to prevent hanging
- Exception logging: Logs warnings for each retry attempt and errors when all retries are exhausted
- Graceful degradation: Skips invalid records (missing url field) with warnings rather than failing the entire sync


## Tables created

The connector creates six tables in your destination:

### PEOPLE
- Primary key: url
- Columns: All fields from SWAPI's people resource, including:
  - created, edited (`UTC_DATETIME`)
  - films, species, starships, vehicles (`JSON` arrays)

### PLANETS
- Primary key: url
- Columns: All fields from SWAPI's planets resource, including:
  - created, edited (`UTC_DATETIME`)
  - residents, films (`JSON` arrays)

### FILMS
- Primary key: url
- Columns: All fields from SWAPI's films resource, including:
  - created, edited (`UTC_DATETIME`)
  - release_date (`NAIVE_DATE`)
  - characters, planets, starships, vehicles, species (`JSON` arrays)

### SPECIES
- Primary key: url
- Columns: All fields from SWAPI's species resource, including:
  - created, edited (`UTC_DATETIME`)
  - people, films (`JSON` arrays)

### STARSHIPS
- Primary key: url
- Columns: All fields from SWAPI's starships resource, including:
  - created, edited (`UTC_DATETIME`)
  - pilots, films (`JSON` arrays)

### VEHICLES
- Primary key: url
- Columns: All fields from SWAPI's vehicles resource, including:
  - created, edited (`UTC_DATETIME`)
  - pilots, films (`JSON` arrays)


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
