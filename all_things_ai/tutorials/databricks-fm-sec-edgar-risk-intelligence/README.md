# Databricks SEC EDGAR Risk Intelligence Connector Example

## Connector overview

This connector syncs SEC EDGAR financial filing data (10-K/10-Q filings and XBRL financial facts) from the [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and enriches it with AI-powered credit risk analysis using the Databricks [`ai_query()`](https://docs.databricks.com/en/large-language-models/ai-functions.html) SQL function. The connector uses an Agent-Driven Discovery pattern where the AI analyzes seed company financials and autonomously recommends related companies to investigate for systemic risk exposure.

The connector features a three-phase core architecture:

- Phase 1 (SEED): Fetch company info and XBRL financial facts for configured seed companies from SEC EDGAR
- Phase 2 (DISCOVERY): ai_query() analyzes each seed company's financials, identifies credit risk signals, and recommends related companies to investigate (suppliers, competitors, counterparties). The connector fetches data for discovered companies automatically.
- Phase 3 (SYNTHESIS): `ai_query()` synthesizes patterns across all companies (seed + discovered) to identify systemic exposure, counterparty risks, and portfolio-level risk grades

Optionally, the connector can create a [Genie Space](https://docs.databricks.com/en/genie/index.html) for natural language analytics on the enriched financial data. This is disabled by default. Enable it with `enable_genie_space=true` in configuration. This phase is independent of the three-phase core architecture and can be enabled without affecting other phases.

## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A Databricks workspace with a SQL Warehouse that supports `ai_query()` (required for AI enrichment and discovery; optional for data-only mode)
- A Databricks Personal Access Token (PAT) with SQL execution permissions
- One or more SEC EDGAR CIK numbers for seed companies

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features

- Syncs company filing metadata and XBRL financial facts from the free SEC EDGAR APIs (no API key required)
- Agent-Driven Discovery: AI analyzes seed company financials and recommends related companies to investigate for systemic risk
- AI enrichment via Databricks `ai_query()` SQL function using Claude Sonnet 4.6 (configurable model)
- Cross-company risk synthesis with portfolio-level grading and counterparty risk identification
- Optional Genie Space creation with financial risk-specific instructions and sample questions
- Data-only mode when `enable_enrichment` is set to `false` for syncing filings without AI analysis
- Per-company checkpointing for reliable resumable syncs across all three phases
- Exponential backoff retry logic for SEC EDGAR API calls; bounded async polling (12 attempts × 10s) on PENDING/RUNNING `ai_query()` statements with explicit pre-poll guard for missing `statement_id`
- Async polling for long-running ai_query() statements that exceed the SQL wait timeout

## Configuration file

The `configuration.json` file contains the following parameters:

```json
{
  "seed_companies": "<COMMA_SEPARATED_CIK_NUMBERS>",
  "databricks_workspace_url": "<DATABRICKS_WORKSPACE_URL>",
  "databricks_token": "<DATABRICKS_PAT_TOKEN>",
  "databricks_warehouse_id": "<DATABRICKS_WAREHOUSE_ID>",
  "databricks_model": "<DATABRICKS_MODEL_NAME>",
  "enable_enrichment": "<TRUE_OR_FALSE>",
  "enable_discovery": "<TRUE_OR_FALSE>",
  "enable_genie_space": "<TRUE_OR_FALSE>",
  "genie_table_identifier": "<CATALOG.SCHEMA.TABLE>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "max_discovery_companies": "<MAX_DISCOVERED_COMPANIES>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

- `seed_companies` (required): Comma-separated list of SEC EDGAR CIK numbers to start with (e.g., `0000320193,0000789019,0001018724` for Apple, Microsoft, Amazon). CIK numbers are zero-padded to 10 digits automatically. Maximum: `20`
- `databricks_workspace_url` (required when enrichment or Genie enabled): Full Databricks workspace URL including `https://` (e.g., `https://dbc-xxxxx.cloud.databricks.com`)
- `databricks_token` (required when enrichment or Genie enabled): Databricks Personal Access Token with SQL execution permissions
- `databricks_warehouse_id` (required when enrichment or Genie enabled): SQL Warehouse ID to execute `ai_query()` statements and create Genie Spaces
- `databricks_model` (optional): Databricks Foundation Model name for `ai_query()`. Default: `databricks-claude-sonnet-4-6`
- `enable_enrichment` (optional): Set to `false` to sync filing data without AI risk analysis. Default: `true`
- `enable_discovery` (optional): Set to `false` to run AI analysis on seed companies only without discovering related companies. Default: `true`
- `enable_genie_space` (optional): Set to `true` to create a Genie Space on the enriched data after sync. Default: `false`
- `genie_table_identifier` (required when Genie enabled): Unity Catalog table path for the Genie Space data source (format: `catalog.schema.table`)
- `max_enrichments` (optional): Maximum number of `ai_query()` enrichment calls per sync to control costs. Default: `10`. Maximum: `50`
- `max_discovery_companies` (optional): Maximum number of discovered companies to fetch per seed company. Default: `3`. Maximum: `10`
- `databricks_timeout` (optional): Timeout in seconds for Databricks SQL Statement API calls. Default: `120`

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The SEC EDGAR APIs are free and do not require authentication. A `User-Agent` header with contact information is required per SEC EDGAR fair access policies. The connector includes this header automatically.

Databricks access requires a Personal Access Token (PAT) with SQL execution permissions:

1. Go to your Databricks workspace.
2. Click your username in the top-right corner and select **Settings**.
3. Click **Developer** in the left panel.
4. Click **Manage** next to **Access tokens**.
5. Click **Generate new token**, provide a description, and click **Generate**.
6. Copy the token value and set it as `databricks_token` in your `configuration.json`.

## Pagination

The SEC EDGAR Company Facts API returns all XBRL financial facts for a company in a single response (no pagination needed). The connector iterates through configured seed companies and agent-discovered companies sequentially, checkpointing after each company to support resumable syncs.

## Data handling

The `def update(configuration, state)` function orchestrates a three-phase core sync pipeline (plus optional Genie Space creation):

Phase 1 (SEED):
1. Validates configuration via `def validate_configuration(configuration)` including Databricks credential checks and sanity ceiling enforcement
2. Parses seed CIK numbers from configuration and zero-pads them via `def pad_cik(cik)`
3. For each seed company, fetches submission info via `def fetch_company_info(session, cik)` and XBRL financial facts via `def fetch_company_facts(session, cik)`
4. Extracts key financial metrics (Assets, Liabilities, Revenue, Net Income, Debt, etc.) via `def extract_latest_facts(facts_data, cik)` and upserts to destination tables

Phase 2 (DISCOVERY):
5. For each seed company, builds a credit risk analysis prompt with financial data via `def build_discovery_prompt(company_name, cik, facts_summary)` and calls `def call_ai_query(session, configuration, prompt)`
6. The AI identifies risk signals, calculates key ratios, and recommends related companies (suppliers, competitors, counterparties) with CIK numbers and reasoning
7. The connector fetches data for discovered companies via `def fetch_and_upsert_company(session, cik, source_label, state)`, type-checking LLM output before use
8. Discovery insights (credit risk scores, risk signals, recommended companies) are upserted to the discovery_insights table

Phase 3 (SYNTHESIS):
9. Builds a cross-company analysis prompt via `def build_synthesis_prompt(companies_analyzed, all_facts)` covering all seed and discovered companies
10. The AI identifies systemic risks, counterparty exposure, and assigns a portfolio-level grade
11. Uses async polling for long-running synthesis queries that exceed the SQL wait timeout

Phase 4 (AGENT — optional, disabled by default):
12. If the `enable_genie_space=` is set to `true`, the connector creates a Genie Space via `def create_genie_space(session, configuration, state)` with financial risk-specific instructions and sample questions. This phase is independent of the three-phase core architecture (SEED, DISCOVERY, SYNTHESIS) and can be enabled without affecting other phases.

## Error handling

The connector implements error handling at multiple levels:

- `def fetch_data_with_retry(session, url, params)` provides exponential backoff retry logic for transient SEC EDGAR API failures (HTTP 429, 500, 502, 503, 504) with immediate failure on authentication errors (401, 403)
- `def call_ai_query(session, configuration, prompt)` catches specific exception types (Timeout, HTTPError, ConnectionError, RequestException, JSONDecodeError) and returns None on failure, allowing the sync to continue with unenriched records. Includes async polling for PENDING/RUNNING SQL statements
- Discovery failures for individual companies are caught and logged without failing the sync, so partial discovery results are preserved
- `def validate_configuration(configuration)` validates all required parameters upfront using `def _is_placeholder(value)` to detect uncommitted placeholder values
- Sanity ceilings enforce maximum values for `max_enrichments` (50), `max_discovery_companies` (10), and `max_seed_companies` (20) to prevent runaway costs
- LLM output is type-checked before use (isinstance validation on recommended_companies list)
- The session is always closed via a try/finally block in `def update(configuration, state)` to release resources even on unexpected errors

## Tables created

The connector creates the `COMPANY_FILINGS`, `FINANCIAL_FACTS`, `DISCOVERY_INSIGHTS`, and `RISK_ANALYSIS` tables.

### COMPANY_FILINGS

The `COMPANY_FILINGS` table consists of the following columns:

- `cik` (STRING, primary key): SEC EDGAR Central Index Key, zero-padded to 10 digits
- `company_name` (STRING): Legal company name from SEC filings
- `ticker` (STRING): Primary stock ticker symbol
- `all_tickers` (STRING): JSON array of all ticker symbols associated with the company
- `sic` (STRING): Standard Industrial Classification code
- `sic_description` (STRING): SIC code description (e.g., "Electronic Computers")
- `state` (STRING): State of incorporation
- `fiscal_year_end` (STRING): Fiscal year end month/day (e.g., "0930" for September 30)
- `latest_10k_date` (STRING): Filing date of the most recent 10-K annual report
- `latest_10q_date` (STRING): Filing date of the most recent 10-Q quarterly report
- `total_filings` (INTEGER): Total number of filings in SEC EDGAR
- `source` (STRING): Whether this company was a "seed" or "discovered" by the AI agent

### FINANCIAL_FACTS

The `FINANCIAL_FACTS` table consists of the following columns:

- `fact_id` (STRING, primary key): Unique identifier composed of CIK and metric name
- `cik` (STRING): SEC EDGAR Central Index Key
- `metric` (STRING): XBRL financial metric name (e.g., "Assets", "Revenues", "NetIncomeLoss", "LongTermDebt")
- `value` (FLOAT): Metric value in USD
- `form` (STRING): SEC form type (10-K or 10-Q)
- `filed` (STRING): Date the filing was submitted to SEC
- `fiscal_year` (INTEGER): Fiscal year of the reported period
- `fiscal_period` (STRING): Fiscal period (e.g., "FY" for full year, "Q1" for first quarter)
- `start_date` (STRING): Start date of the reporting period
- `end_date` (STRING): End date of the reporting period

### DISCOVERY_INSIGHTS

The `DISCOVERY_INSIGHTS` table consists of the following columns:

- `insight_id` (STRING, primary key): Unique identifier for the discovery analysis (e.g., "discovery_0000320193")
- `cik` (STRING): CIK of the company analyzed
- `company_name` (STRING): Name of the company analyzed
- `credit_risk_score` (INTEGER): AI-assigned credit risk score (1-10, where 10 is highest risk)
- `risk_signals` (STRING): JSON array of identified risk signals with severity ratings
- `key_ratios` (STRING): JSON object with calculated financial ratios (debt-to-equity, current ratio)
- `recommended_companies` (STRING): JSON array of companies the AI recommended for investigation, with CIK numbers and reasoning
- `analysis_summary` (STRING): AI-generated narrative summary of the credit risk analysis
- `source` (STRING): Analysis source label (e.g., "seed_analysis")

### RISK_ANALYSIS

The `RISK_ANALYSIS` table consists of the following columns:

- `analysis_id` (STRING, primary key): Unique identifier for the synthesis analysis
- `companies_analyzed` (INTEGER): Number of companies included in the synthesis
- `company_list` (STRING): JSON array of all companies analyzed with CIK and name
- `portfolio_risk_score` (INTEGER): Portfolio-level risk score (1-10)
- `systemic_risks` (STRING): JSON array of systemic risk patterns identified across companies with severity ratings
- `counterparty_risks` (STRING): JSON array of counterparty exposure relationships between companies
- `portfolio_grade` (STRING): Letter grade for portfolio risk (e.g., "A-", "B+", "C")
- `executive_summary` (STRING): AI-generated executive summary of cross-company risk assessment

## Genie Space

When `enable_genie_space` is set to `true`, the connector creates a Databricks Genie Space after data lands. The Genie Space is configured with financial risk-specific instructions and sample questions including "Which companies have the highest credit risk scores?" and "Show me companies with debt-to-equity ratios above 2.0."

The Genie Space is created only once. The `space_id` is persisted in the connector state to avoid creating duplicates on subsequent syncs.

## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

The SEC EDGAR APIs are free and do not require authentication. Rate limits apply (10 requests per second). The connector includes rate limiting delays between requests to stay within these limits. A `User-Agent` header with contact information is required per SEC fair access policies.

Databricks `ai_query()` consumes SQL Warehouse compute credits. The discovery pattern makes multiple `ai_query()` calls per sync (one per seed company for discovery analysis, plus one for cross-company synthesis). Use `max_enrichments` to control costs during development. Set `enable_enrichment` to `false` to test the data pipeline without AI costs, or set `enable_discovery` to `false` to run AI analysis on seed companies only without discovering related companies.
