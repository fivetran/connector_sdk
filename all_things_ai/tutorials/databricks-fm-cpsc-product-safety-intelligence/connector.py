"""
Databricks CPSC Product Safety Intelligence Connector - Multi-Agent Debate

Syncs consumer product recall data from the CPSC (Consumer Product Safety
Commission) SaferProducts API and enriches each recall with competing AI
assessments from two opposing personas using Databricks ai_query() SQL
function, followed by a consensus synthesizer that produces a final
severity and disagreement flag.

This connector demonstrates the third level of the Databricks AI connector
progression: Multi-Agent Debate. Unlike simple enrichment (FDA Drug Labels)
or agent-driven discovery (SEC EDGAR), this pattern produces richer and more
balanced analysis by having two AI experts with opposing perspectives debate
the same product safety incident. The disagreement_flag column identifies
recalls where the experts significantly disagree, flagging them for human
quality review.

Two-phase architecture:
  - Phase 1 (MOVE): Fetch product recall data from the CPSC API
  - Phase 2 (DEBATE): For each recall, three ai_query() calls:
    1. Product Safety Analyst (risk-maximizing perspective)
    2. Manufacturing Quality Engineer (context-aware skeptic)
    3. Consensus Agent (synthesizes both, produces disagreement_flag)

Optional Genie Space creation after data lands for natural language
analytics on the enriched product safety data.

See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For date calculations in incremental sync
from datetime import datetime, timedelta

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

# CPSC API Configuration Constants
__BASE_URL_CPSC = "https://www.saferproducts.gov/RestWebServices/Recall"
__API_TIMEOUT_SECONDS = 30

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__CPSC_RATE_LIMIT_DELAY = 0.5

# Default Configuration Values
__DEFAULT_MAX_RECALLS = 10
__DEFAULT_MAX_ENRICHMENTS = 5
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120
__DEFAULT_LOOKBACK_DAYS = 90

# Databricks SQL Statement API Configuration
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"
__SQL_POLL_INTERVAL_SECONDS = 10
__MAX_POLL_ATTEMPTS = 12

# Genie Space API Configuration
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Sanity ceilings
__MAX_RECALLS_CEILING = 200
__MAX_ENRICHMENTS_CEILING = 50

# Genie Space configuration
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a product safety intelligence agent. This dataset contains "
    "CPSC consumer product recall data enriched with AI-powered multi-agent "
    "debate analysis. Each recall has been analyzed by two competing AI "
    "personas: a Product Safety Analyst (risk-maximizing) and a Manufacturing "
    "Quality Engineer (context-aware skeptic), followed by a consensus "
    "synthesis. The disagreement_flag column identifies recalls where the "
    "experts significantly disagreed, flagging them for human review. Use "
    "the product_recalls table for recall metadata and the debate_consensus "
    "table for AI analysis results."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which recalls have disagreement flags where the experts disagreed?",
    "Show me all recalls with CRITICAL final severity",
    "What product categories have the most recalls this quarter?",
    "List recalls where the debate winner was the safety analyst",
    "Which manufacturers have the most recalls with high severity?",
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
    placeholder. Type-safe for non-strings.
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
    Parse a boolean-like config value. Handles bool, string, None,
    and placeholders.

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
    Read an optional int config value, treating placeholders as unset.

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
    Read an optional string config value, treating placeholders as
    unset.

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
    # Validate numeric parameters
    numeric_params = {
        "max_recalls": "max_recalls must be a positive integer",
        "max_enrichments": ("max_enrichments must be a positive integer"),
        "lookback_days": "lookback_days must be a positive integer",
        "databricks_timeout": "databricks_timeout must be a positive integer",
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

    # Enforce ceilings
    max_recalls = _optional_int(configuration, "max_recalls", __DEFAULT_MAX_RECALLS)
    if max_recalls > __MAX_RECALLS_CEILING:
        raise ValueError(
            f"max_recalls={max_recalls} exceeds ceiling " f"of {__MAX_RECALLS_CEILING}."
        )

    max_enrichments = _optional_int(
        configuration,
        "max_enrichments",
        __DEFAULT_MAX_ENRICHMENTS,
    )
    if max_enrichments > __MAX_ENRICHMENTS_CEILING:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds "
            f"ceiling of {__MAX_ENRICHMENTS_CEILING}."
        )

    # Validate Databricks credentials when enrichment or Genie enabled
    is_enrichment_enabled = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie_enabled = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment_enabled or is_genie_enabled:
        for key in [
            "databricks_workspace_url",
            "databricks_token",
            "databricks_warehouse_id",
        ]:
            if _is_placeholder(configuration.get(key)):
                raise ValueError(f"Missing required Databricks config: " f"{key}")

        workspace_url = configuration.get("databricks_workspace_url", "")
        if not workspace_url.startswith("https://"):
            raise ValueError(
                "databricks_workspace_url must start with " f"'https://'. Got: {workspace_url}"
            )

    if is_genie_enabled:
        if _is_placeholder(configuration.get("genie_table_identifier")):
            raise ValueError("genie_table_identifier is required for " "Genie Space")

    recall_date_start = configuration.get("recall_date_start")
    if recall_date_start and not _is_placeholder(recall_date_start):
        try:
            datetime.strptime(recall_date_start, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"recall_date_start must be in YYYY-MM-DD format, got: {recall_date_start}"
            )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema
    your connector delivers.
    See the technical reference documentation for more details on
    the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration
            settings for the connector.
    """
    return [
        {"table": "product_recalls", "primary_key": ["recall_id"]},
        {
            "table": "safety_assessments",
            "primary_key": ["recall_id"],
        },
        {
            "table": "quality_assessments",
            "primary_key": ["recall_id"],
        },
        {
            "table": "debate_consensus",
            "primary_key": ["recall_id"],
        },
    ]


