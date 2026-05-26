# Dgraph E-Commerce Connector Example

## Connector overview

This connector syncs e-commerce product catalog data from Dgraph graph databases into data warehouses via the GraphQL API. It demonstrates a production-ready implementation that preserves graph relationships in relational format, enabling advanced analytics on product catalogs, recommendations, and customer reviews.

The connector showcases best practices for syncing graph data:
- True incremental sync using DateTime filters (createdAt/updatedAt fields)
- Graph structure preservation via a separate relationships/edges table
- Per-table state checkpointing for efficient resumption
- E-commerce use case: products, categories, attributes, reviews, and their relationships

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
fivetran init <project-path> --template connectors/dgraph
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- True incremental sync using timestamp-based filtering on updatedAt/createdAt fields
- Graph relationship preservation through dedicated edges/relationships table
- Per-table state tracking with independent last_updated timestamps
- Pagination with configurable batch size (default: 100 records per page)
- Checkpointing every 500 records for reliable sync resumption
- GraphQL schema metadata extraction and tracking
- Automatic retry logic with exponential backoff (up to 5 retries)
- Authentication via X-Auth-Token header
- Support for both Dgraph GraphQL endpoint and admin API

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "dgraph_url": "<YOUR_DGRAPH_GRAPHQL_ENDPOINT_URL>",
  "api_key": "<YOUR_DGRAPH_API_KEY_OR_AUTH_TOKEN>"
}
```

Configuration parameters:
- `dgraph_url` (required) - The base URL of your Dgraph instance (e.g., `http://localhost:8080` or `https://your-instance.dgraph.io`). Must start with `http://` or `https://`.
- `api_key` (required) - Authentication token for accessing the Dgraph API.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses only the Python standard library and SDK-provided packages. No additional dependencies are required beyond what is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses API key authentication via the `X-Auth-Token` HTTP header. The authentication token is passed with every GraphQL request to both the `/graphql` and `/admin` endpoints.

To set up authentication, do the following:
1. Obtain an API key or auth token from your Dgraph instance.
2. Add the token to the `api_key` field in your `configuration.json` file.

Once the API key is provided, the connector automatically handles authentication in all GraphQL requests.
For local testing with Docker, authentication may be disabled by default in your Dgraph instance.

## Pagination

The connector implements offset-based pagination using Dgraph's GraphQL `first` and `offset` parameters. Refer to the `sync_categories`, `sync_attributes`, `sync_products`, and `sync_reviews` functions for implementation details.

Pagination logic:
- Each query fetches up to 100 records per page (configurable via the `__PAGE_SIZE` constant)
- The `offset` parameter advances by the number of records returned in each batch
- Pagination continues until fewer records than the page size are retrieved
- State is checkpointed after every 500 records (configurable via the `__CHECKPOINT_INTERVAL` constant)
- Per-table timestamp tracking enables true incremental sync

This approach prevents memory overflow when syncing large datasets and ensures reliable recovery from interruptions.

## Data handling

The connector implements true incremental sync with per-table state management. Refer to the `update` function and individual sync functions:

Sync operations:
1. Schema metadata sync (`sync_schema_metadata`) - Extracts GraphQL type definitions from admin API, performs full sync each time (small dataset)
2. Categories sync (`sync_categories`) - Syncs product categories with incremental filter on `updatedAt` field
3. Attributes sync (`sync_attributes`) - Syncs product attributes with incremental filter on `updatedAt` field
4. Products sync (`sync_products`) - Syncs products with relationships, using incremental filter on `updatedAt` field
5. Reviews sync (`sync_reviews`) - Syncs customer reviews with incremental filter on `createdAt` field

Graph structure preservation:
- All relationships are captured in a separate `relationships` table via the `create_edge_record` function
- Edge types include: `BELONGS_TO_CATEGORY`, `RELATED_TO`, `HAS_ATTRIBUTE`, `REVIEWS_PRODUCT`, `WRITTEN_BY_USER`, `HAS_PARENT`
- Each edge has a composite ID: `{source_id}_{relationship_type}_{target_id}`
- This enables graph reconstruction and relationship analysis in SQL

Data transformation:
- DateTime values are preserved in ISO 8601 format with UTC timezone
- All records include `synced_at` timestamps for audit tracking
- Related entities are tracked via count fields (e.g., `attributes_count`, `related_products_count`)
- Incremental sync uses `ge` (greater than or equal) filter on timestamp fields

## Error handling

The connector implements comprehensive error handling with retry logic. Refer to the `execute_graphql_query` function.

Error handling strategies:
- Authentication errors (401, 403): Fail immediately without retry, log as error
- Bad requests (400): Fail immediately with detailed error message, no retry
- Server errors (5xx): Retry up to 5 times with exponential backoff (base 2 seconds, max 60 seconds)
- Network errors (timeout, connection): Retry with exponential backoff, configurable timeout (30 seconds default)
- GraphQL errors: Log warnings but continue processing if data is present
- Unexpected exceptions: Log error and re-raise with context

Configuration validation (`validate_configuration`):
- Ensures required fields (dgraph_url, api_key) are present
- Validates URL format (must start with http:// or https://)
- Raises ValueError with descriptive message for invalid configuration

All errors are logged using the SDK logging framework with appropriate severity levels (info, warning, error).

## Tables created

The connector creates the following tables in the destination warehouse. The SDK automatically infers column data types from the synced data.

| Table | Primary Key | Description |
|-------|-------------|-------------|
| `product` | `product_id` | Product catalog with SKU, name, price, inventory status, and foreign key to category. Includes counts of related attributes and products. Contains timestamps for creation, updates, and sync tracking. |
| `category` | `category_id` | Product categories with hierarchical parent relationships. Includes name, description, and timestamps for creation, updates, and sync tracking. |
| `attribute` | `attribute_id` | Product attributes for faceted search including name, value, and optional units (e.g., brand, size, color, specs). Contains timestamps for creation, updates, and sync tracking. |
| `review` | `review_id` | Customer reviews with ratings, comments, author information, and foreign key to product. Contains creation and sync timestamps. |
| `relationship` | `edge_id` | Graph edges preserving all relationships between entities. Each edge contains source and target IDs/types, relationship type, and creation timestamp. |
| `schema_metadata` | `type_name` | GraphQL schema type definitions extracted from Dgraph admin API. Includes field counts and extraction timestamps. |

Relationship types in the `relationship` table:
- `BELONGS_TO_CATEGORY`: Product → Category
- `RELATED_TO`: Product → Product (recommendations)
- `HAS_ATTRIBUTE`: Product → Attribute
- `REVIEWS_PRODUCT`: Review → Product
- `WRITTEN_BY_USER`: Review → User
- `HAS_PARENT`: Category → Category (hierarchy)

Incremental sync fields:
- Products, categories, and attributes use `updated_at` for incremental filtering
- Reviews use `created_at` for incremental filtering (reviews are typically immutable)
- All tables include `synced_at` timestamps for audit tracking

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
