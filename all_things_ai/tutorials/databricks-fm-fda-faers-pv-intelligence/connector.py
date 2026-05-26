"""
Databricks FDA FAERS Pharmacovigilance Intelligence Connector - Multi-Agent
Debate

Syncs adverse event reports from the FDA Adverse Event Reporting System
(FAERS) via the OpenFDA Drug Event API and enriches each event with
competing AI assessments from two opposing pharmacovigilance personas
using Databricks ai_query() SQL function, followed by a consensus
synthesizer that produces a final severity and disagreement flag.

This connector pairs with the FDA Drug Label Intelligence connector
(PR #567) to provide a complete drug safety pipeline on Databricks:
labels for drug information + adverse events for post-market surveillance.

Two-phase architecture:
  - Phase 1 (MOVE): Fetch adverse event reports from OpenFDA
  - Phase 2 (DEBATE): For each serious event, three ai_query() calls:
    1. Safety Advocate (risk-maximizing PV perspective)
    2. Clinical Realist (context-aware clinical perspective)
    3. Consensus Agent (synthesizes both, produces disagreement_flag)

The disagreement_flag identifies adverse events where the two experts
significantly disagree on whether the event represents a real safety
signal, flagging them for human pharmacovigilance review.

Optional Genie Space creation after data lands for natural language
analytics on the enriched adverse event data.

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

# For URL-encoding the user-supplied portion of the OpenFDA Lucene query
import urllib.parse

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

# OpenFDA Drug Event API Configuration
__BASE_URL_FDA = "https://api.fda.gov/drug/event.json"
__API_TIMEOUT_SECONDS = 30

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__FDA_RATE_LIMIT_DELAY = 0.3

# Default Configuration Values
__DEFAULT_MAX_EVENTS = 10
__DEFAULT_MAX_ENRICHMENTS = 5
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120
__DEFAULT_LOOKBACK_DAYS = 30

# Databricks SQL Statement API Configuration
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"
__SQL_POLL_INTERVAL_SECONDS = 10
__SQL_MAX_POLL_ATTEMPTS = 12

# OpenFDA pagination
__FDA_PAGE_SIZE = 100

# Lucene reserved characters that must be backslash-escaped before being
# embedded in an OpenFDA search query so user input cannot inject Lucene
# operators or break the query syntax.
__LUCENE_RESERVED_CHARS = '\\+-&|!(){}[]^"~*?:/'

# Genie Space API Configuration
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Sanity ceilings
__MAX_EVENTS_CEILING = 100
__MAX_ENRICHMENTS_CEILING = 50

# Genie Space configuration for pharmacovigilance
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a pharmacovigilance intelligence agent. This dataset contains "
    "FDA adverse event reports (FAERS) enriched with AI-powered multi-agent "
    "debate analysis. Each serious adverse event has been analyzed by two "
    "competing AI personas: a Safety Advocate (risk-maximizing) and a "
    "Clinical Realist (context-aware skeptic), followed by a consensus "
    "synthesis. The disagreement_flag identifies events where the experts "
    "significantly disagreed on whether the event represents a real safety "
    "signal, flagging them for human PV review."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which adverse events have disagreement flags needing PV review?",
    "Show me all events with seriousness death and their consensus severity",
    "What drugs have the most serious adverse events?",
    "List events where the debate winner was the safety advocate",
    "What are the most common adverse reactions in this dataset?",
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

    Args:
        value: Configuration value to evaluate.

    Returns:
        True if the value is None, an empty string, or an angle-bracket
        placeholder (e.g., "<DRUG_NAME>"); otherwise False.
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
    Read an optional string config value, treating placeholders as unset.

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


def _validate_positive_int(configuration, key):
    """
    Raise ValueError if `key` is set to a non-positive-integer value.
    Placeholders and missing keys are treated as unset (no error) so the
    caller's defaults take over.

    Args:
        configuration: Configuration dictionary
        key: Configuration key to validate
    """
    value = configuration.get(key)
    if value is None or _is_placeholder(value):
        return
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a positive integer")
    if parsed < 1:
        raise ValueError(f"{key} must be a positive integer")


def _validate_bool_flag(configuration, key):
    """
    Raise ValueError if `key` is set to anything other than the literal
    strings 'true' or 'false' (case-insensitive). Placeholders and missing
    keys are treated as unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key to validate
    """
    value = configuration.get(key)
    if value is None or _is_placeholder(value):
        return
    if isinstance(value, bool):
        return
    if str(value).strip().lower() not in ("true", "false"):
        raise ValueError(f"{key} must be 'true' or 'false' (got {value!r})")


def _escape_lucene_value(value):
    """
    Backslash-escape Lucene reserved characters in a user-supplied value
    so it cannot inject Lucene operators or break the search query.

    Args:
        value: User-supplied string

    Returns:
        Escaped string safe to embed in a Lucene field:value clause
        (still needs URL-encoding before being placed in a URL).
    """
    return "".join("\\" + c if c in __LUCENE_RESERVED_CHARS else c for c in value)


def _build_search_query(start_date, end_date, search_drug):
    """
    Build the OpenFDA Drug Event search query. The OpenFDA convention
    uses literal `+` as a space within the search parameter and `+AND+`
    as the boolean joiner; ranges use `[X+TO+Y]`.

    User-supplied `search_drug` is Lucene-escaped (so reserved characters
    like `+ : ( ) " :` cannot inject a clause) and URL-encoded so spaces
    and other URL-reserved characters survive the round-trip intact.

    Args:
        start_date: Inclusive lower bound of the receivedate range (YYYYMMDD)
        end_date: Inclusive upper bound of the receivedate range (YYYYMMDD)
        search_drug: Optional drug name to filter on; None or empty
            string means no drug filter.

    Returns:
        Search query string ready to be embedded in the OpenFDA URL
        after `?search=`.
    """
    parts = [f"receivedate:[{start_date}+TO+{end_date}]"]
    if search_drug:
        escaped = _escape_lucene_value(search_drug)
        encoded = urllib.parse.quote(escaped, safe="")
        parts.append(f"patient.drug.medicinalproduct:{encoded}")
    return "+AND+".join(parts)


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
    for param in [
        "max_events",
        "max_enrichments",
        "lookback_days",
        "databricks_timeout",
    ]:
        _validate_positive_int(configuration, param)

    for flag in ["enable_enrichment", "enable_genie_space"]:
        _validate_bool_flag(configuration, flag)

    max_events = _optional_int(configuration, "max_events", __DEFAULT_MAX_EVENTS)
    if max_events > __MAX_EVENTS_CEILING:
        raise ValueError(f"max_events={max_events} exceeds ceiling of {__MAX_EVENTS_CEILING}.")

    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    if max_enrichments > __MAX_ENRICHMENTS_CEILING:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds ceiling of "
            f"{__MAX_ENRICHMENTS_CEILING}."
        )

    is_enrichment = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment or is_genie:
        for key in [
            "databricks_workspace_url",
            "databricks_token",
            "databricks_warehouse_id",
        ]:
            if _is_placeholder(configuration.get(key)):
                raise ValueError(f"Missing required Databricks config: {key}")

        url = configuration.get("databricks_workspace_url", "")
        if not url.startswith("https://"):
            raise ValueError(f"databricks_workspace_url must start with 'https://'. Got: {url}")

    if is_genie and _is_placeholder(configuration.get("genie_table_identifier")):
        raise ValueError("genie_table_identifier required for Genie Space")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "adverse_events", "primary_key": ["safety_report_id"]},
        {"table": "safety_assessments", "primary_key": ["safety_report_id"]},
        {"table": "clinical_assessments", "primary_key": ["safety_report_id"]},
        {"table": "debate_consensus", "primary_key": ["safety_report_id"]},
    ]


def create_session():
    """
    Create a requests session for OpenFDA and Databricks API calls.

    Returns:
        requests.Session with appropriate headers
    """
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "Fivetran-FDA-FAERS-Databricks-Connector/1.0", "Accept": "application/json"}
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
            response = session.get(url, params=params, timeout=__API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s (attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s (attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )
            if status_code in (401, 403):
                msg = f"HTTP {status_code}: Access denied. URL: {url}"
                log.severe(msg)
                raise RuntimeError(msg) from e

            should_retry = status_code in __RETRYABLE_STATUS_CODES
            if should_retry and attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"HTTP {status_code}, retrying in {delay}s")
                time.sleep(delay)
            else:
                attempts = attempt + 1
                raise RuntimeError(f"API request failed after {attempts} attempt(s): {e}") from e


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() with async polling for PENDING states.

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
    model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)
    timeout = _optional_int(configuration, "databricks_timeout", __DEFAULT_DATABRICKS_TIMEOUT)

    url = f"{workspace_url}{__SQL_STATEMENT_ENDPOINT}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    escaped = prompt.replace("'", "''")
    statement = f"SELECT ai_query('{model}', '{escaped}') as response"
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

        statement_id = result.get("statement_id")
        poll_count = 0

        if sql_state in ("PENDING", "RUNNING") and not statement_id:
            log.warning(
                "ai_query() returned PENDING/RUNNING without a statement_id; "
                "cannot poll. Treating as failure."
            )
            return None

        while sql_state in ("PENDING", "RUNNING") and poll_count < __SQL_MAX_POLL_ATTEMPTS:
            poll_count += 1
            time.sleep(__SQL_POLL_INTERVAL_SECONDS)
            poll_resp = session.get(f"{url}/{statement_id}", headers=headers, timeout=timeout)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            sql_state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/{__SQL_MAX_POLL_ATTEMPTS}: {sql_state}")

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


def fetch_adverse_events(session, search_query, limit, skip):
    """
    Fetch a single page of adverse events from the OpenFDA Drug Event API.

    Builds URL manually to avoid requests percent-encoding the Lucene
    search syntax brackets and plus signs. The user-supplied portion of
    `search_query` is already Lucene-escaped + URL-encoded by
    _build_search_query() so embedding it into the URL is safe.

    Args:
        session: requests.Session
        search_query: Lucene search string (e.g., receivedate:[...])
        limit: Max records per page
        skip: Offset for pagination

    Returns:
        Tuple of (results_list, total_count)
    """
    if search_query:
        url = f"{__BASE_URL_FDA}?search={search_query}&limit={limit}&skip={skip}"
    else:
        url = f"{__BASE_URL_FDA}?limit={limit}&skip={skip}"

    data = fetch_data_with_retry(session, url)
    results = data.get("results", [])
    total = data.get("meta", {}).get("results", {}).get("total", 0)
    time.sleep(__FDA_RATE_LIMIT_DELAY)
    return results, total


def fetch_all_events(session, search_query, max_events):
    """
    Paginate the OpenFDA Drug Event API up to `max_events` records.

    Loops with skip+limit until either:
      - max_events have been collected (cap_hit=True), or
      - the API returns an empty page or skip>=total (cap_hit=False
        because we exhausted the matching set).

    The caller uses cap_hit to decide whether it is safe to advance the
    incremental cursor: if cap_hit is True there are still un-synced
    records on the server and the cursor MUST stay where it was so the
    next sync re-fetches them.

    Args:
        session: requests.Session
        search_query: Built by _build_search_query()
        max_events: Hard cap on records fetched in this run

    Returns:
        Tuple of (events_list, total_count, cap_hit_bool)
    """
    events = []
    skip = 0
    total = 0
    page_size = min(__FDA_PAGE_SIZE, max_events)

    while len(events) < max_events:
        remaining = max_events - len(events)
        current_limit = min(page_size, remaining)
        page, page_total = fetch_adverse_events(session, search_query, current_limit, skip)

        if skip == 0:
            total = page_total

        if not page:
            return events, total, False

        events.extend(page)
        skip += len(page)

        if skip >= total or len(page) < current_limit:
            return events, total, False

    cap_hit = total > len(events)
    return events, total, cap_hit


def build_event_record(event):
    """
    Build a normalized adverse event record from raw FAERS data.

    Args:
        event: Raw OpenFDA adverse event dictionary

    Returns:
        Dictionary with normalized event fields
    """
    patient = event.get("patient", {})
    drugs = patient.get("drug", [])
    reactions = patient.get("reaction", [])

    primary_drug = drugs[0].get("medicinalproduct", "Unknown") if drugs else "Unknown"
    primary_reaction = reactions[0].get("reactionmeddrapt", "Unknown") if reactions else "Unknown"

    drug_names = [d.get("medicinalproduct", "") for d in drugs if d.get("medicinalproduct")]
    reaction_names = [
        r.get("reactionmeddrapt", "") for r in reactions if r.get("reactionmeddrapt")
    ]

    sex_map = {"1": "Male", "2": "Female"}

    return {
        "safety_report_id": event.get("safetyreportid"),
        "receive_date": event.get("receivedate"),
        "is_serious": event.get("serious") == "1",
        "seriousness_death": event.get("seriousnessdeath") == "1",
        "seriousness_hospitalization": event.get("seriousnesshospitalization") == "1",
        "seriousness_life_threatening": event.get("seriousnesslifethreatening") == "1",
        "seriousness_disabling": event.get("seriousnessdisabling") == "1",
        "primary_drug": primary_drug,
        "primary_reaction": primary_reaction,
        "patient_age": patient.get("patientonsetage"),
        "patient_age_unit": patient.get("patientonsetageunit"),
        "patient_sex": sex_map.get(str(patient.get("patientsex")), "Unknown"),
        "patient_weight": patient.get("patientweight"),
        "drug_count": len(drugs),
        "reaction_count": len(reactions),
        "drug_list": json.dumps(drug_names) if drug_names else None,
        "reaction_list": json.dumps(reaction_names) if reaction_names else None,
        "report_type": event.get("reporttype"),
        "sender_organization": event.get("sender", {}).get("senderorganization"),
        "occurrence_country": event.get("occurcountry"),
    }


def build_safety_prompt(event_record):
    """
    Build the Safety Advocate prompt (risk-maximizing PV perspective).

    Args:
        event_record: Normalized adverse event record

    Returns:
        Prompt string
    """
    return (
        "You are a senior pharmacovigilance Safety Advocate. Your job is to "
        "identify the MAXIMUM potential safety signal from this adverse event "
        "report. Assume this could be an early indicator of a broader safety "
        "issue. Consider: Is this a known reaction? Could this indicate a new "
        "safety signal? Should this be escalated to the PV team?\n\n"
        f"Drug: {event_record.get('primary_drug', 'N/A')}\n"
        f"Reaction: {event_record.get('primary_reaction', 'N/A')}\n"
        f"Serious: {event_record.get('is_serious', 'N/A')}\n"
        f"Death: {event_record.get('seriousness_death', 'N/A')}\n"
        f"Hospitalization: {event_record.get('seriousness_hospitalization', 'N/A')}\n"
        f"Life-threatening: {event_record.get('seriousness_life_threatening', 'N/A')}\n"
        f"Patient age: {event_record.get('patient_age', 'N/A')} "
        f"{event_record.get('patient_age_unit', '')}\n"
        f"Patient sex: {event_record.get('patient_sex', 'N/A')}\n"
        f"All drugs: {event_record.get('drug_list', 'N/A')}\n"
        f"All reactions: {event_record.get('reaction_list', 'N/A')}\n\n"
        "Analyze from a risk-maximizing PV perspective:\n"
        "1. Could this be an emerging safety signal?\n"
        "2. Is this reaction expected for this drug class?\n"
        "3. Are there drug interaction concerns?\n"
        "4. Should this be escalated for PV team review?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "safety_signal_score": <1-10>,\n'
        '  "signal_classification": "CONFIRMED_SIGNAL|POTENTIAL_SIGNAL|'
        'EXPECTED_REACTION|INSUFFICIENT_DATA",\n'
        '  "escalation_recommendation": "IMMEDIATE|ROUTINE|MONITOR|NONE",\n'
        '  "drug_interaction_concern": true/false,\n'
        '  "vulnerable_population_flag": true/false,\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_clinical_prompt(event_record):
    """
    Build the Clinical Realist prompt (context-aware clinical perspective).

    Args:
        event_record: Normalized adverse event record

    Returns:
        Prompt string
    """
    return (
        "You are a Clinical Realist reviewing this adverse event report. "
        "Your job is to assess the REALISTIC clinical significance. Consider: "
        "Is this reaction expected given the patient demographics and drug "
        "class? Are concomitant medications a more likely cause? Does the "
        "temporal relationship support causality?\n\n"
        f"Drug: {event_record.get('primary_drug', 'N/A')}\n"
        f"Reaction: {event_record.get('primary_reaction', 'N/A')}\n"
        f"Serious: {event_record.get('is_serious', 'N/A')}\n"
        f"Death: {event_record.get('seriousness_death', 'N/A')}\n"
        f"Hospitalization: {event_record.get('seriousness_hospitalization', 'N/A')}\n"
        f"Patient age: {event_record.get('patient_age', 'N/A')} "
        f"{event_record.get('patient_age_unit', '')}\n"
        f"Patient sex: {event_record.get('patient_sex', 'N/A')}\n"
        f"All drugs: {event_record.get('drug_list', 'N/A')}\n"
        f"All reactions: {event_record.get('reaction_list', 'N/A')}\n\n"
        "Analyze from a clinical context perspective:\n"
        "1. Is this reaction expected for this drug class?\n"
        "2. Could concomitant medications explain the reaction?\n"
        "3. Does the patient profile (age, sex) increase expected risk?\n"
        "4. Is this report likely noise or a real clinical signal?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "clinical_risk_score": <1-10>,\n'
        '  "causality_assessment": "CERTAIN|PROBABLE|POSSIBLE|UNLIKELY|'
        'UNASSESSABLE",\n'
        '  "expected_for_drug_class": true/false,\n'
        '  "concomitant_medication_concern": true/false,\n'
        '  "reporting_quality": "HIGH|MEDIUM|LOW",\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_consensus_prompt(event_record, safety_result, clinical_result):
    """
    Build the Consensus synthesizer prompt.

    Args:
        event_record: Normalized adverse event record
        safety_result: Safety Advocate JSON result
        clinical_result: Clinical Realist JSON result

    Returns:
        Prompt string
    """
    return (
        "You are a neutral pharmacovigilance director synthesizing two "
        "expert assessments of the same adverse event. One expert (Safety "
        "Advocate) maximizes risk; the other (Clinical Realist) applies "
        "clinical context. Produce a balanced assessment.\n\n"
        f"Drug: {event_record.get('primary_drug', 'N/A')}\n"
        f"Reaction: {event_record.get('primary_reaction', 'N/A')}\n"
        f"Serious: {event_record.get('is_serious', 'N/A')}\n\n"
        "SAFETY ADVOCATE ASSESSMENT:\n"
        f"{json.dumps(safety_result, indent=2)}\n\n"
        "CLINICAL REALIST ASSESSMENT:\n"
        f"{json.dumps(clinical_result, indent=2)}\n\n"
        "Synthesize:\n"
        "1. Where do they AGREE and DISAGREE?\n"
        "2. Which is MORE PERSUASIVE and why?\n"
        "3. Should this event be escalated for PV review?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "final_severity": "CRITICAL|HIGH|MEDIUM|LOW",\n'
        '  "consensus_risk_score": <1-10>,\n'
        '  "debate_winner": "SAFETY|CLINICAL|DRAW",\n'
        '  "winner_rationale": "...",\n'
        '  "agreement_areas": ["..."],\n'
        '  "disagreement_areas": ["..."],\n'
        '  "disagreement_flag": true/false,\n'
        '  "disagreement_severity": "NONE|MINOR|SIGNIFICANT|FUNDAMENTAL",\n'
        '  "pv_review_recommended": true/false,\n'
        '  "recommended_action": "...",\n'
        '  "executive_summary": "..."\n'
        "}"
    )


def upsert_assessment(table_name, report_id, assessment, assessment_type):
    """
    Upsert an AI assessment record.

    Args:
        table_name: Destination table
        report_id: Safety report identifier
        assessment: Parsed JSON assessment
        assessment_type: Type label

    Returns:
        bool: True if upserted
    """
    if assessment is None:
        log.warning(f"Skipping {assessment_type} for {report_id}: no response")
        return False

    record = flatten_dict(assessment) if assessment else {}
    record["safety_report_id"] = report_id
    record["assessment_type"] = assessment_type

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table_name, data=record)
    return True


def run_multi_agent_debate(session, configuration, events, event_records, state):
    """
    Run Multi-Agent Debate: Safety Advocate vs Clinical Realist for each
    serious adverse event.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        events: List of raw event dictionaries
        event_records: Dict mapping report_id to normalized records
        state: State dict for checkpointing

    Returns:
        Tuple of (debate_count, disagreement_count)
    """
    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    enrichment_count = 0
    disagreement_count = 0

    # Focus debate on serious events
    serious_events = [e for e in events if e.get("serious") == "1"][:max_enrichments]

    log.info(
        f"Starting Multi-Agent Debate for {len(serious_events)} "
        f"serious events (3 ai_query() calls each)"
    )

    for event in serious_events:
        if enrichment_count >= max_enrichments:
            log.info(f"Reached max_enrichments ({max_enrichments})")
            break

        report_id = event.get("safetyreportid")
        record = event_records.get(report_id)
        if not record:
            continue

        # Agent 1: Safety Advocate
        safety_content = call_ai_query(session, configuration, build_safety_prompt(record))
        safety_result = extract_json_from_content(safety_content)
        upsert_assessment("safety_assessments", report_id, safety_result, "safety")

        # Agent 2: Clinical Realist
        clinical_content = call_ai_query(session, configuration, build_clinical_prompt(record))
        clinical_result = extract_json_from_content(clinical_content)
        upsert_assessment("clinical_assessments", report_id, clinical_result, "clinical")

        # Agent 3: Consensus
        if safety_result and clinical_result:
            consensus_content = call_ai_query(
                session,
                configuration,
                build_consensus_prompt(record, safety_result, clinical_result),
            )
            consensus_result = extract_json_from_content(consensus_content)
            upsert_assessment("debate_consensus", report_id, consensus_result, "consensus")

            if consensus_result and consensus_result.get("disagreement_flag"):
                disagreement_count += 1
        else:
            log.warning(f"Skipping consensus for {report_id}: missing assessment")

        enrichment_count += 1

        # Save the progress by checkpointing the state. This is important for ensuring that the
        # sync process can resume from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
        # it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

    return enrichment_count, disagreement_count


def create_genie_space(session, configuration, state):
    """
    Create a Databricks Genie Space for pharmacovigilance analytics.

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
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    serialized = {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": uuid.uuid4().hex, "question": q} for q in __GENIE_SPACE_SAMPLE_QUESTIONS
            ]
        },
        "data_sources": {"tables": [{"identifier": table_id}]},
        "instructions": {
            "text_instructions": [{"id": uuid.uuid4().hex, "content": __GENIE_SPACE_INSTRUCTIONS}]
        },
    }

    payload = {
        "warehouse_id": warehouse_id,
        "title": "FDA FAERS Pharmacovigilance Intelligence",
        "description": (
            "AI-enriched FDA adverse event data with multi-agent "
            "debate analysis. Powered by Fivetran + Databricks."
        ),
        "serialized_space": json.dumps(serialized),
    }

    try:
        resp = session.post(
            url,
            headers=headers,
            json=payload,
            timeout=_optional_int(
                configuration, "databricks_timeout", __DEFAULT_DATABRICKS_TIMEOUT
            ),
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
    Define the update function, which is a required function, and is called by Fivetran during
    each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: all_things_ai/tutorials : databricks-fm-fda-faers-pv-intelligence")

    validate_configuration(configuration)

    max_events = _optional_int(configuration, "max_events", __DEFAULT_MAX_EVENTS)
    is_enrichment = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie = _parse_bool(configuration.get("enable_genie_space"), default=False)
    search_drug = _optional_str(configuration, "search_drug")
    lookback_days = _optional_int(configuration, "lookback_days", __DEFAULT_LOOKBACK_DAYS)

    if is_enrichment:
        model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)
        max_enrichments = _optional_int(
            configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS
        )
        log.info(f"Multi-Agent Debate ENABLED: model={model}, max_enrichments={max_enrichments}")
    else:
        log.info("Multi-Agent Debate DISABLED")

    # Compound cursor: (last_receive_date, last_safety_report_id).
    # The OpenFDA receivedate range filter is inclusive, so when more than
    # max_events records exist on a given date the next sync re-receives
    # the same records. We dedupe via the (date, id) tuple — see
    # databricks-fm-fda-drug-label-intelligence/connector.py for the
    # canonical version of this pattern (PR #567 Codex P1 fix).
    last_receive_date = state.get("last_receive_date")
    last_safety_report_id = state.get("last_safety_report_id")
    if last_receive_date:
        start_date = last_receive_date
    else:
        start_dt = datetime.now() - timedelta(days=lookback_days)
        start_date = start_dt.strftime("%Y%m%d")

    end_date = datetime.now().strftime("%Y%m%d")

    search_query = _build_search_query(start_date, end_date, search_drug)

    log.info(f"Fetching events: {search_query}")

    session = create_session()

    try:
        # --- Phase 1: MOVE ---
        log.info("Phase 1 (MOVE): Fetching adverse events from OpenFDA FAERS")

        events, total, cap_hit = fetch_all_events(session, search_query, max_events)
        log.info(f"OpenFDA reports {total} matching events, fetched {len(events)}")

        if cap_hit:
            log.info(
                f"Reached max_events ({max_events}) of {total} matching "
                f"events; remaining records will be picked up on subsequent "
                f"syncs via the (receivedate, safety_report_id) cursor."
            )

        if not events:
            log.info("No adverse events found")
            # Save the progress by checkpointing the state. This is important for ensuring that
            # the sync process can resume from the correct position in case of next sync or
            # interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells
            # Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices
            # documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            return

        # Upsert event records, skipping any whose compound cursor tuple
        # (receivedate, safety_report_id) is at or below the last cursor.
        # OpenFDA's range filter is inclusive on the lower bound, so the
        # API will always re-emit records dated last_receive_date — the
        # tuple comparison is what guarantees no duplicates.
        event_records = {}
        latest_date = last_receive_date
        latest_id = last_safety_report_id
        skipped = 0

        cursor_tuple = (last_receive_date or "", last_safety_report_id or "")
        latest_tuple = cursor_tuple

        for event in events:
            report_id = event.get("safetyreportid")
            if not report_id:
                continue

            recv_date = event.get("receivedate", "")
            if not recv_date:
                continue

            event_tuple = (recv_date, report_id)
            # OpenFDA's range filter is inclusive, so the API will re-emit
            # records dated last_receive_date. Skip every event whose
            # (date, id) tuple is at or below the cursor — that covers
            # both "earlier date" and "same date, already-synced id".
            if last_receive_date is not None and event_tuple <= cursor_tuple:
                skipped += 1
                continue

            record = build_event_record(event)
            flattened = flatten_dict(record)

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="adverse_events", data=flattened)

            event_records[report_id] = record

            if event_tuple > latest_tuple:
                latest_tuple = event_tuple

        latest_date, latest_id = latest_tuple

        log.info(
            f"Phase 1 complete: {len(event_records)} events upserted, "
            f"{skipped} skipped as already synced"
        )

        if latest_date:
            state["last_receive_date"] = latest_date
        if latest_id:
            state["last_safety_report_id"] = latest_id

        # Save the progress by checkpointing the state. This is important for ensuring that the
        # sync process can resume from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
        # it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # --- Phase 2: DEBATE ---
        if is_enrichment and event_records:
            log.info("Phase 2 (DEBATE): Starting Multi-Agent Debate")
            debate_count, disagreement_count = run_multi_agent_debate(
                session, configuration, events, event_records, state
            )
            log.info(
                f"Debate complete: {debate_count} events debated, "
                f"{disagreement_count} with disagreement flags"
            )

        # --- Phase 3: AGENT ---
        if is_genie:
            log.info("Phase 3 (AGENT): Creating Genie Space")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
                # Save the progress by checkpointing the state. This is important for ensuring
                # that the sync process can resume from the correct position in case of next sync
                # or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells
                # Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the
                # end.
                # Learn more about how and where to checkpoint by reading our best practices
                # documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)

        # Final checkpoint
        # Save the progress by checkpointing the state. This is important for ensuring that the
        # sync process can resume from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
        # it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info(f"Sync complete: {len(event_records)} events synced")

    except (
        RuntimeError,
        ValueError,
        requests.exceptions.RequestException,
        json.JSONDecodeError,
    ) as e:
        log.severe(f"Sync failed: {str(e)}")
        raise

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