def create_session():
    """
    Create a requests session for CPSC API calls.

    The CPSC API requires a browser-like User-Agent header.

    Returns:
        requests.Session configured for CPSC API requests
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": ("Mozilla/5.0 (Fivetran-CPSC-Databricks-" "Connector/1.0)"),
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
        JSON response (list or dictionary)

    Raises:
        RuntimeError: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(
                url,
                params=params,
                timeout=__API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                log.severe(f"Connection failed after " f"{__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(
                    f"Connection failed after " f"{__MAX_RETRIES} attempts: {e}"
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
                msg = f"HTTP {status_code}: Access denied. " f"URL: {url}"
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


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() SQL function via SQL Statement API.

    Includes async polling for PENDING/RUNNING statements that
    exceed the SQL wait timeout.

    Args:
        session: requests.Session for connection pooling
        configuration: Configuration dictionary
        prompt: Prompt text to send to the model

    Returns:
        Response content string, or None on error
    """
    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    model = _optional_str(
        configuration,
        "databricks_model",
        __DEFAULT_DATABRICKS_MODEL,
    )
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
        response = session.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()

        result = response.json()
        sql_state = result.get("status", {}).get("state", "")

        # Poll for PENDING/RUNNING statements. Pre-poll guard: when state is
        # PENDING/RUNNING the initial response is structurally allowed to omit
        # statement_id; polling f"{url}/None" silently 404s. Surface explicitly.
        # Same fix shape as PR #570 NOAA / PR #567 FDA / PR #568 SEC EDGAR.
        statement_id = result.get("statement_id")
        if sql_state in ("PENDING", "RUNNING") and not statement_id:
            log.warning(
                f"ai_query() returned state={sql_state} without a statement_id; "
                "cannot poll. Returning None."
            )
            return None

        poll_count = 0

        while sql_state in ("PENDING", "RUNNING") and poll_count < __MAX_POLL_ATTEMPTS:
            poll_count += 1
            time.sleep(__SQL_POLL_INTERVAL_SECONDS)
            poll_url = f"{url}/{statement_id}"
            poll_resp = session.get(poll_url, headers=headers, timeout=timeout)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            sql_state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/{__MAX_POLL_ATTEMPTS}: {sql_state}")

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


def fetch_recalls(session, start_date, end_date):
    """
    Fetch product recalls from the CPSC SaferProducts API.

    Args:
        session: requests.Session object
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        List of recall record dictionaries
    """
    params = {
        "format": "json",
        "RecallDateStart": start_date,
        "RecallDateEnd": end_date,
    }

    data = fetch_data_with_retry(session, __BASE_URL_CPSC, params=params)

    if not isinstance(data, list):
        log.warning(f"Expected list from CPSC API, got " f"{type(data).__name__}")
        return []

    time.sleep(__CPSC_RATE_LIMIT_DELAY)
    return data


