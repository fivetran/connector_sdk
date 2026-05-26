# Snowflake Cortex Clinical Trial Intelligence Connector Example

## Connector overview

This connector syncs clinical trial records from the ClinicalTrials.gov API v2.0 and enriches them with AI-powered analysis using Snowflake Cortex Agent. It's designed for pharmaceutical companies, biotech firms, clinical research organizations, and investment firms that need automated monitoring of clinical trial landscapes for competitive intelligence, portfolio management, and regulatory strategy.

The connector combines two advanced architectural patterns to deliver automated clinical trial landscape intelligence:

### Pattern A (Agent-Driven Discovery)

A Cortex Agent analyzes seed trials fetched for a configured therapeutic area and recommends related trials to fetch automatically. The agent identifies competing therapies, same drug class trials, same patient population studies, and competing sponsor programs. The connector then fetches those discovered trials without human intervention, expanding coverage beyond the original search.

### Pattern B (Multi-Agent Debate)

Two Cortex Agent personas with opposing expert perspectives evaluate each trial. An Optimist evaluates trial design strengths (sample size, randomization, blinding, endpoint selection, sponsor track record). A Skeptic flags methodology risks (dropout potential, endpoint concerns, statistical power, regulatory hurdles). A Consensus synthesizer produces a balanced evaluation with a disagreement flag that highlights trials where the agents significantly disagree, directing human expert attention to the trials that matter most.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs clinical trial records from ClinicalTrials.gov API v2.0 with no authentication required
- Agent-Driven Discovery automatically expands trial coverage beyond the initial search using Cortex Agent recommendations
- Multi-Agent Debate evaluates each trial from opposing perspectives (Optimist vs Skeptic) with a Consensus synthesizer
- Disagreement flags identify trials where AI agents significantly disagree, directing human expert review to the highest-value targets
- Incremental sync tracks the last update post date to fetch only new or modified trials on subsequent syncs
- Graceful degradation allows data-only mode when Cortex is disabled or unavailable
- Configurable limits for seed trials, discoveries, and debates to control API and Cortex costs
- Per-trial checkpointing during the debate phase prevents data loss on interruption

## Configuration file

The `configuration.json` file accepts the following parameters:

```json
{
    "condition": "<THERAPEUTIC_AREA>",
    "status_filter": "<OVERALL_STATUS>",
    "intervention_filter": "<INTERVENTION_SEARCH>",
    "sponsor_filter": "<SPONSOR_SEARCH>",
    "max_seed_trials": "<MAX_SEED_TRIALS>",
    "max_discoveries": "<MAX_DISCOVERIES>",
    "max_debates": "<MAX_DEBATES>",
    "page_size": "<PAGE_SIZE>",
    "enable_cortex": "<TRUE_OR_FALSE>",
    "snowflake_account": "<SNOWFLAKE_ACCOUNT_HOSTNAME>",
    "snowflake_pat_token": "<SNOWFLAKE_PAT_TOKEN>",
    "cortex_model": "<CORTEX_MODEL>",
    "cortex_timeout": "<CORTEX_TIMEOUT_SECONDS>"
}
```

- `condition` (required): Therapeutic area or condition to search for (e.g., `breast cancer`, `type 2 diabetes`)
- `status_filter` (optional): Filter by overall trial status (e.g., `RECRUITING`, `COMPLETED`, `ACTIVE_NOT_RECRUITING`). Omit or use placeholder to include all statuses
- `intervention_filter` (optional): Additional filter by intervention/treatment name
- `sponsor_filter` (optional): Additional filter by sponsor organization name
- `max_seed_trials` (optional): Maximum number of seed trials to fetch per sync. Default: `20`, max: `500`. For larger pulls, run multiple syncs and rely on the incremental cursor to advance.
- `max_discoveries` (optional): Maximum number of new trials to discover via agent recommendations. Default: `10`
- `max_debates` (optional): Maximum number of trials to run through Multi-Agent Debate per sync. Default: `5`
- `page_size` (optional): Number of trials per API page request. Default: `20`, max: `1000`
- `enable_cortex` (optional): Set to `true` to enable Cortex Agent for Discovery and Debate phases. Default: `false`
- `snowflake_account` (required when Cortex enabled): Snowflake account hostname ending in `snowflakecomputing.com` (for example, `xy12345.us-west-2.snowflakecomputing.com`). Do not include a scheme like `http://` or `https://` — the connector constructs the request URL itself.
- `snowflake_pat_token` (required when Cortex enabled): Snowflake Programmatic Access Token for Cortex API authentication
- `cortex_model` (optional): Cortex model to use. Default: `claude-sonnet-4-6`
- `cortex_timeout` (optional): Timeout in seconds for Cortex API calls. Default: `60`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The ClinicalTrials.gov API v2.0 requires no authentication. The connector can fetch trial data without any API key or credentials.

