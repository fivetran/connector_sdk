# Connector SDK Goshippo API Connector Example

## Connector overview

This connector syncs shipment data from the Goshippo API to your destination using the Fivetran Connector SDK. Goshippo is a shipping platform that provides APIs to manage shipments, get shipping rates, create labels, and track packages.

The connector fetches shipment records along with related data such as shipping rates, parcel details, and messages. It supports incremental synchronization by tracking the last updated timestamp of shipments and only fetching new or updated records in subsequent syncs.

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
fivetran init <project-path> --template connectors/goshippo
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental sync - Fetches only new or updated shipments since the last sync by tracking the `object_updated` timestamp
- Pagination support - Handles API pagination using next-page URL tokens
- Retry logic - Implements exponential backoff for transient errors (rate limits, timeouts, 5xx errors)
- Related data handling - Syncs shipment rates, parcels, and messages along with shipment records
- Regular checkpointing - Checkpoints state every 100 records to ensure sync can resume from the correct position
- Comprehensive error handling - Catches specific exceptions and provides detailed error logging

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "api_token": "<YOUR_GOSHIPPO_API_TOKEN>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

This connector uses API token authentication to connect to the Goshippo API. The API token is passed in the `Authorization` header as `ShippoToken <api_token>` (refer to the `build_headers()` function).

To obtain your API token:

1. Log in to your [Goshippo account](https://apps.goshippo.com/login).
2. Go to **Settings > API**.
3. Copy your API token or generate a new one.
4. Add the API token to the `configuration.json` file.

## Pagination

The connector implements next-page URL pagination to handle large datasets (refer to the `sync_shipments()` function). The Goshippo API returns a `next` URL in the response when more pages are available. The connector extracts the `page_token` parameter from this URL using the `extract_page_token()` function and includes it in subsequent requests via the `build_query_params()` function.

The pagination loop continues until the API returns no `next` URL, indicating that all available data has been fetched. Each page fetches up to 25 shipments as defined by the `__PAGE_SIZE` constant.

## Data handling

The connector processes shipment data and related entities as follows:

1. Main shipments - The `flatten_shipment()` function extracts and flattens shipment fields including addresses (from, to, return), carrier accounts, and metadata. Nested objects like addresses are flattened into individual columns with prefixes (`from_`, `to_`, `return_`).
2. Related data - The `process_shipment()` function coordinates upserting the main shipment record and its related data:
   - Rates - The `process_rates()` function processes shipping rate options including carrier, amount, service level, and estimated delivery days.
   - Parcels - The `process_parcels()` function processes parcel dimensions, weight, and metadata.
   - Messages - The `process_messages()` function processes API messages with a generated unique ID combining shipment ID and message index.

The connector uses the `op.upsert()` operation to insert or update records in the destination tables. Records are processed immediately as they are fetched to avoid loading large datasets into memory.

## Error handling

The connector implements comprehensive error handling with retry logic (refer to the `fetch_shipments_page()`, `handle_response_status()`, and `handle_request_exception()` functions):

- Retry logic - The connector retries requests up to 3 times (`__MAX_RETRIES`) for transient errors including:
   - Network timeouts and connection errors
   - Rate limiting (HTTP 429)
   - Server errors (HTTP 500, 502, 503, 504)
- Exponential backoff - The `calculate_retry_delay()` function implements exponential backoff with a maximum delay of 60 seconds.
- Fail fast - The connector immediately raises exceptions for permanent errors like authentication failures (4xx errors) without retrying.
- Specific exception handling - The connector catches specific exceptions (`RuntimeError`, `requests.RequestException`, `ValueError`, `KeyError`, `requests.Timeout`, `requests.ConnectionError`, `AttributeError`, `IndexError`, `TypeError`) rather than generic exceptions to avoid masking unexpected errors.

All errors are logged using the SDK's logging framework before being raised.

## Tables created

The connector creates the `SHIPMENT`, `SHIPMENT_RATES`, `SHIPMENT_PARCELS`, and `SHIPMENT_MESSAGES` tables in the destination. 

Refer to the `schema()` function for more details.

### SHIPMENTS

| Column | Type | Description |
|--------|------|-------------|
| `object_id` | STRING | Unique identifier for the shipment (Primary Key) |
| `object_created` | STRING | Timestamp when shipment was created |
| `object_updated` | STRING | Timestamp when shipment was last updated |
| `object_owner` | STRING | Owner of the shipment object |
| `status` | STRING | Current status of the shipment |
| `metadata` | STRING | Additional metadata |
| `shipment_date` | STRING | Date of shipment |
| `test` | STRING | Test mode indicator |
| `order` | STRING | Associated order ID |
| `carrier_accounts` | STRING | JSON array of carrier account IDs |
| `customs_declaration` | STRING | Customs declaration ID |
| `alternate_address_to` | STRING | JSON object of alternate delivery address |
| `from_name` | STRING | Sender name |
| `from_company` | STRING | Sender company |
| `from_street1` | STRING | Sender street address |
| `from_city` | STRING | Sender city |
| `from_state` | STRING | Sender state |
| `from_zip` | STRING | Sender ZIP code |
| `from_country` | STRING | Sender country |
| `from_phone` | STRING | Sender phone |
| `from_email` | STRING | Sender email |
| `to_name` | STRING | Recipient name |
| `to_company` | STRING | Recipient company |
| `to_street1` | STRING | Recipient street address |
| `to_city` | STRING | Recipient city |
| `to_state` | STRING | Recipient state |
| `to_zip` | STRING | Recipient ZIP code |
| `to_country` | STRING | Recipient country |
| `to_phone` | STRING | Recipient phone |
| `to_email` | STRING | Recipient email |
| `return_name` | STRING | Return address name |
| `return_company` | STRING | Return address company |
| `return_street1` | STRING | Return address street |
| `return_city` | STRING | Return address city |
| `return_state` | STRING | Return address state |
| `return_zip` | STRING | Return address ZIP code |
| `return_country` | STRING | Return address country |
| `return_phone` | STRING | Return address phone |
| `return_email` | STRING | Return address email |

### SHIPMENT_RATES

| Column | Type | Description |
|--------|------|-------------|
| `rate_object_id` | STRING | Unique identifier for the rate (Primary Key) |
| `shipment_object_id` | STRING | Associated shipment ID (Primary Key) |
| `amount` | STRING | Shipping cost amount |
| `currency` | STRING | Currency code |
| `provider` | STRING | Shipping carrier provider |
| `servicelevel_name` | STRING | Service level name |
| `servicelevel_token` | STRING | Service level token |
| `estimated_days` | STRING | Estimated delivery days |
| `duration_terms` | STRING | Duration terms |
| `carrier_account` | STRING | Carrier account ID |
| `object_created` | STRING | Timestamp when rate was created |

### SHIPMENT_PARCELS

| Column | Type | Description |
|--------|------|-------------|
| `parcel_object_id` | STRING | Unique identifier for the parcel (Primary Key) |
| `shipment_object_id` | STRING | Associated shipment ID (Primary Key) |
| `length` | STRING | Parcel length |
| `width` | STRING | Parcel width |
| `height` | STRING | Parcel height |
| `distance_unit` | STRING | Unit of distance measurement |
| `weight` | STRING | Parcel weight |
| `mass_unit` | STRING | Unit of weight measurement |
| `metadata` | STRING | Additional metadata |
| `object_created` | STRING | Timestamp when parcel was created |
| `object_updated` | STRING | Timestamp when parcel was last updated |

### SHIPMENT_MESSAGES

| Column | Type | Description |
|--------|------|-------------|
| `message_id` | STRING | Generated unique identifier (shipment_id_index) (Primary Key) |
| `shipment_object_id` | STRING | Associated shipment ID |
| `source` | STRING | Message source |
| `code` | STRING | Message code |
| `text` | STRING | Message text |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
