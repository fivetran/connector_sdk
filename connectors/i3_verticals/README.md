# I3 Verticals Burton Platform Connector Example

> Note: This connector is a draft that has not been validated through direct testing against a live API. It is intended as a starting point and example implementation that should be confirmed and tested before production use.

## Connector overview
This connector integrates with the I3 Verticals Burton Platform REST API (v2) to synchronize payment and transaction data into your destination. It fetches charges, refunds, customers, distributions, merchants, and accounts, providing a complete view of payment operations. The connector implements PCI-safe data handling by automatically excluding sensitive card and account fields.

I3 Verticals is a payment technology company whose Burton Platform provides APIs for managing payment processing, customer records, merchant accounts, and settlement distributions.

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
fivetran init <project-path> --template connectors/i3_verticals
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Syncs 6 payment-related tables: charges, refunds, customers, distributions, merchants, and accounts
- Incremental sync using timestamp-based high-water-mark cursors per table
- PCI-safe data handling with automatic exclusion of sensitive fields (card numbers, CVV, PINs, routing numbers)
- OAuth 2.0 client credentials authentication with proactive token refresh
- Configurable rate limiting and page size
- Flexible response envelope parsing for undocumented API response formats
- Recursive record flattening with nested dict support
- Periodic checkpointing every 1000 records for large tables
- Retry logic with exponential backoff for transient errors (429, 5xx)
- Automatic re-authentication on 401 responses

## Configuration file
The configuration file contains OAuth credentials and API connection parameters.

```json
{
  "client_id": "<YOUR_CLIENT_ID>",
  "client_secret": "<YOUR_CLIENT_SECRET>",
  "base_url": "<YOUR_I3_VERTICALS_BASE_URL>",
  "page_size": "100",
  "rate_limit_rps": "2"
}
```

Configuration parameters:
- `client_id` (required): OAuth 2.0 client ID for the Burton Platform API.
- `client_secret` (required): OAuth 2.0 client secret for the Burton Platform API.
- `base_url` (required): Base URL of the Burton Platform API instance.
- `page_size` (optional): Number of records per page for paginated requests. Defaults to `100`.
- `rate_limit_rps` (optional): Maximum requests per second. Defaults to `2`.

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector uses standard libraries provided by Python and does not require any additional packages.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses OAuth 2.0 client credentials flow. The connector posts `client_id` and `client_secret` to the Burton Platform's token endpoint and receives a bearer token with a configurable expiry (typically 3599 seconds). Tokens are cached and refreshed proactively 5 minutes before expiry to avoid mid-sync failures. On 401 responses, the connector forces a token refresh and retries. Refer to `_get_auth_token`.

To obtain credentials:
1. Log in to the I3 Verticals Burton Platform portal.
2. Navigate to the API credentials section.
3. Generate or retrieve your OAuth client ID and client secret.
4. Add these values to your `configuration.json` file.

## Pagination
The connector uses offset-based pagination with configurable page size (default: 100 records per request). Refer to `_sync_table`.

Pagination details:
- Parameters: `limit` and `offset` query parameters
- The connector starts at `offset=0` and increments by the page size after each request
- Pagination stops when the API returns fewer records than the page size
- The connector also checks for `has_more` and `next` fields in the response envelope

## Data handling
- Nested JSON objects are recursively flattened using underscore separators (e.g., `address.city` becomes `address_city`). Refer to `_flatten_record`.
- Array fields are serialized as JSON strings.
- PCI-sensitive fields are automatically excluded at any nesting level: `card_number`, `account_number`, `routing_number`, `cvv`, `pin`, `security_code`, `expiration_date`.
- Timestamp values are normalized to ISO 8601 format. Unix timestamps (integer or float) are converted to UTC ISO strings. Refer to `_normalize_timestamp`.
- Schema column types are inferred automatically by Fivetran from the data.

## Error handling
- Automatic retry with exponential backoff (base 2 seconds, max 60 seconds) for 429, 503, and 5xx errors, up to 5 attempts. Refer to `_api_request`.
- Respects `Retry-After` response headers for rate limit backoff.
- Automatic token refresh and retry on 401 responses.
- Non-retryable 4xx client errors (other than 401 and 429) raise immediately.
- Per-table errors checkpoint current state before re-raising to preserve progress.
- Configurable rate limiting between requests to stay within API quotas.

## Tables created

The connector creates 6 tables:

- `charges` – Payment charge transactions (primary key: `charge_id`). Incremental sync by `charge_timestamp`.
- `refunds` – Refund transactions (primary key: `refund_id`). Incremental sync by `refund_timestamp`.
- `customers` – Customer records (primary key: `customer_id`). Incremental sync by `created_at`.
- `distributions` – Settlement and distribution data (primary key: `distribution_id`). Incremental sync by `distribution_date`.
- `merchants` – Merchant metadata (primary key: `merchant_id`). Incremental sync by `created_at`.
- `accounts` – Payment account metadata (primary key: `account_id`). Incremental sync by `created_at`.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
