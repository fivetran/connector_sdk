# Databricks CPSC Product Safety Intelligence Connector Example

## Connector overview

This connector syncs consumer product recall data from the [CPSC SaferProducts API](https://www.saferproducts.gov/RestWebServices) and enriches each recall with AI-powered multi-agent debate analysis using the Databricks [ai_query()](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function. Two AI personas with opposing expert perspectives analyze each product safety incident, then a consensus agent synthesizes both views and flags disagreements for human review.

The connector features a two-phase architecture:

- Phase 1 (MOVE): Fetch product recall data from the CPSC SaferProducts API
- Phase 2 (DEBATE): For each recall, three ai_query() calls produce competing analyses:
  1. Product Safety Analyst: Risk-maximizing perspective, assumes worst-case consumer exposure
  2. Manufacturing Quality Engineer: Context-aware skeptic, considers batch isolation and root cause containment
  3. Consensus Agent: Synthesizes both perspectives, assigns final severity, produces disagreement_flag and debate_winner

Optional [Genie Space](https://docs.databricks.com/en/genie/index.html) creation after data lands for natural language analytics.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A Databricks workspace with a SQL Warehouse that supports `ai_query()` (required for AI debate; optional for data-only mode)
- A Databricks Personal Access Token (PAT) with SQL execution permissions

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs consumer product recall data from the free CPSC SaferProducts API (no API key required)
- Multi-Agent Debate: two AI personas with opposing perspectives analyze each recall, with a consensus synthesizer
- Disagreement flag identifies recalls where experts significantly disagree, flagging them for human review
- Debate winner field shows which expert was more persuasive for each recall
- AI enrichment via Databricks `ai_query()` SQL function using Claude Sonnet 4.6 (configurable model)
- Optional Genie Space creation with product safety-specific instructions and sample questions
- Incremental sync using recall date as a cursor to fetch only new recalls
- Configurable enrichment budget via `max_enrichments` to control SQL Warehouse compute costs (3x ai_query calls per recall)
- Data-only mode when `enable_enrichment` is set to `false` for syncing recalls without AI debate
- Per-recall checkpointing for reliable resumable syncs during the debate phase
- Async polling for long-running ai_query() statements that exceed the SQL wait timeout

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
  "max_recalls": "<MAX_RECALLS_PER_SYNC>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "recall_date_start": "<YYYY-MM-DD>",
  "lookback_days": "<LOOKBACK_DAYS>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

- `databricks_workspace_url` (required when enrichment or Genie enabled): Full Databricks workspace URL including `https://` (e.g., `https://dbc-xxxxx.cloud.databricks.com`)
- `databricks_token` (required when enrichment or Genie enabled): Databricks Personal Access Token with SQL execution permissions
- `databricks_warehouse_id` (required when enrichment or Genie enabled): SQL Warehouse ID to execute `ai_query()` statements and create Genie Spaces
- `databricks_model` (optional): Databricks Foundation Model name for `ai_query()`. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` to sync recalls without AI debate analysis. Default: `true`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space on the enriched data after sync. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path for the Genie Space data source (format: `catalog.schema.table`)
- `max_recalls` (optional): Maximum number of recalls to sync per run. Default: `10`. Maximum: `200`
- `max_enrichments` (optional): Maximum number of recalls to run through the debate (3 ai_query calls each). Default: `5`. Maximum: `50`
- `recall_date_start` (optional): Override start date for recall fetch (YYYY-MM-DD format). Overrides the incremental cursor and lookback window
- `lookback_days` (optional): Number of days to look back on initial sync when no cursor exists. Default: `90`
- `databricks_timeout` (optional): Timeout in seconds for Databricks SQL Statement API calls. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The CPSC SaferProducts API is free and requires no authentication. The connector uses a browser-compatible User-Agent header as required by the CPSC API.

Databricks access requires a Personal Access Token (PAT) with SQL execution permissions:

1. Navigate to your Databricks workspace
2. Click your username in the top-right corner and select **Settings**
3. Click **Developer** in the left panel
4. Click **Manage** next to **Access tokens**
5. Click **Generate new token**, provide a description, and click **Generate**
6. Copy the token value and set it as `databricks_token` in your `configuration.json`

## Pagination

The CPSC SaferProducts API returns all recalls matching the date range in a single response (no pagination needed). The connector limits processing to `max_recalls` records per sync and uses `recall_date` as the incremental cursor for subsequent syncs.

## Data handling

The `def update(configuration, state)` function orchestrates a three-phase sync pipeline:

Phase 1 (MOVE):
1. Validates configuration via `def validate_configuration(configuration)` including Databricks credential checks and sanity ceiling enforcement
2. Builds a date range from the saved `last_recall_date` state cursor (or `lookback_days` / `recall_date_start` for initial sync)
3. Fetches recalls from the CPSC API via `def fetch_recalls(session, start_date, end_date)` and builds normalized records via `def build_recall_record(recall)` extracting product name, hazard description, injury reports, manufacturer, remedy, and retailer information
4. Upserts recall records and checkpoints state with the latest recall date

Phase 2 (DEBATE):
5. For each recall (up to `max_enrichments`), runs three ai_query() calls via `def run_multi_agent_debate(session, configuration, recalls, recall_records, state)`:
   - `def build_safety_prompt(recall_record)` generates the Product Safety Analyst perspective (risk-maximizing)
   - `def build_quality_prompt(recall_record)` generates the Manufacturing Quality Engineer perspective (context-aware skeptic)
   - `def build_consensus_prompt(recall_record, safety_result, quality_result)` synthesizes both into a final assessment with disagreement_flag and debate_winner
6. Checkpoints after each recall is debated for reliable resumability

Phase 3 (AGENT):
7. If enabled, creates a Genie Space via `def create_genie_space(session, configuration, state)` with product safety-specific instructions and sample questions

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params)` provides exponential backoff retry logic for transient CPSC API failures (HTTP 429, 500, 502, 503, 504) with immediate failure on access errors (401, 403)
- `def call_ai_query(session, configuration, prompt)` catches specific exception types (Timeout, HTTPError, ConnectionError, RequestException, JSONDecodeError) and returns None on failure, allowing the debate to continue with partial results. Includes async polling for PENDING/RUNNING SQL statements
- Individual debate agent failures are handled gracefully via `def upsert_assessment(table_name, recall_id, assessment, assessment_type)`: if the Safety Analyst or Quality Engineer returns None, the consensus step is skipped for that recall but the sync continues
- `def validate_configuration(configuration)` validates all required parameters upfront using `def _is_placeholder(value)` to detect uncommitted placeholder values
- Sanity ceilings enforce maximum values for `max_recalls` (200) and `max_enrichments` (50) to prevent runaway costs
- The session is always closed via a try/finally block in `def update(configuration, state)` to release resources even on unexpected errors

## Tables created

### PRODUCT_RECALLS

The `PRODUCT_RECALLS` table consists of the following columns:

- `recall_id` (INTEGER, primary key): CPSC recall identifier
- `recall_number` (STRING): CPSC recall number (e.g., "25199")
- `recall_date` (STRING): Date the recall was issued (ISO format)
- `title` (STRING): Recall title describing the product and hazard
- `description` (STRING): Detailed description of the recalled product
- `url` (STRING): CPSC recall page URL
- `consumer_contact` (STRING): Contact information for consumers
- `last_publish_date` (STRING): Date the recall was last updated
- `product_name` (STRING): Name of the primary recalled product
- `product_type` (STRING): Product type classification
- `number_of_units` (STRING): Number of units affected by the recall
- `hazard_description` (STRING): Description of the safety hazard
- `hazard_type` (STRING): Hazard type classification
- `injury_description` (STRING): Description of reported injuries
- `manufacturer_name` (STRING): Name of the product manufacturer
- `retailer_name` (STRING): Name of the primary retailer
- `remedy_description` (STRING): Description of the recall remedy
- `all_products` (STRING): JSON array of all products in the recall
- `all_hazards` (STRING): JSON array of all hazards
- `all_injuries` (STRING): JSON array of all injury reports
- `all_manufacturers` (STRING): JSON array of all manufacturers
- `all_retailers` (STRING): JSON array of all retailers
- `all_remedies` (STRING): JSON array of all remedies

### SAFETY_ASSESSMENTS

The `SAFETY_ASSESSMENTS` table consists of the following columns:

- `recall_id` (INTEGER, primary key): CPSC recall identifier
- `assessment_type` (STRING): Always "safety" for this table
- `safety_risk_score` (INTEGER): Risk score from 1-10 (risk-maximizing perspective)
- `worst_case_scenario` (STRING): Description of the worst-case consumer harm scenario
- `defect_classification` (STRING): Classification of the defect type (SYSTEMIC_DESIGN, MANUFACTURING_BATCH, MATERIAL_DEFECT, LABELING, UNKNOWN)
- `consumer_urgency` (STRING): Urgency level for consumers (STOP_USE_IMMEDIATELY, STOP_USE_SOON, USE_WITH_CAUTION, MONITOR)
- `vulnerable_population_risk` (BOOLEAN): Whether children or vulnerable populations are at elevated risk
- `reasoning` (STRING): Detailed reasoning from the Safety Analyst

### QUALITY_ASSESSMENTS

The `QUALITY_ASSESSMENTS` table consists of the following columns:

- `recall_id` (INTEGER, primary key): CPSC recall identifier
- `assessment_type` (STRING): Always "quality" for this table
- `quality_risk_score` (INTEGER): Risk score from 1-10 (manufacturing quality perspective)
- `root_cause_assessment` (STRING): Root cause classification (DESIGN_FLAW, BATCH_DEFECT, MATERIAL_FAILURE, SUPPLIER_ISSUE, LABELING_ERROR, UNKNOWN)
- `containment_feasibility` (STRING): Whether the defect can be contained (FULLY_CONTAINED, PARTIALLY_CONTAINED, UNCONTAINED)
- `remedy_adequacy` (STRING): Whether the manufacturer's remedy is adequate (ADEQUATE, PARTIALLY_ADEQUATE, INADEQUATE)
- `recall_proportionality` (STRING): Whether the recall scope is proportionate (PROPORTIONATE, OVER_BROAD, UNDER_SCOPED)
- `reasoning` (STRING): Detailed reasoning from the Quality Engineer

### DEBATE_CONSENSUS

The `DEBATE_CONSENSUS` table consists of the following columns:

- `recall_id` (INTEGER, primary key): CPSC recall identifier
- `assessment_type` (STRING): Always "consensus" for this table
- `final_severity` (STRING): Balanced final severity (CRITICAL, HIGH, MEDIUM, LOW)
- `consensus_risk_score` (INTEGER): Consensus risk score from 1-10
- `debate_winner` (STRING): Which expert was more persuasive (SAFETY, QUALITY, DRAW)
- `winner_rationale` (STRING): Explanation of why the winning expert was more persuasive
- `agreement_areas` (STRING): JSON array of areas where both experts agreed
- `disagreement_areas` (STRING): JSON array of areas where experts disagreed
- `disagreement_flag` (BOOLEAN): Whether the experts significantly disagreed on this recall
- `disagreement_severity` (STRING): Severity of disagreement (NONE, MINOR, SIGNIFICANT, FUNDAMENTAL)
- `human_review_recommended` (BOOLEAN): Whether human review is recommended
- `recommended_action` (STRING): Recommended next action for the quality team
- `executive_summary` (STRING): Balanced executive summary of the debate outcome

## Genie Space

When `enable_genie_space` is set to `true`, the connector creates a Databricks Genie Space after data lands. The Genie Space is configured with product safety-specific instructions and sample questions including "Which recalls have disagreement flags where the experts disagreed?" and "Show me all recalls with CRITICAL final severity."

The Genie Space is created only once. The `space_id` is persisted in the connector state to avoid creating duplicates on subsequent syncs.

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

This is the third Databricks AI tutorial connector in the Fivetran SDK repository, following the FDA Drug Label Intelligence connector (PR #567, simple enrichment) and SEC EDGAR Risk Intelligence connector (PR #568, agent-driven discovery). It demonstrates the Multi-Agent Debate pattern where two AI experts with opposing perspectives analyze the same data, producing richer analysis than a single enrichment pass. The `disagreement_flag` column is the key innovation, identifying records that need human review.

The CPSC SaferProducts API is free and requires no authentication. The connector includes a browser-compatible User-Agent header and rate limiting delays between requests.

Databricks `ai_query()` consumes SQL Warehouse compute credits. The debate pattern makes 3 ai_query() calls per recall (safety analyst, quality engineer, consensus). Use `max_enrichments` to control costs during development. Set `enable_enrichment` to `false` to test the data pipeline without AI costs.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
