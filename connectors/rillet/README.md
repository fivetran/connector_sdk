# Rillet Connector Example

## Connector overview
This connector fetches core accounting data from the Rillet API and syncs it into Fivetran destination tables. 
Supported resources: accounts, subsidiaries, products, customers, contracts, invoices, invoice payments, credit memos, vendors, vendor credits, bills, charges, reimbursements, journal entries, bank accounts, bank transactions, tax rates, and fields.

## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

1. Obtain an API key following the steps in the [Authentication](#authentication) section.
2. Copy `connectors/rillet/configuration.json` and populate `api_key` with your generated API key.
3. Run the connector locally using `fivetran debug --connector connectors/rillet/connector.py`

## Features
- Cursor-based pagination (`pagination.next_cursor`) across Rillet endpoints.
- Incremental sync using `updated.gt` and `updated_at` timestamps.
- Retry logic with exponential backoff for transient errors and 429 rate-limited responses.
- Data integrity with `op.upsert` and checkpoint state after each batch.
- Separate destination tables for each resource.

## Configuration file
The connector requires the following configuration parameters:

```json
{
  "api_key": "<YOUR_API_KEY>",
  "base_url": "<YOUR_BASE_URL_OPTIONAL_DEFAULT_HTTPS_API_RILLET_COM>",
  "api_version": "<YOUR_API_VERSION_DEFAULT_3>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

This connector uses API key authentication to connect to the Rillet API. The API key is specified in the `configuration.json` file and passed to the API as a Bearer token in the Authorization header.

To set up authentication:

1. **Request Access**: Contact your Rillet Account Manager or Customer Success representative to enable API access for your organization. API keys cannot be generated until this access is activated.
2. **Navigate to Settings**: Once enabled, log in to the Rillet Dashboard and go to Organization Settings.
3. **Access API Management**: Select the API Access or API Keys section within the settings.
4. **Generate the Key**: Click on Create API Key or the Add button. You will be prompted to give your key a descriptive name to identify its purpose.
5. **Configure the Connector**: Copy `connectors/rillet/configuration.json` and populate `api_key` with your generated API key.

## Data handling
- `schema()` defines the table names and primary keys.
- `update()` loops over configured collections and fetches data from Rillet endpoints.
- Each record is upserted using `op.upsert`.
- State keys such as `accounts_cursor`, `accounts_last_updated_at` in `state.json` store progress.

## Error handling
- `validate_configuration()` checks that `api_key` is present and non-empty.
- Requests use retry/backoff for 429/5xx and fail fast on 4xx.
- `RuntimeError` wraps unexpected execution problems and stops sync for Fivetran.

## Tables created
The connector defines destination tables in `schema()` and creates one table per synced resource. Each table uses `id` as the primary key and includes the fields returned by the corresponding Rillet API response.

| Table | Primary key | Description |
| --- | --- | --- |
| `account` | `id` | Records from `/accounts` |
| `subsidiary` | `id` | Records from `/subsidiaries` |
| `product` | `id` | Records from `/products` |
| `customer` | `id` | Records from `/customers` |
| `contract` | `id` | Records from `/contracts` |
| `invoice` | `id` | Records from `/invoices` |
| `invoice_payment` | `id` | Records from `/invoice-payments` |
| `credit_memo` | `id` | Records from `/credit-memos` |
| `vendor` | `id` | Records from `/vendors` |
| `vendor_credit` | `id` | Records from `/vendor-credits` |
| `bill` | `id` | Records from `/bills` |
| `charge` | `id` | Records from `/charges` |
| `reimbursement` | `id` | Records from `/reimbursements` |
| `journal_entry` | `id` | Records from `/journal-entries` |
| `bank_account` | `id` | Records from `/bank-accounts` |
| `bank_transaction` | `id` | Records from `/bank-transactions` |
| `tax_rate` | `id` | Records from `/tax-rates` |
| `field` | `id` | Records from `/fields` |

Refer to the `schema()` function in `connectors/rillet/connector.py` for the table definitions.

## Additional considerations
- `base_url` defaults to `https://api.rillet.com` if omitted.
- Set `api_version` in config for API stability (defaults to 3).
- Webhook docs at https://docs.api.rillet.com/docs/webhooks (not used in connector pull sync).
- For very large datasets, you may further shard by organization subset query parameters.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
