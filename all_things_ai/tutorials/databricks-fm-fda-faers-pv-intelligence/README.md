# Databricks FDA FAERS Pharmacovigilance Intelligence Connector Example

## Connector overview

This connector syncs adverse event reports from the [FDA Adverse Event Reporting System (FAERS)](https://open.fda.gov/apis/drug/event/) via the OpenFDA Drug Event API and enriches each serious event with AI-powered multi-agent debate analysis using the Databricks [ai_query()](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function. Two AI personas with opposing pharmacovigilance perspectives analyze each event, then a consensus agent synthesizes both views and flags disagreements for human PV review.

The connector features a two-phase architecture:

- Phase 1 (MOVE): Fetch adverse event reports from the OpenFDA Drug Event API, optionally filtered by drug name
- Phase 2 (DEBATE): For each serious event, three ai_query() calls produce competing analyses:
  1. Safety Advocate: risk-maximizing pharmacovigilance perspective, flags potential safety signals
  2. Clinical Realist: context-aware clinical perspective, considers patient demographics and concomitant medications
  3. Consensus Agent: synthesizes both, produces disagreement_flag and debate_winner

The `disagreement_flag` identifies adverse events where the two experts significantly disagree on whether the event represents a real safety signal, flagging them for human pharmacovigilance review.

Optionally, the connector can create a [Genie Space](https://docs.databricks.com/en/genie/index.html) for natural language analytics after the data lands.

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

- Syncs adverse event reports from the free OpenFDA Drug Event API (no API key required, 20M+ reports available)
- Multi-Agent Debate: Safety Advocate vs Clinical Realist with consensus synthesizer
- Disagreement flag identifies events where experts disagree on safety signal validity
- Debate winner field shows which expert was more persuasive for each event
- Drug-specific filtering via `search_drug` parameter (e.g., "lipitor", "aspirin")
- AI enrichment via Databricks `ai_query()` SQL function using Claude Sonnet 4.6 (configurable model)
- Optional Genie Space creation with pharmacovigilance-specific instructions and sample questions
- Incremental sync using receive date as a cursor
- Configurable enrichment budget via `max_enrichments` (3x ai_query calls per event)
- Data-only mode when `enable_enrichment` is set to `false`
- Per-event checkpointing for reliable resumable syncs during the debate phase
- Async polling for long-running ai_query() statements

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
  "search_drug": "<DRUG_NAME_OR_EMPTY>",
  "max_events": "<MAX_EVENTS_PER_SYNC>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "lookback_days": "<LOOKBACK_DAYS>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

- `databricks_workspace_url` (required when enrichment or Genie enabled): Full Databricks workspace URL including `https://`
- `databricks_token` (required when enrichment or Genie enabled): Databricks Personal Access Token with SQL execution permissions
- `databricks_warehouse_id` (required when enrichment or Genie enabled): SQL Warehouse ID for `ai_query()` execution
- `databricks_model` (optional): Databricks Foundation Model name. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` to sync events without AI debate. Default: `true`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space after sync. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path (format: `catalog.schema.table`)
- `search_drug` (optional): Drug name to filter adverse events (e.g., "lipitor", "aspirin"). Omit to fetch all events
- `max_events` (optional): Maximum events to sync per run. Default: `10`. Maximum: `100`
- `max_enrichments` (optional): Maximum events to run through debate (3 ai_query calls each). Default: `5`. Maximum: `50`
- `lookback_days` (optional): Days to look back on initial sync. Default: `30`
- `databricks_timeout` (optional): Timeout in seconds for Databricks API calls. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The OpenFDA Drug Event API is free and requires no authentication. An optional API key provides higher rate limits (120K requests/day vs 240/minute without key).

Databricks access requires a Personal Access Token (PAT) with SQL execution permissions:

1. Go to your Databricks workspace.
2. Click your username in the top-right corner and select **Settings**.
3. Click **Developer** in the left panel.
4. Click **Manage** next to **Access tokens**.
5. Click **Generate new token**, provide a description, and click **Generate**.
6. Copy the token value and set it as `databricks_token` in your `configuration.json`.

## Pagination

The OpenFDA Drug Event API supports offset-based pagination via `skip` and `limit` parameters (max 100 per page). The connector paginates with `def fetch_all_events(session, search_query, max_events)` until either `max_events` records have been collected or the API runs out of matching events. Incremental sync uses a compound `(last_receive_date, last_safety_report_id)` cursor: because OpenFDA's `receivedate` range filter is inclusive, the connector skips any event whose `(receivedate, safety_report_id)` tuple is at or below the persisted cursor so a sync that hits `max_events` mid-day re-resumes correctly without duplicating records. The search URL is built manually to preserve Lucene syntax; the user-supplied `search_drug` is Lucene-escaped and URL-encoded by `def _build_search_query(start_date, end_date, search_drug)` before being placed in the URL.

## Data handling

The `def update(configuration, state)` function orchestrates a three-phase sync pipeline:

Phase 1 (MOVE):
1. Validates configuration via `def validate_configuration(configuration)`
2. Builds a Lucene search query from the `last_receive_date` state cursor (or `lookback_days` for initial sync) and optional `search_drug` filter via `def _build_search_query(start_date, end_date, search_drug)`
3. Fetches adverse events via `def fetch_all_events(session, search_query, max_events)` which paginates with `def fetch_adverse_events(session, search_query, limit, skip)` under the hood and reports whether the cap was hit
4. Skips any event whose `(receivedate, safety_report_id)` tuple is at or below the cursor (handles OpenFDA's inclusive range semantics)
5. Builds normalized records via `def build_event_record(event)` extracting primary drug, primary reaction, patient demographics, seriousness indicators, and full drug/reaction lists
6. Upserts records and checkpoints with the latest `(receivedate, safety_report_id)` cursor

Phase 2 (DEBATE):
7. Filters to serious events only for debate (events where `serious = "1"`)
8. For each serious event, runs three ai_query() calls via `def run_multi_agent_debate(session, configuration, events, event_records, state)`:
   - `def build_safety_prompt(event_record)` for the Safety Advocate (signal detection, escalation recommendation)
   - `def build_clinical_prompt(event_record)` for the Clinical Realist (causality assessment, clinical context)
   - `def build_consensus_prompt(event_record, safety_result, clinical_result)` for synthesis
9. Checkpoints after each event is debated

Phase 3 (AGENT):
10. If enabled, the connection creates a Genie Space via `def create_genie_space(session, configuration, state)`

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params)` provides exponential backoff retry logic for transient API failures with immediate failure on access errors
- `def call_ai_query(session, configuration, prompt)` catches specific exception types and returns None on failure, with async polling for PENDING/RUNNING SQL statements
- Individual debate agent failures are handled gracefully: if either analyst returns None, the consensus step is skipped for that event
- `def validate_configuration(configuration)` validates all required parameters using `def _is_placeholder(value)`
- Sanity ceilings enforce maximum values for `max_events` (100) and `max_enrichments` (50)
- The session is always closed via a try/finally block

## Tables created

The connector creates the `ADVERSE_EVENTS`, `SAFETY_ASSESSMENTS`, `CLINICAL_ASSESSMENTS`, and `DEBATE_CONSENSUS` tables.

### ADVERSE_EVENTS

The `ADVERSE_EVENTS` table consists of the following columns:

- `safety_report_id` (STRING, primary key): FDA safety report identifier
- `receive_date` (STRING): Date the report was received (YYYYMMDD format)
- `is_serious` (BOOLEAN): Whether the event was classified as serious
- `seriousness_death` (BOOLEAN): Whether the event resulted in death
- `seriousness_hospitalization` (BOOLEAN): Whether the event required hospitalization
- `seriousness_life_threatening` (BOOLEAN): Whether the event was life-threatening
- `seriousness_disabling` (BOOLEAN): Whether the event caused disability
- `primary_drug` (STRING): Name of the primary suspect drug
- `primary_reaction` (STRING): Primary adverse reaction (MedDRA preferred term)
- `patient_age` (STRING): Patient age at onset
- `patient_age_unit` (STRING): Age unit code
- `patient_sex` (STRING): Patient sex (Male, Female, Unknown)
- `patient_weight` (STRING): Patient weight in kg
- `drug_count` (INTEGER): Number of drugs reported
- `reaction_count` (INTEGER): Number of reactions reported
- `drug_list` (STRING): JSON array of all drug names
- `reaction_list` (STRING): JSON array of all reaction terms
- `report_type` (STRING): Report type code
- `sender_organization` (STRING): Organization that submitted the report
- `occurrence_country` (STRING): Country where the event occurred

### SAFETY_ASSESSMENTS

The `SAFETY_ASSESSMENTS` table consists of the following columns:

- `safety_report_id` (STRING, primary key): FDA safety report identifier
- `assessment_type` (STRING): Always "safety"
- `safety_signal_score` (INTEGER): Signal strength score from 1-10 (risk-maximizing)
- `signal_classification` (STRING): CONFIRMED_SIGNAL, POTENTIAL_SIGNAL, EXPECTED_REACTION, or INSUFFICIENT_DATA
- `escalation_recommendation` (STRING): IMMEDIATE, ROUTINE, MONITOR, or NONE
- `drug_interaction_concern` (BOOLEAN): Whether drug interactions may contribute
- `vulnerable_population_flag` (BOOLEAN): Whether vulnerable populations are at elevated risk
- `reasoning` (STRING): Detailed reasoning from the Safety Advocate

### CLINICAL_ASSESSMENTS

The `CLINICAL_ASSESSMENTS` table consists of the following columns:

- `safety_report_id` (STRING, primary key): FDA safety report identifier
- `assessment_type` (STRING): Always "clinical"
- `clinical_risk_score` (INTEGER): Clinical risk score from 1-10 (context-aware)
- `causality_assessment` (STRING): CERTAIN, PROBABLE, POSSIBLE, UNLIKELY, or UNASSESSABLE
- `expected_for_drug_class` (BOOLEAN): Whether the reaction is expected for this drug class
- `concomitant_medication_concern` (BOOLEAN): Whether concomitant medications may explain the reaction
- `reporting_quality` (STRING): HIGH, MEDIUM, or LOW
- `reasoning` (STRING): Detailed reasoning from the Clinical Realist

### DEBATE_CONSENSUS

The `DEBATE_CONSENSUS` table consists of the following columns:

- `safety_report_id` (STRING, primary key): FDA safety report identifier
- `assessment_type` (STRING): Always "consensus"
- `final_severity` (STRING): Balanced final severity (CRITICAL, HIGH, MEDIUM, LOW)
- `consensus_risk_score` (INTEGER): Consensus risk score from 1-10
- `debate_winner` (STRING): Which expert was more persuasive (SAFETY, CLINICAL, DRAW)
- `winner_rationale` (STRING): Explanation of why the winning expert was more persuasive
- `agreement_areas` (STRING): JSON array of areas where both experts agreed
- `disagreement_areas` (STRING): JSON array of areas where experts disagreed
- `disagreement_flag` (BOOLEAN): Whether the experts significantly disagreed
- `disagreement_severity` (STRING): NONE, MINOR, SIGNIFICANT, or FUNDAMENTAL
- `pv_review_recommended` (BOOLEAN): Whether human PV review is recommended
- `recommended_action` (STRING): Recommended next action for the PV team
- `executive_summary` (STRING): Balanced executive summary of the debate outcome

## Genie Space

When `enable_genie_space` is set to `true`, the connector creates a Databricks Genie Space after data lands. The Genie Space is configured with pharmacovigilance-specific instructions and sample questions including "Which adverse events have disagreement flags needing PV review?" and "What drugs have the most serious adverse events?"

The Genie Space is created only once. The `space_id` is persisted in the connector state to avoid creating duplicates on subsequent syncs.

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

This connector pairs with the [FDA Drug Label Intelligence community connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/databricks-fm-fda-drug-label-intelligence) to provide a complete drug safety pipeline on Databricks. Drug labels provide the reference data (interactions, contraindications, black box warnings) while FAERS adverse events provide post-market surveillance data. Together they map directly to the Databricks BioPharma outcome "Pharmacovigilance (Drug Safety and Adverse Event Detection)."

The OpenFDA Drug Event API is free and requires no authentication. Rate limits apply (240 requests per minute without key). The connector includes rate limiting delays between requests.

Databricks `ai_query()` consumes SQL Warehouse compute credits. The debate pattern makes 3 ai_query() calls per serious event. Use `max_enrichments` to control costs. Set `enable_enrichment` to `false` for data-only mode.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
