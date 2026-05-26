"""
FHIR R4 Healthcare Intelligence Connector

Syncs clinical data from a FHIR R4 server and enriches it with
AI-powered hybrid analysis using Databricks ai_query():
  - Discovery: AI identifies at-risk patient populations and
    related conditions to investigate
  - Debate: Clinical Risk Analyst vs Resource Allocation Analyst
    debate intervention priorities for high-risk patients
  - Genie Space: Natural language clinical analytics

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

# For timestamp generation on final checkpoint
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

# FHIR API Configuration Constants
__BASE_URL_FHIR = "https://hapi.fhir.org/baseR4"
__API_TIMEOUT_SECONDS = 30
__FHIR_ACCEPT_HEADER = "application/fhir+json"
__FHIR_RATE_LIMIT_DELAY = 0.1

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

# Default Configuration Values
__DEFAULT_MAX_PATIENTS = 20
__DEFAULT_MAX_ENRICHMENTS = 5
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120
__DEFAULT_PAGE_SIZE = 50
__DEFAULT_CONDITION_FILTER = ""

# Databricks SQL Statement API
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"

# Genie Space API
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Sanity ceilings
__MAX_PATIENTS_CEILING = 500
__MAX_ENRICHMENTS_CEILING = 20

# Per-patient resource fetch cap (prevents unbounded memory on large histories)
__MAX_RESOURCES_PER_PATIENT = 100

# Genie Space configuration
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a population health intelligence agent. This dataset contains "
    "FHIR R4 clinical data enriched with AI-powered hybrid analysis: "
    "agent-driven discovery of at-risk patient populations, plus multi-agent "
    "debate between a Clinical Risk Analyst and a Resource Allocation Analyst. "
    "The disagreement_flag identifies patients where the analysts significantly "
    "disagreed on intervention priority. Use patients, conditions, observations, "
    "and medications for clinical data; population_insights for cohort risk "
    "analysis; and clinical_assessments, resource_assessments, debate_consensus "
    "for AI-recommended intervention levels."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which diabetic patients have an A1C above 9 and haven't been seen in 90 days?",
    "Show me patients with the highest readmission risk and recommended interventions",
    "What preventive screenings are overdue for patients over 65?",
    "Which patients have disagreement flags between the clinical and resource analysts?",
    "List patients where the debate winner was the clinical risk analyst",
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
    Type-safe for non-strings.
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
    Read an optional string config value, treating placeholders as unset.

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
    Validate the configuration dictionary to ensure all required parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    # Validate numeric parameters
    for param in ["max_patients", "max_enrichments"]:
        value = configuration.get(param)
        if value is not None and not _is_placeholder(value):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{param} must be a positive integer")
            if parsed < 1:
                raise ValueError(f"{param} must be a positive integer")

    # Enforce ceilings
    max_patients = _optional_int(configuration, "max_patients", __DEFAULT_MAX_PATIENTS)
    if max_patients > __MAX_PATIENTS_CEILING:
        raise ValueError(
            f"max_patients={max_patients} exceeds ceiling of {__MAX_PATIENTS_CEILING}."
        )

    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    if max_enrichments > __MAX_ENRICHMENTS_CEILING:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds ceiling of {__MAX_ENRICHMENTS_CEILING}."
        )

    # Validate FHIR base URL if provided
    fhir_url = _optional_str(configuration, "fhir_base_url", __BASE_URL_FHIR)
    if fhir_url and not (
        fhir_url.startswith("https://") or fhir_url.startswith("http://")  # noqa: W503
    ):
        raise ValueError(f"fhir_base_url must start with 'http://' or 'https://'. Got: {fhir_url}")

    # Validate Databricks credentials when enrichment is enabled
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

        workspace_url = configuration.get("databricks_workspace_url", "")
        if not workspace_url.startswith("https://"):
            raise ValueError(
                f"databricks_workspace_url must start with 'https://'. Got: {workspace_url}"
            )

    if is_genie:
        if _is_placeholder(configuration.get("genie_table_identifier")):
            raise ValueError("genie_table_identifier required for Genie Space")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "patients", "primary_key": ["patient_id"]},
        {"table": "conditions", "primary_key": ["condition_id"]},
        {"table": "observations", "primary_key": ["observation_id"]},
        {"table": "medications", "primary_key": ["medication_id"]},
        {"table": "population_insights", "primary_key": ["insight_id"]},
        {"table": "clinical_assessments", "primary_key": ["patient_id"]},
        {"table": "resource_assessments", "primary_key": ["patient_id"]},
        {"table": "debate_consensus", "primary_key": ["patient_id"]},
    ]


def create_session():
    """
    Create a requests session with FHIR-required Accept header.

    Returns:
        requests.Session configured for FHIR API calls
    """
    session = requests.Session()
    session.headers.update({"Accept": __FHIR_ACCEPT_HEADER})
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
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )

            if status_code in (401, 403):
                msg = f"HTTP {status_code}: Check your FHIR server credentials. URL: {url}"
                log.severe(msg)
                raise RuntimeError(msg) from e

            should_retry = status_code in __RETRYABLE_STATUS_CODES

            if should_retry and attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"HTTP {status_code}, retrying in {delay_seconds}s")
                time.sleep(delay_seconds)
            else:
                attempts = attempt + 1
                raise RuntimeError(f"API request failed after {attempts} attempt(s): {e}") from e


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() with async polling for PENDING statements.

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
    timeout_seconds = _optional_int(
        configuration, "databricks_timeout", __DEFAULT_DATABRICKS_TIMEOUT
    )

    url = f"{workspace_url}{__SQL_STATEMENT_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    escaped = prompt.replace("'", "''")
    statement = f"SELECT ai_query('{model}', '{escaped}') as response"

    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": __SQL_WAIT_TIMEOUT,
    }

    try:
        # Retry initial POST for transient failures
        response = None
        for attempt in range(__MAX_RETRIES):
            try:
                response = session.post(
                    url, headers=headers, json=payload, timeout=timeout_seconds
                )
                if response.status_code in __RETRYABLE_STATUS_CODES:
                    delay = __BASE_DELAY_SECONDS * (2**attempt)
                    log.warning(
                        f"ai_query() attempt {attempt + 1} returned {response.status_code}, retrying in {delay}s"
                    )
                    time.sleep(delay)
                    continue
                if response.status_code in (401, 403):
                    response.raise_for_status()
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < __MAX_RETRIES - 1:
                    delay = __BASE_DELAY_SECONDS * (2**attempt)
                    log.warning(
                        f"ai_query() attempt {attempt + 1} failed: {e}, retrying in {delay}s"
                    )
                    time.sleep(delay)
                else:
                    raise
        response.raise_for_status()

        result = response.json()
        sql_state = result.get("status", {}).get("state", "")

        # Poll for PENDING/RUNNING states
        statement_id = result.get("statement_id")
        if sql_state in ("PENDING", "RUNNING") and not statement_id:
            log.warning("ai_query() returned PENDING/RUNNING with no statement_id — cannot poll")
            return None
        poll_count = 0
        max_polls = 12
        poll_interval_seconds = 10

        while sql_state in ("PENDING", "RUNNING") and poll_count < max_polls:
            poll_count += 1
            time.sleep(poll_interval_seconds)
            poll_url = f"{url}/{statement_id}"
            poll_resp = session.get(poll_url, headers=headers, timeout=timeout_seconds)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            sql_state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/{max_polls}: {sql_state}")

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
        log.warning(f"ai_query() timeout after {timeout_seconds}s")
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


def extract_codeable_concept(obj):
    """
    Extract code, display, and system from a FHIR CodeableConcept.

    Args:
        obj: FHIR CodeableConcept dictionary

    Returns:
        Tuple of (code, display, system)
    """
    if not obj or not isinstance(obj, dict):
        return None, None, None

    codings = obj.get("coding", [])
    if codings and isinstance(codings, list) and len(codings) > 0:
        first = codings[0]
        return (
            first.get("code"),
            first.get("display") or obj.get("text"),
            first.get("system"),
        )

    return None, obj.get("text"), None


def extract_reference_id(obj):
    """
    Extract the resource ID from a FHIR Reference object.

    Args:
        obj: FHIR Reference dictionary

    Returns:
        Resource ID string or None
    """
    if not obj or not isinstance(obj, dict):
        return None
    ref = obj.get("reference", "")
    if "/" in ref:
        return ref.split("/")[-1]
    return ref or None


def extract_quantity(obj):
    """
    Extract value and unit from a FHIR Quantity object.

    Args:
        obj: FHIR Quantity dictionary

    Returns:
        Tuple of (value, unit)
    """
    if not obj or not isinstance(obj, dict):
        return None, None
    return obj.get("value"), obj.get("unit")


def fetch_fhir_bundle(session, url, params=None, max_results=None):
    """
    Fetch all pages of a FHIR Bundle resource following Bundle.link pagination.

    Args:
        session: requests.Session
        url: FHIR resource endpoint URL
        params: Optional query parameters for the first request
        max_results: Optional ceiling on total resources returned

    Returns:
        List of FHIR resource dictionaries
    """
    resources = []
    next_url = url
    current_params = params

    while next_url:
        try:
            data = fetch_data_with_retry(session, next_url, params=current_params)
        except RuntimeError as e:
            log.warning(f"Failed to fetch FHIR bundle page: {e}")
            break

        # Only pass params on the first request; subsequent requests use the full next URL
        current_params = None

        entries = data.get("entry", [])
        for entry in entries:
            resource = entry.get("resource", {})
            if resource:
                resources.append(resource)

        if max_results and len(resources) >= max_results:
            resources = resources[:max_results]
            break

        # Follow Bundle.link with relation=next for pagination
        next_url = None
        for link in data.get("link", []):
            if link.get("relation") == "next":
                next_url = link.get("url")
                break

        time.sleep(__FHIR_RATE_LIMIT_DELAY)

    return resources


def build_patient_record(resource):
    """
    Build a normalized patient record from a FHIR Patient resource.

    Args:
        resource: FHIR Patient resource dictionary

    Returns:
        Normalized patient record dictionary
    """
    patient_id = resource.get("id")

    # Name: prefer official use, fall back to first name entry
    given_name = None
    family_name = None
    names = resource.get("name", [])
    if names and isinstance(names, list):
        official = next((n for n in names if n.get("use") == "official"), names[0])
        given_list = official.get("given", [])
        given_name = given_list[0] if given_list else None
        family_name = official.get("family")

    # MRN from identifiers
    mrn = None
    identifiers = resource.get("identifier", [])
    if identifiers and isinstance(identifiers, list):
        mrn = identifiers[0].get("value")

    # Address
    address_line = None
    city = None
    addr_state = None
    postal_code = None
    country = None
    addresses = resource.get("address", [])
    if addresses and isinstance(addresses, list) and len(addresses) > 0:
        first_addr = addresses[0]
        lines = first_addr.get("line", [])
        address_line = lines[0] if lines else None
        city = first_addr.get("city")
        addr_state = first_addr.get("state")
        postal_code = first_addr.get("postalCode")
        country = first_addr.get("country")

    # Marital status
    _, marital_display, _ = extract_codeable_concept(resource.get("maritalStatus"))

    # Communication language
    language = None
    communications = resource.get("communication", [])
    if communications and isinstance(communications, list) and len(communications) > 0:
        lang_obj = communications[0].get("language", {})
        _, language, _ = extract_codeable_concept(lang_obj)

    return {
        "patient_id": patient_id,
        "mrn": mrn,
        "given_name": given_name,
        "family_name": family_name,
        "gender": resource.get("gender"),
        "birth_date": resource.get("birthDate"),
        "deceased_boolean": resource.get("deceasedBoolean"),
        "deceased_date_time": resource.get("deceasedDateTime"),
        "marital_status": marital_display,
        "language": language,
        "address_line": address_line,
        "city": city,
        "state": addr_state,
        "postal_code": postal_code,
        "country": country,
        "active": resource.get("active", True),
        "last_updated": resource.get("meta", {}).get("lastUpdated"),
    }


def build_condition_record(resource):
    """
    Build a normalized condition record from a FHIR Condition resource.

    Args:
        resource: FHIR Condition resource dictionary

    Returns:
        Normalized condition record dictionary, or None if missing required fields
    """
    condition_id = resource.get("id")
    patient_id = extract_reference_id(resource.get("subject"))

    if not condition_id or not patient_id:
        return None

    code, display, system = extract_codeable_concept(resource.get("code"))
    category_list = resource.get("category") or []
    category_code, _, _ = extract_codeable_concept(category_list[0] if category_list else {})
    clinical_status_code, _, _ = extract_codeable_concept(resource.get("clinicalStatus"))
    verification_code, _, _ = extract_codeable_concept(resource.get("verificationStatus"))

    # Onset: try dateTime, then string, then Period.start
    onset_date = resource.get("onsetDateTime") or resource.get("onsetString")
    if not onset_date and resource.get("onsetPeriod"):
        onset_date = resource.get("onsetPeriod", {}).get("start")

    abatement_date = resource.get("abatementDateTime") or resource.get("abatementString")

    return {
        "condition_id": condition_id,
        "patient_id": patient_id,
        "code": code,
        "display": display,
        "code_system": system,
        "category": category_code,
        "clinical_status": clinical_status_code,
        "verification_status": verification_code,
        "onset_date": onset_date,
        "abatement_date": abatement_date,
        "recorded_date": resource.get("recordedDate"),
        "last_updated": resource.get("meta", {}).get("lastUpdated"),
    }


def build_observation_record(resource):
    """
    Build a normalized observation record from a FHIR Observation resource.

    Args:
        resource: FHIR Observation resource dictionary

    Returns:
        Normalized observation record dictionary, or None if missing required fields
    """
    observation_id = resource.get("id")
    patient_id = extract_reference_id(resource.get("subject"))

    if not observation_id or not patient_id:
        return None

    code, display, system = extract_codeable_concept(resource.get("code"))
    category_list = resource.get("category") or []
    category_code, _, _ = extract_codeable_concept(category_list[0] if category_list else {})

    # Value: Quantity, CodeableConcept, string, boolean, or integer
    obs_value = None
    value_unit = None
    if resource.get("valueQuantity"):
        obs_value, value_unit = extract_quantity(resource.get("valueQuantity"))
    elif resource.get("valueCodeableConcept"):
        _, obs_value, _ = extract_codeable_concept(resource.get("valueCodeableConcept"))
    elif resource.get("valueString"):
        obs_value = resource.get("valueString")
    elif resource.get("valueBoolean") is not None:
        obs_value = str(resource.get("valueBoolean"))
    elif resource.get("valueInteger") is not None:
        obs_value = resource.get("valueInteger")

    # Effective date: prefer dateTime, then Period.start
    effective_date = resource.get("effectiveDateTime")
    if not effective_date and resource.get("effectivePeriod"):
        effective_date = resource.get("effectivePeriod", {}).get("start")

    # Reference range
    reference_range_low = None
    reference_range_high = None
    ref_ranges = resource.get("referenceRange") or []
    if ref_ranges and isinstance(ref_ranges, list):
        first_range = ref_ranges[0]
        reference_range_low, _ = extract_quantity(first_range.get("low"))
        reference_range_high, _ = extract_quantity(first_range.get("high"))

    # Interpretation
    interpretation_list = resource.get("interpretation") or []
    interp_code = None
    if isinstance(interpretation_list, list) and interpretation_list:
        interp_code, _, _ = extract_codeable_concept(interpretation_list[0])

    return {
        "observation_id": observation_id,
        "patient_id": patient_id,
        "code": code,
        "display": display,
        "code_system": system,
        "category": category_code,
        "value": obs_value,
        "value_unit": value_unit,
        "status": resource.get("status"),
        "effective_date": effective_date,
        "issued": resource.get("issued"),
        "interpretation": interp_code,
        "reference_range_low": reference_range_low,
        "reference_range_high": reference_range_high,
        "last_updated": resource.get("meta", {}).get("lastUpdated"),
    }


def build_medication_record(resource):
    """
    Build a normalized medication record from a FHIR MedicationRequest resource.

    Args:
        resource: FHIR MedicationRequest resource dictionary

    Returns:
        Normalized medication record dictionary, or None if missing required fields
    """
    medication_id = resource.get("id")
    patient_id = extract_reference_id(resource.get("subject"))

    if not medication_id or not patient_id:
        return None

    # Medication name from CodeableConcept or Reference
    med_code = None
    med_display = None
    med_system = None
    if resource.get("medicationCodeableConcept"):
        med_code, med_display, med_system = extract_codeable_concept(
            resource.get("medicationCodeableConcept")
        )
    elif resource.get("medicationReference"):
        med_display = resource.get("medicationReference", {}).get("display")

    # Dosage instructions
    dosage_text = None
    dosage_timing = None
    dosage_route = None
    dosage_instructions = resource.get("dosageInstruction") or []
    if dosage_instructions and isinstance(dosage_instructions, list):
        first_dosage = dosage_instructions[0]
        dosage_text = first_dosage.get("text")
        if first_dosage.get("timing"):
            dosage_timing = json.dumps(first_dosage.get("timing"))
        _, dosage_route, _ = extract_codeable_concept(first_dosage.get("route"))

    return {
        "medication_id": medication_id,
        "patient_id": patient_id,
        "medication_code": med_code,
        "medication_display": med_display,
        "medication_system": med_system,
        "status": resource.get("status"),
        "intent": resource.get("intent"),
        "authored_on": resource.get("authoredOn"),
        "dosage_text": dosage_text,
        "dosage_timing": dosage_timing,
        "dosage_route": dosage_route,
        "last_updated": resource.get("meta", {}).get("lastUpdated"),
    }


def format_patients_for_discovery(patient_records, condition_records_by_patient):
    """
    Format patient cohort data into a summary string for the discovery prompt.

    Args:
        patient_records: List of normalized patient record dictionaries
        condition_records_by_patient: Dict mapping patient_id to condition list

    Returns:
        Formatted cohort summary string
    """
    if not patient_records:
        return "  No patients"
    lines = []
    for patient in patient_records[:20]:
        pid = patient.get("patient_id")
        conditions = condition_records_by_patient.get(pid, [])
        condition_str = ", ".join(
            c.get("display") or c.get("code") or "Unknown" for c in conditions[:3]
        )
        lines.append(
            f"  - DOB: {patient.get('birth_date', 'N/A')}, "
            f"Gender: {patient.get('gender', 'N/A')}, "
            f"Conditions: {condition_str or 'None recorded'}"
        )
    return "\n".join(lines)


def build_discovery_prompt(condition_filter, patients_summary):
    """
    Build the ai_query() prompt for population health discovery analysis.

    Args:
        condition_filter: ICD-10 code prefix used to filter patients (empty = all)
        patients_summary: Formatted summary of the patient cohort

    Returns:
        Prompt string
    """
    cohort_label = f"ICD-10 prefix '{condition_filter}'" if condition_filter else "all conditions"
    return (
        "You are a population health analyst. Analyze this patient cohort "
        f"({cohort_label}) and identify at-risk populations.\n\n"
        f"PATIENT COHORT:\n{patients_summary}\n\n"
        "YOUR TASKS:\n"
        "1. Identify the most prevalent conditions and risk factors\n"
        "2. Which patients are at highest risk for readmission or complications?\n"
        "3. What comorbidities should be investigated?\n"
        "4. What preventive screenings are overdue for this population?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "dominant_conditions": ["..."],\n'
        '  "risk_factors": ["..."],\n'
        '  "high_risk_indicators": "...",\n'
        '  "recommended_screenings": ["..."],\n'
        '  "comorbidities_to_investigate": ["..."],\n'
        '  "population_risk_summary": "..."\n'
        "}"
    )


def build_clinical_prompt(patient_record, condition_summaries, obs_summaries, med_summaries):
    """
    Build the Clinical Risk Analyst prompt (urgency-maximizing).

    Args:
        patient_record: Normalized patient record dictionary
        condition_summaries: List of condition summary strings
        obs_summaries: List of observation summary strings
        med_summaries: List of medication summary strings

    Returns:
        Prompt string
    """
    conditions_text = "\n".join(f"  - {c}" for c in condition_summaries[:10])
    obs_text = "\n".join(f"  - {o}" for o in obs_summaries[:10])
    med_text = "\n".join(f"  - {m}" for m in med_summaries[:10])

    return (
        "You are a Clinical Risk Analyst. Assess the MAXIMUM clinical risk for "
        "this patient. Assume worst-case: poor medication adherence, missed "
        "follow-ups, undiagnosed complications. Advocate for aggressive care "
        "management.\n\n"
        f"PATIENT: {patient_record.get('given_name', 'Unknown')} "
        f"{patient_record.get('family_name', '')}, "
        f"DOB: {patient_record.get('birth_date', 'N/A')}, "
        f"Gender: {patient_record.get('gender', 'N/A')}\n\n"
        f"CONDITIONS:\n{conditions_text}\n\n"
        f"RECENT OBSERVATIONS:\n{obs_text}\n\n"
        f"MEDICATIONS:\n{med_text}\n\n"
        "Analyze from a clinical urgency perspective:\n"
        "1. What is the worst-case clinical scenario?\n"
        "2. Should this patient be escalated to intensive care management?\n"
        "3. What interventions are immediately needed?\n"
        "4. What complications is this patient at risk for?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "clinical_risk_score": <1-10>,\n'
        '  "worst_case_scenario": "...",\n'
        '  "intervention_recommendation": '
        '"INPATIENT_CARE_MGMT|OUTPATIENT_INTENSIFY|TELEHEALTH|ROUTINE",\n'
        '  "immediate_actions": ["..."],\n'
        '  "complication_risks": ["..."],\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_resource_prompt(patient_record, condition_summaries, obs_summaries, med_summaries):
    """
    Build the Resource Allocation Analyst prompt (proportional response).

    Args:
        patient_record: Normalized patient record dictionary
        condition_summaries: List of condition summary strings
        obs_summaries: List of observation summary strings
        med_summaries: List of medication summary strings

    Returns:
        Prompt string
    """
    conditions_text = "\n".join(f"  - {c}" for c in condition_summaries[:10])
    obs_text = "\n".join(f"  - {o}" for o in obs_summaries[:10])
    med_text = "\n".join(f"  - {m}" for m in med_summaries[:10])

    return (
        "You are a Resource Allocation Analyst. Assess the REALISTIC clinical "
        "risk and recommend PROPORTIONAL resource allocation. Consider "
        "cost-effectiveness and system capacity.\n\n"
        f"PATIENT: {patient_record.get('given_name', 'Unknown')} "
        f"{patient_record.get('family_name', '')}, "
        f"DOB: {patient_record.get('birth_date', 'N/A')}, "
        f"Gender: {patient_record.get('gender', 'N/A')}\n\n"
        f"CONDITIONS:\n{conditions_text}\n\n"
        f"RECENT OBSERVATIONS:\n{obs_text}\n\n"
        f"MEDICATIONS:\n{med_text}\n\n"
        "Analyze from a proportional-response perspective:\n"
        "1. What is the probability-weighted expected clinical risk?\n"
        "2. Is intensive care management proportionate or excessive?\n"
        "3. What is the most cost-effective intervention?\n"
        "4. What compensating factors reduce the risk?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "resource_risk_score": <1-10>,\n'
        '  "expected_risk": "...",\n'
        '  "intervention_recommendation": '
        '"INPATIENT_CARE_MGMT|OUTPATIENT_INTENSIFY|TELEHEALTH|ROUTINE",\n'
        '  "cost_effective_actions": ["..."],\n'
        '  "mitigating_factors": ["..."],\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_consensus_prompt(patient_record, clinical_result, resource_result):
    """
    Build the Consensus synthesizer prompt.

    Args:
        patient_record: Normalized patient record dictionary
        clinical_result: Clinical Risk Analyst JSON result dictionary
        resource_result: Resource Allocation Analyst JSON result dictionary

    Returns:
        Prompt string
    """
    return (
        "You are a neutral care management director synthesizing two expert "
        "assessments of the same patient. One expert (Clinical) maximizes "
        "urgency; the other (Resource) applies proportional analysis. Produce "
        "a balanced intervention recommendation.\n\n"
        f"PATIENT: {patient_record.get('given_name', 'Unknown')} "
        f"{patient_record.get('family_name', '')}\n\n"
        "CLINICAL RISK ANALYST:\n"
        f"{json.dumps(clinical_result, indent=2)}\n\n"
        "RESOURCE ALLOCATION ANALYST:\n"
        f"{json.dumps(resource_result, indent=2)}\n\n"
        "Synthesize:\n"
        "1. Where do they AGREE and DISAGREE?\n"
        "2. Which assessment is MORE PERSUASIVE and why?\n"
        "3. What is the balanced recommended intervention level?\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "intervention_level": '
        '"INPATIENT_CARE_MGMT|OUTPATIENT_INTENSIFY|TELEHEALTH|ROUTINE",\n'
        '  "consensus_risk_score": <1-10>,\n'
        '  "debate_winner": "CLINICAL|RESOURCE|DRAW",\n'
        '  "winner_rationale": "...",\n'
        '  "agreement_areas": ["..."],\n'
        '  "disagreement_areas": ["..."],\n'
        '  "disagreement_flag": true|false,\n'
        '  "disagreement_severity": "NONE|MINOR|SIGNIFICANT|FUNDAMENTAL",\n'
        '  "recommended_next_step": "...",\n'
        '  "executive_summary": "..."\n'
        "}"
    )


def upsert_assessment(table_name, patient_id, assessment, assessment_type):
    """
    Upsert an AI assessment record to the destination table.

    Args:
        table_name: Destination table name
        patient_id: Patient identifier
        assessment: Parsed JSON assessment dictionary
        assessment_type: Type label string (clinical, resource, consensus)

    Returns:
        bool: True if upserted, False if skipped
    """
    if assessment is None:
        log.warning(f"Skipping {assessment_type} for {patient_id}: no response")
        return False

    record = flatten_dict(assessment) if assessment else {}
    record["patient_id"] = patient_id
    record["assessment_type"] = assessment_type

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table_name, data=record)
    return True


def run_move_phase(session, base_url, max_patients, condition_filter, state):
    """
    Phase 1 (MOVE): Fetch clinical data from the FHIR server.

    Fetches Patient resources (with optional condition filter), then for each
    patient fetches Conditions, Observations, and MedicationRequests.

    Args:
        session: requests.Session
        base_url: FHIR server base URL
        max_patients: Maximum number of patients to sync
        condition_filter: ICD-10 code prefix to filter patients (empty = all)
        state: State dictionary for checkpointing

    Returns:
        Tuple of (patient_records, condition_records_by_patient,
                  observation_records_by_patient, medication_records_by_patient)
    """
    patient_records = []
    condition_records_by_patient = {}
    observation_records_by_patient = {}
    medication_records_by_patient = {}

    patient_params = {"_count": str(__DEFAULT_PAGE_SIZE), "_sort": "-_lastUpdated"}
    last_sync = state.get("last_sync")
    if last_sync:
        patient_params["_lastUpdated"] = f"gt{last_sync}"
    if condition_filter:
        patient_params["_has:Condition:patient:code"] = condition_filter

    log.info(
        f"Fetching patients (condition filter: {condition_filter or 'none'}, max: {max_patients})"
    )
    patient_resources = fetch_fhir_bundle(
        session,
        f"{base_url}/Patient",
        params=patient_params,
        max_results=max_patients,
    )

    log.info(f"Fetched {len(patient_resources)} patient resources")

    for resource in patient_resources:
        patient_record = build_patient_record(resource)
        if not patient_record.get("patient_id"):
            log.warning("Skipping patient without ID")
            continue

        patient_records.append(patient_record)
        pid = patient_record["patient_id"]

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="patients", data=flatten_dict(patient_record))

        # Fetch Conditions for this patient
        condition_resources = fetch_fhir_bundle(
            session,
            f"{base_url}/Condition",
            params={"patient": pid, "_count": "100"},
            max_results=__MAX_RESOURCES_PER_PATIENT,
        )
        patient_conditions = []
        for cond_resource in condition_resources:
            cond_record = build_condition_record(cond_resource)
            if cond_record:
                patient_conditions.append(cond_record)
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="conditions", data=flatten_dict(cond_record))
        condition_records_by_patient[pid] = patient_conditions

        # Fetch Observations (labs/vitals) for this patient
        obs_resources = fetch_fhir_bundle(
            session,
            f"{base_url}/Observation",
            params={"patient": pid, "category": "laboratory", "_count": "100"},
            max_results=__MAX_RESOURCES_PER_PATIENT,
        )
        patient_observations = []
        for obs_resource in obs_resources:
            obs_record = build_observation_record(obs_resource)
            if obs_record:
                patient_observations.append(obs_record)
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="observations", data=flatten_dict(obs_record))
        observation_records_by_patient[pid] = patient_observations

        # Fetch MedicationRequests for this patient
        med_resources = fetch_fhir_bundle(
            session,
            f"{base_url}/MedicationRequest",
            params={"patient": pid, "_count": "100"},
            max_results=__MAX_RESOURCES_PER_PATIENT,
        )
        patient_medications = []
        for med_resource in med_resources:
            med_record = build_medication_record(med_resource)
            if med_record:
                patient_medications.append(med_record)
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="medications", data=flatten_dict(med_record))
        medication_records_by_patient[pid] = patient_medications

    return (
        patient_records,
        condition_records_by_patient,
        observation_records_by_patient,
        medication_records_by_patient,
    )


def run_discovery_phase(
    session,
    configuration,
    patient_records,
    condition_records_by_patient,
    state,
):
    """
    Phase 2 (DISCOVERY): AI identifies at-risk patient populations.

    Analyzes the full patient cohort and generates population-level risk
    stratification and recommended interventions in population_insights.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        patient_records: List of normalized patient record dictionaries
        condition_records_by_patient: Dict mapping patient_id to condition list
        state: State dictionary for checkpointing
    """
    condition_filter = _optional_str(configuration, "condition_filter", __DEFAULT_CONDITION_FILTER)
    patients_summary = format_patients_for_discovery(patient_records, condition_records_by_patient)

    prompt = build_discovery_prompt(condition_filter, patients_summary)
    log.info("Calling ai_query() for population health discovery")

    content = call_ai_query(session, configuration, prompt)
    result = extract_json_from_content(content)

    if not result or not isinstance(result, dict):
        log.warning("Discovery phase: no valid JSON result from ai_query()")
        return

    condition_label = (condition_filter or "all_conditions").replace(" ", "_")
    insight_id = f"insight_{condition_label}"

    insight_record = {
        "insight_id": insight_id,
        "condition_filter": condition_filter or "none",
        "patient_count": len(patient_records),
        "dominant_conditions": result.get("dominant_conditions"),
        "risk_factors": result.get("risk_factors"),
        "high_risk_indicators": result.get("high_risk_indicators"),
        "recommended_screenings": result.get("recommended_screenings"),
        "comorbidities_to_investigate": result.get("comorbidities_to_investigate"),
        "population_risk_summary": result.get("population_risk_summary"),
    }

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="population_insights", data=flatten_dict(insight_record))

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state=state)


def run_debate_phase(
    session,
    configuration,
    patient_records,
    condition_records_by_patient,
    observation_records_by_patient,
    medication_records_by_patient,
    state,
):
    """
    Phase 3 (DEBATE): Clinical Risk vs Resource Allocation debate per patient.

    For each high-risk patient, runs three ai_query() calls: Clinical Risk
    Analyst, Resource Allocation Analyst, and Consensus Agent.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        patient_records: List of normalized patient record dictionaries
        condition_records_by_patient: Dict mapping patient_id to condition list
        observation_records_by_patient: Dict mapping patient_id to observation list
        medication_records_by_patient: Dict mapping patient_id to medication list
        state: State dictionary for checkpointing

    Returns:
        Tuple of (debate_count, disagreement_count)
    """
    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    enrichment_count = 0
    disagreement_count = 0

    debate_patients = patient_records[:max_enrichments]
    log.info(f"Starting debate for {len(debate_patients)} patients (3 ai_query() calls each)")

    for patient_record in debate_patients:
        if enrichment_count >= max_enrichments:
            log.info("Enrichment budget exhausted")
            break

        pid = patient_record.get("patient_id")
        conditions = condition_records_by_patient.get(pid, [])
        observations = observation_records_by_patient.get(pid, [])
        medications = medication_records_by_patient.get(pid, [])

        condition_summaries = [
            f"{c.get('display') or c.get('code') or 'Unknown'} "
            f"({c.get('clinical_status', 'N/A')})"
            for c in conditions[:10]
        ]
        obs_summaries = [
            f"{o.get('display') or o.get('code') or 'Unknown'}: "
            f"{o.get('value')} {o.get('value_unit') or ''} "
            f"({o.get('effective_date', 'N/A')})"
            for o in observations[:10]
        ]
        med_summaries = [
            f"{m.get('medication_display') or m.get('medication_code') or 'Unknown'} "
            f"({m.get('status', 'N/A')})"
            for m in medications[:10]
        ]

        # Agent 1: Clinical Risk Analyst
        clinical_content = call_ai_query(
            session,
            configuration,
            build_clinical_prompt(
                patient_record, condition_summaries, obs_summaries, med_summaries
            ),
        )
        clinical_result = extract_json_from_content(clinical_content)
        upsert_assessment("clinical_assessments", pid, clinical_result, "clinical")

        # Agent 2: Resource Allocation Analyst
        resource_content = call_ai_query(
            session,
            configuration,
            build_resource_prompt(
                patient_record, condition_summaries, obs_summaries, med_summaries
            ),
        )
        resource_result = extract_json_from_content(resource_content)
        upsert_assessment("resource_assessments", pid, resource_result, "resource")

        # Agent 3: Consensus
        if clinical_result and resource_result:
            consensus_content = call_ai_query(
                session,
                configuration,
                build_consensus_prompt(patient_record, clinical_result, resource_result),
            )
            consensus_result = extract_json_from_content(consensus_content)
            upsert_assessment("debate_consensus", pid, consensus_result, "consensus")

            if consensus_result and consensus_result.get("disagreement_flag"):
                disagreement_count += 1
        else:
            log.warning(f"Skipping consensus for {pid}: missing analyst assessment")

        enrichment_count += 1

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

    return enrichment_count, disagreement_count


def create_genie_space(session, configuration, state):
    """
    Phase 4 (AGENT): Create a Databricks Genie Space for clinical analytics.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        state: State dictionary for persisting the Genie Space ID

    Returns:
        Space ID string, or None on error
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
                {"id": uuid.uuid4().hex, "question": q} for q in __GENIE_SPACE_SAMPLE_QUESTIONS
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
        "title": "FHIR Healthcare Intelligence",
        "description": (
            "AI-enriched FHIR R4 clinical data with hybrid analysis. "
            "Powered by Fivetran + Databricks."
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
        log.warning(f"Genie Space HTTP error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Genie Space error: {str(e)}")
        return None


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: all_things_ai/tutorials : databricks-fm-fhir-healthcare-intelligence")

    validate_configuration(configuration)

    # Parse configuration
    base_url = _optional_str(configuration, "fhir_base_url", __BASE_URL_FHIR)
    max_patients = _optional_int(configuration, "max_patients", __DEFAULT_MAX_PATIENTS)
    condition_filter = _optional_str(configuration, "condition_filter", __DEFAULT_CONDITION_FILTER)
    is_enrichment = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_discovery = _parse_bool(configuration.get("enable_discovery"), default=True)
    is_genie = _parse_bool(configuration.get("enable_genie_space"), default=False)

    log.info(f"FHIR base URL: {base_url}")
    log.info(f"Max patients: {max_patients}, condition filter: {condition_filter or 'none'}")

    if is_enrichment:
        model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)
        log.info(f"Hybrid analysis ENABLED: model={model}")
    else:
        log.info("Hybrid analysis DISABLED")

    session = create_session()

    try:
        # --- Phase 1: MOVE ---
        log.info("Phase 1 (MOVE): Fetching clinical data from FHIR")

        (
            patient_records,
            condition_records_by_patient,
            observation_records_by_patient,
            medication_records_by_patient,
        ) = run_move_phase(session, base_url, max_patients, condition_filter, state)

        log.info(f"Phase 1 complete: {len(patient_records)} patients fetched")

        if not patient_records:
            log.info("No patients found — nothing to enrich")
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            return

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # --- Phase 2: DISCOVERY ---
        if is_enrichment and is_discovery:
            log.info("Phase 2 (DISCOVERY): AI population health analysis")
            run_discovery_phase(
                session,
                configuration,
                patient_records,
                condition_records_by_patient,
                state,
            )
            log.info("Discovery phase complete")

        # --- Phase 3: DEBATE ---
        if is_enrichment:
            log.info("Phase 3 (DEBATE): Clinical vs Resource debate per patient")

            debate_count, disagreement_count = run_debate_phase(
                session,
                configuration,
                patient_records,
                condition_records_by_patient,
                observation_records_by_patient,
                medication_records_by_patient,
                state,
            )

            log.info(
                f"Debate complete: {debate_count} patients debated, "
                f"{disagreement_count} with disagreement flags"
            )
        else:
            log.info("Enrichment disabled, skipping discovery and debate.")

        # --- Phase 4: AGENT ---
        if is_genie:
            log.info("Phase 4 (AGENT): Creating Genie Space")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)

        # Final checkpoint
        state["last_sync"] = datetime.now(timezone.utc).isoformat()

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info(f"Sync complete: {len(patient_records)} patients, all clinical phases done")

    except (requests.exceptions.RequestException, ValueError, RuntimeError) as e:
        log.severe(f"Unexpected error during sync: {str(e)}")
        raise

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
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
