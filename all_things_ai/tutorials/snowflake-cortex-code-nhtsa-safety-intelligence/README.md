# Snowflake Cortex Code NHTSA Safety Intelligence Connector Example

## Connector overview

This connector syncs vehicle recall campaigns, consumer safety complaints, and vehicle specifications from NHTSA (National Highway Traffic Safety Administration) public APIs, then uses Snowflake Cortex Agent to analyze the data and autonomously discover related vehicles to investigate. This is the agent-driven discovery pattern: the AI analyzes initial safety data and decides which additional vehicles to fetch next based on shared components, platform similarities, and cross-manufacturer safety trends.

Built entirely with Snowflake Cortex Code and the Fivetran Connector Builder Skill.

Use cases:
- Automotive safety intelligence - Analyze recall and complaint patterns across vehicle makes, models, and years to identify systemic safety issues
- Agent-driven discovery - Let Snowflake Cortex Agent autonomously decide which related vehicles to investigate based on component failure patterns
- Cross-vehicle synthesis - Generate fleet-wide safety grades and component risk rankings across multiple vehicles
- Regulatory monitoring - Track NHTSA recall campaigns and consumer complaints for specific vehicles or entire manufacturer fleets

APIs used:
- [NHTSA Recalls API](https://api.nhtsa.gov) - Vehicle recall campaigns by make/model/year
- [NHTSA Complaints API](https://api.nhtsa.gov) - Consumer safety complaints by make/model/year
- [NHTSA vPIC API](https://vpic.nhtsa.dot.gov/api/) - Vehicle product information catalog (models for a make)
- [Snowflake Cortex Agent](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-llm-rest-api) - Discovery analysis and cross-vehicle synthesis via REST API

Key capabilities:
- Three-phase sync: seed vehicle fetch, agent-driven discovery, cross-vehicle synthesis
- Agent autonomy: Cortex Agent recommends which related vehicles to investigate next
- Real-time AI enrichment during data ingestion
- Component failure pattern analysis across vehicle platforms
- Cost control with configurable discovery and enrichment limits
- Graceful degradation: works without Cortex (data-only mode) when AI is disabled


## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- Snowflake account with Cortex enabled (for Agent-Driven Discovery phases)
- Snowflake Personal Access Token (PAT) for Cortex API access


## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template all_things_ai/tutorials/snowflake-cortex-code-nhtsa-safety-intelligence
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- Exponential backoff retry logic for transient API failures and rate limiting
- Automatic PascalCase-to-snake_case field normalization for warehouse compatibility
- Nested structure flattening and list-to-JSON serialization


## Configuration file

The connector requires the following configuration parameters in `configuration.json`:

```json
{
    "seed_make": "<VEHICLE_MAKE>",
    "seed_model": "<VEHICLE_MODEL>",
    "seed_year": "<MODEL_YEAR>",
    "discovery_depth": "<DISCOVERY_DEPTH_1_TO_3>",
    "max_discoveries": "<MAX_VEHICLES_PER_DISCOVERY>",
    "enable_cortex": "<TRUE_OR_FALSE>",
    "snowflake_account": "<YOUR_SNOWFLAKE_ACCOUNT_HOSTNAME>",
    "snowflake_pat_token": "<YOUR_SNOWFLAKE_PAT>",
    "cortex_model": "<CORTEX_MODEL_NAME>",
    "max_enrichments": "<MAX_CORTEX_ENRICHMENTS>"
}
```

Configuration parameters:
- `seed_make` (required) - Vehicle manufacturer to start investigation (e.g., "Tesla", "Toyota", "Ford")
- `seed_model` (required) - Vehicle model to start investigation (e.g., "Model 3", "Camry", "F-150")
- `seed_year` (required) - Model year to start investigation (e.g., "2023")
- `discovery_depth` (optional) - Discovery phase depth: 0=data only, 1=discovery only, 2=discovery+synthesis. Defaults to "2"
- `max_discoveries` (optional) - Maximum vehicles the agent can discover per sync. Defaults to "3"
- `enable_cortex` (optional) - Enable Snowflake Cortex Agent for discovery and synthesis phases. Defaults to "false"
- `snowflake_account` (conditional) - Snowflake account URL (e.g., "orgname-acctname.snowflakecomputing.com"), required if Cortex is enabled
- `snowflake_pat_token` (conditional) - Snowflake Personal Access Token, required if Cortex is enabled
- `cortex_model` (optional) - Cortex LLM model for analysis. Defaults to "claude-sonnet-4-6"
- `max_enrichments` (optional) - Maximum Cortex API calls per sync for cost control. Defaults to "10"

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Authentication

NHTSA APIs:
- No authentication required for any NHTSA endpoint
- All three APIs (Recalls, Complaints, vPIC) are free and public
- The connector includes a descriptive User-Agent header as a courtesy

Snowflake Cortex Agent:
- Uses [Personal Access Token (PAT) authentication](https://docs.snowflake.com/en/en/user-guide/programmatic-access-tokens#label-pat-generate)
- Generate PAT via Snowflake UI: Profile > Account Settings > Security > Personal Access Tokens
- Token format: "ver:1-hint:abc123..."
- Token is sent as a Bearer token in the Authorization header


## Pagination

NHTSA APIs return all results for a given make/model/year in a single response. No pagination is required.

The connector processes discovered vehicles sequentially with rate limiting delays (0.5 seconds between API calls) to respect NHTSA server capacity.


## Data handling

The connector processes data through a three-phase pipeline, implemented in `def update(configuration, state)`:

**Phase 1 - Seed Vehicle Fetch:**
1. Fetch recalls from NHTSA Recalls API via `def fetch_recalls(session, make, model, year)`
2. Fetch complaints from NHTSA Complaints API via `def fetch_complaints(session, make, model, year)`
3. Fetch vehicle specs from NHTSA vPIC API via `def fetch_vehicle_specs(session, make)`
4. Normalize PascalCase API field names to snake_case and upsert records

**Phase 2 - Agent-driven discovery (requires Cortex):**
1. Build analysis prompt with component failure summaries via `def build_discovery_prompt(make, model, year, recalls, complaints)`
2. Call Cortex Agent for pattern analysis via `def call_cortex_agent(configuration, prompt, cortex_session=None)`
3. Agent recommends related vehicles based on shared components and safety patterns
4. Fetch recalls, complaints, and specs for each discovered vehicle
5. Upsert discovery insights with component risk rankings

**Phase 3 - Cross-Vehicle Synthesis (requires Cortex and multiple vehicles):**
1. Build synthesis prompt with pre-computed aggregate data via `def build_synthesis_prompt(vehicles_investigated, aggregates)` using component frequency counts instead of full in-memory record lists
2. Call Cortex Agent for fleet-wide analysis
3. Upsert safety analysis with component risk rankings and fleet safety grade

Data transformations:
- PascalCase API field names normalized to snake_case (e.g., `NHTSACampaignNumber` becomes `nhtsa_campaign_number`)
- Nested dictionaries flattened using underscore separators via `def flatten_dict(d, parent_key, sep)`
- Lists serialized to JSON strings for warehouse compatibility
- State checkpointed after each phase and each discovered vehicle


## Error handling

The connector implements comprehensive error handling - refer to `def fetch_data_with_retry(session, url, params, headers)`:

Retry logic:
- Exponential backoff for transient failures (429, 500, 502, 503, 504 status codes)
- Maximum 3 retry attempts with delays of 1s, 2s, 4s
- Connection errors and timeouts are retried with the same backoff pattern
- Non-retryable errors (401, 403) are logged and raised immediately

Cortex Agent handling via `def call_cortex_agent(configuration, prompt, cortex_session=None)`:
- Retry logic with exponential backoff for transient failures (429, 500, 502, 503, 504)
- Authentication errors (401, 403) are logged and not retried
- Agent timeouts are retried up to 3 times; sync continues without AI enrichment if all fail
- Invalid JSON responses from the agent are logged and treated as empty results
- Empty agent responses result in skipped discovery/synthesis phases
- Markdown code fences in agent responses are automatically stripped before JSON parsing
- LLM output is type-validated before use (e.g., recommended_vehicles must be a list of dicts)
- `max_enrichments` budget is enforced with a counter before each Cortex call
- Cortex calls use a dedicated `requests.Session` via `def _create_cortex_session(configuration)` for TCP connection pooling across discovery and synthesis phases
- Streaming responses are explicitly closed via `response.close()` in a finally block

Validation:
- Configuration validation occurs before sync starts - refer to `def validate_configuration(configuration)`
- Records without primary keys are logged as warnings and skipped
- Snowflake account URL format validated when Cortex is enabled


## Tables created

The connector creates five tables covering NHTSA safety data and AI-generated insights.

### RECALLS

Vehicle recall campaign records from the NHTSA Recalls API.

Primary key: `nhtsa_campaign_number`, `make`, `model`, `model_year`

| Column | Type | Description |
|--------|------|-------------|
| `nhtsa_campaign_number` | STRING | NHTSA recall campaign identifier |
| `manufacturer` | STRING | Vehicle manufacturer name |
| `make` | STRING | Vehicle make |
| `model` | STRING | Vehicle model |
| `model_year` | STRING | Model year |
| `component` | STRING | Affected component (e.g., "ELECTRICAL SYSTEM", "AIR BAGS") |
| `summary` | STRING | Recall description and affected vehicles |
| `consequence` | STRING | Safety consequence of the defect |
| `remedy` | STRING | Manufacturer remedy and owner notification details |
| `notes` | STRING | Additional notes including NHTSA hotline information |
| `report_received_date` | STRING | Date NHTSA received the recall report (DD/MM/YYYY) |
| `park_it` | BOOLEAN | Whether the vehicle should be parked immediately |
| `park_outside` | BOOLEAN | Whether the vehicle should be parked outside |
| `over_the_air_update` | BOOLEAN | Whether the recall can be resolved via OTA software update |
| `nhtsa_action_number` | STRING | Related NHTSA enforcement action number |
| `source` | STRING | Record source: "seed" or "discovered" |

### COMPLAINTS

Consumer safety complaint records from the NHTSA Complaints API.

Primary key: `odi_number`

| Column | Type | Description |
|--------|------|-------------|
| `odi_number` | INTEGER | NHTSA Office of Defects Investigation number |
| `manufacturer` | STRING | Vehicle manufacturer name |
| `crash` | BOOLEAN | Whether a crash was involved |
| `fire` | BOOLEAN | Whether a fire was involved |
| `number_of_injuries` | INTEGER | Number of injuries reported |
| `number_of_deaths` | INTEGER | Number of deaths reported |
| `date_of_incident` | STRING | Date of the safety incident (MM/DD/YYYY) |
| `date_complaint_filed` | STRING | Date the complaint was filed (MM/DD/YYYY) |
| `vin` | STRING | Partial vehicle identification number |
| `components` | STRING | Affected vehicle components |
| `summary` | STRING | Consumer complaint narrative |
| `products` | STRING | JSON-serialized array of affected product details |
| `source` | STRING | Record source: "seed" or "discovered" |

### VEHICLE_SPECS

Vehicle model specifications from the NHTSA vPIC API.

Primary key: `make_id`, `model_id`

| Column | Type | Description |
|--------|------|-------------|
| `make_id` | INTEGER | NHTSA make identifier |
| `make_name` | STRING | Vehicle manufacturer name |
| `model_id` | INTEGER | NHTSA model identifier |
| `model_name` | STRING | Vehicle model name |
| `source` | STRING | Record source: "seed" or "discovered" |

### DISCOVERY_INSIGHTS

AI-generated discovery analysis from the Cortex Agent (Phase 2).

Primary key: `insight_id`

| Column | Type | Description |
|--------|------|-------------|
| `insight_id` | STRING | Unique insight identifier |
| `seed_make` | STRING | Seed vehicle make |
| `seed_model` | STRING | Seed vehicle model |
| `seed_year` | STRING | Seed vehicle year |
| `top_components` | STRING | JSON-serialized array of top failing components with severity |
| `severity_score` | INTEGER | Overall severity score (1-10) |
| `crash_count` | INTEGER | Number of crash incidents identified |
| `fire_count` | INTEGER | Number of fire incidents identified |
| `recommended_vehicles` | STRING | JSON-serialized array of vehicles the agent recommends investigating |
| `analysis_summary` | STRING | Agent-generated analysis narrative |

### SAFETY_ANALYSIS

AI-generated cross-vehicle synthesis from the Cortex Agent (Phase 3).

Primary key: `analysis_id`

| Column | Type | Description |
|--------|------|-------------|
| `analysis_id` | STRING | Unique analysis identifier |
| `seed_make` | STRING | Seed vehicle make |
| `seed_model` | STRING | Seed vehicle model |
| `seed_year` | STRING | Seed vehicle year |
| `vehicles_analyzed` | INTEGER | Number of vehicles included in the analysis |
| `total_recalls_analyzed` | INTEGER | Total recall records analyzed |
| `total_complaints_analyzed` | INTEGER | Total complaint records analyzed |
| `component_risk_rankings` | STRING | JSON-serialized array of component risk rankings across all vehicles |
| `manufacturer_response_score` | INTEGER | Manufacturer response quality score (1-10) |
| `systemic_issues` | STRING | JSON-serialized array of systemic industry issues identified |
| `fleet_safety_grade` | STRING | Overall fleet safety grade (A-F) |
| `executive_summary` | STRING | Agent-generated executive summary |


## Cost considerations

Cortex Agent enrichment costs scale with the discovery depth and number of discovered vehicles:

Example cost projections (using claude-sonnet-4-6 model):
- Data-only mode (enable_cortex=false): $0.00 per sync (NHTSA APIs are free)
- Discovery only (discovery_depth=1, max_discoveries=3): approximately $0.002 per sync (1 agent call)
- Full pipeline (discovery_depth=2, max_discoveries=3): approximately $0.004 per sync (2 agent calls)

Use the `discovery_depth` and `max_discoveries` configuration parameters to control costs during testing and production.


## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

Agent-driven discovery pattern:
- The agent analyzes component failure patterns and recommends related vehicles based on shared platforms, competitor vehicles in the same class, and adjacent model years
- Discovery is bounded by `max_discoveries` to prevent runaway API usage
- The agent returns structured JSON that the connector parses to determine next fetch targets

Sync behavior:
- This connector performs full refresh on each sync
- NHTSA data changes infrequently (new recalls and complaints are added periodically)
- Recommended sync frequency: every 24 hours for monitoring, weekly for general analysis
- The connector checkpoints after each phase and each discovered vehicle for safe resumption
