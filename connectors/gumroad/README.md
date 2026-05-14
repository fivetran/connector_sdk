# Gumroad Connector Example

## Connector overview

This connector fetches sales, products, and subscriber data from the Gumroad API and syncs it to your destination. Gumroad is a platform for creators to sell digital products and memberships. The connector supports incremental syncing of sales data based on timestamps and full refreshes of products and subscribers. It handles pagination automatically and flattens nested JSON objects into relational tables for easy querying and analysis.

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
fivetran init <project-path> --template connectors/gumroad
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental syncing of sales data using date-based filtering
- Full syncing of products and their variants
- Automated pagination handling for large datasets
- Subscriber data collection across all products
- Flattening of nested JSON structures into relational tables
- Automatic retry logic with exponential backoff for API failures
- Configurable checkpointing for resumable syncs

## Configuration file

The connector requires the following configuration parameter:

```json
{
  "access_token": "<YOUR_GUMROAD_ACCESS_TOKEN>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector does not require any additional Python packages beyond those pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses access token authentication to connect to the Gumroad API. The access token is obtained through OAuth 2.0 authentication with Gumroad.

To set up authentication:

1. Log in to your [Gumroad account] (https://gumroad.com).

2. Navigate to **Settings** > **Advanced** > **Applications**.

3. Click **Create new application** and fill in the required details.

4. Once the application is created, click **Generate access token**.

5. Copy the access token and add it to the `configuration.json` file as the value for `access_token`.

6. Ensure your application has the `view_sales` scope to access sales metrics and subscriber information.

## Pagination

The connector handles pagination automatically for endpoints that return paginated results. The Gumroad API uses a `page_key` parameter for pagination, where the response includes a `next_page_key` field that indicates the key for the next page of results.

The pagination logic is implemented in the `sync_sales()`, `sync_payouts()`, and `fetch_product_subscribers()` functions. The connector continues fetching pages until no `next_page_key` is returned, indicating all data has been retrieved.

For subscribers, the connector sets `paginated=true` in the request to enable pagination with a 100-item limit per page.

## Data handling

The connector processes data from four main Gumroad API endpoints:

- Sales endpoint: Fetches transaction data with support for incremental syncing using the `after` parameter to filter by date. Nested objects like `card` and `affiliate` are flattened into top-level columns. Complex fields like `variants` and `custom_fields` are serialized as JSON strings.

- Products endpoint: Retrieves all products for the authenticated user. Product variants are extracted into a separate `product_variants` table to enable analysis of pricing and options. Fields like `tags`, `custom_fields`, and `purchasing_power_parity_prices` are stored as JSON strings for flexibility.

- Subscribers endpoint: Iterates through all products and fetches active subscribers for each. The connector handles pagination automatically and combines data from multiple products into a single subscribers table.

- Payouts endpoint: Fetches payout data with support for incremental syncing using the `after` parameter to filter by date. Includes both completed and upcoming payouts, tracking payment processor information and bank account details.

The flattening logic is handled by dedicated functions: `flatten_sale()`, `flatten_product()`, `flatten_subscriber()`, and `flatten_payout()`. These functions extract nested objects and convert complex data types to simple key-value pairs suitable for relational databases.

## Error handling

The connector implements comprehensive error handling with retry logic and exponential backoff. The `make_api_request()` function handles transient errors by retrying failed requests up to 3 times with increasing delays (1s, 2s, 4s).

Retryable errors include:
- HTTP 429 (Rate Limit Exceeded)
- HTTP 5xx (Server Errors)
- Request timeouts
- Connection errors

Non-retryable errors such as authentication failures (HTTP 401) or invalid requests (HTTP 400) are logged and raised immediately without retry attempts. All errors are logged using the SDK's logging mechanism with appropriate severity levels (warning for retries, error for final failures).

## Tables created

The connector creates the following tables in the destination:

| Table Name | Primary Key | Description |
|------------|-------------|-------------|
| `sales` | `id` | Transaction and purchase data with customer and payment information. |
| `products` | `id` | Product information including name, description, pricing, and sales metrics. |
| `subscribers` | `id` | Subscription data with subscriber details and subscription status. |
| `product_variants` | `product_id`, `variant_title`, `option_name` | Product variant options with pricing differences and configuration. |
| `payouts` | `id` | Payout information including amounts, currency, status, and payment processor details. |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