For Cortex Agent enrichment (Phases 2 and 3), the connector authenticates with Snowflake using a Programmatic Access Token (PAT). To generate a PAT:

1. Log in to your Snowflake account.
2. Go to **Settings** > **Security** > **Programmatic access tokens**.
3. Create a new token. The Snowflake user must have the `SNOWFLAKE.CORTEX_USER` database role granted to use Cortex inference.
4. Copy the token value and set it as `snowflake_pat_token` in your configuration.

Set `snowflake_account` to the Snowflake hostname only (for example, `xy12345.us-west-2.snowflakecomputing.com`). The connector rejects configuration values that start with `http://` or `https://`.

## Pagination

The connector uses cursor-based pagination via the ClinicalTrials.gov API v2.0 `pageToken` mechanism. Each API response includes a `nextPageToken` value that the connector passes to the next request to retrieve the following page of results. The `pageSize` parameter controls how many trials are returned per page (default: `20`, maximum: `1000`).

The connector continues paginating until it reaches the configured `max_seed_trials` limit or exhausts all available results. After each page, the connector upserts the records it received, persists the `nextPageToken` and composite incremental cursor to state, and checkpoints so that an interrupted sync can resume without duplicate work or gaps.

## Data handling

The `def update(configuration, state)` function orchestrates three sequential phases:

Phase 1 (Seed): The `def fetch_and_upsert_seed_trials(session, configuration, state)` function queries the ClinicalTrials.gov API for trials matching the configured condition. It applies optional filters for status, intervention, and sponsor. Records are upserted one page at a time so peak memory stays bounded regardless of the configured `max_seed_trials` value. For incremental syncs, the function uses a composite cursor of `last_update_post_date` plus the set of `nct_id` values already synced on that date (stored in `synced_nct_ids_at_cursor`). Because `lastUpdatePostDate` is day-granularity, this composite cursor guarantees that trials sharing the cursor date are not skipped when `max_seed_trials` caps a prior window. The `def build_trial_record(study)` function extracts key fields from the deeply nested API response and flattens them into a single-level dictionary.

Phase 2 (Discovery): The `def run_discovery_phase(session, configuration, trial_records, state)` function sends seed trial summaries to a Cortex Agent that identifies competing therapies, related drug classes, and recruitment overlaps. The agent returns recommended search terms, which the connector executes against the ClinicalTrials.gov API to fetch new trials not in the seed set.

Phase 3 (Debate): The `def run_debate_phase(configuration, trial_records, state)` function runs three Cortex Agent personas per trial. The `def build_optimist_prompt(trial_record)` function generates the design-strength evaluation prompt. The `def build_skeptic_prompt(trial_record)` function generates the methodology-risk evaluation prompt. The `def build_consensus_prompt(trial_record, optimist_result, skeptic_result)` function generates the synthesis prompt that reads both assessments and produces a final evaluation with a disagreement flag.

All nested API responses are flattened using `def flatten_dict(d, parent_key, sep)` before upsert. Lists and arrays are serialized to JSON strings for warehouse compatibility.

## Error handling

The `def fetch_data_with_retry(session, url, params)` function implements exponential backoff retry logic for transient API failures. HTTP 429, 500, 502, 503, and 504 status codes trigger automatic retries with exponential backoff (1s, 2s, 4s). HTTP 401 and 403 errors fail immediately with a descriptive credential check message. The connector validates all required configuration parameters in `def validate_configuration(configuration)` before starting the sync.

