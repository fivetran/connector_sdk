"""
Databricks SEC EDGAR Risk Intelligence Connector - Agent-Driven Discovery

Syncs SEC EDGAR financial filing data (10-K/10-Q filings and XBRL financial facts)
and enriches it with AI-powered credit risk analysis using Databricks ai_query()
SQL function. The connector uses an Agent-Driven Discovery pattern where the AI
analyzes seed company financials and autonomously recommends related companies
to investigate for systemic risk exposure.

This connector demonstrates the second level of the Databricks AI connector
progression: Agent-Driven Discovery. Unlike the simple enrichment pattern
(FDA Drug Labels), the AI here decides what additional data to fetch, making
the data pipeline adaptive rather than static.

Three-phase architecture:
  - Phase 1 (SEED): Fetch company info and XBRL financial facts for seed companies
  - Phase 2 (DISCOVERY): AI analyzes financials, identifies risk signals, and
    recommends related companies to investigate. Connector fetches those companies.
  - Phase 3 (SYNTHESIS): AI synthesizes patterns across all companies (seed +
    discovered) to identify systemic exposure and cross-company risk.

Optional Genie Space creation after data lands for natural language analytics.

See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For generating unique IDs for Genie Space config elements
import uuid

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# SEC EDGAR API Configuration Constants
__BASE_URL_SUBMISSIONS = "https://data.sec.gov/submissions"
__BASE_URL_FACTS = "https://data.sec.gov/api/xbrl/companyfacts"
__API_TIMEOUT_SECONDS = 30
__SEC_USER_AGENT = "Fivetran-SEC-EDGAR-Databricks-Connector/1.0 (developers@fivetran.com)"

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__SEC_RATE_LIMIT_DELAY = 0.15

# Default Configuration Values
__DEFAULT_MAX_DISCOVERY_COMPANIES = 3
__DEFAULT_MAX_ENRICHMENTS = 10
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120

# Databricks SQL Statement API Configuration
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"

# Genie Space API Configuration
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Sanity ceilings for user-configurable limits
__MAX_SEED_COMPANIES_CEILING = 20
__MAX_DISCOVERY_COMPANIES_CEILING = 10
__MAX_ENRICHMENTS_CEILING = 50

# Key XBRL financial metrics to extract
__KEY_FINANCIAL_METRICS = [
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "Revenues",
    "NetIncomeLoss",
    "CashAndCashEquivalentsAtCarryingValue",
    "LongTermDebt",
    "OperatingIncomeLoss",
    "EarningsPerShareBasic",
    "CommonStockSharesOutstanding",
]

# Genie Space configuration for financial risk analytics
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a financial risk intelligence agent. This dataset contains "
    "SEC EDGAR filing data enriched with AI-powered credit risk analysis. "
    "Each company has financial facts (assets, liabilities, revenue, net "
    "income, debt) from their 10-K and 10-Q filings, plus AI-generated "
    "risk assessments including credit risk scores, risk signals, and "
    "cross-company exposure analysis. Use the financial_facts table for "
    "raw financial data and the discovery_insights and risk_analysis "
    "tables for AI-generated risk intelligence. When answering questions "
    "about risk, reference specific financial ratios like debt-to-equity "
    "and current ratio."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which companies have the highest credit risk scores?",
    "Show me companies with debt-to-equity ratios above 2.0",
    "What systemic risk patterns were identified across companies?",
    "Compare revenue trends for all seed companies",
    "Which discovered companies pose the greatest counterparty risk?",
]


def flatten_dict(d, parent_key="", sep="_"):
    """
    Flatten nested dictionaries and serialize lists to JSON strings.
    REQUIRED for Fivetran compatibility.

    Args:
        d: Dictionary to flatten
        parent_key: Prefix for nested keys (used in recursion)
        sep: Separator between nested key levels

    Returns:
        Flattened dictionary with all nested structures resolved
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, (list, tuple)):
            items.append((new_key, json.dumps(v) if v else None))
        else:
            items.append((new_key, v))
    return dict(items)


def _is_placeholder(value):
    """
    Check if a configuration value is unset or an angle-bracket
    placeholder.

    Type-safe: returns False for non-strings (bool/int/float) so this
    helper can be called on any config value without risking
    AttributeError.
    """
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if not value:
        return True
    return value.startswith("<") and value.endswith(">")


def _parse_bool(value, default=False):
    """
    Parse a boolean-like config value. Accepts bool directly,
    "true"/"false" strings (case-insensitive), and None/placeholders
    (returns default).

    Args:
        value: Configuration value to parse
        default: Default if value is None or placeholder

    Returns:
        Boolean interpretation of the value
    """
    if isinstance(value, bool):
        return value
    if value is None or _is_placeholder(value):
        return default
    return str(value).strip().lower() == "true"


