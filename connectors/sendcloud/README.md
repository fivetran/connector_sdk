# Sendcloud API Connector Example

## Connector overview

This connector integrates with the Sendcloud API to extract shipment data including packages, delivery times, parcels, shipping carriers, customs information, and error tracking. The connector uses cursor-based pagination to efficiently handle large datasets and implements incremental synchronization based on the updated_after timestamp. It flattens nested JSON objects and creates breakout tables for array fields to maintain normalized data structures in the destination.

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
fivetran init <project-path> --template connectors/sendcloud
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Incremental data synchronization using cursor-based pagination
- Automatic retry logic with exponential backoff for transient API failures
- Flattening of nested JSON objects into columnar format
- Breakout tables for array fields (parcels, documents, items, errors, customs)
- State management with checkpointing at page boundaries
- Support for both production and mock API servers
- Comprehensive error handling and logging

## Configuration file

The connector requires the following configuration parameters:

```json
{
  "username": "<YOUR_SENDCLOUD_API_USERNAME>",
  "password": "<YOUR_SENDCLOUD_API_PASSWORD>",
  "start_date": "<YYYY-MM-DD_FORMAT_EXAMPLE_2023-01-01>",
  "use_mock_server": "<TRUE_OR_FALSE_DEFAULT_FALSE>"
}
```

Configuration parameters:
- `username`: Your Sendcloud API public key (required)
- `password`: Your Sendcloud API secret key (required)
- `start_date`: ISO date to begin synchronization in YYYY-MM-DD format (required)
- `use_mock_server`: Set to "true" to use Stoplight mock server for testing, "false" for production API (optional, defaults to "false")

Note: Ensure that [`configuration.json`](configuration.json) file is not checked into version control to protect sensitive information.

## Requirements file

This connector does not require any additional Python packages beyond the pre-installed packages in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your [`requirements.txt`](requirements.txt).

## Authentication

This connector uses HTTP Basic Authentication to connect to the Sendcloud API. The credentials are specified in the configuration file and encoded as Base64 in the Authorization header (refer to the `get_auth_header()` function in [`connector.py`](connector.py)).

To set up authentication:

1. Log in to your Sendcloud account at https://account.sendcloud.com.
2. Navigate to **Settings > Integrations > API**.
3. Generate or retrieve your API public key (`username`) and secret key (`password`).
4. Add the `username` and `password` to the [`configuration.json`](configuration.json) file.
5. Set the `start_date` to begin synchronization from a specific date.

## Pagination

The connector implements cursor-based pagination to handle large datasets efficiently (refer to the `update()` and `determine_next_cursor()` functions in [`connector.py`](connector.py)).

The Sendcloud API returns pagination metadata in the response with a next_cursor field. The connector extracts this cursor and uses it in subsequent requests to fetch the next page. If the API does not provide an explicit cursor and the page is full, the connector generates a cursor using the encode_cursor function as a fallback mechanism. Pagination continues until no more records are returned or the API indicates there are no more pages.

## Data handling

The connector processes shipment data through multiple stages (refer to the `flatten_shipment_data()` and `process_shipment_arrays()` functions in [`connector.py`](connector.py)):

- Main shipment fields are flattened into the primary shipments table
- Nested single objects (addresses, prices, delivery dates) are flattened into the same table with prefixed column names
- Array fields are extracted into separate breakout tables with foreign keys
- Each table is designed with composite primary keys consisting of the shipment_id plus the unique identifier for that entity
- The connector uses immediate processing of each page rather than loading all data into memory

## Error handling

The connector implements comprehensive error handling with automatic retry logic (refer to the `fetch_shipments_page()` function in [`connector.py`](connector.py)):

- HTTP errors with status codes 400, 401, 403, 404 are treated as permanent failures and fail immediately without retry
- Transient errors (500, 502, 503, 504, timeouts, connection errors) trigger exponential backoff retry logic up to 3 attempts
- Each retry waits progressively longer: 1 second, 2 seconds, 4 seconds
- All errors are logged with appropriate severity levels for troubleshooting
- Invalid shipment records without IDs are skipped with warning logs
- API responses with unexpected data types are handled gracefully

## Tables created

The connector creates the following tables in the destination:

| Table Name          | Primary Key                                               | Description                                                   | Key Columns                                                                                                                                   |
|---------------------|-----------------------------------------------------------|---------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| shipment            | `id`                                                      | Main table with flattened shipment information                | order_number, from_name, from_address_line_1, to_name, to_address_line_1, ship_with_type, total_order_price_value, total_order_price_currency |
| shipment_parcel     | `shipment_id`, `parcel_id`                                | Parcels with tracking and dimensional information             | tracking_number, tracking_url, status_message, status_code, dimensions_length, dimensions_width, dimensions_height, weight_value, weight_unit |
| parcel_document     | `shipment_id`, `parcel_id`, `document_type`               | Parcel documents like labels and customs forms                | document_type, link, size                                                                                                                     |
| parcel_item         | `shipment_id`, `parcel_id`, `item_sku`                    | Items within each parcel                                      | item_id, item_description, item_quantity, item_weight_value, item_price_value, item_hs_code, item_origin_country                              |
| item_property       | `shipment_id`, `parcel_id`, `item_sku`, `property_name`   | Custom properties of items                                    | item_id, property_name, property_value                                                                                                        |
| parcel_label_note   | `shipment_id`, `parcel_id`, `note_order`                  | Label notes on parcels                                        | note_order, note_text                                                                                                                         |
| shipment_error      | `shipment_id`, `error_id`                                 | Errors associated with shipments                              | error_status, error_code, error_title, error_detail                                                                                           |
| customs_declaration | `shipment_id`, `declaration_text`                         | Customs declaration statements                                | declaration_text                                                                                                                              |
| customs_tax_number  | `shipment_id`, `tax_type`, `tax_name`, `tax_country_code` | Tax identification numbers for sender, receiver, and importer | tax_type, tax_name, tax_country_code, tax_number                                                                                              |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
