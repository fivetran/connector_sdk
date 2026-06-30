# SharePoint Multi-Site Connector Example

## Connector overview

This connector extracts structured data from CSV and Excel files stored across multiple SharePoint sites and loads it into destination tables. It uses the Microsoft Graph API to discover files, read their content, and track modifications incrementally.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:
```bash
fivetran init <project-path> --template connectors/sharepoint_multi_site_connector
```

`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory. 
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note : Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Key Features
- Multi-site ingestion which connects to multiple SharePoint sites in a single sync run
- CSV and Excel support parses .csv, .xlsx, and .xlsm file formats
- Row-level extraction emits each row of a parsed file as an individual record
- Incremental sync uses lastModifiedDateTime to process only new or changed files
- Deletion handling detects files removed from SharePoint and marks them accordingly
- Recursive folder traversal discovers files in nested folder structures within document libraries

## Configuration file
*Detail the configuration keys defined for your connector, which are uploaded to Fivetran from the configuration.json file.* 

```
{
    "tenant_id": "<YOUR_TENANT_ID>",
    "client_id": "<YOUR_CLIENT_ID>",
    "client_secret": "<YOUR_CLIENT_SECRET>",
    "site_urls": "<YOUR_SITE_URLS_COMMA_SEPARATED>",
    "site_ids": "<YOUR_SITE_IDS_OPTIONAL_COMMA_SEPARATED>",
    "folder_path": "<OPTIONAL_FOLDER_PATH_E.G._Documents/Reports>",
    "sync_subfolders": "<OPTIONAL_BOOLEAN_TRUE_OR_FALSE>",
    "file_pattern": "<OPTIONAL_FILENAME_SUBSTRING_FILTER>",
    "delimiter": "<OPTIONAL_CSV_DELIMITER_E.G._COMMA_OR_SEMICOLON>",
    "skip_rows": "<OPTIONAL_NUMBER_OF_ROWS_TO_SKIP_AT_START_OF_FILE>",
}

```

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector uses the openpyxl package to parse Excel files (.xlsx, .xlsm).

```
openpyxl
```

> Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector authenticates with the Microsoft Graph API using the OAuth 2.0 client credentials flow. The tenant ID, client ID, and client secret from configuration.json are exchanged for a bearer access token from the Microsoft identity platform. The token is passed in the Authorization header of all Graph API requests.

To set up authentication:
1. Sign in to the Azure Portal.
2. Go to Azure Active Directory > App registrations and click New registration.
Complete the registration form and click Register.
3. On the application overview page, copy the Application (client) ID and Directory (tenant) ID.
4. Go to Certificates & secrets > New client secret, enter a description and expiry, and click Add. Copy the secret value immediately — it will not be displayed again.
5. Go to API permissions > Add a permission > Microsoft Graph > Application permissions and add Sites.Read.All and Files.Read.All.
6. Click Grant admin consent to activate the permissions.
7. Add the tenant ID, client ID, and client secret to your configuration.json file.
Pagination

The Microsoft Graph API returns results in pages when listing drive items. The connector follows the @odata.nextLink URL included in each API response to retrieve subsequent pages until all items have been fetched. This applies to both file discovery and recursive traversal of subfolders.

## Data handling
The connector iterates over each SharePoint site URL in the configuration and uses the Microsoft Graph API to list files in the site's document library, including files in nested folders. 

For each file, the connector compares the lastModifiedDateTime returned by the API against the timestamp stored in state to determine whether the file needs to be processed.

Files that are new or modified since the last sync are downloaded and parsed. CSV files are read row by row and Excel files (.xlsx, .xlsm) are parsed using openpyxl. Each data row is written as a record to the file_rows table, and file metadata is written to the files table. File types that are not supported, such as PDF or images, are skipped during discovery.

## Error handling
HTTP errors from the Microsoft Graph API, including authentication failures and permission errors, are raised immediately to prevent silent data loss. Transient network errors and rate-limit responses (HTTP 429) are retried using exponential backoff. Files that cannot be parsed due to unsupported content structure or corruption are logged and skipped without interrupting the overall sync.

## Tables created

### files
Metadata about each file.

### file_rows
Row-level data extracted from files.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