Cortex Agent failures are handled gracefully in `def call_cortex_agent(configuration, prompt, cortex_session)`. Timeouts, HTTP errors, connection errors, and JSON parse failures are caught individually (no generic exception handling) and return None, allowing the sync to continue with data-only results. Streaming responses are closed in a finally block to prevent resource leaks. When Cortex is disabled or all agent calls fail, Phase 1 data still syncs successfully.

## Tables created

### TRIALS

The `TRIALS` table consists of the following columns:
- `nct_id` (STRING, primary key): ClinicalTrials.gov NCT identifier (e.g., NCT06085833)
- `brief_title` (STRING): Short title of the clinical trial
- `official_title` (STRING): Full official title of the trial
- `acronym` (STRING): Trial acronym if assigned
- `overall_status` (STRING): Current recruitment status (RECRUITING, COMPLETED, etc.)
- `brief_summary` (STRING): Summary description of the trial
- `conditions` (STRING): JSON array of conditions/diseases studied
- `keywords` (STRING): JSON array of keywords associated with the trial
- `study_type` (STRING): Type of study (INTERVENTIONAL, OBSERVATIONAL)
- `phases` (STRING): JSON array of trial phases (PHASE1, PHASE2, PHASE3, etc.)
- `allocation` (STRING): Allocation method (RANDOMIZED, NON_RANDOMIZED, NA)
- `intervention_model` (STRING): Intervention model (PARALLEL, SINGLE_GROUP, etc.)
- `primary_purpose` (STRING): Primary purpose (TREATMENT, PREVENTION, DIAGNOSTIC, etc.)
- `masking` (STRING): Masking/blinding approach (DOUBLE, SINGLE, NONE, etc.)
- `enrollment_count` (INTEGER): Target or actual enrollment count
- `enrollment_type` (STRING): ESTIMATED or ACTUAL enrollment
- `lead_sponsor_name` (STRING): Name of the lead sponsor organization
- `lead_sponsor_class` (STRING): Sponsor classification (INDUSTRY, NIH, OTHER_GOV, etc.)
- `start_date` (STRING): Trial start date
- `completion_date` (STRING): Expected or actual completion date
- `last_update_post_date` (STRING): Date of the last update posted to ClinicalTrials.gov
- `eligibility_criteria` (STRING): Full text of eligibility criteria
- `sex` (STRING): Eligible sex (ALL, MALE, FEMALE)
- `minimum_age` (STRING): Minimum eligible age
- `maximum_age` (STRING): Maximum eligible age
- `healthy_volunteers` (STRING): Whether healthy volunteers are accepted
- `interventions` (STRING): JSON array of intervention details
- `arm_groups` (STRING): JSON array of study arm/group details
- `has_results` (BOOLEAN): Whether the trial has posted results
- `synced_at` (STRING): ISO 8601 timestamp of when the record was synced

### DISCOVERY_INSIGHTS

The `DISCOVERY_INSIGHTS` table consists of the following columns:
- `nct_id` (STRING, primary key): NCT identifier or "DISCOVERY_ANALYSIS" for the overall analysis record
- `assessment_type` (STRING): Always "discovery"
- `discovery_source` (STRING): Source of discovery (agent_recommended for discovered trials)
- `analysis_summary` (STRING): Agent's summary of the seed trial landscape
- `recommended_searches` (STRING): JSON array of recommended search terms with rationale
- `competing_therapies_identified` (STRING): JSON array of competing therapies found
- `recruitment_overlap_risk` (STRING): Risk level for recruitment competition (HIGH, MEDIUM, LOW)
- `therapeutic_landscape_gaps` (STRING): JSON array of identified gaps in the therapeutic landscape
- `assessed_at` (STRING): ISO 8601 timestamp of the assessment

### OPTIMIST_ASSESSMENTS

