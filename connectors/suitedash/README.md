# SuiteDash CRM Connector Example

## Connector overview
This example shows how to use Connector SDK to extracts companies, contacts, and their relationships data from the [SuiteDash CRM](https://app.suitedash.com/secure-api), handling proper data flattening and pagination. It's designed for organizations using SuiteDash CRM who want to analyze their customer and prospect data in their data warehouse.


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
fivetran init <project-path> --template connectors/suitedash
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- **Companies sync**: Extracts all company records from the `/companies` endpoint.
- **Contacts sync**: Extracts all contact records from the `/contacts` endpoint.
- **Relationship mapping**: Creates a separate table for contact-company relationships data.
- **Data flattening**: Flattens nested JSON objects (primaryContact, category, address) into flat table columns.
- **Array handling**: Converts tags and circles arrays to comma-separated strings.
- **Pagination support**: Handles SuiteDash's next-page-URL pagination automatically.
- **Error handling**: Robust error handling for API failures and network issues.


## Configuration file
The configuration file defines the authentication credentials required to connect to the SuiteDash API.

```json
{
  "public_id": "<YOUR_SUITEDASH_PUBLIC_ID>",
  "secret_key": "<YOUR_SUITEDASH_SECRET_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The requirements.txt file specifies additional Python libraries required by the connector. Following Fivetran best practices, this connector doesn't require additional dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector uses SuiteDash's secure API authentication mechanism which requires:
- `X-Public-ID`: Your SuiteDash account public ID (UUID format)
- `X-Secret-Key`: Your SuiteDash secret key

To obtain these credentials:
1. Log into your SuiteDash account.
2. Navigate to **Account Settings** > **API Settings**.
3. Generate or copy your Public ID and Secret Key.
4. Configure these values in your `configuration.json` file.


## Pagination
The connector handles SuiteDash's pagination using the next-page-URL mechanism. The API returns pagination metadata in the response:

```json
{
  "meta": {
    "pagination": {
      "pageSize": 10,
      "totalPages": 2,
      "totalItems": 15,
      "currentPageNumber": 1,
      "previousPage": null,
      "nextPage": "https://app.suitedash.com/secure-api/companies?page=2"
    }
  }
}
```

The pagination logic is implemented in the `sync_endpoint_with_pagination()` function.


## Data handling
The connector processes and transforms SuiteDash data as follows:

**Data flattening**: Nested objects are flattened using the `flatten_nested_object()` function:
- `primaryContact` → `primaryContact_uid`, `primaryContact_first_name`, etc.
- `category` → `category_name`, `category_color`, `category_isDefault`
- `address` → `address_address_line_1`, `address_city`, `address_state`, etc.

**Array processing**:
- `tags` arrays are converted to comma-separated strings
- `circles` arrays are converted to comma-separated strings
- `companies` arrays in contacts create separate relationship records

**Data types**: The connector lets Fivetran infer data types automatically, only defining primary keys in the schema.


## Error handling
Error handling is implemented throughout the connector:
- **Configuration validation**: The `validate_configuration()` function ensures required credentials are present
- **API request handling**: The `make_api_request()` function catches HTTP errors and network issues
- **Exception propagation**: All functions raise `RuntimeError` with descriptive messages for upstream handling


## Tables created

The connector creates the following tables in your destination:

| Table name                     | Primary key                  | Description |
|--------------------------------|------------------------------|-------------|
| `COMPANY`                      | `uid`                        | Contains flattened company data from the `/companies` endpoint |
| `CONTACT`                      | `uid`                        | Contains flattened contact data from the `/contacts` endpoint |
| `CONTACT_COMPANY_RELATIONSHIP` | `contact_uid`, `company_uid` | Junction table mapping contacts to their associated companies |


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.