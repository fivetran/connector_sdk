# DataCamp LMS Catalog API Connector Example

## Connector overview

The [DataCamp](https://www.datacamp.com/) custom connector for Fivetran fetches course catalog data from the DataCamp LMS Catalog API and syncs it to your destination. This connector syncs data from content endpoints, including courses, projects, tracks, practices, assessments, and custom tracks.

The connector implements bearer token authentication with comprehensive retry logic and provides robust data flattening with breakout tables for nested relationships. It supports both live production servers and mock/test environments through optional URL prefix configuration, following Fivetran best practices for reliability, security, and maintainability.

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
fivetran init <project-path> --template connectors/data_camp
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

The connector supports the following features:

- **Multiple content types**: Supports courses, projects, tracks, practices, assessments, and custom tracks
- **Bearer token authentication**: Secure authentication using DataCamp API access tokens
- **Flexible server configuration**: Optional base_url parameter supports live production and mock/test environments
- **Retry logic with exponential backoff**: Automatic retries for failed API requests with exponential backoff 
- **Data flattening**: Comprehensive flattening of nested objects and arrays into relational structures
- **Breakout tables**: Separate tables for nested relationships (chapters, topics, content)
- **State management**: Maintains sync state with checkpointing for reliable syncs
- **Error handling**: Individual record error handling without stopping entire sync
- **Comprehensive logging**: Detailed logging for troubleshooting and monitoring with retry attempt tracking

## Configuration file

The connector requires bearer token authentication for the DataCamp LMS Catalog API. The base URL is optional and defaults to the live DataCamp API endpoint.

```json
{
  "bearer_token": "<YOUR_DATACAMP_BEARER_TOKEN>",
  "base_url": "<YOUR_OPTIONAL_DATACAMP_BASE_URL>"
}
```

### Configuration parameters

- `bearer_token` (required): Your DataCamp API bearer token for authentication.
- `base_url` (optional): Custom base URL for the DataCamp API. This parameter is optional and you have two options:
  - Leave blank to use the default DataCamp production server: `https://lms-catalog-api.datacamp.com`
  - You can specify a URL for testing or mock environments.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector example uses the standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector uses bearer token authentication with the DataCamp LMS Catalog API. The authentication is handled in the `update` function through the following process:

- Using a pre-configured bearer token for all API requests.
- Adding the token to the authorization header as `Bearer {token}`.
- Validating token presence during connector initialization.
- Handling authentication errors gracefully with detailed logging.

To obtain the necessary credentials:
1. Contact your DataCamp account representative to set up API access.
2. Request bearer token credentials for the LMS Catalog API.
3. Ensure your token has access to all required catalog endpoints.

## Pagination

The DataCamp LMS Catalog API does not support traditional pagination. The connector processes each endpoint as a complete dataset:

- Each endpoint returns the complete current catalog
- Processes one endpoint type at a time
- Uses checkpointing to track progress through endpoints
- The connector can resume from the last successfully processed endpoint

Refer to the `update` function for the sequential endpoint processing logic.

## Data handling

The connector processes JSON data from the DataCamp API and transforms it into structured records using a clean, generic architecture. To achieve that the connector:

- Uses a single `process_endpoint` function that handles all content types with configurable parameters for different processing requirements
- Uses a single `flatten_item` function that handles all content types with configurable parameters for different flattening behaviors
- Flattens nested dictionaries (like topic information) while preserving important relationships
- Creates separate tables for nested arrays (chapters, topics, and content) using configurable breakout parameters
- Maintains all original field names and values where possible
- Uses natural keys from the API (`id` fields)
- Uses clear variable names like `flattened_item_data` for better code readability
- Processes each endpoint with specific configuration parameters

The `update` function processes each content type with a specific configuration:
- **Endpoint configuration**: URL, table name, and primary key information from `__ENDPOINTS` constant
- **Flatten parameters**: Content-specific flattening options (skip_keys, flatten_topic, flatten_licenses, etc.)
- **Breakout configuration**: Optional child table specifications for nested arrays

Data is delivered to Fivetran using upsert operations for each record, ensuring data consistency and enabling incremental updates.

## Error handling

The connector implements comprehensive error handling strategies following Fivetran best practices:

- Failed records don't stop the entire sync process
- HTTP errors are caught and logged with severity levels
- Automatic retries with exponential backoff 
- Configurable timeout (30 seconds default) for API requests to prevent hanging
- Uses Fivetran's logging framework with retry attempt tracking
- Checkpoints progress after each endpoint to enable recovery

## Tables created

The connector creates the following tables in your destination:

| Table name              | Primary key              | Description |
|-------------------------|--------------------------|-------------|
| `COURSE`                | `id`                     | Course catalog with flattened course data |
| `COURSE_CHAPTER`        | `id`, `course_id`        | Breakout table for course chapters |
| `PROJECT`               | `id`                     | Project catalog with flattened project data |
| `PROJECT_TOPIC`         | `project_id`, `name`     | Breakout table for project topics |
| `TRACK`                 | `id`                     | Learning track catalog |
| `TRACK_CONTENT`         | `track_id`, `position`   | Breakout table for track content items |
| `PRACTICE`              | `id`                     | Practice exercise catalog |
| `ASSESSMENT`            | `id`                     | Assessment catalog |
| `CUSTOM_TRACK`          | `id`                     | Custom learning track catalog |
| `CUSTOM_TRACK_CONTENT`  | `custom_track_id`, `position` | Breakout table for custom track content |

All main tables include flattened versions of complex nested objects, while breakout tables maintain relationships through foreign keys.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
