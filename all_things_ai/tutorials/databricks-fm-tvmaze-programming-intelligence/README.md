# Databricks TVMaze Programming Intelligence Connector Example

## Connector overview

This connector syncs TV show metadata from the [TVMaze API](https://www.tvmaze.com/api) and enriches each show with AI-powered multi-agent debate using the Databricks [ai_query()](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function.

A Programming Optimist and a Programming Skeptic each argue their case for a show's renewal probability. A Consensus agent synthesizes both perspectives into a `renewal_rating` and sets a `disagreement_flag` when the analysts meaningfully disagree — flagging shows for human programming team review.

The `disagreement_flag` is the product: pre-computed analyst contention surfaces the shows that warrant human judgment, without requiring dashboards or scheduled jobs.

Optional [Genie Space](https://docs.databricks.com/en/genie/index.html) creation after data lands enables natural language programming analytics.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A Databricks workspace with a SQL Warehouse that supports `ai_query()` (required for AI enrichment; optional for data-only mode)
- A Databricks Personal Access Token (PAT) with SQL execution permissions

Note: The TVMaze API requires no authentication or API key.

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs TV show metadata from the TVMaze public catalog (~70,000 shows)
- Initial sync paginates `/shows?page=N` with configurable page cap and per-page checkpointing for safe resume
- Incremental sync uses `/updates/shows?since=month` as a cursor, fetching only shows updated since the last sync
- AI enrichment via Databricks `ai_query()` with a three-agent Multi-Agent Debate: Programming Optimist, Programming Skeptic, and Consensus
- `disagreement_flag` surfaces shows where the two analysts meaningfully disagree for human review queues
- Optional genre and status filtering to scope syncs to relevant shows
- Optional Genie Space creation with programming-analytics instructions and sample questions
- Configurable enrichment budget via `max_enrichments` to control costs
- Data-only mode when `enable_enrichment` is set to `false`
- Async polling for long-running `ai_query()` statements with PENDING/RUNNING state handling

## Configuration file

The `configuration.json` file contains the following parameters:

```json
{
  "databricks_workspace_url": "<DATABRICKS_WORKSPACE_URL>",
  "databricks_token": "<DATABRICKS_PAT_TOKEN>",
  "databricks_warehouse_id": "<DATABRICKS_WAREHOUSE_ID>",
  "databricks_model": "<DATABRICKS_MODEL_NAME>",
  "enable_enrichment": "<TRUE_OR_FALSE>",
  "enable_genie_space": "<TRUE_OR_FALSE>",
  "genie_table_identifier": "<CATALOG.SCHEMA.TABLE>",
  "initial_sync_max_pages": "<MAX_PAGES_FOR_INITIAL_SYNC>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "genre_filter": "<OPTIONAL_GENRE_FILTER>",
  "status_filter": "<OPTIONAL_STATUS_FILTER>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

- `databricks_workspace_url` (required): Full Databricks workspace URL including `https://`
- `databricks_token` (required): Databricks Personal Access Token with SQL execution permissions
- `databricks_warehouse_id` (required): SQL Warehouse ID for `ai_query()` execution
- `databricks_model` (optional): Databricks Foundation Model name. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` for data-only mode. Default: `false`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space after sync. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path in `catalog.schema.table` format
- `initial_sync_max_pages` (optional): Maximum pages to fetch per sync run during initial load. Default: `10`. Maximum: `300`. Each page returns approximately 250 shows.
- `max_enrichments` (optional): Maximum `ai_query()` calls per sync. Default: `50`. Maximum: `500`
- `genre_filter` (optional): Comma-separated genre filter, for example `Drama,Crime`. Leave empty to sync all genres.
- `status_filter` (optional): Filter by show status: `Running`, `Ended`, `To Be Determined`, or `In Development`. Leave empty to sync all statuses.
- `databricks_timeout` (optional): Databricks SQL query timeout in seconds. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The TVMaze API is public and requires no authentication or API key.

Databricks access requires a Personal Access Token (PAT) with SQL execution permissions:

1. Navigate to your Databricks workspace.
2. Click your username in the top-right corner and select **Settings**.
3. Click **Developer** in the left panel.
4. Click **Manage** next to **Access tokens**.
5. Click **Generate new token**, provide a description, and click **Generate**.
6. Copy the token value and set it as `databricks_token` in your `configuration.json`

## Pagination

The TVMaze API uses page-based pagination for the initial catalog sync. The connector fetches pages via `GET /shows?page=N`, where each page returns approximately 250 shows. Pagination ends when the API returns HTTP 404. The `initial_sync_max_pages` parameter caps the number of pages fetched per sync run, enabling safe multi-run initial loads with per-page checkpointing.

For incremental syncs, the connector calls `GET /updates/shows?since=month` to retrieve a map of show IDs updated in the past month, then filters to shows updated after the stored `last_updates_poll` timestamp.

## Data handling

The `def update(configuration, state)` function orchestrates the sync in several phases:

1. Validates configuration via `def validate_configuration(configuration)` including Databricks credential checks and sanity ceilings on configurable limits
2. MOVE: Fetches shows from the TVMaze API via `def fetch_data_with_retry(session, url, params)`, normalizes nested structures via `def flatten_show(show)`, and upserts records with per-page checkpointing.
3. DEBATE: For each show in the current sync batch (up to `max_enrichments`), fetches embedded cast and episode data, builds a context string via `def build_show_context(show, embedded)`, and runs three `ai_query()` calls via `def run_debate(databricks_session, configuration, show_record, embedded, state)`: Programming Optimist, Programming Skeptic, and Consensus
4. AGENT: Optionally creates a Genie Space via `def create_genie_space(databricks_session, configuration, state)` with programming-analytics instructions and sample questions

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params)` provides exponential backoff for transient failures (429, 500-504) with immediate failure on auth errors (401, 403) and None return on HTTP 404 to signal end of pagination
- `def call_ai_query(session, configuration, prompt)` catches specific exception types (`Timeout`, `HTTPError`, `ConnectionError`, `RequestException`, `JSONDecodeError`) and returns None on failure, with async polling for PENDING and RUNNING states up to `__SQL_MAX_POLL_ATTEMPTS`
- `def _extract_json(raw)` strips markdown code fences from model responses before JSON parsing
- `def validate_configuration(configuration)` validates all parameters using `def _is_placeholder(value)` with sanity ceilings of 300 pages and 500 enrichments
- Both TVMaze and Databricks sessions are always closed via a try/finally block

## Tables created

### SHOWS

The `SHOWS` table consists of the following columns:

- `show_id` (INT, primary key): TVMaze show identifier
- `name` (STRING): Show title
- `type` (STRING): Show type, for example Scripted, Reality, Animation
- `language` (STRING): Primary language
- `genres` (STRING): JSON array of genres
- `status` (STRING): Show status: Running, Ended, To Be Determined, or In Development
- `runtime` (INT): Episode runtime in minutes
- `average_runtime` (INT): Average episode runtime in minutes
- `premiered` (STRING): Premiere date in YYYY-MM-DD format
- `ended` (STRING): End date in YYYY-MM-DD format, null if still running
- `official_site` (STRING): Official website URL
- `network_name` (STRING): Broadcast or cable network name
- `network_country_code` (STRING): Network country code, for example US or GB
- `web_channel_name` (STRING): Streaming service name
- `schedule_time` (STRING): Air time in HH:MM format
- `schedule_days` (STRING): JSON array of broadcast days
- `summary` (STRING): Show description, may contain HTML
- `image_medium` (STRING): Medium portrait image URL
- `image_original` (STRING): Original portrait image URL
- `rating_average` (FLOAT): TVMaze user rating on a scale of 0 to 10
- `weight` (INT): TVMaze popularity weight
- `updated` (INT): Unix timestamp of last TVMaze update
- `optimist_assessment` (STRING): JSON output of the Programming Optimist agent. Populated when enrichment is enabled.
- `skeptic_assessment` (STRING): JSON output of the Programming Skeptic agent. Populated when enrichment is enabled.
- `renewal_rating` (STRING): Consensus renewal rating: HIGH, MEDIUM, or LOW. Populated when enrichment is enabled.
- `disagreement_flag` (BOOLEAN): True when the Optimist and Skeptic analysts meaningfully disagree. Populated when enrichment is enabled.
- `debate_winner` (STRING): Which analyst the Consensus sided with: OPTIMIST, SKEPTIC, or DRAW. Populated when enrichment is enabled.
- `consensus_rationale` (STRING): Consensus synthesis explanation. Populated when enrichment is enabled.
- `human_review_recommended` (BOOLEAN): True when disagreement_flag is true or renewal_rating is LOW. Populated when enrichment is enabled.
- `enrichment_timestamp` (STRING): ISO-8601 timestamp of the AI enrichment run

## Additional considerations

This example was contributed by [Kai Lee](https://github.com/fivetran-kaiyulee) with [Kelly Kohlleffel](https://github.com/kellykohlleffel).

Data provided by [TVmaze](https://www.tvmaze.com), licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

Databricks `ai_query()` consumes SQL Warehouse compute credits. Use `max_enrichments` to control costs. Set `enable_enrichment` to `false` for data-only mode.

The TVMaze API rate limit is 20 requests per 10 seconds. The connector includes rate limiting delays between individual show fetches during incremental sync and enrichment pre-fetch.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