def build_recall_record(recall):
    """
    Build a normalized recall record from raw CPSC API data.

    Args:
        recall: Raw CPSC recall dictionary

    Returns:
        Dictionary with normalized recall fields
    """
    # Extract first product, hazard, injury, manufacturer
    products = recall.get("Products", [])
    hazards = recall.get("Hazards", [])
    injuries = recall.get("Injuries", [])
    manufacturers = recall.get("Manufacturers", [])
    retailers = recall.get("Retailers", [])
    remedies = recall.get("Remedies", [])

    first_product = products[0] if products else {}
    first_hazard = hazards[0] if hazards else {}
    first_injury = injuries[0] if injuries else {}
    first_manufacturer = manufacturers[0] if manufacturers else {}
    first_retailer = retailers[0] if retailers else {}
    first_remedy = remedies[0] if remedies else {}

    return {
        "recall_id": recall.get("RecallID"),
        "recall_number": recall.get("RecallNumber"),
        "recall_date": recall.get("RecallDate"),
        "title": recall.get("Title"),
        "description": recall.get("Description"),
        "url": recall.get("URL"),
        "consumer_contact": recall.get("ConsumerContact"),
        "last_publish_date": recall.get("LastPublishDate"),
        "product_name": first_product.get("Name"),
        "product_type": first_product.get("Type"),
        "number_of_units": first_product.get("NumberOfUnits"),
        "hazard_description": first_hazard.get("Name"),
        "hazard_type": first_hazard.get("HazardType"),
        "injury_description": first_injury.get("Name"),
        "manufacturer_name": first_manufacturer.get("Name"),
        "retailer_name": first_retailer.get("Name"),
        "remedy_description": first_remedy.get("Name"),
        "all_products": json.dumps(products) if products else None,
        "all_hazards": json.dumps(hazards) if hazards else None,
        "all_injuries": json.dumps(injuries) if injuries else None,
        "all_manufacturers": (json.dumps(manufacturers) if manufacturers else None),
        "all_retailers": (json.dumps(retailers) if retailers else None),
        "all_remedies": (json.dumps(remedies) if remedies else None),
    }


