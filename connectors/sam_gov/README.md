# SAM.gov Opportunities Connector Example

## Connector overview
This connector fetches government contracting opportunities from the SAM.gov (System for Award Management) API. It replicates opportunity data, including solicitations, awards, contact information, and related metadata. The connector supports incremental synchronization and handles large datasets through pagination. Data is organized into multiple tables with proper foreign key relationships to maintain referential integrity while providing a normalized structure for analysis.

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
fivetran init <project-path> --template connectors/sam_gov
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Configurable date range sync of government contracting opportunities from SAM.gov
- Pagination support for large datasets (up to 1000 records per API call)
- Upsert-based sync captures updates to existing opportunities within the configured date window
- State management and checkpointing for resumable syncs
- Normalized data structure with breakout tables for arrays
- Flattened nested objects for easier analysis
- Comprehensive error handling with retry logic
- Support for all SAM.gov opportunity types (solicitations, awards, notices, etc.)

## Configuration file
The configuration requires your SAM.gov API key and date range for opportunity posting dates. The API key can be obtained from your SAM.gov account.

```json
{
  "api_key": "<YOUR_SAM_GOV_API_KEY>",
  "posted_from": "<MM/DD/YYYY_START_DATE>",
  "posted_to": "<MM/DD/YYYY_END_DATE_WITHIN_ONE_YEAR>"
}
```

### Configuration parameters
- `api_key`: Your SAM.gov public API key (required)
- `posted_from`: Start date for initial sync in MM/dd/yyyy format (required for first sync)
- `posted_to`: End date for initial sync in MM/dd/yyyy format (required for first sync)

### Important date range limitation
- The date range between `posted_from` and `posted_to` must be less than 1 year (maximum 364 days)
- This is a SAM.gov API limitation, not a connector limitation
- The connector will validate this requirement and throw an error if exceeded during initial sync
- For incremental syncs exceeding this limit, the connector automatically chunks the date range into 364-day windows

### Sync strategy
The connector supports hybrid sliding window incremental sync:

Initial sync (first run):
- Uses `posted_from` and `posted_to` dates from configuration for historical backfill
- After completion, automatically switches to incremental mode

Incremental sync (subsequent runs):
- Automatically calculates date window using `last_posted_to` from previous sync minus a 30-day overlap window
- Advances to the current date, capturing new opportunities and updates
- If the date range exceeds one year, the connector automatically chunks the range into successive 364-day windows and processes them all in a single sync run, ensuring no data is missed even after extended downtime

### Overlap window strategy
- Default 30-day overlap window ensures recent opportunity updates are captured
- The overlap window is configured in the code as a constant named __INCREMENTAL_WINDOW_DAYS with a value of 30
- A smaller overlap makes the sync more API-efficient but reduces the time window in which updates are detected
- A larger overlap captures more late or out-of-order updates but increases the number of API calls

### Example progression
```
Initial Sync: [01/01/2024 - 12/30/2024] (364 days)
  → State saves: last_posted_to = 12/30/2024

Sync 2 (short downtime): [12/01/2024 - 03/15/2025] (30-day overlap, 104 days total)
  → Processed in 1 window, completes in single run
  → State saves: last_posted_to = 03/15/2025

Sync 3 (long downtime - ~2 years): [02/14/2025 - 12/17/2026] (30-day overlap, 671 days total)
  → Window 1: [02/14/2025 - 02/13/2026] (364 days)
  → Window 2: [02/14/2026 - 12/17/2026] (306 days)
  → Both windows processed sequentially in single sync run
  → State saves: last_posted_to = 12/17/2026
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication
The SAM.gov API uses API key authentication. To obtain an API key:

1. Create an account on [SAM.gov](https://sam.gov)
2. Navigate to your Account Details page
3. Enter your account password to access API key information
4. Generate a new public API key
5. Copy the API key (it's visible until you navigate away from the page)

The API key should be included in every request as the `api_key` parameter. Different user roles (federal vs non-federal) have different rate limits.

## Pagination
The connector implements pagination using the SAM.gov API's `limit` and `offset` parameters (refer to the `fetch_opportunities_page` function and the pagination loop in the `update` function):
- Page size: Maximum 1000 records per request
- Pagination logic: Processes data page by page in a loop, tracking offset position
- State management: Tracks `last_offset` and `total_records_processed` for resumable syncs
- Checkpointing: Saves progress every 100 records to handle interruptions gracefully

## Data handling
The connector processes SAM.gov opportunity data through several transformation steps (refer to the `process_main_opportunity_record` and `process_breakout_tables` functions):

1. Main opportunity table - Stores core opportunity information with flattened nested objects
2. Breakout tables - Separate tables for array data with foreign key relationships:
  - `point_of_contact` - Contact information for each opportunity
  - `naics_code` - NAICS classification codes
  - `link` - API self-reference links
  - `resource_link` - Document and resource URLs

Flattening strategy (implemented in the `flatten_dict` function):
- Nested objects like `placeOfPerformance` become `place_of_performance_*` columns
- Award information becomes `award_*` columns
- Empty objects are converted to NULL values

Data transformation (refer to the `process_main_opportunity_record` function):
- CamelCase API fields converted to snake_case database columns
- Array fields extracted to separate tables with composite primary keys
- Foreign key relationships maintained through `notice_id`

## Error handling
The connector implements comprehensive error handling with retry logic and detailed error messages (refer to the `make_api_request`, `make_api_request_with_retry`, and `validate_configuration` functions):

Configuration validation errors:
- Missing required fields (`api_key`, `posted_from`, `posted_to`)
- Invalid date format (must be MM/dd/yyyy)
- Date range exceeding one year

API request errors with specific handling:
- 401 Unauthorized - Invalid API key
- 403 Forbidden - Access denied or quota exceeded
- 404 Not Found - Invalid endpoint
- 429 Rate Limit - Too many requests
- 500+ Server errors - SAM.gov service issues
- Timeout errors - Slow API response
- Connection errors - Network issues

Additional features:
- Retry logic - Exponential backoff for transient errors (3 attempts maximum)
- Individual record resilience - Failed records don't stop the entire sync
- Detailed logging - Comprehensive error tracking for troubleshooting

## Tables created
The connector creates the following tables (refer to the `schema` function):

### opportunity
- Primary key: `notice_id`
- Description: Core opportunity information with flattened nested objects
- Key columns: title, solicitation_number, posted_date, type, naics_code, response_dead_line, organization_type, office_address fields, place_of_performance fields, award fields
- Note: `award_amount` field is defined as DECIMAL(15,2) for financial precision

### point_of_contact
- Primary key: `notice_id`, `contact_index`
- Description: Contact information for each opportunity
- Foreign key: `notice_id` references opportunity table
- Key columns: type, full_name, email, phone, fax, title

### naics_code
- Primary key: `notice_id`, `code_index`
- Description: NAICS classification codes for each opportunity
- Foreign key: `notice_id` references opportunity table
- Key columns: naics_code

### link
- Primary key: `notice_id`, `link_index`
- Description: API reference links
- Foreign key: `notice_id` references opportunity table
- Key columns: rel, href

### resource_link
- Primary key: `notice_id`, `link_index`
- Description: Document and resource URLs
- Foreign key: `notice_id` references opportunity table
- Key columns: resource_link

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
