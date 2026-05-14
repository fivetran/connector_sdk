"""
Databricks FDA Drug Label Intelligence Connector - Syncs drug labeling data from the
OpenFDA Drug Labeling API, enriches each label with AI analysis using Databricks
ai_query() SQL function, and creates a Genie Space for natural language analytics.

This connector demonstrates the full Fivetran data lifecycle on Databricks:
  - MOVE: Fetch drug labels from the free OpenFDA API
  - TRANSFORM: Enrich each label with AI analysis via Databricks ai_query() SQL function
  - AGENT: Create a Genie Space so analysts can query enriched drug data in natural language

AI enrichment uses ai_query() through the Databricks SQL Statement Execution API,
which runs on the SQL Warehouse. This avoids the need for a separate Foundation Model
serving endpoint and works with any PAT that has SQL execution permissions.

The optional Genie Space is created after data lands, configured with pharma-specific
instructions and sample questions so analysts can immediately ask questions like
"Which drugs have HIGH interaction risk and a black box warning?"

This is the first Databricks AI tutorial connector in the Fivetran SDK repository,
demonstrating destination-agnostic AI enrichment patterns.

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

# OpenFDA API Configuration Constants
__BASE_URL_FDA = "https://api.fda.gov/drug/label.json"
__API_TIMEOUT_SECONDS = 30

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__FDA_RATE_LIMIT_DELAY = 0.25

# Default Configuration Values
__DEFAULT_MAX_LABELS = 25
__DEFAULT_BATCH_SIZE = 5
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120
__DEFAULT_MAX_ENRICHMENTS = 25

# Databricks SQL Statement API Configuration
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"
__DATABRICKS_RATE_LIMIT_DELAY = 0.5

# Genie Space API Configuration
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Enrichment prompt truncation limit (drug label text can be very long)
__MAX_LABEL_TEXT_CHARS = 3000

# Sanity ceiling for user-configurable limits
__MAX_LABELS_CEILING = 500
__MAX_ENRICHMENTS_CEILING = 500

# Genie Space instructions and sample questions for drug label analytics
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a pharmaceutical drug label intelligence agent. This dataset "
    "contains FDA drug labeling data enriched with AI-powered analysis. "
    "Each record represents a drug label (package insert) with fields for "
    "brand name, generic name, manufacturer, therapeutic category, "
    "drug interaction risk level (HIGH/MEDIUM/LOW), contraindication "
    "summaries, black box warning status, and patient-friendly descriptions. "
    "When answering questions, prioritize patient safety insights and "
    "clearly distinguish between HIGH, MEDIUM, and LOW risk drugs. "
    "Use the enrichment fields (interaction_risk_level, therapeutic_category, "
    "has_black_box_warning) for filtering and the summary fields for context."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which drugs have HIGH interaction risk and a black box warning?",
    "Show me all cardiovascular drugs sorted by interaction risk level",
    "What are the most common therapeutic categories in this dataset?",
    "List drugs with contraindications and their patient-friendly descriptions",
    "Which manufacturers have the most drugs with black box warnings?",
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
    Check if a configuration value is unset or an angle-bracket placeholder.

    Type-safe: returns False for non-strings (bool/int/float) so this helper
    can be called on any config value without risking AttributeError.
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
    Parse a boolean-like config value. Accepts bool directly, "true"/"false"
    strings (case-insensitive), and None/placeholders (returns default).

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
    Read an optional int config value, treating placeholders/None as unset.

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
    Read an optional string config value, treating placeholders/None as unset.

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
    Validate the configuration dictionary to ensure all required parameters
    are present and valid.

    Args:
        configuration: a dictionary that holds the configuration settings
            for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing
            or invalid.
    """
    # Validate numeric parameters if present
    numeric_params = {
        "max_labels": "max_labels must be a positive integer",
        "batch_size": "batch_size must be a positive integer",
        "max_enrichments": "max_enrichments must be a positive integer",
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
    max_labels = _optional_int(configuration, "max_labels", __DEFAULT_MAX_LABELS)
    if max_labels > __MAX_LABELS_CEILING:
        raise ValueError(
            f"max_labels={max_labels} exceeds the connector ceiling of "
            f"{__MAX_LABELS_CEILING}. Run multiple smaller syncs instead."
        )

    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    if max_enrichments > __MAX_ENRICHMENTS_CEILING:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds the ceiling of "
            f"{__MAX_ENRICHMENTS_CEILING}. Run multiple smaller syncs."
        )

    # Validate Databricks credentials when enrichment or Genie is enabled
    is_enrichment_enabled = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie_enabled = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment_enabled or is_genie_enabled:
        for key in ["databricks_workspace_url", "databricks_token"]:
            if _is_placeholder(configuration.get(key)):
                raise ValueError(f"Missing required Databricks config: {key}")

        workspace_url = configuration.get("databricks_workspace_url", "")
        if not workspace_url.startswith("https://"):
            raise ValueError(
                "databricks_workspace_url must start with 'https://' "
                "(e.g., 'https://dbc-xxxxx.cloud.databricks.com'). "
                f"Got: {workspace_url}"
            )

    if is_enrichment_enabled:
        if _is_placeholder(configuration.get("databricks_warehouse_id")):
            raise ValueError("databricks_warehouse_id is required for ai_query() " "enrichment")

    if is_genie_enabled:
        if _is_placeholder(configuration.get("databricks_warehouse_id")):
            raise ValueError("databricks_warehouse_id is required for Genie Space " "creation")
        if _is_placeholder(configuration.get("genie_table_identifier")):
            raise ValueError(
                "genie_table_identifier is required for Genie Space "
                "creation (format: catalog.schema.table)"
            )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your
    connector delivers.
    See the technical reference documentation for more details on the
    schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings
            for the connector.
    """
    return [
        {
            "table": "drug_labels_enriched",
            "primary_key": ["label_id"],
            "columns": {
                "label_id": "STRING",
            },
        }
    ]


def create_session():
    """
    Create a requests session with a descriptive User-Agent header.

    Returns:
        requests.Session configured for OpenFDA and Databricks API requests
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Fivetran-FDA-DrugLabel-Databricks-Connector/2.0"})
    return session