def build_safety_prompt(recall_record):
    """
    Build the Product Safety Analyst prompt (risk-maximizing).

    Args:
        recall_record: Normalized recall record dictionary

    Returns:
        Formatted prompt string
    """
    return (
        "You are a senior Product Safety Analyst at the CPSC. Your job is "
        "to identify the MAXIMUM realistic consumer risk from this product "
        "recall. Assume worst-case consumer exposure: products still in "
        "homes, continued use by unaware consumers, children present.\n\n"
        f"RECALL: {recall_record.get('title', 'N/A')}\n"
        f"Product: {recall_record.get('product_name', 'N/A')}\n"
        f"Units: {recall_record.get('number_of_units', 'N/A')}\n"
        f"Description: {recall_record.get('description', 'N/A')[:800]}\n"
        f"Hazard: {recall_record.get('hazard_description', 'N/A')[:400]}\n"
        f"Injuries: {recall_record.get('injury_description', 'N/A')[:400]}\n"
        f"Manufacturer: {recall_record.get('manufacturer_name', 'N/A')}\n"
        f"Remedy: {recall_record.get('remedy_description', 'N/A')[:400]}\n\n"
        "Analyze from a risk-maximizing perspective:\n"
        "1. What is the worst-case consumer harm scenario?\n"
        "2. Is this likely a systemic design defect or isolated batch issue?\n"
        "3. How urgently should consumers stop using this product?\n"
        "4. Are children or vulnerable populations at elevated risk?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "safety_risk_score": <1-10>,\n'
        '  "worst_case_scenario": "...",\n'
        '  "defect_classification": "SYSTEMIC_DESIGN|MANUFACTURING_BATCH|'
        'MATERIAL_DEFECT|LABELING|UNKNOWN",\n'
        '  "consumer_urgency": "STOP_USE_IMMEDIATELY|STOP_USE_SOON|'
        'USE_WITH_CAUTION|MONITOR",\n'
        '  "vulnerable_population_risk": true/false,\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_quality_prompt(recall_record):
    """
    Build the Manufacturing Quality Engineer prompt
    (context-aware skeptic).

    Args:
        recall_record: Normalized recall record dictionary

    Returns:
        Formatted prompt string
    """
    return (
        "You are a Manufacturing Quality Engineer reviewing this product "
        "recall. Your job is to assess the REALISTIC scope and root cause "
        "of the defect. Consider: Is this a systemic design flaw or an "
        "isolated manufacturing batch issue? Can the root cause be "
        "contained? Are corrective actions adequate?\n\n"
        f"RECALL: {recall_record.get('title', 'N/A')}\n"
        f"Product: {recall_record.get('product_name', 'N/A')}\n"
        f"Units: {recall_record.get('number_of_units', 'N/A')}\n"
        f"Description: {recall_record.get('description', 'N/A')[:800]}\n"
        f"Hazard: {recall_record.get('hazard_description', 'N/A')[:400]}\n"
        f"Injuries: {recall_record.get('injury_description', 'N/A')[:400]}\n"
        f"Manufacturer: {recall_record.get('manufacturer_name', 'N/A')}\n"
        f"Remedy: {recall_record.get('remedy_description', 'N/A')[:400]}\n\n"
        "Analyze from a manufacturing quality perspective:\n"
        "1. Is the root cause likely batch-specific or design-level?\n"
        "2. Is the manufacturer's remedy adequate for the defect scope?\n"
        "3. What quality controls could have prevented this?\n"
        "4. Is this recall proportionate to the actual risk, or overly "
        "broad?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "quality_risk_score": <1-10>,\n'
        '  "root_cause_assessment": "DESIGN_FLAW|BATCH_DEFECT|'
        'MATERIAL_FAILURE|SUPPLIER_ISSUE|LABELING_ERROR|UNKNOWN",\n'
        '  "containment_feasibility": "FULLY_CONTAINED|PARTIALLY_CONTAINED|'
        'UNCONTAINED",\n'
        '  "remedy_adequacy": "ADEQUATE|PARTIALLY_ADEQUATE|INADEQUATE",\n'
        '  "recall_proportionality": "PROPORTIONATE|OVER_BROAD|'
        'UNDER_SCOPED",\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_consensus_prompt(recall_record, safety_result, quality_result):
    """
    Build the Consensus synthesizer prompt that reads both analyst
    assessments.

    Args:
        recall_record: Normalized recall record dictionary
        safety_result: Product Safety Analyst JSON result
        quality_result: Quality Engineer JSON result

    Returns:
        Formatted prompt string
    """
    return (
        "You are a neutral product safety director synthesizing two "
        "expert assessments of the same product recall. One expert "
        "(Safety Analyst) maximizes consumer risk; the other (Quality "
        "Engineer) applies manufacturing context. Produce a balanced "
        "final assessment.\n\n"
        f"RECALL: {recall_record.get('title', 'N/A')}\n"
        f"Product: {recall_record.get('product_name', 'N/A')}\n\n"
        "SAFETY ANALYST ASSESSMENT:\n"
        f"{json.dumps(safety_result, indent=2)}\n\n"
        "QUALITY ENGINEER ASSESSMENT:\n"
        f"{json.dumps(quality_result, indent=2)}\n\n"
        "Synthesize:\n"
        "1. Where do the experts AGREE? Where do they DISAGREE?\n"
        "2. Which expert is MORE PERSUASIVE overall and why?\n"
        "3. What is the balanced final severity?\n"
        "4. Does this recall need human review due to significant "
        "expert disagreement?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "final_severity": "CRITICAL|HIGH|MEDIUM|LOW",\n'
        '  "consensus_risk_score": <1-10>,\n'
        '  "debate_winner": "SAFETY|QUALITY|DRAW",\n'
        '  "winner_rationale": "...",\n'
        '  "agreement_areas": ["..."],\n'
        '  "disagreement_areas": ["..."],\n'
        '  "disagreement_flag": true/false,\n'
        '  "disagreement_severity": "NONE|MINOR|SIGNIFICANT|'
        'FUNDAMENTAL",\n'
        '  "human_review_recommended": true/false,\n'
        '  "recommended_action": "...",\n'
        '  "executive_summary": "..."\n'
        "}"
    )


def upsert_assessment(table_name, recall_id, assessment, assessment_type):
    """
    Upsert an AI assessment record to the specified table.

    Args:
        table_name: Destination table name
        recall_id: Recall identifier
        assessment: Parsed JSON assessment from ai_query()
        assessment_type: Type label (safety, quality, consensus)

    Returns:
        bool: True if upserted, False if assessment was None
    """
    if assessment is None:
        log.warning(
            f"Skipping {assessment_type} assessment for " f"recall {recall_id}: no response"
        )
        return False

    record = {
        "recall_id": recall_id,
        "assessment_type": assessment_type,
    }
    record.update(flatten_dict(assessment))

    # The 'upsert' operation is used to insert or update data
    # in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record
    # to be upserted.
    op.upsert(table=table_name, data=record)
    return True


def run_multi_agent_debate(session, configuration, recalls, recall_records, state):
    """
    Run the Multi-Agent Debate phase: three ai_query() calls per
    recall (safety analyst, quality engineer, consensus).

    Args:
        session: requests.Session for Databricks API
        configuration: Configuration dictionary
        recalls: List of raw recall dictionaries (for IDs)
        recall_records: Dict mapping recall_id to flat records
        state: State dictionary for checkpointing

    Returns:
        Tuple of (debate_count, disagreement_count)
    """
    max_enrichments = _optional_int(
        configuration,
        "max_enrichments",
        __DEFAULT_MAX_ENRICHMENTS,
    )
    enrichment_count = 0
    disagreement_count = 0

    log.info(
        f"Starting Multi-Agent Debate for up to "
        f"{max_enrichments} recalls "
        f"(3 ai_query() calls per recall)"
    )

    for recall in recalls:
        if enrichment_count >= max_enrichments:
            log.info(f"Reached max_enrichments limit " f"({max_enrichments}), stopping debate")
            break

        recall_id = recall.get("RecallID")
        recall_record = recall_records.get(recall_id)
        if not recall_record:
            continue

        # Agent 1: Product Safety Analyst
        safety_prompt = build_safety_prompt(recall_record)
        safety_content = call_ai_query(session, configuration, safety_prompt)
        safety_result = extract_json_from_content(safety_content)
        upsert_assessment(
            "safety_assessments",
            recall_id,
            safety_result,
            "safety",
        )

        # Agent 2: Manufacturing Quality Engineer
        quality_prompt = build_quality_prompt(recall_record)
        quality_content = call_ai_query(session, configuration, quality_prompt)
        quality_result = extract_json_from_content(quality_content)
        upsert_assessment(
            "quality_assessments",
            recall_id,
            quality_result,
            "quality",
        )

        # Agent 3: Consensus (only if both returned results)
        if safety_result and quality_result:
            consensus_prompt = build_consensus_prompt(recall_record, safety_result, quality_result)
            consensus_content = call_ai_query(session, configuration, consensus_prompt)
            consensus_result = extract_json_from_content(consensus_content)
            upsert_assessment(
                "debate_consensus",
                recall_id,
                consensus_result,
                "consensus",
            )

            if consensus_result and consensus_result.get("disagreement_flag"):
                disagreement_count += 1
        else:
            log.warning(
                f"Skipping consensus for recall "
                f"{recall_id}: missing safety or quality "
                f"assessment"
            )

        enrichment_count += 1

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

    return enrichment_count, disagreement_count


def create_genie_space(session, configuration, state):
    """
    Create a Databricks Genie Space for product safety analytics.

    Args:
        session: requests.Session for Databricks API
        configuration: Configuration dictionary
        state: State dictionary for persisting space_id

    Returns:
        Space ID if created, or existing space_id from state
    """
    existing_space_id = state.get("genie_space_id")
    if existing_space_id:
        log.info(f"Genie Space already exists: " f"{existing_space_id}")
        return existing_space_id

    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    table_identifier = configuration.get("genie_table_identifier")

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
        "title": "CPSC Product Safety Intelligence",
        "description": (
            "AI-enriched CPSC product recall data with "
            "multi-agent debate analysis. Powered by "
            "Fivetran + Databricks."
        ),
        "serialized_space": json.dumps(serialized),
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        space_id = result.get("space_id")
        if space_id:
            log.info(f"Genie Space created: {space_id}")
            return space_id
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
    Define the update function, which is a required function,
    and is called by Fivetran during each sync.
    See the technical reference documentation for more details
    on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from
            previous runs
        The state dictionary is empty for the first sync or for
            any full re-sync
    """
    log.warning(
        "Example: all_things_ai/tutorials : " "databricks-fm-cpsc-product-safety-intelligence"
    )

    validate_configuration(configuration)

    # Read configuration
    max_recalls = _optional_int(configuration, "max_recalls", __DEFAULT_MAX_RECALLS)
    is_enrichment_enabled = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie_enabled = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment_enabled:
        model = _optional_str(
            configuration,
            "databricks_model",
            __DEFAULT_DATABRICKS_MODEL,
        )
        max_enrichments = _optional_int(
            configuration,
            "max_enrichments",
            __DEFAULT_MAX_ENRICHMENTS,
        )
        log.info(
            f"Multi-Agent Debate ENABLED: model={model}, " f"max_enrichments={max_enrichments}"
        )
    else:
        log.info("Multi-Agent Debate DISABLED")

    # Build date range for fetch
    last_recall_date = state.get("last_recall_date")
    lookback_days = _optional_int(
        configuration,
        "lookback_days",
        __DEFAULT_LOOKBACK_DAYS,
    )

    if last_recall_date:
        start_date = last_recall_date
    else:
        start_dt = datetime.now() - timedelta(days=lookback_days)
        start_date = start_dt.strftime("%Y-%m-%d")

    # Allow override via configuration
    config_start = _optional_str(configuration, "recall_date_start")
    if config_start:
        start_date = config_start

    end_date = datetime.now().strftime("%Y-%m-%d")

    log.info(f"Fetching recalls from {start_date} to {end_date}")

    session = create_session()

    try:
        # --- Phase 1: MOVE --- Fetch recalls from CPSC
        log.info("Phase 1 (MOVE): Fetching product recalls " "from CPSC")

        recalls = fetch_recalls(session, start_date, end_date)
        log.info(f"CPSC returned {len(recalls)} recalls")

        if not recalls:
            log.info("No recalls found in date range")
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
            return

        # Limit to max_recalls
        recalls_to_process = recalls[:max_recalls]

        # Upsert recall records and build lookup dict
        recall_records = {}
        latest_recall_date = last_recall_date

        for recall in recalls_to_process:
            recall_id = recall.get("RecallID")
            if not recall_id:
                continue

            record = build_recall_record(recall)
            flattened = flatten_dict(record)

            # The 'upsert' operation is used to insert or
            # update data in the destination table.
            # The first argument is the name of the
            # destination table.
            # The second argument is a dictionary containing
            # the record to be upserted.
            op.upsert(table="product_recalls", data=flattened)

            recall_records[recall_id] = record

            # Track latest date for incremental cursor
            recall_date = recall.get("RecallDate", "")
            if recall_date:
                date_str = recall_date[:10]
                if latest_recall_date is None or date_str > latest_recall_date:
                    latest_recall_date = date_str

        log.info(f"Phase 1 complete: {len(recall_records)} " f"recalls upserted")

        # Update cursor
        if latest_recall_date:
            state["last_recall_date"] = latest_recall_date

        # Save the progress by checkpointing the state.
        # This is important for ensuring that the sync
        # process can resume from the correct position in
        # case of next sync or interruptions.
        # You should checkpoint even if you are not using
        # incremental sync, as it tells Fivetran it is safe
        # to write to destination.
        # For large datasets, checkpoint regularly (e.g.,
        # every N records) not only at the end.
        # Learn more about how and where to checkpoint by
        # reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # --- Phase 2: DEBATE --- Multi-Agent Debate
        if is_enrichment_enabled and recall_records:
            log.info("Phase 2 (DEBATE): Starting Multi-Agent " "Debate")

            debate_count, disagreement_count = run_multi_agent_debate(
                session,
                configuration,
                recalls_to_process,
                recall_records,
                state,
            )

            log.info(
                f"Debate complete: {debate_count} recalls "
                f"debated, {disagreement_count} with "
                f"disagreement flags"
            )
        else:
            if not is_enrichment_enabled:
                log.info(
                    "Enrichment disabled, skipping debate. "
                    "Set enable_enrichment=true to enable."
                )

        # --- Phase 3: AGENT --- Create Genie Space
        if is_genie_enabled:
            log.info("Phase 3 (AGENT): Creating Genie Space")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
                # Save the progress by checkpointing the
                # state. This is important for ensuring that
                # the sync process can resume from the
                # correct position in case of next sync or
                # interruptions.
                # You should checkpoint even if you are not
                # using incremental sync, as it tells
                # Fivetran it is safe to write to
                # destination.
                # For large datasets, checkpoint regularly
                # (e.g., every N records) not only at the
                # end.
                # Learn more about how and where to
                # checkpoint by reading our best practices
                # documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)

        # Final checkpoint
        # Save the progress by checkpointing the state. This
        # is important for ensuring that the sync process can
        # resume from the correct position in case of next
        # sync or interruptions.
        # You should checkpoint even if you are not using
        # incremental sync, as it tells Fivetran it is safe
        # to write to destination.
        # For large datasets, checkpoint regularly (e.g.,
        # every N records) not only at the end.
        # Learn more about how and where to checkpoint by
        # reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info(f"Sync complete: {len(recall_records)} recalls " f"synced")

    except Exception as e:
        log.severe(f"Unexpected error during sync: {str(e)}")
        raise

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to
# be run directly from the command line or IDE 'run' button.
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
