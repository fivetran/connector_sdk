"""
Databricks NOAA Weather Risk Intelligence Connector - Hybrid
(Agent-Driven Discovery + Multi-Agent Debate)

Syncs severe weather alerts from the NOAA Weather API and enriches them
with AI-powered hybrid analysis using Databricks ai_query() SQL function.
This is the capstone connector in the Databricks AI tutorial series,
combining both advanced patterns in a single connector.

Four-phase architecture:
  - Phase 1 (MOVE): Fetch weather alerts from NOAA Weather API for
    configured states
  - Phase 2 (DISCOVERY): AI analyzes weather patterns and recommends
    additional states/regions to investigate for related weather system
    impact
  - Phase 3 (DEBATE): For each significant event, two AI personas debate:
    1. Emergency Response Analyst (urgency-maximizing)
    2. Resource Planning Analyst (probability-weighted, proportional)
    3. Consensus Agent (synthesizes both, produces disagreement_flag)
  - Phase 4 (AGENT): Optional Genie Space creation for natural language
    weather risk analytics

This connector demonstrates the fourth and final level of the Databricks
AI connector progression: Hybrid (Discovery + Debate). It combines the
adaptive data fetching of agent-driven discovery with the balanced
multi-perspective analysis of multi-agent debate, producing the richest
AI-enriched dataset in the series.

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

# For date calculations
from datetime import datetime, timezone

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

# NOAA Weather API Configuration
__BASE_URL_NOAA = "https://api.weather.gov"
__API_TIMEOUT_SECONDS = 30
__NOAA_USER_AGENT = "Fivetran-NOAA-Weather-Databricks-Connector/1.0 " "(developers@fivetran.com)"

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__NOAA_RATE_LIMIT_DELAY = 0.3

# Default Configuration Values
__DEFAULT_MAX_EVENTS = 20
__DEFAULT_MAX_ENRICHMENTS = 5
__DEFAULT_MAX_DISCOVERY_REGIONS = 3
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120
__DEFAULT_ALERT_STATES = "TX,OK,KS"
__DEFAULT_SEVERITY_FILTER = "Severe,Extreme"

# Databricks SQL Statement API
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"

# Genie Space API
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Sanity ceilings
__MAX_EVENTS_CEILING = 200
__MAX_ENRICHMENTS_CEILING = 20
__MAX_DISCOVERY_REGIONS_CEILING = 10

# Genie Space configuration
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a weather risk intelligence agent. This dataset contains "
    "NOAA severe weather alerts enriched with AI-powered hybrid analysis: "
    "agent-driven discovery of related weather impacts across regions, "
    "plus multi-agent debate between an Emergency Response Analyst and "
    "a Resource Planning Analyst. The disagreement_flag identifies alerts "
    "where the experts significantly disagreed on response urgency. "
    "Use weather_events for alert data, discovery_insights for regional "
    "risk patterns, and debate_consensus for AI analysis results."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which weather events have disagreement flags between the analysts?",
    "Show me all Extreme severity alerts and their recommended actions",
    "What states were identified by the discovery agent as at risk?",
    "List events where the debate winner was the emergency analyst",
    "What weather event types have the highest consensus risk scores?",
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
    Parse a boolean-like config value.

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
    Read an optional int config value, treating placeholders as
    unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key
        default: Default value

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
    Read an optional string config value, treating placeholders
    as unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key
        default: Default value

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
    for param in [
        "max_events",
        "max_enrichments",
        "max_discovery_regions",
        "databricks_timeout",
    ]:
        value = configuration.get(param)
        if value is not None and not _is_placeholder(value):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{param} must be a positive integer")
            if parsed < 1:
                raise ValueError(f"{param} must be a positive integer")

    # Enforce ceilings
    max_events = _optional_int(configuration, "max_events", __DEFAULT_MAX_EVENTS)
    if max_events > __MAX_EVENTS_CEILING:
        raise ValueError(f"max_events={max_events} exceeds ceiling " f"of {__MAX_EVENTS_CEILING}.")

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

    max_discovery_regions = _optional_int(
        configuration,
        "max_discovery_regions",
        __DEFAULT_MAX_DISCOVERY_REGIONS,
    )
    if max_discovery_regions > __MAX_DISCOVERY_REGIONS_CEILING:
        raise ValueError(
            f"max_discovery_regions={max_discovery_regions} exceeds "
            f"ceiling of {__MAX_DISCOVERY_REGIONS_CEILING}."
        )

    # Validate Databricks credentials.
    # Discovery is a phase inside enrichment — it cannot run when
    # enable_enrichment=false regardless of its own flag, so the credential
    # gate keys off enrichment + genie only. This preserves "data-only mode"
    # (enable_enrichment=false) without forcing users to also explicitly
    # disable discovery.
    is_enrichment = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment or is_genie:
        for key in [
            "databricks_workspace_url",
            "databricks_token",
            "databricks_warehouse_id",
        ]:
            if _is_placeholder(configuration.get(key)):
                raise ValueError(f"Missing required Databricks config: " f"{key}")

        url = configuration.get("databricks_workspace_url", "")
        if not url.startswith("https://"):
            raise ValueError("databricks_workspace_url must start with " f"'https://'. Got: {url}")

    if is_genie:
        if _is_placeholder(configuration.get("genie_table_identifier")):
            raise ValueError("genie_table_identifier required for " "Genie Space")


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
        {"table": "weather_events", "primary_key": ["event_id"]},
        {
            "table": "discovery_insights",
            "primary_key": ["insight_id"],
        },
        {
            "table": "emergency_assessments",
            "primary_key": ["event_id"],
        },
        {
            "table": "planning_assessments",
            "primary_key": ["event_id"],
        },
        {
            "table": "debate_consensus",
            "primary_key": ["event_id"],
        },
    ]


def create_session():
    """
    Create a requests session for NOAA and Databricks API calls.

    Returns:
        requests.Session with NOAA-required User-Agent header
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": __NOAA_USER_AGENT,
            "Accept": "application/geo+json",
        }
    )
    return session