def _optional_int(configuration, key, default):
    """
    Read an optional int config value, treating placeholders/None as
    unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key to read
        default: Default value if key is missing or placeholder

    Returns:
        Integer value or default
    """
    value = configuration.get(key)
    if _is_placeholder(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _optional_str(configuration, key, default=None):
    """
    Read an optional string config value, treating placeholders/None
    as unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key to read
        default: Default value if key is missing or placeholder

    Returns:
        String value or default
    """
    value = configuration.get(key)
    if _is_placeholder(value):
        return default
    return value


def pad_cik(cik):
    """
    Zero-pad a CIK number to 10 digits as required by SEC EDGAR APIs.

    Args:
        cik: CIK number as string or integer

    Returns:
        Zero-padded 10-digit CIK string
    """
    return str(cik).strip().zfill(10)


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required
    parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration
            settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is
            missing or invalid.
    """
    # seed_companies is always required and must be a comma-separated list
    # of one-or-more numeric CIKs (10-digit zero-padded or any positive int).
    seed_value = configuration.get("seed_companies")
    if _is_placeholder(seed_value):
        raise ValueError("seed_companies is required (comma-separated CIK numbers)")
    seed_parts = [s.strip() for s in str(seed_value).split(",") if s.strip()]
    if not seed_parts:
        raise ValueError("seed_companies must contain at least one CIK after parsing")
    for part in seed_parts:
        if not part.isdigit():
            raise ValueError(f"seed_companies entries must be numeric CIKs, got: {part!r}")
    if len(seed_parts) > __MAX_SEED_COMPANIES_CEILING:
        raise ValueError(
            f"seed_companies has {len(seed_parts)} entries, exceeds ceiling "
            f"of {__MAX_SEED_COMPANIES_CEILING}."
        )

    # Validate numeric parameters
    numeric_params = {
        "max_enrichments": "max_enrichments must be a positive integer",
        "max_discovery_companies": ("max_discovery_companies must be a positive integer"),
    }

    for param, error_msg in numeric_params.items():
        value = configuration.get(param)
        if value is not None and not _is_placeholder(value):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                raise ValueError(error_msg)
            if parsed < 1:
                raise ValueError(error_msg)

    # Enforce sanity ceilings
    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    if max_enrichments > __MAX_ENRICHMENTS_CEILING:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds ceiling "
            f"of {__MAX_ENRICHMENTS_CEILING}."
        )

    max_discovery = _optional_int(
        configuration,
        "max_discovery_companies",
        __DEFAULT_MAX_DISCOVERY_COMPANIES,
    )
    if max_discovery > __MAX_DISCOVERY_COMPANIES_CEILING:
        raise ValueError(
            f"max_discovery_companies={max_discovery} exceeds "
            f"ceiling of {__MAX_DISCOVERY_COMPANIES_CEILING}."
        )

    # Validate Databricks credentials when enrichment or Genie enabled
    is_enrichment_enabled = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_discovery_enabled = _parse_bool(configuration.get("enable_discovery"), default=True)
    is_genie_enabled = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment_enabled or is_discovery_enabled or is_genie_enabled:
        for key in [
            "databricks_workspace_url",
            "databricks_token",
            "databricks_warehouse_id",
        ]:
            if _is_placeholder(configuration.get(key)):
                raise ValueError(f"Missing required Databricks config: {key}")

        workspace_url = configuration.get("databricks_workspace_url", "")
        if not workspace_url.startswith("https://"):
            raise ValueError(
                "databricks_workspace_url must start with " "'https://'. Got: " + workspace_url
            )

    if is_genie_enabled:
        if _is_placeholder(configuration.get("genie_table_identifier")):
            raise ValueError("genie_table_identifier is required for Genie Space")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema
    your connector delivers.
    See the technical reference documentation for more details on the
    schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration
            settings for the connector.
    """
    return [
        {
            "table": "company_filings",
            "primary_key": ["cik"],
        },
        {
            "table": "financial_facts",
            "primary_key": ["fact_id"],
        },
        {
            "table": "discovery_insights",
            "primary_key": ["insight_id"],
        },
        {
            "table": "risk_analysis",
            "primary_key": ["analysis_id"],
        },
    ]


def create_session():
    """
    Create a requests session for SEC EDGAR API calls.

    The SEC EDGAR API requires a User-Agent header with contact
    information. No authentication is needed.

    Returns:
        requests.Session configured for SEC EDGAR API requests
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": __SEC_USER_AGENT,
            "Accept": "application/json",
        }
    )
    return session


def fetch_data_with_retry(session, url, params=None):
    """
    Fetch data from API with exponential backoff retry logic.

    Args:
        session: requests.Session object for connection pooling
        url: Full URL to fetch
        params: Optional query parameters

    Returns:
        JSON response as dictionary

    Raises:
        RuntimeError: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=__API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                log.severe(f"Connection failed after {__MAX_RETRIES} " f"attempts: {url}")
                raise RuntimeError(
                    f"Connection failed after {__MAX_RETRIES} " f"attempts: {e}"
                ) from e

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                log.severe(f"Timeout after {__MAX_RETRIES} " f"attempts: {url}")
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} " f"attempts: {e}") from e

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )

            if status_code in (401, 403):
                msg = f"HTTP {status_code}: Check credentials. " f"URL: {url}"
                log.severe(msg)
                raise RuntimeError(msg) from e

            should_retry = status_code in __RETRYABLE_STATUS_CODES

            if should_retry and attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Request failed with status "
                    f"{status_code}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay)
            else:
                attempts = attempt + 1
                log.severe(
                    f"Request failed after {attempts} "
                    f"attempt(s). URL: {url}, "
                    f"Status: {status_code or 'N/A'}, "
                    f"Error: {str(e)}"
                )
                raise RuntimeError(
                    f"API request failed after {attempts} " f"attempt(s): {e}"
                ) from e