def fetch_data_with_retry(session, url, params=None, headers=None):
    """
    Fetch data from API with exponential backoff retry logic.

    Args:
        session: requests.Session object for connection pooling
        url: Full URL to fetch
        params: Optional query parameters
        headers: Optional request headers

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
                headers=headers,
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
                log.error(f"Connection failed after {__MAX_RETRIES} " f"attempts: {url}")
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
                log.error(f"Timeout after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )

            if status_code in (401, 403):
                msg = f"HTTP {status_code}: Check your API credentials " f"and scopes. URL: {url}"
                log.error(msg)
                raise RuntimeError(msg) from e

            should_retry = status_code in __RETRYABLE_STATUS_CODES

            if should_retry and attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Request failed with status {status_code}, "
                    f"retrying in {delay}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay)
            else:
                attempts = attempt + 1
                log.error(
                    f"Request failed after {attempts} attempt(s). "
                    f"URL: {url}, "
                    f"Status: {status_code or 'N/A'}, "
                    f"Error: {str(e)}"
                )
                raise RuntimeError(
                    f"API request failed after {attempts} " f"attempt(s): {e}"
                ) from e


def truncate_text(text, max_chars):
    """
    Truncate text to a maximum character count with ellipsis indicator.

    Drug label sections can be extremely long (10K+ chars). This ensures
    prompts sent via ai_query() stay within token limits.

    Args:
        text: Text string to truncate
        max_chars: Maximum character count

    Returns:
        Truncated string with ellipsis if truncated, or original string
    """
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars] + "... [truncated]"


def extract_label_text_sections(label):
    """
    Extract key text sections from an OpenFDA drug label record.

    Drug labels have dozens of sections. We extract the ones most relevant
    for AI enrichment: drug interactions, contraindications, boxed warnings,
    indications, and drug name.

    Args:
        label: OpenFDA drug label record dictionary

    Returns:
        Dictionary with extracted text sections (may be empty strings)
    """

    def get_first(field_list):
        """Extract first element from OpenFDA array fields."""
        if isinstance(field_list, list) and field_list:
            return field_list[0]
        return ""

    return {
        "drug_name": get_first(label.get("openfda", {}).get("brand_name", [])),
        "generic_name": get_first(label.get("openfda", {}).get("generic_name", [])),
        "drug_interactions": get_first(label.get("drug_interactions", [])),
        "contraindications": get_first(label.get("contraindications", [])),
        "boxed_warning": get_first(label.get("boxed_warning", [])),
        "indications_and_usage": get_first(label.get("indications_and_usage", [])),
        "warnings": get_first(label.get("warnings", [])),
    }


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() SQL function via the SQL Statement API.

    Executes a SQL statement that uses the ai_query() function to call
    a Foundation Model through the SQL Warehouse. This avoids the need
    for a separate model serving endpoint and works with any PAT that
    has SQL execution permissions.

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
    timeout = _optional_int(configuration, "databricks_timeout", __DEFAULT_DATABRICKS_TIMEOUT)

    url = f"{workspace_url}{__SQL_STATEMENT_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Escape single quotes in prompt for SQL string literal
    escaped_prompt = prompt.replace("'", "''")

    statement = f"SELECT ai_query('{model}', '{escaped_prompt}') as response"

    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": __SQL_WAIT_TIMEOUT,
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()

        result = response.json()
        state = result.get("status", {}).get("state", "")

        # Poll for PENDING/RUNNING statements that exceed the
        # SQL wait timeout (large enrichment prompts).
        # Pre-poll guard: when state is PENDING/RUNNING the initial response
        # is structurally allowed to omit statement_id. Polling f"{url}/None"
        # silently 404s 12 times before giving up; the failure mode is invisible.
        # Surface it instead. Same fix shape as PR #570 NOAA.
        statement_id = result.get("statement_id")
        if state in ("PENDING", "RUNNING") and not statement_id:
            log.warning(
                f"ai_query() returned state={state} without a statement_id; "
                "cannot poll. Returning None."
            )
            return None

        poll_count = 0
        max_polls = 12
        poll_interval_seconds = 10

        while state in ("PENDING", "RUNNING") and poll_count < max_polls:
            poll_count += 1
            time.sleep(poll_interval_seconds)
            poll_url = f"{url}/{statement_id}"
            poll_resp = session.get(poll_url, headers=headers, timeout=timeout)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/{max_polls}: {state}")

        if state == "SUCCEEDED":
            data_array = result.get("result", {}).get("data_array", [])
            if data_array and data_array[0]:
                return data_array[0][0]
        elif state == "FAILED":
            error = result.get("status", {}).get("error", {})
            log.warning(f"ai_query() failed: {error.get('message', 'Unknown')}")
        else:
            log.warning(f"ai_query() final state: {state}")

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
    Extract a JSON object from a string that may contain surrounding text.

    LLM responses often include explanatory text around the JSON. This
    function finds and parses the JSON portion.

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


def enrich_drug_label(session, configuration, sections):
    """
    Orchestrate Databricks ai_query() enrichment for a single drug label.

    Sends a single comprehensive prompt via ai_query() that extracts all
    enrichment fields at once, minimizing SQL Warehouse compute.

    Args:
        session: requests.Session object for connection pooling
        configuration: Configuration dictionary with Databricks settings
        sections: Dictionary of extracted label text sections

    Returns:
        Tuple of (enrichment_dict, success_flag). The dict is always
        returned so the destination columns are populated (NULL on
        failure); the flag is True only when ai_query() returned a
        parseable JSON response. Callers should only count successful
        enrichments against the budget.
    """
    model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)

    enrichment = {
        "interaction_risk_level": None,
        "contraindication_summary": None,
        "has_black_box_warning": None,
        "black_box_summary": None,
        "patient_friendly_description": None,
        "therapeutic_category": None,
        "enrichment_model": model,
    }

    drug_name = sections.get("drug_name", "Unknown")
    generic_name = sections.get("generic_name", "")
    interactions = truncate_text(sections.get("drug_interactions", ""), __MAX_LABEL_TEXT_CHARS)
    contraindications = truncate_text(
        sections.get("contraindications", ""), __MAX_LABEL_TEXT_CHARS
    )
    boxed_warning = truncate_text(sections.get("boxed_warning", ""), __MAX_LABEL_TEXT_CHARS)
    indications = truncate_text(sections.get("indications_and_usage", ""), __MAX_LABEL_TEXT_CHARS)

    prompt = (
        "Analyze this FDA drug label and respond ONLY with a JSON "
        "object in this exact format. No text outside the JSON.\n\n"
        "{\n"
        '  "interaction_risk_level": "HIGH or MEDIUM or LOW",\n'
        '  "contraindication_summary": "Plain-English summary of key '
        'contraindications (2-3 sentences max)",\n'
        '  "has_black_box_warning": true or false,\n'
        '  "black_box_summary": "Summary of boxed warning if present, '
        'or null if none",\n'
        '  "patient_friendly_description": "What this drug does and '
        'what it treats, written for a patient (2-3 sentences)",\n'
        '  "therapeutic_category": "e.g., Cardiovascular, Oncology, '
        "Neurology, Immunology, Infectious Disease, Endocrine, "
        'Respiratory, Psychiatry, Pain Management, Other"\n'
        "}\n\n"
        f"Drug Name: {drug_name}\n"
        f"Generic Name: {generic_name}\n\n"
        f"Indications and Usage:\n{indications}\n\n"
        f"Drug Interactions:\n{interactions}\n\n"
        f"Contraindications:\n{contraindications}\n\n"
        f"Boxed Warning:\n{boxed_warning}\n\n"
        "JSON:"
    )

    content = call_ai_query(session, configuration, prompt)
    result = extract_json_from_content(content)
    success = bool(result) and isinstance(result, dict)

    if success:
        enrichment["interaction_risk_level"] = result.get("interaction_risk_level")
        enrichment["contraindication_summary"] = result.get("contraindication_summary")
        has_bbw = result.get("has_black_box_warning")
        if isinstance(has_bbw, bool):
            enrichment["has_black_box_warning"] = has_bbw
        enrichment["black_box_summary"] = result.get("black_box_summary")
        enrichment["patient_friendly_description"] = result.get("patient_friendly_description")
        enrichment["therapeutic_category"] = result.get("therapeutic_category")

    time.sleep(__DATABRICKS_RATE_LIMIT_DELAY)
    return enrichment, success


def build_label_record(label, label_id):
    """
    Build a normalized record from a raw OpenFDA drug label.

    Extracts the most useful fields from the complex OpenFDA label
    structure into a flat record suitable for analytics.

    Args:
        label: Raw OpenFDA drug label dictionary
        label_id: Unique identifier for this label

    Returns:
        Dictionary with normalized label fields
    """
    openfda = label.get("openfda", {})

    def get_first(field_list):
        """Extract first element from OpenFDA array fields."""
        if isinstance(field_list, list) and field_list:
            return field_list[0]
        return None

    def get_list_as_json(field_list):
        """Serialize OpenFDA array fields to JSON strings."""
        if isinstance(field_list, list) and field_list:
            return json.dumps(field_list)
        return None

    return {
        "label_id": label_id,
        "set_id": label.get("set_id"),
        "version": label.get("version"),
        "effective_time": label.get("effective_time"),
        "brand_name": get_first(openfda.get("brand_name", [])),
        "generic_name": get_first(openfda.get("generic_name", [])),
        "manufacturer_name": get_first(openfda.get("manufacturer_name", [])),
        "product_type": get_first(openfda.get("product_type", [])),
        "route": get_list_as_json(openfda.get("route", [])),
        "substance_name": get_list_as_json(openfda.get("substance_name", [])),
        "rxcui": get_list_as_json(openfda.get("rxcui", [])),
        "spl_id": get_first(openfda.get("spl_id", [])),
        "application_number": get_first(openfda.get("application_number", [])),
        "pharm_class_epc": get_list_as_json(openfda.get("pharm_class_epc", [])),
        "has_drug_interactions": bool(label.get("drug_interactions")),
        "has_contraindications": bool(label.get("contraindications")),
        "has_boxed_warning": bool(label.get("boxed_warning")),
        "has_warnings": bool(label.get("warnings")),
    }


def fetch_labels_page(session, skip, limit, effective_date_filter=None):
    """
    Fetch a page of drug labels from the OpenFDA API.

    Args:
        session: requests.Session object for connection pooling
        skip: Number of records to skip (pagination offset)
        limit: Number of records to return per page
        effective_date_filter: Optional date filter for incremental sync

    Returns:
        Tuple of (results_list, total_count) from the API response

    Raises:
        RuntimeError: If the API request fails after all retry attempts
    """
    params = {"limit": limit, "skip": skip}

    # OpenFDA search syntax uses brackets and + signs that must NOT be
    # percent-encoded. Build the URL manually when a search filter is
    # present to avoid requests double-encoding these characters.
    # Sort ascending by (effective_time, id) so the cursor advances
    # deterministically. Required for the (last_effective_time, last_label_id)
    # compound cursor to skip already-synced records reliably across syncs.
    if effective_date_filter:
        search_param = f"effective_time:{effective_date_filter}"
        url = f"{__BASE_URL_FDA}?search={search_param}&sort=effective_time:asc"
        data = fetch_data_with_retry(session, url, params=params)
    else:
        params = dict(params)
        params["sort"] = "effective_time:asc"
        data = fetch_data_with_retry(session, __BASE_URL_FDA, params=params)

    results = data.get("results", [])
    total = data.get("meta", {}).get("results", {}).get("total", 0)
    return results, total


def build_label_id(label):
    """Stable, deterministic identifier for a drug label.

    Combines set_id + version when present; falls back to label.id, then to
    a hash of the raw payload. Used as both the destination primary key
    and the secondary key on the (effective_time, label_id) compound
    cursor that drives incremental sync.
    """
    set_id = label.get("set_id", "")
    version = label.get("version", "")
    if set_id:
        return f"{set_id}_{version}"
    return label.get("id", str(hash(str(label))))


def process_batch(
    session,
    configuration,
    labels,
    is_enrichment_enabled,
    enriched_count,
    max_enrichments,
    last_effective_time=None,
    last_label_id=None,
):
    """
    Process a batch of drug labels: build records, enrich, and upsert.

    Skips records already synced according to the compound
    (effective_time, label_id) cursor. The OpenFDA `[X+TO+Y]` filter is
    inclusive on the lower bound, so without this skip a sync that hit
    `max_labels` mid-day would re-process the same records on the next
    sync (and loop indefinitely if a single day exceeds `max_labels`).

    Args:
        session: requests.Session object for connection pooling
        configuration: Configuration dictionary
        labels: List of raw OpenFDA drug label dictionaries
            (assumed sorted asc by effective_time then label_id)
        is_enrichment_enabled: Whether ai_query() enrichment is active
        enriched_count: Current count of enrichments performed
        max_enrichments: Maximum enrichments allowed per sync
        last_effective_time: Cursor lower-bound effective_time from state
        last_label_id: Cursor lower-bound label_id from state (tie-break
            within the same effective_time)

    Returns:
        Tuple of (synced_count, enriched_count, latest_effective_time,
        latest_label_id). The two latest_* values together form the
        compound cursor saved to state.
    """
    synced_count = 0
    latest_effective_time = None
    latest_label_id = None

    for label in labels:
        label_id = build_label_id(label)
        effective_time = label.get("effective_time", "")

        # Skip records already synced (compound cursor comparison).
        # OpenFDA's date filter is inclusive on the lower bound, so the
        # first batch of records on the cursor day will be re-fetched
        # every sync — they must be filtered out client-side.
        if last_effective_time is not None and last_label_id is not None:
            if (effective_time, label_id) <= (last_effective_time, last_label_id):
                continue

        # Build normalized record
        record = build_label_record(label, label_id)

        # Track the highest (effective_time, label_id) processed in this
        # batch. With server-side asc sort, this is the last record we
        # see — but we compare anyway to be defensive against unsorted
        # responses.
        if latest_effective_time is None or (  # noqa: W503
            effective_time,
            label_id,
        ) > (  # noqa: W503
            latest_effective_time,
            latest_label_id or "",
        ):  # noqa: W503
            latest_effective_time = effective_time
            latest_label_id = label_id

        # Enrich with ai_query() if enabled and within budget
        if is_enrichment_enabled and enriched_count < max_enrichments:  # noqa: W503  # noqa: W503
            sections = extract_label_text_sections(label)
            has_content = any(
                sections.get(key)
                for key in [
                    "drug_interactions",
                    "contraindications",
                    "indications_and_usage",
                ]
            )
            if has_content:
                enrichment, enrichment_ok = enrich_drug_label(session, configuration, sections)
                record.update(enrichment)
                # Only count toward the budget when ai_query() returned
                # parseable JSON; failed calls leave enrichment columns
                # NULL but do not consume the user's enrichment quota.
                if enrichment_ok:
                    enriched_count += 1

        # Flatten any remaining nested structures
        flattened = flatten_dict(record)

        # The 'upsert' operation is used to insert or update data
        # in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record
        # to be upserted.
        op.upsert(table="drug_labels_enriched", data=flattened)

        synced_count += 1

    return synced_count, enriched_count, latest_effective_time, latest_label_id


def create_genie_space(session, configuration, state):
    """
    Create a Databricks Genie Space for the enriched drug label data.

    Uses the Databricks Genie REST API to create a space configured with
    pharma-specific instructions and sample questions, pointed at the
    destination table containing enriched drug labels.

    The Genie Space is only created once. The space_id is persisted in
    state to avoid creating duplicates on subsequent syncs.

    Args:
        session: requests.Session object for connection pooling
        configuration: Configuration dictionary with Databricks settings
        state: State dictionary for persisting the space_id

    Returns:
        Space ID string if created, or existing space_id from state
    """
    # Skip if Genie Space already created
    existing_space_id = state.get("genie_space_id")
    if existing_space_id:
        log.info(f"Genie Space already exists: {existing_space_id}")
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

    # Build the serialized_space payload matching Databricks format
    serialized = {
        "version": 2,
        "config": {
            "sample_questions": [
                {
                    "id": uuid.uuid4().hex,
                    "question": [q],
                }
                for q in __GENIE_SPACE_SAMPLE_QUESTIONS
            ]
        },
        "data_sources": {"tables": [{"identifier": table_identifier}]},
        "instructions": {
            "text_instructions": [
                {
                    "id": uuid.uuid4().hex,
                    "content": [__GENIE_SPACE_INSTRUCTIONS],
                }
            ]
        },
    }

    payload = {
        "warehouse_id": warehouse_id,
        "title": "FDA Drug Label Intelligence",
        "description": (
            "AI-enriched FDA drug labeling data with interaction "
            "risk levels, contraindication summaries, black box "
            "warning detection, and therapeutic categorization. "
            "Powered by Fivetran + Databricks."
        ),
        "serialized_space": json.dumps(serialized),
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        space_id = result.get("space_id")

        if space_id:
            log.info(f"Genie Space created: {space_id} " f"(title: FDA Drug Label Intelligence)")
            return space_id
        else:
            log.warning("Genie Space creation returned no space_id")
            return None

    except requests.exceptions.HTTPError as e:
        log.warning(f"Genie Space creation HTTP error: {str(e)}")
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
    log.warning("Example: all_things_ai/tutorials : " "databricks-fm-fda-drug-label-intelligence")

    # Validate the configuration
    validate_configuration(configuration)

    # Read configuration with defaults
    max_labels = _optional_int(configuration, "max_labels", __DEFAULT_MAX_LABELS)
    batch_size = _optional_int(configuration, "batch_size", __DEFAULT_BATCH_SIZE)
    is_enrichment_enabled = _parse_bool(configuration.get("enable_enrichment"), default=True)
    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    is_genie_enabled = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment_enabled:
        model = _optional_str(
            configuration,
            "databricks_model",
            __DEFAULT_DATABRICKS_MODEL,
        )
        log.info(
            f"Databricks ai_query() enrichment ENABLED: "
            f"model={model}, max_enrichments={max_enrichments}"
        )
    else:
        log.info("Databricks ai_query() enrichment DISABLED")

    if is_genie_enabled:
        log.info("Genie Space creation ENABLED")

    # Retrieve state for incremental sync. The cursor is compound
    # (effective_time, label_id) so we can skip records already synced
    # within a partially-completed day on the next run.
    last_effective_time = state.get("last_effective_time")
    last_label_id = state.get("last_label_id")
    log.info(
        f"Last synced cursor: effective_time={last_effective_time}, " f"label_id={last_label_id}"
    )

    # Build date filter for incremental sync
    effective_date_filter = None
    if last_effective_time:
        effective_date_filter = f"[{last_effective_time}+TO+20991231]"

    # Create session for connection pooling
    session = create_session()

    try:
        # --- Phase 1: MOVE --- Fetch drug labels from OpenFDA
        log.info("Phase 1 (MOVE): Fetching drug labels from OpenFDA")
        results, total = fetch_labels_page(
            session,
            skip=0,
            limit=min(batch_size, max_labels),
            effective_date_filter=effective_date_filter,
        )

        log.info(f"OpenFDA reports {total} total matching labels")

        if not results:
            log.info("No new drug labels to sync")
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
            return

        # --- Phase 2: TRANSFORM --- Enrich and upsert labels
        log.info("Phase 2 (TRANSFORM): Enriching and upserting labels")
        total_synced = 0
        enriched_count = 0
        overall_latest_time = last_effective_time
        overall_latest_label_id = last_label_id
        skip = 0

        while total_synced < max_labels:
            if skip > 0:
                page_size = min(batch_size, max_labels - total_synced)
                results, _ = fetch_labels_page(
                    session,
                    skip=skip,
                    limit=page_size,
                    effective_date_filter=effective_date_filter,
                )

            if not results:
                break

            batch_num = (skip // batch_size) + 1
            log.info(f"Processing batch {batch_num} " f"({len(results)} labels)")

            synced, enriched_count, latest_time, latest_label_id = process_batch(
                session,
                configuration,
                results,
                is_enrichment_enabled,
                enriched_count,
                max_enrichments,
                last_effective_time=overall_latest_time,
                last_label_id=overall_latest_label_id,
            )

            total_synced += synced
            skip += len(results)

            # Advance the compound cursor only if this batch produced a
            # strictly greater (effective_time, label_id) tuple.
            if latest_time and latest_label_id:
                if overall_latest_time is None or (latest_time, latest_label_id) > (
                    overall_latest_time,
                    overall_latest_label_id or "",
                ):
                    overall_latest_time = latest_time
                    overall_latest_label_id = latest_label_id

            if overall_latest_time:
                state["last_effective_time"] = overall_latest_time
                state["last_label_id"] = overall_latest_label_id

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
                f"Checkpointed at cursor: effective_time="
                f"{overall_latest_time}, label_id="
                f"{overall_latest_label_id}"
            )

            if total_synced >= max_labels or len(results) < batch_size:  # noqa: W503  # noqa: W503
                break

            time.sleep(__FDA_RATE_LIMIT_DELAY)

        log.info(
            f"Sync complete: {total_synced} labels synced, "
            f"{enriched_count} enriched with ai_query()"
        )

        # --- Phase 3: AGENT --- Create Genie Space
        if is_genie_enabled and total_synced > 0:
            log.info("Phase 3 (AGENT): Creating Genie Space for " "drug label analytics")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
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

    except Exception as e:
        log.error(f"Unexpected error during sync: {str(e)}")
        raise

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be
# run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the
# Fivetran debug command:
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
