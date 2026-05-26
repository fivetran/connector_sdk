# Databricks FDA Drug Label Intelligence Connector Example

## Connector overview

This connector syncs drug labeling data (package inserts) from the [OpenFDA Drug Labeling API](https://open.fda.gov/apis/drug/label/) and enriches each label with AI-powered analysis using the Databricks [ai_query()](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function during ingestion. Optionally, the connector creates a [Genie Space](https://docs.databricks.com/en/genie/index.html) on the enriched data so analysts can query drug label intelligence in natural language.

The connector demonstrates the full Fivetran data lifecycle on Databricks:

- MOVE: Fetch drug labels from the free OpenFDA API into Databricks via Fivetran
- TRANSFORM: Enrich each label with AI analysis via `ai_query()` running on the SQL Warehouse
- AGENT: Create a Genie Space with pharma-specific instructions and sample questions

AI enrichment uses `ai_query()` through the Databricks SQL Statement Execution API, which runs on the SQL warehouse. This avoids the need for a separate foundation model serving endpoint and works with any personal access token (PAT) that has SQL execution permissions. The default model is `databricks-claude-sonnet-4-6`.

Enrichments include drug interaction risk classification (HIGH/MEDIUM/LOW), plain-English contraindication summaries, black box warning detection and summarization, patient-friendly drug descriptions, and AI-classified therapeutic categories.

This is the first Databricks AI tutorial connector in the Fivetran SDK repository, designed for healthcare and BioPharma analytics use cases.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A Databricks workspace with a SQL warehouse that supports `ai_query()` (required for AI enrichment; optional for data-only mode)
- A Databricks personal access token (PAT) with SQL execution permissions

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs drug labeling data from the free OpenFDA Drug Labeling API (no API key required)
- AI enrichment via Databricks `ai_query()` SQL function using Claude Sonnet 4.6 (configurable model)
- Optional Genie Space creation with pharma-specific instructions and sample questions for natural language analytics
- Incremental sync using the label effective date as a cursor to fetch only new or updated labels
- Configurable enrichment budget via `max_enrichments` to control SQL Warehouse compute costs
- Data-only mode when `enable_enrichment` is set to `false` for syncing labels without AI enrichment
- Batch processing with per-batch checkpointing for reliable resumable syncs
- Exponential backoff retry logic for both OpenFDA and Databricks SQL Statement API calls
- Automatic text truncation for long label sections to stay within model token limits

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
  "max_labels": "<MAX_LABELS_PER_SYNC>",
  "batch_size": "<BATCH_SIZE>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```
Configuration parameters:

- `databricks_workspace_url` (required when enrichment or Genie enabled): Full Databricks workspace URL including `https://` (e.g., `https://dbc-xxxxx.cloud.databricks.com`)
- `databricks_token` (required when enrichment or Genie enabled): Databricks personal access token with SQL execution permissions
- `databricks_warehouse_id` (required when enrichment or Genie enabled): SQL Warehouse ID to execute `ai_query()` statements and create Genie Spaces
- `databricks_model` (optional): Databricks Foundation Model name for `ai_query()`. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` to sync drug labels without AI enrichment. Default: `true`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space on the enriched data after sync. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path for the Genie Space data source in the following format: `catalog.schema.table`
- `max_labels` (optional): Maximum number of drug labels to sync per run. Default: `25`. Maximum: `500`
- `batch_size` (optional): Number of labels to process per batch before checkpointing. Default: `5`
- `max_enrichments` (optional): Maximum number of `ai_query()` enrichment calls per sync to control costs. Default: `25`. Maximum: `500`
- `databricks_timeout` (optional): Timeout in seconds for Databricks SQL Statement API calls. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The OpenFDA Drug Labeling API is free and requires no authentication.

Databricks access requires a personal access token (PAT) with SQL execution permissions. To obtain the PAT:

1. Navigate to your Databricks workspace.
2. Click your username in the top-right corner and select **Settings**.
3. Click **Developer** in the left panel.
4. Select **Manage** next to **Access tokens**.
5. Click **Generate new token**.
6. Provide a description and click **Generate**.
7. Copy the token value and set it as `databricks_token` in your `configuration.json`.

The PAT must have permissions to execute SQL statements on the specified SQL warehouse. The `ai_query()` function is available on Databricks SQL Warehouses with Foundation Model APIs enabled.

## Pagination

The connector uses offset-based pagination with the OpenFDA API. Each sync fetches labels in batches controlled by the `batch_size` parameter (default: `5`). The connector tracks progress via the `skip` parameter and checkpoints state after each batch so that interrupted syncs resume from the last completed batch rather than restarting.

## Data handling

The `def update(configuration, state)` function orchestrates a three-phase sync pipeline:

Phase 1 (MOVE):
1. Validates configuration via `def validate_configuration(configuration)` including Databricks credential checks when enrichment or Genie Space creation is enabled.
2. Builds an incremental date filter from the saved `last_effective_time` state cursor.
3. Fetches drug labels page by page from the OpenFDA API via `def fetch_labels_page(session, skip, limit, effective_date_filter)`.

Phase 2 (TRANSFORM):
1. For each label, builds a normalized record via `def build_label_record(label, label_id)` extracting brand name, generic name, manufacturer, route, substance, and clinical section indicators.
2. If enrichment is enabled and within the enrichment budget, extracts clinical text sections via `def extract_label_text_sections(label)` and calls `ai_query()` via `def enrich_drug_label(session, configuration, sections)` for AI analysis.
3. Flattens any nested structures via `def flatten_dict(d, parent_key, sep)` and upserts to the destination table.
4. Checkpoints state after each batch with the latest effective time cursor.

Phase 3 (AGENT):
If Genie Space creation is enabled and data was synced, creates a Genie Space via `def create_genie_space(session, configuration, state)` with pharma-specific instructions and sample questions pointed at the destination table.

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params, headers)` provides exponential backoff retry logic for transient API failures (HTTP 429, 500, 502, 503, 504) with immediate failure on authentication errors (401, 403)
- `def call_ai_query(session, configuration, prompt)` catches specific exception types (Timeout, HTTPError, ConnectionError, RequestException, JSONDecodeError) and returns None on failure, allowing the sync to continue with unenriched records
- `def create_genie_space(session, configuration, state)` catches HTTP and request errors and logs warnings without failing the sync, since data has already landed successfully
- `def validate_configuration(configuration)` validates all required parameters upfront using `def _is_placeholder(value)` to detect uncommitted placeholder values
- Sanity ceilings enforce maximum values for `max_labels` (500) and `max_enrichments` (500) to prevent runaway costs
- The session is always closed via a try/finally block in `def update(configuration, state)` to release resources even on unexpected errors

## Tables created

### DRUG_LABELS_ENRICHED

The `DRUG_LABELS_ENRICHED` table consists of the following columns:

- `label_id` (STRING, primary key): Unique identifier composed of set_id and version (e.g., `abc123_1`)
- `set_id` (STRING): FDA-assigned set identifier for the drug label
- `version` (STRING): Label version number
- `effective_time` (STRING): Date the label became effective (YYYYMMDD format)
- `brand_name` (STRING): Brand name of the drug (e.g., "Lipitor")
- `generic_name` (STRING): Generic chemical name (e.g., "atorvastatin calcium")
- `manufacturer_name` (STRING): Name of the drug manufacturer
- `product_type` (STRING): FDA product type classification
- `route` (STRING): JSON array of administration routes (e.g., oral, intravenous)
- `substance_name` (STRING): JSON array of active substance names
- `rxcui` (STRING): JSON array of RxNorm concept unique identifiers
- `spl_id` (STRING): Structured Product Labeling identifier
- `application_number` (STRING): FDA application number (NDA/ANDA/BLA)
- `pharm_class_epc` (STRING): JSON array of established pharmacologic class
- `has_drug_interactions` (BOOLEAN): Whether the label contains a drug interactions section
- `has_contraindications` (BOOLEAN): Whether the label contains a contraindications section
- `has_boxed_warning` (BOOLEAN): Whether the label contains a boxed (black box) warning section
- `has_warnings` (BOOLEAN): Whether the label contains a warnings section
- `interaction_risk_level` (STRING): AI-classified drug interaction risk level (HIGH, MEDIUM, or LOW). Populated when enrichment is enabled
- `contraindication_summary` (STRING): AI-generated plain-English summary of key contraindications. Populated when enrichment is enabled
- `has_black_box_warning` (BOOLEAN): AI-determined presence of a boxed warning based on label text analysis. Populated when enrichment is enabled
- `black_box_summary` (STRING): AI-generated summary of the boxed warning content. Populated when enrichment is enabled
- `patient_friendly_description` (STRING): AI-generated patient-friendly description of what the drug does and what it treats. Populated when enrichment is enabled
- `therapeutic_category` (STRING): AI-classified therapeutic category (e.g., Cardiovascular, Oncology, Neurology). Populated when enrichment is enabled
- `enrichment_model` (STRING): Name of the Databricks Foundation Model used for enrichment

## Genie Space

When `enable_genie_space` is set to `true`, the connector creates a Databricks Genie Space after data lands. The Genie Space is configured with:

- Pharma-specific instructions that guide the Genie agent to prioritize patient safety insights and use the AI enrichment fields for filtering
- Five sample questions including "Which drugs have HIGH interaction risk and a black box warning?" and "Show me all cardiovascular drugs sorted by interaction risk level"
- A pointer to the destination table specified in `genie_table_identifier`

The Genie Space is created only once. The `space_id` is persisted in the connector state to avoid creating duplicates on subsequent syncs.

Note: The `genie_table_identifier` must be a fully qualified Unity Catalog path (e.g., `my_catalog.my_schema.drug_labels_enriched`). The table must exist in the Databricks workspace before the Genie Space can query it, so the Genie Space is most useful after at least one successful sync with `fivetran deploy`.

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

This is the first Databricks AI tutorial connector in the Fivetran SDK repository. It uses `ai_query()` through the SQL Statement Execution API rather than a dedicated model serving endpoint, which simplifies setup and works with standard SQL Warehouse permissions. The optional Genie Space creation demonstrates the full Move, Transform, Agent data lifecycle within a single connector.

The OpenFDA API is free and does not require authentication. Rate limits apply (240 requests per minute without an API key, higher with a key). The connector includes rate limiting delays between requests to stay within these limits.

Databricks `ai_query()` consumes SQL warehouse compute credits. Costs vary by model and token usage. Use the `max_enrichments` parameter to control costs during development and testing. Set `enable_enrichment` to `false` to test the data pipeline without incurring compute costs.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