def fetch_company_info(session, cik):
    """
    Fetch company submission info from SEC EDGAR.

    Args:
        session: requests.Session object
        cik: Zero-padded 10-digit CIK number

    Returns:
        Company info dictionary with name, tickers, SIC, and
        recent filings metadata

    Raises:
        RuntimeError: If the API request fails
    """
    url = f"{__BASE_URL_SUBMISSIONS}/CIK{cik}.json"
    data = fetch_data_with_retry(session, url)
    time.sleep(__SEC_RATE_LIMIT_DELAY)
    return data


def fetch_company_facts(session, cik):
    """
    Fetch XBRL financial facts for a company from SEC EDGAR.

    Returns all reported financial facts across all filings.
    We extract key metrics (revenue, assets, liabilities, etc.)
    from the us-gaap taxonomy.

    Args:
        session: requests.Session object
        cik: Zero-padded 10-digit CIK number

    Returns:
        Dictionary with us-gaap financial facts

    Raises:
        RuntimeError: If the API request fails
    """
    url = f"{__BASE_URL_FACTS}/CIK{cik}.json"
    data = fetch_data_with_retry(session, url)
    time.sleep(__SEC_RATE_LIMIT_DELAY)
    return data


def extract_latest_facts(facts_data, cik):
    """
    Extract the latest value for key financial metrics from XBRL data.

    For each metric, finds the most recent USD value from 10-K or
    10-Q filings.

    Args:
        facts_data: Raw XBRL companyfacts response
        cik: Company CIK for record identification

    Returns:
        List of financial fact record dictionaries
    """
    us_gaap = facts_data.get("facts", {}).get("us-gaap", {})
    records = []

    for metric in __KEY_FINANCIAL_METRICS:
        if metric not in us_gaap:
            continue

        usd_values = us_gaap[metric].get("units", {}).get("USD", [])
        if not usd_values:
            continue

        # Filter to 10-K and 10-Q filings, get the actual most recent by
        # filed date. SEC API ordering is not guaranteed, so sort explicitly
        # rather than trusting list position.
        filing_values = [v for v in usd_values if v.get("form") in ("10-K", "10-Q")]
        if not filing_values:
            continue

        latest = max(filing_values, key=lambda v: v.get("filed", ""))

        records.append(
            {
                "fact_id": f"{cik}_{metric}",
                "cik": cik,
                "metric": metric,
                "value": latest.get("val"),
                "form": latest.get("form"),
                "filed": latest.get("filed"),
                "fiscal_year": latest.get("fy"),
                "fiscal_period": latest.get("fp"),
                "start_date": latest.get("start"),
                "end_date": latest.get("end"),
            }
        )

    return records


