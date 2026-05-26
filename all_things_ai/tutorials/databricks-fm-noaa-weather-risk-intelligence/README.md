# Databricks NOAA Weather Risk Intelligence Connector Example

## Connector overview

This connector syncs severe weather alerts from the [NOAA Weather API](https://www.weather.gov/documentation/services-web-api) and enriches them with AI-powered hybrid analysis using the Databricks [ai_query()](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function. It combines Agent-Driven Discovery (identifying related regions affected by the same weather system) with Multi-Agent Debate (Emergency Response vs Resource Planning perspectives) in a single connector.

The connector features a four-phase architecture:

- Phase 1 (MOVE): Fetch weather alerts from NOAA Weather API for configured states
- Phase 2 (DISCOVERY): ai_query() analyzes weather patterns and recommends additional states to investigate for related weather system impact. The connector fetches alerts for discovered states automatically.
- Phase 3 (DEBATE): For each significant event, three ai_query() calls produce competing analyses:
  1. Emergency Response Analyst: urgency-maximizing, advocates immediate evacuation and resource deployment
  2. Resource Planning Analyst: probability-weighted impact assessment, proportional allocation
  3. Consensus Agent: synthesizes both, produces disagreement_flag, debate_winner, and recommended_action
- Phase 4 (AGENT): Optional [Genie Space](https://docs.databricks.com/en/genie/index.html) creation for natural language weather risk analytics

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A Databricks workspace with a SQL Warehouse that supports `ai_query()` (required for AI analysis; optional for data-only mode)
- A Databricks Personal Access Token (PAT) with SQL execution permissions

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs severe weather alerts from the free NOAA Weather API (no API key required)
- Hybrid AI pattern: combines agent-driven discovery with multi-agent debate in a single connector
- Discovery phase identifies additional states affected by the same weather systems
- Debate phase produces Emergency Response vs Resource Planning perspectives with disagreement flags
- AI enrichment via Databricks `ai_query()` SQL function using Claude Sonnet 4.6 (configurable model)
- Optional Genie Space creation with weather risk-specific instructions and sample questions
- Configurable state monitoring via `alert_states` parameter (e.g., tornado alley: TX,OK,KS)
- Severity filtering to focus debate analysis on significant events only
- Per-event checkpointing for reliable resumable syncs during discovery and debate phases
- Async polling for long-running ai_query() statements that exceed the SQL wait timeout
- Data-only mode when `enable_enrichment` is set to `false`

## Configuration file

The `configuration.json` file contains the following parameters:

```json
{
  "alert_states": "<COMMA_SEPARATED_STATE_CODES>",
  "databricks_workspace_url": "<DATABRICKS_WORKSPACE_URL>",
  "databricks_token": "<DATABRICKS_PAT_TOKEN>",
  "databricks_warehouse_id": "<DATABRICKS_WAREHOUSE_ID>",
  "databricks_model": "<DATABRICKS_MODEL_NAME>",
  "enable_enrichment": "<TRUE_OR_FALSE>",
  "enable_discovery": "<TRUE_OR_FALSE>",
  "enable_genie_space": "<TRUE_OR_FALSE>",
  "genie_table_identifier": "<CATALOG.SCHEMA.TABLE>",
  "max_events": "<MAX_EVENTS_PER_STATE>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "max_discovery_regions": "<MAX_DISCOVERED_STATES>",
  "severity_filter": "<COMMA_SEPARATED_SEVERITIES>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

- `alert_states` (optional): Comma-separated US state codes to monitor. Default: `TX,OK,KS` (tornado alley)
- `databricks_workspace_url` (required when enrichment or Genie enabled): Full Databricks workspace URL including `https://`
- `databricks_token` (required when enrichment or Genie enabled): Databricks Personal Access Token with SQL execution permissions
- `databricks_warehouse_id` (required when enrichment or Genie enabled): SQL Warehouse ID for `ai_query()` execution
- `databricks_model` (optional): Databricks Foundation Model name. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` to sync weather data without AI analysis. Default: `true`
- `enable_discovery` (optional): Set to `false` to skip discovery of related states. Default: `true`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space after sync. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path (format: `catalog.schema.table`)
- `max_events` (optional): Maximum events to process per state. Default: `20`. Maximum: `200`
- `max_enrichments` (optional): Maximum ai_query() calls for discovery + debate combined. Default: `5`. Maximum: `20`
- `max_discovery_regions` (optional): Maximum states to discover per seed state. Default: `3`. Maximum: `10`
- `severity_filter` (optional): Comma-separated severity levels for debate phase. Default: `Severe,Extreme`
- `databricks_timeout` (optional): Timeout in seconds for Databricks API calls. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The NOAA Weather API is free and requires no authentication. A `User-Agent` header with contact information is required per NOAA API usage policies. The connector includes this header automatically.

Databricks access requires a Personal Access Token (PAT) with SQL execution permissions:

1. Go to your Databricks workspace.
2. Click your username in the top-right corner and select **Settings**.
3. Click **Developer** in the left panel.
4. Click **Manage** next to **Access tokens**.
5. Click **Generate new token**, provide a description, and click **Generate**.
6. Copy the token value and set it as `databricks_token` in your `configuration.json`.

## Pagination

The NOAA Weather API returns alerts as a GeoJSON feature collection. The connector fetches up to `max_events` alerts per state in a single request, iterating across configured seed states and AI-discovered states. Checkpointing occurs after each state fetch and after each debate to support resumable syncs.

## Data handling

The `def update(configuration, state)` function orchestrates a four-phase sync pipeline:

Phase 1 (MOVE):
1. Validates configuration via `def validate_configuration(configuration)`
2. Fetches weather alerts for each seed state via `def fetch_alerts_for_state(session, state_code)` using the NOAA Weather API
3. Builds normalized event records via `def build_event_record(feature, source_label)` and upserts to the weather_events table

Phase 2 (DISCOVERY):
4. For each seed state, builds a weather pattern analysis prompt via `def build_discovery_prompt(state_code, events_summary)` and calls `def call_ai_query(session, configuration, prompt)`
5. The AI identifies the dominant weather system and recommends adjacent states to investigate
6. The connector fetches alerts for discovered states and upserts them with source="discovered"
7. Type-checks LLM output before using recommended states

Phase 3 (DEBATE):
8. Filters events by severity for debate (configurable via `severity_filter`)
9. For each significant event, runs three ai_query() calls via `def run_debate_phase(session, configuration, events, event_records, state)`:
   - `def build_emergency_prompt(event_record)` for the Emergency Response Analyst
   - `def build_planning_prompt(event_record)` for the Resource Planning Analyst
   - `def build_consensus_prompt(event_record, emergency_result, planning_result)` for synthesis
10. Checkpoints after each event is debated

Phase 4 (AGENT):
11. If enabled, creates a Genie Space via `def create_genie_space(session, configuration, state)`

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params)` provides exponential backoff retry logic for transient NOAA API failures with immediate failure on access errors
- `def call_ai_query(session, configuration, prompt)` catches specific exception types and returns None on failure, with async polling for PENDING/RUNNING SQL statements
- Discovery failures for individual states are caught and logged without failing the sync
- Individual debate agent failures are handled gracefully: if either analyst returns None, the consensus step is skipped for that event
- `def validate_configuration(configuration)` validates all required parameters using `def _is_placeholder(value)`
- Sanity ceilings enforce maximum values for `max_events` (200), `max_enrichments` (20), and `max_discovery_regions` (10)
- The session is always closed via a try/finally block

## Tables created

### WEATHER_EVENTS

The `WEATHER_EVENTS` table consists of the following columns:

- `event_id` (STRING, primary key): Unique event identifier derived from NOAA alert ID
- `noaa_id` (STRING): Original NOAA alert URN identifier
- `event_type` (STRING): Weather event type (e.g., "Tornado Warning", "Severe Thunderstorm Warning")
- `severity` (STRING): NOAA severity level (Minor, Moderate, Severe, Extreme)
- `certainty` (STRING): Certainty level (Possible, Likely, Observed)
- `urgency` (STRING): Urgency level (Future, Expected, Immediate)
- `headline` (STRING): Alert headline text
- `description` (STRING): Detailed event description (truncated to 2000 chars)
- `instruction` (STRING): Safety instructions for affected populations
- `area_desc` (STRING): Description of affected geographic areas
- `affected_zones` (STRING): JSON array of affected NOAA weather zones
- `onset` (STRING): Event onset time (ISO 8601)
- `expires` (STRING): Alert expiration time (ISO 8601)
- `ends` (STRING): Expected event end time (ISO 8601)
- `sent` (STRING): Time the alert was issued
- `effective` (STRING): Time the alert became effective
- `sender_name` (STRING): Name of the issuing NWS office
- `status` (STRING): NOAA alert status (Actual, Exercise, System, Test, Draft)
- `message_type` (STRING): Alert message type (Alert, Update, Cancel, Ack, Error)
- `category` (STRING): NOAA category code (Met, Geo, Safety, Security, Rescue, Fire, Health, Env, Transport, Infra, CBRNE, Other)
- `source` (STRING): Whether this event was from a "seed" state or "discovered" by the AI

### DISCOVERY_INSIGHTS

The `DISCOVERY_INSIGHTS` table consists of the following columns:

- `insight_id` (STRING, primary key): Unique identifier (e.g., "discovery_TX")
- `state_code` (STRING): State analyzed
- `weather_system` (STRING): AI-identified dominant weather system
- `system_severity` (STRING): Severity of the weather system (EXTREME, SEVERE, MODERATE, MINOR)
- `recommended_states` (STRING): JSON array of states recommended for investigation with reasoning
- `regional_risk_summary` (STRING): AI-generated summary of regional weather risk
- `source` (STRING): Analysis source label

### EMERGENCY_ASSESSMENTS

The `EMERGENCY_ASSESSMENTS` table consists of the following columns:

- `event_id` (STRING, primary key): Weather event identifier
- `assessment_type` (STRING): Always "emergency"
- `emergency_risk_score` (INTEGER): Risk score from 1-10 (urgency-maximizing)
- `worst_case_impact` (STRING): Description of worst-case impact scenario
- `evacuation_recommendation` (STRING): ORDER, RECOMMEND, STANDBY, or UNNECESSARY
- `resource_deployment` (STRING): FULL, PARTIAL, STANDBY, or NONE
- `estimated_population_at_risk` (STRING): Estimated population exposure
- `reasoning` (STRING): Detailed reasoning from the Emergency Response Analyst

### PLANNING_ASSESSMENTS

The `PLANNING_ASSESSMENTS` table consists of the following columns:

- `event_id` (STRING, primary key): Weather event identifier
- `assessment_type` (STRING): Always "planning"
- `planning_risk_score` (INTEGER): Risk score from 1-10 (probability-weighted)
- `expected_impact` (STRING): Probability-weighted expected impact assessment
- `evacuation_assessment` (STRING): PROPORTIONATE, EXCESSIVE, INSUFFICIENT, or UNNECESSARY
- `resource_recommendation` (STRING): FULL, PARTIAL, STANDBY, or NONE
- `cost_effectiveness` (STRING): HIGH, MEDIUM, or LOW
- `reasoning` (STRING): Detailed reasoning from the Resource Planning Analyst

### DEBATE_CONSENSUS

The `DEBATE_CONSENSUS` table consists of the following columns:

- `event_id` (STRING, primary key): Weather event identifier
- `assessment_type` (STRING): Always "consensus"
- `final_severity` (STRING): Balanced final severity (CRITICAL, HIGH, MEDIUM, LOW)
- `consensus_risk_score` (INTEGER): Consensus risk score from 1-10
- `debate_winner` (STRING): Which expert was more persuasive (EMERGENCY, PLANNING, DRAW)
- `winner_rationale` (STRING): Explanation of why the winning expert was more persuasive
- `agreement_areas` (STRING): JSON array of areas where both experts agreed
- `disagreement_areas` (STRING): JSON array of areas where experts disagreed
- `disagreement_flag` (BOOLEAN): Whether the experts significantly disagreed
- `disagreement_severity` (STRING): Severity of disagreement (NONE, MINOR, SIGNIFICANT, FUNDAMENTAL)
- `recommended_action` (STRING): Balanced recommended action for emergency management
- `executive_summary` (STRING): Balanced executive summary of the debate outcome

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

Databricks `ai_query()` consumes SQL Warehouse compute credits. The hybrid pattern makes multiple `ai_query()` calls per sync: one per seed state for discovery analysis, plus 3 per significant event for debate. Use `max_enrichments` to control costs. Set `enable_enrichment` to `false` for data-only mode, or `enable_discovery` to `false` to skip discovery and run debate only.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
