# NPPES NPI Registry Connector Example

## Connector overview

This connector fetches healthcare provider data from the National Plan and Provider Enumeration System (NPPES) NPI Registry API. The NPI Registry is a public database maintained by the Centers for Medicare & Medicaid Services (CMS) that contains information about all healthcare providers and organizations. This connector enables users to sync provider information including basic demographics, addresses, taxonomies, identifiers, endpoints, and practice locations into their data warehouse for analysis and reporting.

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
fivetran init <project-path> --template connectors/npi_registry
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Fetches provider data from the NPPES NPI Registry public API
- Accepts a pre-configured API URL generated from the demo API interface
- Implements automatic pagination using the skip parameter (max skip value: 1000)
- Flattens nested JSON structures into relational tables
- Creates seven normalized tables: provider, address, taxonomy, identifier, endpoint, other_name, and practice_location
- Implements checkpointing for resumable syncs
- Includes retry logic with exponential backoff for API requests
- No authentication required (public API)

## Configuration file

The `configuration.json` file requires a single parameter: the complete API URL generated from the NPPES API demo interface.

```json
{
  "api_url": "<YOUR_NPI_REGISTRY_API_URL>"
}
```

### Configuration parameters

- `api_url` (required): Complete API URL generated from the NPPES API demo page. The URL should include your search criteria and the `limit` parameter. The API supports a maximum limit of 200 results per request.

Note: Ensure that the `configuration.json` file is not checked into version control if it contains any sensitive information.

### How to generate your API URL

To generate your API URL:

1. Visit the [NPPES API Demo Page](https://npiregistry.cms.hhs.gov/demo-api).
2. Enter your search criteria (provider name, location, taxonomy, etc.).
3. Set the Limit parameter to 200 (the API's maximum allowed value).
4. Click **Submit** to generate the API URL.
5. Copy the complete URL from the demo interface.
6. Paste it into the `configuration.json` file as the value for `api_url`.

Note: The connector automatically handles pagination by modifying the `skip` parameter. You do not need to modify the skip value in your configuration URL.

## Requirements file

This connector does not require any additional Python packages beyond those pre-installed in the Fivetran environment. Therefore, no `requirements.txt` file is needed.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The NPPES NPI Registry API is a public API that does not require authentication. No API keys, tokens, or credentials are needed to access the data.

## Pagination

The connector implements offset-based pagination using the `skip` parameter. Refer to the `fetch_npi_data` function in `connector.py`.

## Data handling

The connector processes the nested JSON response from the NPI Registry API and flattens it into seven relational tables. Refer to the `process_provider_record` and `upsert_child_records` functions in `connector.py`.

Data transformation process:

1. The API returns a JSON array of provider results.
2. Each provider record contains nested objects and arrays.
3. The connector extracts the main provider information and creates a record in the `provider` table.
4. Nested arrays (addresses, taxonomies, identifiers, etc.) are flattened into separate child tables using a generic function.
5. Each child table includes the NPI number as a foreign key for joining.
6. All data types are inferred by Fivetran except for primary keys which are explicitly defined.

Flattening functions:

- `flatten_provider_basic` – Extracts basic provider information and flattens the `basic` object
- `upsert_child_records` – Generic function that handles flattening and upserting for all child tables (addresses, taxonomies, identifiers, endpoints, other_names, practice_locations)

## Error handling

The connector implements robust error handling to manage API failures and data issues. Refer to the `make_api_request_with_retry` function and the error handling blocks in the `update` function.

Error handling strategies:

- Retry logic with exponential backoff for transient API errors (max 3 retries)
- Request timeout of 30 seconds to prevent hanging connections
- Specific exception handling for `requests.exceptions.RequestException`
- Validation of configuration parameters before starting the sync
- Graceful handling of missing NPI numbers (records are skipped with a warning)
- Comprehensive logging at INFO, WARNING, and ERROR levels
- All unhandled exceptions are caught and logged before raising a RuntimeError

## Tables created

The connector creates the following tables in your destination:

| Table name         | Primary key                                   | Description                                                                                                                                                                                                                                                                                                                                                              |
|--------------------|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `PROVIDER`         | `number`                                      | Main provider information including enumeration type, creation/update timestamps, and flattened `basic` object fields (`organization_name`, `provider_name`, `credentials`, `authorized_official_information`, etc.)                                                                      |
| `ADDRESS`          | `number`, `address_purpose`                   | Provider addresses (`LOCATION` or `MAILING`) with fields: `address_1`, `address_2`, `city`, `state`, `postal_code`, `country_code`, `country_name`, `telephone_number`, `fax_number`, `address_type`                                                                                      |
| `TAXONOMY`         | `number`, `code`                              | Healthcare provider taxonomy/specialty information with fields: `taxonomy_group`, `description`, `state`, `license`, `primary`                                                                                                                    |
| `IDENTIFIER`       | `number`, `identifier`                        | Other provider identifiers such as state licenses with fields: `code`, `description`, `issuer`, `state`                                                                                                                                                                                  |
| `ENDPOINT`         | `number`, `endpoint`                          | Electronic health record endpoint information with fields: `endpointType`, `endpointTypeDescription`, `endpointDescription`, `affiliation`, `affiliationName`, `use`, `useDescription`, `useOtherDescription`, `contentType`, `contentTypeDescription`, `contentOtherDescription`, plus address fields                          |
| `OTHER_NAME`       | `number`, `code`, `type`                      | Alternative organization names with fields: `organization_name`, `type`                                                                                                                                                                                                                   |
| `PRACTICE_LOCATION`| `number`, `address_1`                         | Secondary practice location addresses with fields: `address_2`, `city`, `state`, `postal_code`, `country_code`, `country_name`, `telephone_number`                                                                                                |

All tables use the NPI `number` as the primary key or as part of a composite primary key, enabling easy joins across related data.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.