def build_company_record(company_info, cik, source_label):
    """
    Build a normalized company filing record from SEC EDGAR
    submission data.

    Args:
        company_info: Raw SEC EDGAR submissions response
        cik: Zero-padded CIK number
        source_label: "seed" or "discovered"

    Returns:
        Dictionary with normalized company fields
    """
    # Extract latest 10-K and 10-Q filing dates
    recent = company_info.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])

    latest_10k = None
    latest_10q = None
    for i in range(min(len(forms), len(dates))):
        if forms[i] == "10-K" and latest_10k is None:
            latest_10k = dates[i]
        elif forms[i] == "10-Q" and latest_10q is None:
            latest_10q = dates[i]
        if latest_10k and latest_10q:
            break

    tickers = company_info.get("tickers", [])

    return {
        "cik": cik,
        "company_name": company_info.get("name"),
        "ticker": tickers[0] if tickers else None,
        "all_tickers": json.dumps(tickers) if tickers else None,
        "sic": company_info.get("sic"),
        "sic_description": company_info.get("sicDescription"),
        "state": company_info.get("stateOfIncorporation"),
        "fiscal_year_end": company_info.get("fiscalYearEnd"),
        "latest_10k_date": latest_10k,
        "latest_10q_date": latest_10q,
        "total_filings": len(forms),
        "source": source_label,
    }


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() SQL function via SQL Statement API.

    Args:
        session: requests.Session object for connection pooling
        configuration: Configuration dictionary with Databricks settings
        prompt: Prompt text to send to the model

    Returns:
        Response content string, or None on error
    """
    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)
    timeout = _optional_int(
        configuration,
        "databricks_timeout",
        __DEFAULT_DATABRICKS_TIMEOUT,
    )

    url = f"{workspace_url}{__SQL_STATEMENT_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    escaped_prompt = prompt.replace("'", "''")
    statement = f"SELECT ai_query('{model}', '{escaped_prompt}') " f"as response"

    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": __SQL_WAIT_TIMEOUT,
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()

        result = response.json()
        sql_state = result.get("status", {}).get("state", "")

        # Poll for PENDING/RUNNING statements (synthesis prompts
        # can exceed the 50s wait_timeout). Pre-poll guard: when state
        # is PENDING/RUNNING the initial response is structurally allowed
        # to omit statement_id; polling f"{url}/None" silently 404s 12
        # times. Surface the failure mode explicitly. Same fix shape as
        # PR #570 NOAA and PR #567 FDA.
        statement_id = result.get("statement_id")
        if sql_state in ("PENDING", "RUNNING") and not statement_id:
            log.warning(
                f"ai_query() returned state={sql_state} without a statement_id; "
                "cannot poll. Returning None."
            )
            return None

        poll_count = 0
        max_polls = 12
        poll_interval_seconds = 10

        while sql_state in ("PENDING", "RUNNING") and poll_count < max_polls:
            poll_count += 1
            time.sleep(poll_interval_seconds)
            poll_url = f"{url}/{statement_id}"
            poll_resp = session.get(poll_url, headers=headers, timeout=timeout)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            sql_state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/{max_polls}: " f"{sql_state}")

        if sql_state == "SUCCEEDED":
            data_array = result.get("result", {}).get("data_array", [])
            if data_array and data_array[0]:
                return data_array[0][0]
        elif sql_state == "FAILED":
            error = result.get("status", {}).get("error", {})
            log.warning("ai_query() failed: " + error.get("message", "Unknown"))
        else:
            log.warning(f"ai_query() final state: {sql_state}")

        return None

    except requests.exceptions.Timeout:
        log.warning(f"ai_query() timeout after {timeout}s")
        return None
    except requests.exceptions.HTTPError as e:
        body = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.json().get("message", "")[:200]
            except (json.JSONDecodeError, AttributeError):
                body = e.response.text[:200]
        log.warning(f"ai_query() HTTP error: {str(e)} — {body}")
        return None
    except requests.exceptions.ConnectionError as e:
        log.warning(f"ai_query() connection error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"ai_query() API error: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        log.warning(f"ai_query() JSON parse error: {str(e)}")
        return None


def extract_json_from_content(content):
    """
    Extract a JSON object from a string that may contain
    surrounding text.

    Args:
        content: String potentially containing a JSON object

    Returns:
        Parsed dictionary if JSON found, or None
    """
    if not content or "{" not in content:
        return None
    json_start = content.find("{")
    json_end = content.rfind("}") + 1
    try:
        return json.loads(content[json_start:json_end])
    except json.JSONDecodeError:
        return None


def build_discovery_prompt(company_name, cik, facts_summary):
    """
    Build the ai_query() prompt for discovery analysis.

    The agent analyzes a company's financials and recommends
    related companies to investigate for risk exposure.

    Args:
        company_name: Company name
        cik: Company CIK number
        facts_summary: Formatted string of key financial metrics

    Returns:
        Prompt string for ai_query()
    """
    return (
        "You are a credit risk analyst at a major bank. Analyze "
        "this company's financial data from SEC filings and "
        "identify risk signals. Then recommend 2-3 related "
        "companies to investigate for systemic risk exposure.\n\n"
        f"COMPANY: {company_name} (CIK: {cik})\n\n"
        f"KEY FINANCIAL METRICS (from latest 10-K/10-Q):\n"
        f"{facts_summary}\n\n"
        "YOUR TASKS:\n"
        "1. Calculate key ratios: debt-to-equity, current ratio "
        "(if data available)\n"
        "2. Identify the top 3 risk signals from the financials\n"
        "3. Assign a credit risk score (1-10, where 10 is highest "
        "risk)\n"
        "4. Recommend 2-3 related companies to investigate. "
        "Provide their CIK numbers. Consider:\n"
        "   - Key suppliers or customers mentioned in filings\n"
        "   - Competitors in the same SIC code\n"
        "   - Companies with similar risk profiles\n\n"
        "Return ONLY valid JSON (no markdown, no code fences):\n"
        "{\n"
        '  "credit_risk_score": 5,\n'
        '  "risk_signals": [\n'
        '    {"signal": "...", "severity": "HIGH/MEDIUM/LOW"}\n'
        "  ],\n"
        '  "key_ratios": {\n'
        '    "debt_to_equity": 1.5,\n'
        '    "current_ratio": 1.2\n'
        "  },\n"
        '  "recommended_companies": [\n'
        '    {"cik": "0000012345", "name": "...", '
        '"reason": "..."}\n'
        "  ],\n"
        '  "analysis_summary": "..."\n'
        "}"
    )


def build_synthesis_prompt(companies_analyzed, all_facts):
    """
    Build the ai_query() prompt for cross-company risk synthesis.

    Args:
        companies_analyzed: List of (cik, name) tuples
        all_facts: Dict mapping CIK to list of fact records

    Returns:
        Prompt string for ai_query()
    """
    company_list = "\n".join([f"  - {name} (CIK: {cik})" for cik, name in companies_analyzed])

    # Build financial summary for each company
    summaries = []
    for cik, name in companies_analyzed:
        facts = all_facts.get(cik, [])
        if facts:
            lines = []
            for f in facts:
                val = f.get("value")
                if val is not None:
                    lines.append(
                        f"    {f['metric']}: "
                        f"${val:,.0f} ({f.get('form')}, "
                        f"{f.get('filed')})"
                    )
            if lines:
                summaries.append(f"  {name} (CIK: {cik}):\n" + "\n".join(lines))

    financial_overview = "\n\n".join(summaries) if summaries else "  No financial data available"

    return (
        "You are a senior credit risk analyst. You have "
        "investigated multiple companies:\n"
        f"{company_list}\n\n"
        f"FINANCIAL OVERVIEW:\n{financial_overview}\n\n"
        "Analyze ALL companies together:\n"
        "1. Cross-company risk correlations\n"
        "2. Systemic exposure patterns (shared industries, "
        "supply chains, or risk factors)\n"
        "3. Portfolio-level risk assessment\n"
        "4. Which companies pose the greatest counterparty "
        "risk to each other?\n\n"
        "Return ONLY valid JSON (no markdown, no code fences):\n"
        "{\n"
        '  "portfolio_risk_score": 5,\n'
        '  "systemic_risks": [\n'
        '    {"risk": "...", "affected_companies": ["..."], '
        '"severity": "HIGH/MEDIUM/LOW"}\n'
        "  ],\n"
        '  "counterparty_risks": [\n'
        '    {"company_a": "...", "company_b": "...", '
        '"exposure": "..."}\n'
        "  ],\n"
        '  "portfolio_grade": "B+",\n'
        '  "executive_summary": "..."\n'
        "}"
    )


def format_facts_for_prompt(fact_records):
    """
    Format financial fact records into a readable string for prompts.

    Args:
        fact_records: List of financial fact dictionaries

    Returns:
        Formatted string with key metrics
    """
    if not fact_records:
        return "  No financial data available"

    lines = []
    for f in fact_records:
        val = f.get("value")
        if val is not None:
            lines.append(f"  {f['metric']}: ${val:,.0f} " f"({f.get('form')}, {f.get('filed')})")
    return "\n".join(lines) if lines else "  No financial data available"


def fetch_and_upsert_company(session, cik, source_label, state):
    """
    Fetch company info and financial facts, upsert to tables.

    Args:
        session: requests.Session for SEC EDGAR API
        cik: Zero-padded CIK number
        source_label: "seed" or "discovered"
        state: State dictionary for checkpointing

    Returns:
        Tuple of (company_name, fact_records) or (None, []) on failure
    """
    try:
        company_info = fetch_company_info(session, cik)
    except RuntimeError as e:
        log.warning(f"Failed to fetch company info for {cik}: {e}")
        return None, []

    company_name = company_info.get("name", f"CIK-{cik}")
    record = build_company_record(company_info, cik, source_label)
    flattened = flatten_dict(record)

    # The 'upsert' operation is used to insert or update data
    # in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record
    # to be upserted.
    op.upsert(table="company_filings", data=flattened)

    # Fetch XBRL financial facts
    try:
        facts_data = fetch_company_facts(session, cik)
    except RuntimeError as e:
        log.warning(f"Failed to fetch facts for {cik}: {e}")
        return company_name, []

    fact_records = extract_latest_facts(facts_data, cik)

    for fact in fact_records:
        fact_flattened = flatten_dict(fact)
        # The 'upsert' operation is used to insert or update data
        # in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record
        # to be upserted.
        op.upsert(table="financial_facts", data=fact_flattened)

    log.info(f"Fetched {company_name} ({cik}): " f"{len(fact_records)} financial facts")

    return company_name, fact_records


def run_discovery_phase(
    session,
    configuration,
    seed_companies,
    all_facts,
    state,
):
    """
    Run the Agent-Driven Discovery phase.

    For each seed company, the AI analyzes financials and recommends
    related companies. The connector fetches data for discovered
    companies.

    Args:
        session: requests.Session for API calls
        configuration: Configuration dictionary
        seed_companies: List of (cik, name) tuples
        all_facts: Dict mapping CIK to fact records
        state: State dictionary for checkpointing

    Returns:
        List of all companies analyzed (seed + discovered)
    """
    max_enrichments = _optional_int(
        configuration,
        "max_enrichments",
        __DEFAULT_MAX_ENRICHMENTS,
    )
    max_discovery = _optional_int(
        configuration,
        "max_discovery_companies",
        __DEFAULT_MAX_DISCOVERY_COMPANIES,
    )
    enrichment_count = 0
    all_companies = list(seed_companies)
    # Initialize discovered_ciks with the seed CIKs so that LLM-recommended
    # companies that overlap the seed set are not re-fetched.
    discovered_ciks = {cik for cik, _ in seed_companies}

    for cik, name in seed_companies:
        if enrichment_count >= max_enrichments:
            log.info("Enrichment budget exhausted")
            break

        facts = all_facts.get(cik, [])
        facts_summary = format_facts_for_prompt(facts)

        prompt = build_discovery_prompt(name, cik, facts_summary)
        log.info(f"Calling ai_query() for discovery: {name}")

        content = call_ai_query(session, configuration, prompt)
        result = extract_json_from_content(content)
        enrichment_count += 1

        if not result or not isinstance(result, dict):
            log.warning(f"No discovery result for {name}, skipping")
            continue

        # Upsert discovery insight
        insight = {
            "insight_id": f"discovery_{cik}",
            "cik": cik,
            "company_name": name,
            "credit_risk_score": result.get("credit_risk_score"),
            "risk_signals": result.get("risk_signals"),
            "key_ratios": result.get("key_ratios"),
            "recommended_companies": result.get("recommended_companies"),
            "analysis_summary": result.get("analysis_summary"),
            "source": "seed_analysis",
        }
        flattened_insight = flatten_dict(insight)

        # The 'upsert' operation is used to insert or update data
        # in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record
        # to be upserted.
        op.upsert(table="discovery_insights", data=flattened_insight)

        # Save the progress by checkpointing the state. This is
        # important for ensuring that the sync process can resume
        # from the correct position in case of next sync or
        # interruptions.
        # You should checkpoint even if you are not using
        # incremental sync, as it tells Fivetran it is safe to
        # write to destination.
        # For large datasets, checkpoint regularly (e.g., every N
        # records) not only at the end.
        # Learn more about how and where to checkpoint by reading
        # our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # Fetch discovered companies (type-check LLM output)
        recommended = result.get("recommended_companies", [])
        if not isinstance(recommended, list):
            log.warning(
                f"Expected list for recommended_companies, "
                f"got {type(recommended).__name__}. Skipping."
            )
            continue

        def _valid_company(c):
            cik = c.get("cik") if isinstance(c, dict) else None
            return cik and cik not in discovered_ciks

        companies_to_fetch = [c for c in recommended if _valid_company(c)][:max_discovery]

        log.info(
            f"Agent recommended {len(recommended)} companies, "
            f"fetching {len(companies_to_fetch)}"
        )

        for company in companies_to_fetch:
            d_cik = pad_cik(company.get("cik", ""))
            d_name_hint = company.get("name", "Unknown")
            d_reason = company.get("reason", "")

            if not d_cik or d_cik in discovered_ciks:
                continue

            discovered_ciks.add(d_cik)

            log.info(f"Fetching discovered company: " f"{d_name_hint} ({d_cik}) — {d_reason}")

            try:
                d_name, d_facts = fetch_and_upsert_company(session, d_cik, "discovered", state)
                if d_name:
                    all_companies.append((d_cik, d_name))
                    all_facts[d_cik] = d_facts
            except (
                RuntimeError,
                requests.exceptions.RequestException,
            ) as e:
                log.warning(f"Failed to fetch discovered company " f"{d_cik}: {e}. Skipping.")

            # Save the progress by checkpointing the state.
            # This is important for ensuring that the sync
            # process can resume from the correct position in
            # case of next sync or interruptions.
            # You should checkpoint even if you are not using
            # incremental sync, as it tells Fivetran it is
            # safe to write to destination.
            # For large datasets, checkpoint regularly (e.g.,
            # every N records) not only at the end.
            # Learn more about how and where to checkpoint by
            # reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)

    return all_companies


def run_synthesis_phase(session, configuration, companies_analyzed, all_facts, state):
    """
    Run cross-company risk synthesis.

    The AI analyzes all companies together to identify systemic
    risk patterns and counterparty exposure.

    Args:
        session: requests.Session for Databricks API
        configuration: Configuration dictionary
        companies_analyzed: List of (cik, name) tuples
        all_facts: Dict mapping CIK to fact records
        state: State dictionary for checkpointing
    """
    prompt = build_synthesis_prompt(companies_analyzed, all_facts)
    log.info(
        "Calling ai_query() for cross-company synthesis " f"({len(companies_analyzed)} companies)"
    )

    content = call_ai_query(session, configuration, prompt)
    result = extract_json_from_content(content)

    if not result or not isinstance(result, dict):
        log.warning("No synthesis result returned")
        return

    analysis = {
        "analysis_id": "portfolio_synthesis",
        "companies_analyzed": len(companies_analyzed),
        "company_list": json.dumps([{"cik": c[0], "name": c[1]} for c in companies_analyzed]),
        "portfolio_risk_score": result.get("portfolio_risk_score"),
        "systemic_risks": result.get("systemic_risks"),
        "counterparty_risks": result.get("counterparty_risks"),
        "portfolio_grade": result.get("portfolio_grade"),
        "executive_summary": result.get("executive_summary"),
    }
    flattened = flatten_dict(analysis)

    # The 'upsert' operation is used to insert or update data
    # in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record
    # to be upserted.
    op.upsert(table="risk_analysis", data=flattened)

    # Save the progress by checkpointing the state. This is
    # important for ensuring that the sync process can resume
    # from the correct position in case of next sync or
    # interruptions.
    # You should checkpoint even if you are not using
    # incremental sync, as it tells Fivetran it is safe to
    # write to destination.
    # For large datasets, checkpoint regularly (e.g., every N
    # records) not only at the end.
    # Learn more about how and where to checkpoint by reading
    # our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state=state)

    log.info(
        f"Synthesis complete: portfolio grade "
        f"{result.get('portfolio_grade')}, "
        f"{len(companies_analyzed)} companies analyzed"
    )


def create_genie_space(session, configuration, state):
    """
    Create a Databricks Genie Space for financial risk analytics.

    Args:
        session: requests.Session for Databricks API
        configuration: Configuration dictionary
        state: State dictionary for persisting space_id

    Returns:
        Space ID if created, or existing space_id from state
    """
    existing_space_id = state.get("genie_space_id")
    if existing_space_id:
        log.info(f"Genie Space already exists: {existing_space_id}")
        return existing_space_id

    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    table_identifier = configuration.get("genie_table_identifier")
    timeout = _optional_int(
        configuration,
        "databricks_timeout",
        __DEFAULT_DATABRICKS_TIMEOUT,
    )

    url = f"{workspace_url}{__GENIE_SPACE_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    serialized = {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": uuid.uuid4().hex, "question": q} for q in __GENIE_SPACE_SAMPLE_QUESTIONS
            ]
        },
        "data_sources": {"tables": [{"identifier": table_identifier}]},
        "instructions": {
            "text_instructions": [
                {
                    "id": uuid.uuid4().hex,
                    "content": __GENIE_SPACE_INSTRUCTIONS,
                }
            ]
        },
    }

    payload = {
        "warehouse_id": warehouse_id,
        "title": "SEC EDGAR Risk Intelligence",
        "description": (
            "AI-enriched SEC financial filing data with "
            "credit risk scores, risk signals, and "
            "cross-company exposure analysis. Powered by "
            "Fivetran + Databricks."
        ),
        "serialized_space": json.dumps(serialized),
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        space_id = result.get("space_id")
        if space_id:
            log.info(f"Genie Space created: {space_id}")
            return space_id
        else:
            log.warning("Genie Space returned no space_id")
            return None
    except requests.exceptions.HTTPError as e:
        log.warning(f"Genie Space creation error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Genie Space creation error: {str(e)}")
        return None


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is
    called by Fivetran during each sync.
    See the technical reference documentation for more details on the
    update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous
            runs
        The state dictionary is empty for the first sync or for any
            full re-sync
    """
    log.warning("Example: all_things_ai/tutorials : " "databricks-fm-sec-edgar-risk-intelligence")

    validate_configuration(configuration)

    # Parse configuration
    seed_companies_str = configuration.get("seed_companies", "")
    seed_ciks = [pad_cik(c.strip()) for c in seed_companies_str.split(",") if c.strip()][
        :__MAX_SEED_COMPANIES_CEILING
    ]

    is_enrichment_enabled = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_discovery_enabled = _parse_bool(configuration.get("enable_discovery"), default=True)
    is_genie_enabled = _parse_bool(configuration.get("enable_genie_space"), default=False)

    log.info(f"Seed companies: {len(seed_ciks)} CIKs")

    if is_enrichment_enabled:
        model = _optional_str(
            configuration,
            "databricks_model",
            __DEFAULT_DATABRICKS_MODEL,
        )
        log.info(f"Enrichment ENABLED: model={model}")
    else:
        log.info("Enrichment DISABLED")

    if is_discovery_enabled:
        log.info("Agent-Driven Discovery ENABLED")
    else:
        log.info("Agent-Driven Discovery DISABLED")

    session = create_session()

    try:
        # --- Phase 1: SEED --- Fetch company data
        log.info("Phase 1 (SEED): Fetching company data from " "SEC EDGAR")

        seed_companies = []
        all_facts = {}

        for cik in seed_ciks:
            name, facts = fetch_and_upsert_company(session, cik, "seed", state)
            if name:
                seed_companies.append((cik, name))
                all_facts[cik] = facts
            # Per-company checkpoint inside Phase 1 so the seed loop is
            # resumable from any partial-failure boundary, matching the
            # discovery and debate-phase checkpointing cadence.
            op.checkpoint(state=state)

        log.info(f"Phase 1 complete: {len(seed_companies)} " f"companies fetched")

        if not seed_companies:
            log.info("No companies fetched, nothing to sync")
            # Save the progress by checkpointing the state.
            # This is important for ensuring that the sync
            # process can resume from the correct position in
            # case of next sync or interruptions.
            # You should checkpoint even if you are not using
            # incremental sync, as it tells Fivetran it is
            # safe to write to destination.
            # For large datasets, checkpoint regularly (e.g.,
            # every N records) not only at the end.
            # Learn more about how and where to checkpoint by
            # reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            return

        # Save the progress by checkpointing the state. This is
        # important for ensuring that the sync process can resume
        # from the correct position in case of next sync or
        # interruptions.
        # You should checkpoint even if you are not using
        # incremental sync, as it tells Fivetran it is safe to
        # write to destination.
        # For large datasets, checkpoint regularly (e.g., every N
        # records) not only at the end.
        # Learn more about how and where to checkpoint by reading
        # our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # --- Phase 2: DISCOVERY --- Agent-Driven Discovery
        all_companies = list(seed_companies)

        if is_enrichment_enabled and is_discovery_enabled:
            log.info("Phase 2 (DISCOVERY): Starting Agent-Driven " "Discovery")
            all_companies = run_discovery_phase(
                session,
                configuration,
                seed_companies,
                all_facts,
                state,
            )

            # --- Phase 3: SYNTHESIS ---
            if len(all_companies) > 1:
                log.info("Phase 3 (SYNTHESIS): Cross-company risk " "analysis")
                run_synthesis_phase(
                    session,
                    configuration,
                    all_companies,
                    all_facts,
                    state,
                )
        else:
            log.info(
                "Enrichment disabled, skipping discovery and "
                "synthesis. Set enable_enrichment=true to enable."
            )

        # --- AGENT (optional) --- Create Genie Space
        if is_genie_enabled:
            log.info("(AGENT): Creating Genie Space")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
                # Save the progress by checkpointing the state.
                # This is important for ensuring that the sync
                # process can resume from the correct position
                # in case of next sync or interruptions.
                # You should checkpoint even if you are not
                # using incremental sync, as it tells Fivetran
                # it is safe to write to destination.
                # For large datasets, checkpoint regularly
                # (e.g., every N records) not only at the end.
                # Learn more about how and where to checkpoint
                # by reading our best practices documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)

        # Final state update
        state["last_sync_seed_ciks"] = seed_companies_str

        # Save the progress by checkpointing the state. This is
        # important for ensuring that the sync process can resume
        # from the correct position in case of next sync or
        # interruptions.
        # You should checkpoint even if you are not using
        # incremental sync, as it tells Fivetran it is safe to
        # write to destination.
        # For large datasets, checkpoint regularly (e.g., every N
        # records) not only at the end.
        # Learn more about how and where to checkpoint by reading
        # our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info(f"Sync complete: {len(all_companies)} total " f"companies analyzed")

    except Exception as e:
        log.severe(f"Unexpected error during sync: {str(e)}")
        raise

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be
# run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using
# the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick
# debugging during development, such as using IDE debug tools
# (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your
# connector in production.
# Always test using 'fivetran debug' prior to finalizing and
# deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