The `OPTIMIST_ASSESSMENTS` table consists of the following columns:
- `nct_id` (STRING, primary key): NCT identifier of the assessed trial
- `assessment_type` (STRING): Always "optimist"
- `design_strength_score` (INTEGER): Overall design strength score (1-10)
- `sample_size_assessment` (STRING): Sample size adequacy (ADEQUATE, BORDERLINE, UNDERPOWERED, OVERPOWERED)
- `randomization_quality` (STRING): Randomization quality (EXCELLENT, GOOD, ACCEPTABLE, POOR)
- `blinding_quality` (STRING): Blinding approach quality assessment
- `endpoint_quality` (STRING): Endpoint selection quality (STRONG, MODERATE, WEAK)
- `sponsor_strength` (STRING): Sponsor track record (ESTABLISHED, EMERGING, UNKNOWN)
- `success_probability` (STRING): Overall success probability (HIGH, MODERATE, LOW)
- `key_strengths` (STRING): JSON array of identified design strengths
- `reasoning` (STRING): Detailed reasoning for the assessment
- `assessed_at` (STRING): ISO 8601 timestamp of the assessment

### SKEPTIC_ASSESSMENTS

The `SKEPTIC_ASSESSMENTS` table consists of the following columns:
- `nct_id` (STRING, primary key): NCT identifier of the assessed trial
- `assessment_type` (STRING): Always "skeptic"
- `methodology_risk_score` (INTEGER): Overall methodology risk score (1-10)
- `dropout_risk` (STRING): Patient dropout risk (HIGH, MODERATE, LOW)
- `endpoint_concerns` (STRING): Endpoint quality concerns (SIGNIFICANT, MINOR, NONE)
- `statistical_power_risk` (STRING): Statistical power risk (UNDERPOWERED, ADEQUATE, WELL_POWERED)
- `regulatory_hurdle_risk` (STRING): Regulatory approval risk (HIGH, MODERATE, LOW)
- `recruitment_feasibility` (STRING): Patient recruitment feasibility (CHALLENGING, FEASIBLE, EASY)
- `failure_probability` (STRING): Overall failure probability (HIGH, MODERATE, LOW)
- `key_risks` (STRING): JSON array of identified methodology risks
- `reasoning` (STRING): Detailed reasoning for the assessment
- `assessed_at` (STRING): ISO 8601 timestamp of the assessment

### DEBATE_CONSENSUS

The `DEBATE_CONSENSUS` table consists of the following columns:
- `nct_id` (STRING, primary key): NCT identifier of the assessed trial
- `assessment_type` (STRING): Always "consensus"
- `overall_quality` (STRING): Balanced quality assessment (EXCELLENT, GOOD, FAIR, POOR)
- `consensus_score` (INTEGER): Synthesized quality score (1-10)
- `debate_winner` (STRING): Which analyst was more persuasive (OPTIMIST, SKEPTIC, DRAW)
- `winner_rationale` (STRING): Explanation of why the winning analyst's assessment was more persuasive
- `agreement_areas` (STRING): JSON array of areas where Optimist and Skeptic agree
- `disagreement_areas` (STRING): JSON array of areas where they disagree
- `disagreement_flag` (BOOLEAN): True when agents significantly disagree, indicating the trial needs human expert review
- `disagreement_severity` (STRING): Severity of disagreement (NONE, MINOR, SIGNIFICANT, FUNDAMENTAL)
- `human_review_recommended` (BOOLEAN): Whether human expert review is recommended
- `monitoring_priority` (STRING): Recommended monitoring priority (WATCH_CLOSELY, PERIODIC_REVIEW, LOW_PRIORITY)
- `recommended_action` (STRING): Specific recommended action for this trial
- `executive_summary` (STRING): Concise executive summary of the balanced assessment
- `assessed_at` (STRING): ISO 8601 timestamp of the assessment

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

The ClinicalTrials.gov API v2.0 is a free public API with no authentication required. While there are no documented rate limits, the connector uses connection pooling via requests.Session and respects reasonable request pacing. For Cortex Agent enrichment, costs are determined by the configured cortex_model and the number of trials processed through the Discovery and Debate phases. Use the max_seed_trials, max_discoveries, and max_debates configuration parameters to control costs.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
