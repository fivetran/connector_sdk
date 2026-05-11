# Databricks Best Buy Retail Intelligence Connector Example

## Connector overview

This connector syncs product catalog data from the [Best Buy Products API](https://bestbuyapis.github.io/api-reference/) and enriches each product with AI-powered retail analytics using the Databricks [ai_query()](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function. Enrichments include competitive positioning assessment, price optimization recommendations, and customer sentiment analysis.

This connector demonstrates Fivetran's value for the Retail vertical on Databricks, mapping directly to the Databricks FY27 Retail Outcome Map outcomes: Dynamic Price Optimization, Product Affinity, Assortment Optimization, and Behavioral Segmentation.

Optional [Genie Space](https://docs.databricks.com/en/genie/index.html) creation after data lands for natural language retail analytics.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A Best Buy Developer API key (free at https://bestbuy.com/developer)
- A Databricks workspace with a SQL Warehouse that supports `ai_query()` (required for AI enrichment; optional for data-only mode)
- A Databricks Personal Access Token (PAT) with SQL execution permissions

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs product catalog data from the Best Buy Products API with pricing, reviews, and availability
- AI enrichment via Databricks `ai_query()` with Claude Sonnet 4.6 for competitive positioning, price optimization, and sentiment analysis
- Optional category filtering via `search_category` parameter
- Optional Genie Space creation with retail-specific instructions and sample questions
- Configurable enrichment budget via `max_enrichments` to control costs
- Data-only mode when `enable_enrichment` is set to `false`
- Sorted by customer review count to prioritize high-engagement products
- Async polling for long-running ai_query() statements

## Configuration file

The `configuration.json` file contains the following parameters:

```json
{
  "api_key": "<BESTBUY_API_KEY>",
  "databricks_workspace_url": "<DATABRICKS_WORKSPACE_URL>",
  "databricks_token": "<DATABRICKS_PAT_TOKEN>",
  "databricks_warehouse_id": "<DATABRICKS_WAREHOUSE_ID>",
  "databricks_model": "<DATABRICKS_MODEL_NAME>",
  "enable_enrichment": "<TRUE_OR_FALSE>",
  "enable_genie_space": "<TRUE_OR_FALSE>",
  "genie_table_identifier": "<CATALOG.SCHEMA.TABLE>",
  "search_category": "<CATEGORY_NAME_OR_EMPTY>",
  "max_products": "<MAX_PRODUCTS_PER_SYNC>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "batch_size": "<BATCH_SIZE>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

- `api_key` (required): Best Buy Developer API key (free at https://bestbuy.com/developer)
- `databricks_workspace_url` (required when enrichment or Genie enabled): Full Databricks workspace URL including `https://`
- `databricks_token` (required when enrichment or Genie enabled): Databricks Personal Access Token
- `databricks_warehouse_id` (required when enrichment or Genie enabled): SQL Warehouse ID
- `databricks_model` (optional): Databricks Foundation Model name. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` for data-only mode. Default: `true`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path
- `search_category` (optional): Best Buy category name to filter products (e.g., "Laptops", "TVs")
- `max_products` (optional): Maximum products per sync. Default: `25`. Maximum: `500`
- `max_enrichments` (optional): Maximum ai_query() calls per sync. Default: `10`. Maximum: `100`
- `batch_size` (optional): Products per API page. Default: `25`
- `databricks_timeout` (optional): Timeout in seconds. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The Best Buy Products API requires a free Developer API key. Register at https://bestbuy.com/developer to obtain one.

Databricks access requires a Personal Access Token (PAT) with SQL execution permissions:

1. Navigate to your Databricks workspace
2. Click your username in the top-right corner and select **Settings**
3. Click **Developer** in the left panel
4. Click **Manage** next to **Access tokens**
5. Click **Generate new token**, provide a description, and click **Generate**
6. Copy the token value and set it as `databricks_token` in your `configuration.json`

## Pagination

The Best Buy Products API supports page-based pagination via `pageSize` parameter (max 100). The connector fetches up to `max_products` in a single page, sorted by customer review count descending to prioritize high-engagement products.

## Data handling

The `def update(configuration, state)` function orchestrates the sync:

1. Validates configuration via `def validate_configuration(configuration)` including Best Buy API key and Databricks credential checks
2. Fetches products from Best Buy API with optional category filtering via `def fetch_data_with_retry(session, url, params)`
3. Builds normalized records via `def build_product_record(product)` extracting SKU, pricing, reviews, manufacturer, category, and availability
4. If enrichment is enabled, enriches each product via `def enrich_product(session, configuration, record)` using ai_query() for competitive positioning, price optimization, and sentiment analysis
5. Upserts each enriched record and checkpoints state after each batch so interrupted syncs resume from the last completed batch rather than restarting from the beginning
6. If `enable_genie_space` is `true` and data was synced, creates a Genie Space via `def create_genie_space(session, configuration, state)` with retail-specific instructions and sample questions pointed at the destination table

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params)` provides exponential backoff for transient failures with immediate failure on auth errors (401, 403)
- `def call_ai_query(session, configuration, prompt)` catches specific exception types and returns None on failure, with async polling for PENDING states
- `def validate_configuration(configuration)` validates all parameters using `def _is_placeholder(value)`
- Sanity ceilings enforce maximum values for `max_products` (500) and `max_enrichments` (100)
- The session is always closed via a try/finally block

## Genie Space

When `enable_genie_space` is set to `true`, the connector creates a Databricks Genie Space after data lands. The Genie Space is configured with:

- Retail-specific instructions that guide the Genie agent to focus on competitive positioning, pricing trends, and customer sentiment insights
- Sample questions for common retail analytics queries
- A pointer to the destination table specified in `genie_table_identifier`

The Genie Space is created only once. The `genie_space_id` is persisted in the connector state to avoid creating duplicates on subsequent syncs.

Note: The `genie_table_identifier` must be a fully qualified Unity Catalog path (e.g., `my_catalog.my_schema.products_enriched`). The table must exist in the Databricks workspace before the Genie Space can query it, so the Genie Space is most useful after at least one successful sync with `fivetran deploy`.

## Tables created

### PRODUCTS_ENRICHED

The `PRODUCTS_ENRICHED` table consists of the following columns:

Primary key: `sku`

| Column | Type | Description |
|--------|------|-------------|
| `sku` | STRING | Best Buy SKU identifier |
| `name` | STRING | Product name |
| `sale_price` | FLOAT | Current sale price in USD |
| `regular_price` | FLOAT | Regular (non-sale) price in USD |
| `on_sale` | BOOLEAN | Whether the product is currently on sale |
| `percent_savings` | FLOAT | Percentage savings from regular price |
| `customer_review_average` | FLOAT | Average customer review score (0-5) |
| `customer_review_count` | INTEGER | Number of customer reviews |
| `manufacturer` | STRING | Product manufacturer name |
| `short_description` | STRING | Product description (truncated to 500 chars) |
| `category` | STRING | Product category name |
| `category_path` | STRING | JSON array of full category hierarchy |
| `condition` | STRING | Product condition (New, Refurbished, etc.) |
| `free_shipping` | BOOLEAN | Whether free shipping is available |
| `in_store_available` | BOOLEAN | In-store availability |
| `online_available` | BOOLEAN | Online availability |
| `url` | STRING | Product page URL on bestbuy.com |
| `competitive_positioning` | STRING | AI-classified market positioning (PREMIUM, MID_MARKET, VALUE, BUDGET). Populated when enrichment is enabled |
| `price_optimization` | STRING | AI-generated price optimization recommendation. Populated when enrichment is enabled |
| `price_action` | STRING | AI-recommended price action (INCREASE, MAINTAIN, DECREASE, CLEARANCE). Populated when enrichment is enabled |
| `sentiment_summary` | STRING | AI-generated customer sentiment analysis. Populated when enrichment is enabled |
| `retail_category_ai` | STRING | AI-classified retail category. Populated when enrichment is enabled |
| `enrichment_model` | STRING | Databricks Foundation Model used for enrichment |

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

This connector demonstrates Fivetran's value for the Retail vertical on the Databricks Intelligence Platform. It maps directly to the Databricks FY27 Retail Outcome Map outcomes for Dynamic Price Optimization, Product Affinity, and Assortment Optimization.

The Best Buy Products API requires a free Developer API key. Rate limits vary by key tier. The connector includes rate limiting delays between requests.

Databricks `ai_query()` consumes SQL Warehouse compute credits. Use `max_enrichments` to control costs. Set `enable_enrichment` to `false` for data-only mode.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
