# OWASP API Vulnerabilities Connector Example

## Connector overview
This connector retrieves API security vulnerability data from the National Vulnerability Database (NVD) 2.0 API. It is designed to help security teams and developers monitor for vulnerabilities relevant to the OWASP API Security Top 10. The connector fetches Common Vulnerabilities and Exposures (CVEs) based on a configurable list of Common Weakness Enumerations (CWEs), processes the data, and syncs it to your destination. The CWEs drive what CVEs get fetched.

### Contributor

This connector was contributed by [Ashish Saha](https://www.linkedin.com/in/ashish-saha-senior-engineering-manager/) (GitHub: [@aksaha9](https://github.com/aksaha9)).

Ashish is a seasoned API Security and DevSecOps specialist with over a decade of experience helping global enterprises secure APIs at scale, previously leading vulnerability management programs at a major financial institution.

The OWASP API Vulnerabilities connector was developed as part of Ashish’s submission to the AI Accelerate Hackathon 2025 – Fivetran Challenge - https://devpost.com/software/owasp-api-vulnerability-adviso.

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
fivetran init <project-path> --template connectors/owasp_api_vulns
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Features
- Fetches vulnerability data from the NVD 2.0 API.
- Supports both full and incremental syncs based on the `lastModifiedDate` of CVEs.
- Filters vulnerabilities by a configurable list of CWE IDs.
- Includes an additional filter to only include CVEs with "api" in the description if the CWE doesn't match the primary list.
- Skips CVEs with an "UNKNOWN" severity to ensure data quality.
- Supports configurable logging levels (`standard` for summary logs, `debug` for verbose logs).
- Creates two tables: `owasp_api_vulnerabilities` for the CVE data and `owasp_api_sync_log` for sync metadata.

## Configuration file
The connector requires the following configuration parameters in the `configuration.json` file.

```json
{
  "api_key": "<YOUR_NVD_API_KEY>",
  "force_full_sync": "<ENABLE_FORCE_FULL_SYNC>",
  "write_temp_files": "<ENABLE_TEMP_FILE_WRITE>",
  "logging_level": "<YOUR_LOGGING_LEVEL>",
  "cwe_ids": "<YOUR_CWE_ID_SEPARATED_BY_COMMA>"
}
```

- `api_key` (required) - Your API key for the NVD 2.0 API.
- `force_full_sync` (optional) - Set to `true` to ignore the saved state and perform a full re-sync. Defaults to `false`.
- `write_temp_files` (optional) - Set to `true` to save the raw API responses to a local `raw_data` directory for debugging. Defaults to `false`.
- `logging_level` (optional) - Set to `standard` for summary logging or `debug` for verbose, detailed logging. Defaults to `debug`.
- `cwe_ids` (optional) - A comma-separated string of CWE IDs to filter the vulnerabilities. Defaults to a predefined list of OWASP-related CWEs.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
This connector does not require any external Python libraries to be listed in `requirements.txt`.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector authenticates with the NVD 2.0 API using an API key. The key is provided in the `configuration.json` file and sent in the `apiKey` header of each request.

To obtain an API key:
1. Visit the [National Vulnerability Database website](https://nvd.nist.gov/developers/request-an-api-key).
2. Click **Request an API Key** and fill out the registration form.
3. Check your email for the API key confirmation.
4. Make a note of the API key and add it to your `configuration.json` file.

Note: While an API key is optional, using one provides higher rate limits (50 requests per 30 seconds vs 5 requests per 30 seconds for public access).

## Pagination
The connector handles pagination differently for full and incremental syncs, as detailed in the `update` function.
- For full syncs, it uses the `startIndex` and `resultsPerPage` parameters to iterate through all available records in a `while` loop.
- For incremental syncs, it fetches all records modified since the last sync in a single request, as pagination is not supported by the NVD API when using date range filters.

## Data handling
The connector fetches, processes, and delivers data to Fivetran as outlined in the `update` function.
- It fetches CVE data from the NVD API based on the configured CWEs.
- For incremental syncs, it uses the `last_sync_time` from the state to fetch only new or modified records.
- It filters out records that have an "UNKNOWN" severity.
- It processes the JSON response, transforms the data into a flat structure, and uses `op.upsert` to send records to the `owasp_api_vulnerabilities` and `owasp_api_sync_log` tables.
- After each successful sync, it uses `op.checkpoint` to save the current timestamp, ensuring the next sync will resume from that point.

## Error handling
The connector implements several error-handling strategies within the `update` function.
- It checks the HTTP status code of each API response. If the status is not 200, it logs an `error` with details from the response and stops processing for that CWE.
- It implements an exponential backoff retry strategy for transient network errors, 5xx server errors, and rate limit errors (HTTP 403 and 429).
- To proactively manage rate limits, the connector applies a fixed delay of 0.6 seconds (`__API_RATE_LIMIT_DELAY`) between paginated requests.
- It wraps the JSON decoding process in a `try...except` block to catch `json.JSONDecodeError` and logs an `error` if the response is not valid JSON.
- A general `try...except` block is used to catch any other exceptions during the API request and processing loop, logging an `error` to prevent the entire sync from failing.

## Tables created
The connector creates two tables in the destination, as defined in the `schema` function.

### OWASP_API_VULNERABILITIES

Description: Stores detailed vulnerability data.

    ```json
    {
        "table": "owasp_api_vulnerabilities",
        "primary_key": ["cve_id"],
        "columns": {
            "cve_id": "STRING",
            "description": "STRING",
            "published_date": "STRING",
            "last_modified_date": "STRING",
            "cwe_ids": "JSON",
            "affected_libraries": "JSON",
            "fixed_versions": "JSON",
            "remediations": "JSON",
            "severity": "STRING"
        }
    }
    ```

### OWASP_API__SYNC_LOGIC 

Description: Records metadata for each sync operation.

    ```json
    {
        "table": "owasp_api_sync_log",
        "primary_key": ["sync_datetime"],
        "columns": {
            "sync_datetime": "STRING",
            "sync_type": "STRING",
            "total_rows_upserted": "LONG"
        }
    }
    ```

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
