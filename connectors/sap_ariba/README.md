# SAP Ariba Purchase Orders Connector Example

## Connector overview
This example demonstrates how to use the Fivetran Connector SDK to extract purchase order and line-item data from the SAP Ariba API. The connector retrieves purchase order headers and details, processes them into row-oriented records, and loads them into a Fivetran destination. It also supports paging, timestamp normalization, and retry logic.

This connector uses the SAP Ariba Sandbox API for illustration, but it can be adapted for production tenants by updating the configuration values.

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
fivetran init <project-path> --template connectors/sap_ariba
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Fetches purchase order and item data from the SAP Ariba API.
- Handles pagination using `$top` and `$skip` query parameters.
- Tracks sync progress using state and checkpoints.
- Converts SAP Ariba timestamps to ISO 8601 UTC format.
- Retries API calls automatically for rate limits or network failures.
- Performs idempotent data loading using `op.upsert`.

## Configuration file
The connector reads configuration values from `configuration.json`, which defines the authentication values required to access SAP Ariba.

Example:
{
  "api_key": "<YOUR_SAP_ARIBA_API_KEY>"
}

Key descriptions:
- `api_key` (required) – SAP Ariba API key used for authentication.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The `requirements.txt` file lists additional Python dependencies used by the connector. This example does not require any external libraries beyond those preinstalled in the Fivetran execution environment.

## Authentication
The connector authenticates using a single API key passed through HTTP headers. The API key is supplied by the `api_key` field in `configuration.json` and is applied to all API requests.

Refer to `make_api_request()` in `connector.py`.

## Pagination
The SAP Ariba API uses the `$top` and `$skip` query parameters to return paginated data. The connector increments the `$skip` value after every page and continues making requests until the API returns no additional records.

Refer to `sync_rows()` in `connector.py`.

## Data handling
The connector retrieves, parses, normalizes, and loads SAP Ariba data into destination tables. Every record is delivered using `op.upsert`, and large sync operations periodically call `op.checkpoint(state)` to save progress. Timestamp fields returned in Ariba date format are converted to ISO 8601 using the `convert_to_iso` helper.

Refer to `update()` and `filter_columns()` in `connector.py`.

## Error handling
The connector includes automatic retry logic for transient errors and rate-limited responses. Error handling is performed in `make_api_request()`, which uses backoff logic, raises authentication errors, and logs unexpected responses. 

## Tables created

The connector creates the `ORDER` and `ITEM` tables in the destination from SAP Ariba purchase order data (refer to the `schema()` function for more details):

### ORDER

- Primary key: `payloadId`, `revision`, `rowId`
- Columns:
  - `documentNumber` (STRING): Purchase order document number
  - `orderDate` (UTC_DATETIME): Date the purchase order was created
  - `supplierName` (STRING): Name of the supplier
  - `supplierANID` (STRING): Supplier's Ariba Network ID
  - `buyerANID` (STRING): Buyer's Ariba Network ID
  - `customerName` (STRING): Name of the customer
  - `systemId` (STRING): System identifier
  - `payloadId` (STRING): Unique payload identifier
  - `revision` (STRING): Document revision number
  - `endpointId` (STRING): Endpoint identifier
  - `created` (UTC_DATETIME): Timestamp when record was created
  - `status` (STRING): Current status of the purchase order
  - `documentStatus` (STRING): Document status
  - `amount` (DOUBLE): Purchase order amount
  - `numberOfInvoices` (INT): Count of associated invoices
  - `invoiced_amount` (DOUBLE): Total invoiced amount
  - `company_code` (STRING): Company code
  - `rowId` (INT): Unique row identifier for this sync
  - `last_updated_at` (UTC_DATETIME): Timestamp of last sync

### ITEM

- Primary key: `documentNumber`, `lineNumber`, `rowId`
- Columns:
  - `documentNumber` (STRING): Reference to parent purchase order number
  - `lineNumber` (INT): Line item number within the purchase order
  - `quantity` (DOUBLE): Ordered quantity
  - `unitOfMeasure` (STRING): Unit of measurement for quantity
  - `supplierPart` (STRING): Supplier's part number
  - `buyerPartId` (STRING): Buyer's part identifier
  - `manufacturerPartId` (STRING): Manufacturer's part identifier
  - `description` (STRING): Item description
  - `itemShipToName` (STRING): Ship-to location name
  - `itemShipToStreet` (STRING): Ship-to street address
  - `itemShipToCity` (STRING): Ship-to city
  - `itemShipToState` (STRING): Ship-to state or province
  - `itemShipToPostalCode` (STRING): Ship-to postal code
  - `itemShipToCountry` (STRING): Ship-to country
  - `isoCountryCode` (STRING): ISO country code for ship-to location
  - `itemShipToCode` (STRING): Ship-to location code
  - `itemLocation` (STRING): Item location identifier
  - `requestedDeliveryDate` (UTC_DATETIME): Requested delivery date
  - `requestedShipmentDate` (UTC_DATETIME): Requested shipment date
  - `rowId` (INT): Unique row identifier for this sync
  - `last_updated_at` (UTC_DATETIME): Timestamp of last sync

## Additional considerations
This example demonstrates how to work with timestamp conversion, pagination, and API retry patterns. It may require modifications before being used in production environments. For assistance, contact Fivetran Support.
