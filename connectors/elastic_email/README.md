# Elastic Email Connector Example

## Connector overview

This connector syncs email marketing data from Elastic Email to your destination using the Elastic Email REST API v4. It retrieves campaigns, contacts, lists, segments, templates, events, statistics, files, domains, and suppression data. The connector is designed for marketing teams and analysts who need to consolidate email campaign performance data with other business metrics in their data warehouse.

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
fivetran init <project-path> --template connectors/elastic_email
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Full sync of campaigns, contacts, lists, segments, and templates
- Incremental sync of events based on date filtering
- Campaign statistics and performance metrics
- File and domain management data
- Email suppression tracking including bounces, complaints, and unsubscribes
- Automatic retry logic with exponential backoff for transient API errors
- Pagination support for large datasets
- Checkpoint mechanism for resumable syncs
- Flattened data structure for easy querying in destination

## Configuration file

The connector requires the following configuration parameters:

```
{
  "api_key": "<YOUR_ELASTIC_EMAIL_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector uses only the standard libraries provided by the Fivetran Connector SDK runtime. No additional packages are required.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector uses API key authentication to connect to the Elastic Email API. The API key is passed via the `X-ElasticEmail-ApiKey` header for all API requests.

To set up authentication:

1. Log in to your [Elastic Email account](https://app.elasticemail.com).
2. Navigate to **Settings** and then **API**.
3. Click on **Create Additional API Key** or use an existing key.
4. Make a note of the API key value.
5. Add the API key to your `configuration.json` file as the value for `api_key`.

The connector validates that the API key is present during initialization. Refer to the `validate_configuration` function in [connector.py](connector.py).

## Pagination

The connector handles pagination using offset-based pagination for all API endpoints. Each endpoint supports `limit` and `offset` parameters to retrieve data in batches. The connector uses a page limit of 100 records per request and automatically increments the offset until all data is retrieved. Refer to the `process_paginated_endpoint` function in [connector.py](connector.py).

## Data handling

The connector processes data from the Elastic Email API and transforms it for the destination:

- Nested JSON objects are flattened into a single-level dictionary with underscore-separated keys
- Arrays within records are serialized as JSON strings
- All records are upserted to the destination using the appropriate primary keys
- Incremental sync is supported for events using date-based filtering
- Data is processed in batches to avoid loading large datasets into memory

Refer to the `flatten_dict` and `process_paginated_endpoint` functions in [connector.py](connector.py).

## Error handling

The connector implements comprehensive error handling:

- Retry logic with exponential backoff for transient errors (429, 500, 502, 503, 504 status codes)
- Maximum of 3 retry attempts with delays of 1, 2, and 4 seconds
- Specific exception handling for timeout and connection errors
- All errors are logged using the SDK logging framework
- Failed requests raise RuntimeError with descriptive error messages

Refer to the `make_request_with_retry` function in [connector.py](connector.py).

## Tables created

The connector creates the following tables in the destination:

| Table Name | Primary Key | Description |
|------------|-------------|-------------|
| `CAMPAIGN` | `name` | Email marketing campaigns. |
| `CONTACT` | `email` | Contact list with email addresses and metadata. |
| `LIST` | `listName` | Contact lists used for segmentation. |
| `SEGMENT` | `name` | Dynamic contact segments based on rules. |
| `TEMPLATE` | `name` | Email templates for campaigns. |
| `EVENT` | `transactionID` | Email delivery events (sent, opened, clicked, bounced). |
| `CAMPAIGN_STATISTICS` | `name` | Campaign performance statistics. |
| `FILE` | `name` | Uploaded files and attachments. |
| `DOMAIN` | `domain` | Verified sending domains. |
| `SUPPRESSION` | `email` | All suppressed email addresses. |
| `BOUNCE` | `email` | Bounced email addresses. |
| `COMPLAINT` | `email` | Spam complaint email addresses. |
| `USUBSCRIBE` | `email` | Unsubscribed email addresses. |

All table schemas are defined with primary keys only. Column data types are inferred by Fivetran based on the actual data. Nested objects are flattened with underscore-separated column names. Refer to the `schema` function in [connector.py](connector.py).

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