def fetch_data_with_retry(session, url, params=None):
    """
    Fetch data from API with exponential backoff retry logic.

    Args:
        session: requests.Session object
        url: Full URL to fetch
        params: Optional query parameters

    Returns:
        JSON response as dictionary

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
            log.warning(f"Connection error: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Connection failed after " f"{__MAX_RETRIES} attempts: {e}"
                ) from e

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
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
                log.warning(f"HTTP {status_code}, retrying in " f"{delay}s")
                time.sleep(delay)
            else:
                attempts = attempt + 1
                raise RuntimeError(
                    f"API request failed after {attempts} " f"attempt(s): {e}"
                ) from e


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() with async polling for PENDING
    statements.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        prompt: Prompt text

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

    escaped = prompt.replace("'", "''")
    statement = f"SELECT ai_query('{model}', '{escaped}') " f"as response"

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

        # Poll for PENDING/RUNNING. Guard against a missing statement_id —
        # without it, the poll URL would become `.../None` and produce a
        # confusing HTTP error. Treat as an unrecoverable response.
        statement_id = result.get("statement_id")
        if sql_state in ("PENDING", "RUNNING") and not statement_id:
            log.warning(
                "ai_query() returned state="
                f"{sql_state} without a statement_id; cannot poll. "
                "Returning None."
            )
            return None

        poll_count = 0
        max_polls = 12
        poll_interval = 10

        while sql_state in ("PENDING", "RUNNING") and poll_count < max_polls:
            poll_count += 1
            time.sleep(poll_interval)
            poll_url = f"{url}/{statement_id}"
            poll_resp = session.get(poll_url, headers=headers, timeout=timeout)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            sql_state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/" f"{max_polls}: {sql_state}")

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
        log.warning(f"ai_query() error: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        log.warning(f"ai_query() JSON parse error: {str(e)}")
        return None


def extract_json_from_content(content):
    """
    Extract a JSON object from LLM response text.

    Args:
        content: String potentially containing JSON

    Returns:
        Parsed dictionary if found, or None
    """
    if not content or "{" not in content:
        return None
    start = content.find("{")
    end = content.rfind("}") + 1
    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return None


def fetch_alerts_for_state(session, state_code):
    """
    Fetch weather alerts for a US state from NOAA Weather API.

    Args:
        session: requests.Session
        state_code: Two-letter US state code (e.g., "TX")

    Returns:
        List of alert feature dictionaries
    """
    url = f"{__BASE_URL_NOAA}/alerts"
    params = {
        "area": state_code,
        "status": "actual",
        "limit": 50,
    }

    try:
        data = fetch_data_with_retry(session, url, params=params)
        features = data.get("features", [])
        log.info(f"Fetched {len(features)} alerts for " f"{state_code}")
        time.sleep(__NOAA_RATE_LIMIT_DELAY)
        return features
    except RuntimeError as e:
        log.warning(f"Failed to fetch alerts for {state_code}: " f"{e}")
        return []


def build_event_record(feature, source_label):
    """
    Build a normalized event record from a NOAA alert feature.

    Args:
        feature: GeoJSON feature dictionary
        source_label: "seed" or "discovered"

    Returns:
        Dictionary with normalized event fields
    """
    props = feature.get("properties", {})

    # Build a stable event_id from the NOAA alert ID
    raw_id = props.get("id", "")
    event_id = raw_id.replace("urn:oid:", "").replace(".", "_")

    return {
        "event_id": event_id,
        "noaa_id": raw_id,
        "event_type": props.get("event"),
        "severity": props.get("severity"),
        "certainty": props.get("certainty"),
        "urgency": props.get("urgency"),
        "headline": props.get("headline"),
        "description": (props.get("description") or "")[:2000],
        "instruction": (props.get("instruction") or "")[:1000] or None,
        "area_desc": props.get("areaDesc"),
        "affected_zones": props.get("affectedZones"),
        "onset": props.get("onset"),
        "expires": props.get("expires"),
        "ends": props.get("ends"),
        "sent": props.get("sent"),
        "effective": props.get("effective"),
        "sender_name": props.get("senderName"),
        "status": props.get("status"),
        "message_type": props.get("messageType"),
        "category": props.get("category"),
        "source": source_label,
    }


def build_discovery_prompt(state_code, events_summary):
    """
    Build the ai_query() prompt for discovery analysis.

    The agent analyzes weather patterns in a state and recommends
    additional states/regions to investigate.

    Args:
        state_code: State being analyzed
        events_summary: Formatted weather event summary

    Returns:
        Prompt string
    """
    return (
        "You are a meteorological risk analyst. Analyze these "
        "weather alerts and identify related weather systems "
        "that may be affecting adjacent states.\n\n"
        f"STATE: {state_code}\n\n"
        f"CURRENT ALERTS:\n{events_summary}\n\n"
        "YOUR TASKS:\n"
        "1. Identify the dominant weather system(s) causing "
        "these alerts\n"
        "2. Assess which adjacent states are likely affected "
        "by the same system\n"
        "3. Recommend 2-3 states to investigate next\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "weather_system": "...",\n'
        '  "system_severity": "EXTREME|SEVERE|MODERATE|MINOR",\n'
        '  "recommended_states": [\n'
        '    {"state": "XX", "reason": "..."}\n'
        "  ],\n"
        '  "regional_risk_summary": "..."\n'
        "}"
    )


def build_emergency_prompt(event_record):
    """
    Build the Emergency Response Analyst prompt
    (urgency-maximizing).

    Args:
        event_record: Normalized event record dictionary

    Returns:
        Prompt string
    """
    return (
        "You are an Emergency Response Analyst. Your job is to "
        "assess the MAXIMUM threat to life and property from this "
        "weather event. Assume worst-case: populated areas in the "
        "path, no advance preparation, vulnerable populations "
        "present.\n\n"
        f"EVENT: {event_record.get('event_type', 'N/A')}\n"
        f"Severity: {event_record.get('severity', 'N/A')}\n"
        f"Urgency: {event_record.get('urgency', 'N/A')}\n"
        f"Certainty: {event_record.get('certainty', 'N/A')}\n"
        f"Headline: {event_record.get('headline', 'N/A')}\n"
        f"Area: {event_record.get('area_desc', 'N/A')}\n"
        f"Description: {event_record.get('description', 'N/A')[:600]}\n"
        f"Instruction: {event_record.get('instruction', 'N/A')}\n\n"
        "Analyze from an urgency-maximizing perspective:\n"
        "1. What is the worst-case impact scenario?\n"
        "2. Should evacuation be ordered or recommended?\n"
        "3. What emergency resources should be pre-positioned?\n"
        "4. How many people are potentially at risk?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "emergency_risk_score": <1-10>,\n'
        '  "worst_case_impact": "...",\n'
        '  "evacuation_recommendation": '
        '"ORDER|RECOMMEND|STANDBY|UNNECESSARY",\n'
        '  "resource_deployment": "FULL|PARTIAL|STANDBY|NONE",\n'
        '  "estimated_population_at_risk": "...",\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_planning_prompt(event_record):
    """
    Build the Resource Planning Analyst prompt
    (probability-weighted, proportional).

    Args:
        event_record: Normalized event record dictionary

    Returns:
        Prompt string
    """
    return (
        "You are a Resource Planning Analyst. Your job is to "
        "assess the REALISTIC impact of this weather event and "
        "recommend PROPORTIONAL resource allocation. Consider: "
        "What is the probability-weighted expected impact? Are "
        "resources being allocated efficiently? Would a smaller "
        "response be adequate?\n\n"
        f"EVENT: {event_record.get('event_type', 'N/A')}\n"
        f"Severity: {event_record.get('severity', 'N/A')}\n"
        f"Urgency: {event_record.get('urgency', 'N/A')}\n"
        f"Certainty: {event_record.get('certainty', 'N/A')}\n"
        f"Headline: {event_record.get('headline', 'N/A')}\n"
        f"Area: {event_record.get('area_desc', 'N/A')}\n"
        f"Description: {event_record.get('description', 'N/A')[:600]}\n"
        f"Instruction: {event_record.get('instruction', 'N/A')}\n\n"
        "Analyze from a proportional-response perspective:\n"
        "1. What is the probability-weighted expected impact?\n"
        "2. Is full evacuation proportionate or excessive?\n"
        "3. What is the most cost-effective resource posture?\n"
        "4. What compensating factors reduce the risk?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "planning_risk_score": <1-10>,\n'
        '  "expected_impact": "...",\n'
        '  "evacuation_assessment": '
        '"PROPORTIONATE|EXCESSIVE|INSUFFICIENT|UNNECESSARY",\n'
        '  "resource_recommendation": "FULL|PARTIAL|STANDBY|NONE",\n'
        '  "cost_effectiveness": "HIGH|MEDIUM|LOW",\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_consensus_prompt(event_record, emergency_result, planning_result):
    """
    Build the Consensus synthesizer prompt.

    Args:
        event_record: Normalized event record
        emergency_result: Emergency Analyst JSON result
        planning_result: Planning Analyst JSON result

    Returns:
        Prompt string
    """
    return (
        "You are a neutral emergency management director "
        "synthesizing two expert assessments of the same weather "
        "event. One expert (Emergency) maximizes urgency; the "
        "other (Planning) applies proportional analysis. Produce "
        "a balanced assessment.\n\n"
        f"EVENT: {event_record.get('event_type', 'N/A')} — "
        f"{event_record.get('headline', 'N/A')}\n\n"
        "EMERGENCY ANALYST:\n"
        f"{json.dumps(emergency_result, indent=2)}\n\n"
        "PLANNING ANALYST:\n"
        f"{json.dumps(planning_result, indent=2)}\n\n"
        "Synthesize:\n"
        "1. Where do they AGREE and DISAGREE?\n"
        "2. Which is MORE PERSUASIVE and why?\n"
        "3. What is the balanced recommended action?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "final_severity": "CRITICAL|HIGH|MEDIUM|LOW",\n'
        '  "consensus_risk_score": <1-10>,\n'
        '  "debate_winner": "EMERGENCY|PLANNING|DRAW",\n'
        '  "winner_rationale": "...",\n'
        '  "agreement_areas": ["..."],\n'
        '  "disagreement_areas": ["..."],\n'
        '  "disagreement_flag": true/false,\n'
        '  "disagreement_severity": '
        '"NONE|MINOR|SIGNIFICANT|FUNDAMENTAL",\n'
        '  "recommended_action": "...",\n'
        '  "executive_summary": "..."\n'
        "}"
    )


def upsert_assessment(table_name, event_id, assessment, assessment_type):
    """
    Upsert an AI assessment record.

    Args:
        table_name: Destination table
        event_id: Event identifier
        assessment: Parsed JSON assessment
        assessment_type: Type label

    Returns:
        bool: True if upserted
    """
    if assessment is None:
        log.warning(f"Skipping {assessment_type} for " f"{event_id}: no response")
        return False

    record = {
        "event_id": event_id,
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


def format_events_for_prompt(event_records):
    """
    Format event records into a summary string for prompts.

    Args:
        event_records: List of event record dictionaries

    Returns:
        Formatted summary string
    """
    if not event_records:
        return "  No events"
    lines = []
    for e in event_records[:10]:
        lines.append(
            f"  - {e.get('event_type', 'Unknown')}: "
            f"{e.get('severity', '?')} severity, "
            f"{e.get('headline', 'No headline')[:80]}"
        )
    return "\n".join(lines)


def run_discovery_phase(
    session,
    configuration,
    seed_states,
    all_events,
    event_records_by_state,
    state,
):
    """
    Run Agent-Driven Discovery: AI identifies additional states
    affected by the same weather systems.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        seed_states: List of seed state codes
        all_events: List of all event records (mutable)
        event_records_by_state: Dict of state->records
        state: State dict for checkpointing

    Returns:
        Tuple of (set of all states analyzed, ai_query call count).
        The call count is the number of ai_query() calls made during
        discovery and is threaded into run_debate_phase() so that
        max_enrichments enforces a single combined budget across both
        phases (contract: max_enrichments = total ai_query() calls for
        discovery + debate combined).
    """
    max_enrichments = _optional_int(
        configuration,
        "max_enrichments",
        __DEFAULT_MAX_ENRICHMENTS,
    )
    max_discovery = _optional_int(
        configuration,
        "max_discovery_regions",
        __DEFAULT_MAX_DISCOVERY_REGIONS,
    )
    enrichment_count = 0
    all_states = set(seed_states)
    discovered_states = set()

    for state_code in seed_states:
        if enrichment_count >= max_enrichments:
            break

        events = event_records_by_state.get(state_code, [])
        summary = format_events_for_prompt(events)

        prompt = build_discovery_prompt(state_code, summary)
        log.info(f"Calling ai_query() for discovery: " f"{state_code}")

        content = call_ai_query(session, configuration, prompt)
        result = extract_json_from_content(content)
        enrichment_count += 1

        if not result or not isinstance(result, dict):
            continue

        # Upsert discovery insight
        insight = {
            "insight_id": f"discovery_{state_code}",
            "state_code": state_code,
            "weather_system": result.get("weather_system"),
            "system_severity": result.get("system_severity"),
            "recommended_states": result.get("recommended_states"),
            "regional_risk_summary": result.get("regional_risk_summary"),
            "source": "seed_analysis",
        }
        flattened = flatten_dict(insight)

        # The 'upsert' operation is used to insert or update
        # data in the destination table.
        # The first argument is the name of the destination
        # table.
        # The second argument is a dictionary containing the
        # record to be upserted.
        op.upsert(table="discovery_insights", data=flattened)

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

        # Fetch discovered states (type-check LLM output)
        recommended = result.get("recommended_states", [])
        if not isinstance(recommended, list):
            continue

        states_to_fetch = [
            s
            for s in recommended
            if isinstance(s, dict)
            and s.get("state")  # noqa: W503
            and s.get("state") not in all_states  # noqa: W503
            and s.get("state") not in discovered_states  # noqa: W503
        ][:max_discovery]

        for rec in states_to_fetch:
            d_state = rec.get("state", "").upper()[:2]
            if not d_state or d_state in discovered_states:
                continue

            discovered_states.add(d_state)
            all_states.add(d_state)

            log.info(f"Fetching discovered state: {d_state} " f"— {rec.get('reason', '')[:80]}")

            d_features = fetch_alerts_for_state(session, d_state)
            d_records = []
            for feature in d_features:
                record = build_event_record(feature, "discovered")
                if not record.get("event_id"):
                    continue
                d_records.append(record)
                flattened_r = flatten_dict(record)

                # The 'upsert' operation is used to insert
                # or update data in the destination table.
                # The first argument is the name of the
                # destination table.
                # The second argument is a dictionary
                # containing the record to be upserted.
                op.upsert(
                    table="weather_events",
                    data=flattened_r,
                )

            all_events.extend(d_records)
            event_records_by_state[d_state] = d_records

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

    return all_states, enrichment_count


def run_debate_phase(
    session,
    configuration,
    events,
    state,
    starting_enrichment_count=0,
):
    """
    Run Multi-Agent Debate: Emergency vs Planning analysts
    debate each significant event.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        events: List of event records to debate
        state: State dict for checkpointing
        starting_enrichment_count: ai_query() call count carried in
            from run_discovery_phase() so max_enrichments enforces a
            single combined budget across both phases.

    Returns:
        Tuple of (total_enrichment_count, disagreement_count,
        events_debated). total_enrichment_count is the cumulative
        ai_query() call count including discovery.
    """
    max_enrichments = _optional_int(
        configuration,
        "max_enrichments",
        __DEFAULT_MAX_ENRICHMENTS,
    )
    enrichment_count = starting_enrichment_count
    disagreement_count = 0
    events_debated = 0

    # Filter to significant events for debate. Cap candidate list at
    # the best-case number of events that could fit in the remaining
    # budget (2 calls per event minimum: emergency + planning). The
    # per-call budget checks below are the tight enforcement.
    severity_filter = _optional_str(
        configuration,
        "severity_filter",
        __DEFAULT_SEVERITY_FILTER,
    )
    severity_levels = [s.strip() for s in severity_filter.split(",")]

    remaining_budget = max(0, max_enrichments - enrichment_count)
    max_candidate_events = remaining_budget // 2
    debate_events = [e for e in events if e.get("severity") in severity_levels][
        :max_candidate_events
    ]

    log.info(
        f"Starting debate for {len(debate_events)} "
        f"significant events (up to 3 ai_query() calls each, "
        f"remaining budget: {remaining_budget})"
    )

    for event in debate_events:
        # Need at least 2 calls to meaningfully debate an event.
        if enrichment_count + 2 > max_enrichments:
            log.info("Enrichment budget exhausted — cannot fit both " "analysts for next event")
            break

        event_id = event.get("event_id")

        # Agent 1: Emergency Response Analyst
        emergency_content = call_ai_query(
            session,
            configuration,
            build_emergency_prompt(event),
        )
        enrichment_count += 1
        emergency_result = extract_json_from_content(emergency_content)
        upsert_assessment(
            "emergency_assessments",
            event_id,
            emergency_result,
            "emergency",
        )

        # Agent 2: Resource Planning Analyst
        planning_content = call_ai_query(
            session,
            configuration,
            build_planning_prompt(event),
        )
        enrichment_count += 1
        planning_result = extract_json_from_content(planning_content)
        upsert_assessment(
            "planning_assessments",
            event_id,
            planning_result,
            "planning",
        )

        # Agent 3: Consensus (only if both analysts succeeded AND
        # budget allows one more call).
        if emergency_result and planning_result:
            if enrichment_count >= max_enrichments:
                log.warning(
                    f"Skipping consensus for {event_id}: " f"budget exhausted after planning call"
                )
            else:
                consensus_content = call_ai_query(
                    session,
                    configuration,
                    build_consensus_prompt(
                        event,
                        emergency_result,
                        planning_result,
                    ),
                )
                enrichment_count += 1
                consensus_result = extract_json_from_content(consensus_content)
                upsert_assessment(
                    "debate_consensus",
                    event_id,
                    consensus_result,
                    "consensus",
                )

                if consensus_result and consensus_result.get("disagreement_flag"):
                    disagreement_count += 1
        else:
            log.warning(f"Skipping consensus for {event_id}: " f"missing analyst assessment")

        events_debated += 1

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

    return enrichment_count, disagreement_count, events_debated


def create_genie_space(session, configuration, state):
    """
    Create a Databricks Genie Space for weather risk analytics.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        state: State dict for persisting space_id

    Returns:
        Space ID or None
    """
    existing = state.get("genie_space_id")
    if existing:
        log.info(f"Genie Space exists: {existing}")
        return existing

    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    table_id = configuration.get("genie_table_identifier")

    url = f"{workspace_url}{__GENIE_SPACE_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    serialized = {
        "version": 2,
        "config": {
            "sample_questions": [
                {
                    "id": uuid.uuid4().hex,
                    "question": q,
                }
                for q in __GENIE_SPACE_SAMPLE_QUESTIONS
            ]
        },
        "data_sources": {"tables": [{"identifier": table_id}]},
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
        "title": "NOAA Weather Risk Intelligence",
        "description": (
            "AI-enriched NOAA weather data with hybrid "
            "analysis. Powered by Fivetran + Databricks."
        ),
        "serialized_space": json.dumps(serialized),
    }

    try:
        resp = session.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        space_id = result.get("space_id")
        if space_id:
            log.info(f"Genie Space created: {space_id}")
            return space_id
        return None
    except requests.exceptions.HTTPError as e:
        log.warning(f"Genie Space error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Genie Space error: {str(e)}")
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
        "Example: all_things_ai/tutorials : " "databricks-fm-noaa-weather-risk-intelligence"
    )

    validate_configuration(configuration)

    # Parse configuration
    alert_states_str = _optional_str(
        configuration,
        "alert_states",
        __DEFAULT_ALERT_STATES,
    )
    seed_states = [s.strip().upper() for s in alert_states_str.split(",") if s.strip()]
    max_events = _optional_int(
        configuration,
        "max_events",
        __DEFAULT_MAX_EVENTS,
    )
    is_enrichment = _parse_bool(
        configuration.get("enable_enrichment"),
        default=True,
    )
    is_discovery = _parse_bool(
        configuration.get("enable_discovery"),
        default=True,
    )
    is_genie = _parse_bool(
        configuration.get("enable_genie_space"),
        default=False,
    )

    log.info(f"Monitoring states: {', '.join(seed_states)}")

    if is_enrichment:
        model = _optional_str(
            configuration,
            "databricks_model",
            __DEFAULT_DATABRICKS_MODEL,
        )
        log.info(f"Hybrid analysis ENABLED: model={model}")
    else:
        log.info("Hybrid analysis DISABLED")

    session = create_session()

    try:
        # --- Phase 1: MOVE ---
        log.info("Phase 1 (MOVE): Fetching weather alerts " "from NOAA")

        all_events = []
        event_records_by_state = {}

        for state_code in seed_states:
            features = fetch_alerts_for_state(session, state_code)
            state_records = []

            for feature in features[:max_events]:
                record = build_event_record(feature, "seed")
                if not record.get("event_id"):
                    continue

                state_records.append(record)
                flattened = flatten_dict(record)

                # The 'upsert' operation is used to insert
                # or update data in the destination table.
                # The first argument is the name of the
                # destination table.
                # The second argument is a dictionary
                # containing the record to be upserted.
                op.upsert(
                    table="weather_events",
                    data=flattened,
                )

            all_events.extend(state_records)
            event_records_by_state[state_code] = state_records

        log.info(f"Phase 1 complete: {len(all_events)} events " f"from {len(seed_states)} states")

        if not all_events:
            log.info("No weather events found")
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

        # --- Phase 2: DISCOVERY ---
        discovery_enrichment_count = 0
        if is_enrichment and is_discovery:
            log.info("Phase 2 (DISCOVERY): Agent-Driven " "Discovery of related regions")
            all_states, discovery_enrichment_count = run_discovery_phase(
                session,
                configuration,
                seed_states,
                all_events,
                event_records_by_state,
                state,
            )
            log.info(
                f"Discovery complete: "
                f"{len(all_states)} total states analyzed "
                f"({discovery_enrichment_count} ai_query() calls)"
            )

        # --- Phase 3: DEBATE ---
        if is_enrichment:
            log.info("Phase 3 (DEBATE): Multi-Agent Debate " "on significant events")

            total_enrichment_count, disagreement_count, events_debated = run_debate_phase(
                session,
                configuration,
                all_events,
                state,
                starting_enrichment_count=discovery_enrichment_count,
            )

            log.info(
                f"Debate complete: {events_debated} events debated "
                f"({total_enrichment_count - discovery_enrichment_count} "
                f"ai_query() calls), {disagreement_count} with "
                f"disagreement flags"
            )
            log.info(f"Total ai_query() calls this sync: " f"{total_enrichment_count}")
        else:
            log.info("Enrichment disabled, skipping discovery " "and debate.")

        # --- Phase 4: AGENT ---
        if is_genie:
            log.info("Phase 4 (AGENT): Creating Genie Space")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
                # Save the progress by checkpointing the
                # state. This is important for ensuring
                # that the sync process can resume from
                # the correct position in case of next
                # sync or interruptions.
                # You should checkpoint even if you are
                # not using incremental sync, as it tells
                # Fivetran it is safe to write to
                # destination.
                # For large datasets, checkpoint
                # regularly (e.g., every N records) not
                # only at the end.
                # Learn more about how and where to
                # checkpoint by reading our best
                # practices documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)

        # Final checkpoint
        state["last_sync"] = datetime.now(timezone.utc).isoformat()

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

        log.info(f"Sync complete: {len(all_events)} total " f"events across all phases")

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
