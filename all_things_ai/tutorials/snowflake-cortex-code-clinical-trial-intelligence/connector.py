"""
Snowflake Cortex Clinical Trial Intelligence - Discovery + Multi-Agent Debate Connector

Syncs clinical trial records from the ClinicalTrials.gov API v2.0 for a configured
therapeutic area and enriches them with competing AI assessments from Snowflake Cortex
Agent personas. This connector combines two advanced patterns:

Pattern A (Agent-Driven Discovery): A Cortex Agent analyzes seed trials and recommends
related trials to fetch automatically -- competing therapies, same drug class, same
patient population. The connector then fetches those discovered trials without human
intervention.

Pattern B (Multi-Agent Debate): Two Cortex Agent personas with opposing expert
perspectives evaluate each trial:
  - Optimist: Evaluates trial design strengths (sample size, randomization, blinding,
    endpoint selection, sponsor track record)
  - Skeptic: Flags methodology risks (dropout potential, endpoint concerns, statistical
    power, regulatory hurdles)
  - Consensus: Synthesized evaluation with disagreement flag highlighting trials where
    the agents significantly disagree, flagging them for human expert review.

Built with Claude Code and the Fivetran Connector Builder Skill.

APIs Used:
1. ClinicalTrials.gov API v2.0 - Clinical trial records (no authentication required)
2. Snowflake Cortex Agent - Discovery, Optimist, Skeptic, and Consensus personas

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
from datetime import datetime, timezone

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# API Configuration Constants
__CT_BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
__API_TIMEOUT_SECONDS = 30

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

# Pagination Constants
__DEFAULT_PAGE_SIZE = 20
__MAX_PAGE_SIZE = 1000

# Sync Defaults
__DEFAULT_MAX_SEED_TRIALS = 20
__DEFAULT_MAX_DISCOVERIES = 10
__DEFAULT_MAX_DEBATES = 5

# Sanity ceiling on max_seed_trials to prevent unbounded memory growth per sync.
# Users needing larger pulls should run multiple syncs with the incremental cursor.
__MAX_SEED_TRIALS_CEILING = 500

# Cortex Agent Configuration
__CORTEX_AGENT_ENDPOINT = "/api/v2/cortex/inference:complete"
__DEFAULT_CORTEX_MODEL = "claude-sonnet-4-6"
__DEFAULT_CORTEX_TIMEOUT = 60


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

    Type-safe: returns False for non-strings (booleans, ints) so the helper
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
    Parse a boolean-like configuration value that may be a bool or string.

    Accepts bool directly (for programmatic callers passing real booleans),
    and string values "true"/"false" (case-insensitive) from JSON config.

    Args:
        value: bool, string, or None.
        default: value returned when input is None or a placeholder.

    Returns:
        bool: parsed boolean.
    """
    if isinstance(value, bool):
        return value
    if value is None or _is_placeholder(value):
        return default
    return str(value).strip().lower() == "true"


def _optional_int(configuration, key, default):
    """
    Read an optional integer config value, treating placeholders/None as unset.

    Args:
        configuration: Configuration dictionary.
        key: Key to read.
        default: Default integer if the value is missing or a placeholder.

    Returns:
        int: parsed integer or default.
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
        configuration: Configuration dictionary.
        key: Key to read.
        default: Default value if the entry is missing or a placeholder.

    Returns:
        str or default: the value if a real string, otherwise default.
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
    # Condition is always required
    condition = configuration.get("condition")
    if _is_placeholder(condition):
        raise ValueError("Missing required configuration value: condition")

    # Cortex configuration validation
    is_cortex_enabled = _parse_bool(configuration.get("enable_cortex"), default=False)
    if is_cortex_enabled:
        cortex_required = ["snowflake_account", "snowflake_pat_token"]
        for key in cortex_required:
            value = configuration.get(key)
            if _is_placeholder(value):
                raise ValueError(f"Missing required Cortex configuration value: {key}")

        snowflake_account = configuration.get("snowflake_account", "")
        # Must be a hostname (no scheme), so reject anything starting with http:// or https://
        if snowflake_account.startswith("http://") or snowflake_account.startswith("https://"):
            raise ValueError(
                "snowflake_account must be a hostname (e.g., "
                "'xy12345.region.snowflakecomputing.com'), not a full URL. "
                f"Got: {snowflake_account}"
            )
        if not snowflake_account.endswith("snowflakecomputing.com"):
            raise ValueError(
                "snowflake_account must end with 'snowflakecomputing.com'. "
                f"Got: {snowflake_account}"
            )

    # Validate numeric fields. Each field consumed via int() at runtime must be
    # in this loop. Placeholder values fall through to the runtime default;
    # values must be positive integers (zero or negative rejected).
    numeric_fields = [
        "max_seed_trials",
        "max_discoveries",
        "max_debates",
        "page_size",
        "cortex_timeout",
    ]
    for field in numeric_fields:
        value = configuration.get(field)
        if value is None or _is_placeholder(value):
            continue
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise ValueError(f"{field} must be a positive integer, got: {value!r}")
        if int_value <= 0:
            raise ValueError(f"{field} must be a positive integer, got: {value!r}")

    # Guard against unbounded memory use: cap max_seed_trials at 500
    max_seed = _optional_int(configuration, "max_seed_trials", __DEFAULT_MAX_SEED_TRIALS)
    if max_seed > __MAX_SEED_TRIALS_CEILING:
        raise ValueError(
            f"max_seed_trials={max_seed} exceeds the connector ceiling of "
            f"{__MAX_SEED_TRIALS_CEILING}. Reduce the value or run multiple smaller syncs."
        )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "trials", "primary_key": ["nct_id"]},
        {"table": "discovery_insights", "primary_key": ["nct_id"]},
        {"table": "optimist_assessments", "primary_key": ["nct_id"]},
        {"table": "skeptic_assessments", "primary_key": ["nct_id"]},
        {"table": "debate_consensus", "primary_key": ["nct_id"]},
    ]


def create_session():
    """
    Create a requests.Session with appropriate headers for ClinicalTrials.gov API.

    Returns:
        requests.Session: Configured session with connection pooling
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "FivetranConnectorSDK/ClinicalTrialIntelligence/1.0",
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
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.severe(f"Connection failed after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s " f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.severe(f"Timeout after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )

            if status_code in (401, 403):
                msg = f"HTTP {status_code}: Check your API credentials " f"and scopes. URL: {url}"
                log.severe(msg)
                raise RuntimeError(msg) from e

            should_retry = status_code in __RETRYABLE_STATUS_CODES

            if should_retry and attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Request failed with status {status_code}, "
                    f"retrying in {delay_seconds}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                attempts = attempt + 1
                log.severe(
                    f"Request failed after {attempts} attempt(s). "
                    f"URL: {url}, Status: {status_code or 'N/A'}, "
                    f"Error: {str(e)}"
                )
                raise RuntimeError(f"API request failed after {attempts} attempt(s): {e}") from e


def build_trial_record(study):
    """
    Build a flat trial record from a raw ClinicalTrials.gov API study response.

    Extracts key fields from the deeply nested protocolSection structure and
    flattens them into a single-level dictionary suitable for Fivetran upsert.

    Args:
        study: Study record dictionary from ClinicalTrials.gov API v2.0

    Returns:
        Flattened dictionary ready for upsert, or None if nct_id is missing
    """
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    description = protocol.get("descriptionModule", {})
    conditions = protocol.get("conditionsModule", {})
    design = protocol.get("designModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    arms = protocol.get("armsInterventionsModule", {})

    nct_id = identification.get("nctId")
    if not nct_id:
        return None

    # Extract design details
    design_info = design.get("designInfo", {})
    enrollment_info = design.get("enrollmentInfo", {})
    masking_info = design_info.get("maskingInfo", {})

    # Extract sponsor info
    lead_sponsor = sponsor.get("leadSponsor", {})

    # Extract date structures
    start_date = status.get("startDateStruct", {})
    completion_date = status.get("completionDateStruct", {})
    last_update = status.get("lastUpdatePostDateStruct", {})

    record = {
        "nct_id": nct_id,
        "brief_title": identification.get("briefTitle"),
        "official_title": identification.get("officialTitle"),
        "acronym": identification.get("acronym"),
        "overall_status": status.get("overallStatus"),
        "brief_summary": description.get("briefSummary"),
        "conditions": json.dumps(conditions.get("conditions", [])),
        "keywords": json.dumps(conditions.get("keywords", [])),
        "study_type": design.get("studyType"),
        "phases": json.dumps(design.get("phases", [])),
        "allocation": design_info.get("allocation"),
        "intervention_model": design_info.get("interventionModel"),
        "primary_purpose": design_info.get("primaryPurpose"),
        "masking": masking_info.get("masking"),
        "enrollment_count": enrollment_info.get("count"),
        "enrollment_type": enrollment_info.get("type"),
        "lead_sponsor_name": lead_sponsor.get("name"),
        "lead_sponsor_class": lead_sponsor.get("class"),
        "start_date": start_date.get("date"),
        "completion_date": completion_date.get("date"),
        "last_update_post_date": last_update.get("date"),
        "eligibility_criteria": eligibility.get("eligibilityCriteria"),
        "sex": eligibility.get("sex"),
        "minimum_age": eligibility.get("minimumAge"),
        "maximum_age": eligibility.get("maximumAge"),
        "healthy_volunteers": eligibility.get("healthyVolunteers"),
        "interventions": json.dumps(arms.get("interventions", [])),
        "arm_groups": json.dumps(arms.get("armGroups", [])),
        "has_results": study.get("hasResults", False),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }

    return record


def _should_skip_for_incremental(update_date, nct_id, last_update_date, synced_at_cursor):
    """
    Decide whether an incoming study has already been captured by a prior sync.

    The ClinicalTrials.gov `lastUpdatePostDate` is day-granularity, so an equality
    check on date alone would drop any trial updated on the same day as the stored
    cursor. We instead use a composite cursor: the latest `last_update_date` we
    have fully consumed plus the set of `nct_id` values we have already synced at
    that exact date. Anything strictly newer than the cursor is a hit; anything at
    the cursor date only skips if its nct_id is in the synced set.

    Args:
        update_date: `lastUpdatePostDate` on the incoming study (YYYY-MM-DD) or None.
        nct_id: NCT identifier on the incoming study.
        last_update_date: Date cursor stored in state, or None on first sync.
        synced_at_cursor: Set of nct_ids already synced at `last_update_date`.

    Returns:
        bool: True if the study should be skipped.
    """
    if not last_update_date or not update_date:
        return False
    if update_date > last_update_date:
        return False
    if update_date < last_update_date:
        return True
    # Same-day record: skip only if we've already synced this specific nct_id.
    return nct_id in synced_at_cursor


def _build_seed_params(configuration):
    """
    Build the initial query parameters for the seed-trial search.

    Args:
        configuration: Configuration dictionary.

    Returns:
        dict: parameters ready to pass to the ClinicalTrials.gov studies endpoint.
    """
    page_size = min(
        _optional_int(configuration, "page_size", __DEFAULT_PAGE_SIZE),
        __MAX_PAGE_SIZE,
    )
    params = {
        "query.cond": configuration.get("condition"),
        "pageSize": page_size,
        "sort": "LastUpdatePostDate",
        "countTotal": "true",
    }
    status_filter = _optional_str(configuration, "status_filter")
    if status_filter:
        params["filter.overallStatus"] = status_filter
    intervention_filter = _optional_str(configuration, "intervention_filter")
    if intervention_filter:
        params["query.intr"] = intervention_filter
    sponsor_filter = _optional_str(configuration, "sponsor_filter")
    if sponsor_filter:
        params["query.spons"] = sponsor_filter
    return params


def fetch_and_upsert_seed_trials(session, configuration, state):
    """
    Phase 1: Fetch, upsert, and checkpoint seed trials page by page.

    Processes records one page at a time so memory usage stays bounded regardless
    of `max_seed_trials`, and checkpoints the page token plus composite incremental
    cursor after every page so an interrupted sync can resume without gaps or
    duplicate work.

    State fields written:
        - `seed_page_token`: most recent `nextPageToken` returned by the API,
          or None when the window is exhausted.
        - `last_update_post_date`: latest `lastUpdatePostDate` fully consumed.
        - `synced_nct_ids_at_cursor`: list of nct_ids already synced at that
          date (composite cursor tie-breaker for day-granularity updates).

    Args:
        session: Authenticated requests.Session for ClinicalTrials.gov.
        configuration: Configuration dictionary.
        state: State dictionary for incremental sync (mutated in place).

    Returns:
        dict: mapping nct_id -> flat trial record (for downstream phases).
    """
    max_seed = _optional_int(configuration, "max_seed_trials", __DEFAULT_MAX_SEED_TRIALS)
    condition = configuration.get("condition")
    last_update_date = state.get("last_update_post_date")
    synced_at_cursor = set(state.get("synced_nct_ids_at_cursor", []))

    params = _build_seed_params(configuration)
    resume_token = state.get("seed_page_token")
    if resume_token:
        params["pageToken"] = resume_token
        params.pop("countTotal", None)

    trial_records = {}
    total_upserted = 0

    log.info(
        f"Fetching seed trials for condition: {condition} "
        f"(max: {max_seed}, last_update: {last_update_date or 'initial sync'}, "
        f"resume_token: {'yes' if resume_token else 'no'})"
    )

    while total_upserted < max_seed:
        # Capture the token used to fetch THIS page BEFORE we fetch — needed
        # so a capped sync can persist the current-page token (not the next
        # page's) and re-fetch THIS page on resume to pick up records that
        # didn't fit in the cap. Without this, capping mid-page silently
        # skips the unread tail of the page on the next sync.
        current_page_token = params.get("pageToken")
        data = fetch_data_with_retry(session, __CT_BASE_URL, params=params)
        studies = data.get("studies", [])
        total_count = data.get("totalCount")

        if not studies:
            # End of result set reached — clear the pagination token and stop.
            state["seed_page_token"] = None
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            break

        if total_count:
            log.info(f"Fetched page with {len(studies)} trials (total matching: {total_count})")

        page_upsert_count = 0
        latest_in_page = None
        oldest_in_page = None
        nct_ids_at_latest_in_page = []

        for study in studies:
            protocol = study.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            status_mod = protocol.get("statusModule", {})
            nct_id = identification.get("nctId")
            update_date = status_mod.get("lastUpdatePostDateStruct", {}).get("date")

            if not nct_id:
                continue

            if _should_skip_for_incremental(
                update_date, nct_id, last_update_date, synced_at_cursor
            ):
                continue

            record = build_trial_record(study)
            if not record:
                continue

            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="trials", data=record)
            trial_records[nct_id] = record
            page_upsert_count += 1
            total_upserted += 1

            # Track page-level date extrema for cursor advancement decisions.
            if update_date:
                if latest_in_page is None or update_date > latest_in_page:
                    latest_in_page = update_date
                    nct_ids_at_latest_in_page = [nct_id]
                elif update_date == latest_in_page:
                    nct_ids_at_latest_in_page.append(nct_id)
                if oldest_in_page is None or update_date < oldest_in_page:
                    oldest_in_page = update_date

            if total_upserted >= max_seed:
                break

        log.info(f"Upserted {page_upsert_count} trials from this page (total: {total_upserted})")

        next_token = data.get("nextPageToken")
        reached_cap = total_upserted >= max_seed

        if reached_cap and next_token:
            # Capped mid-page. Persist the CURRENT page's token (not the next
            # one) so the next sync re-fetches THIS page and the unread tail
            # is picked up. The composite cursor (latest_in_page +
            # nct_ids_at_latest_in_page) ensures already-synced records are
            # skipped on the re-fetch via _should_skip_for_incremental.
            state["seed_page_token"] = current_page_token
            if latest_in_page:
                _advance_cursor(
                    state,
                    latest_in_page,
                    nct_ids_at_latest_in_page,
                    last_update_date,
                    synced_at_cursor,
                )
                last_update_date = state["last_update_post_date"]
                synced_at_cursor = set(state["synced_nct_ids_at_cursor"])
        elif not next_token:
            # Window exhausted. Advance cursor to the latest date we saw overall
            # on this sync and record the nct_ids at that date for next time.
            state["seed_page_token"] = None
            if latest_in_page:
                _advance_cursor(
                    state,
                    latest_in_page,
                    nct_ids_at_latest_in_page,
                    last_update_date,
                    synced_at_cursor,
                )
                last_update_date = state["last_update_post_date"]
                synced_at_cursor = set(state["synced_nct_ids_at_cursor"])
        else:
            # More pages remain and we haven't hit the cap; persist progress.
            state["seed_page_token"] = next_token
            if latest_in_page:
                _advance_cursor(
                    state,
                    latest_in_page,
                    nct_ids_at_latest_in_page,
                    last_update_date,
                    synced_at_cursor,
                )
                last_update_date = state["last_update_post_date"]
                synced_at_cursor = set(state["synced_nct_ids_at_cursor"])

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        if not next_token or reached_cap:
            break

        params["pageToken"] = next_token
        params.pop("countTotal", None)

    log.info(f"Total seed trials fetched: {total_upserted}")
    return trial_records


def _advance_cursor(
    state, new_date, new_nct_ids_at_date, prior_cursor_date, prior_synced_at_cursor
):
    """
    Advance the composite incremental cursor (date + nct_ids at that date).

    If the new date is strictly newer than the prior cursor, the nct_id set resets
    to the records we just saw at that date. If the new date matches the prior
    cursor, we union the nct_id sets so we don't lose prior same-day records.
    Advancing to an older date is a no-op (we never move the cursor backwards).

    Args:
        state: Mutable state dict.
        new_date: Candidate new cursor date (YYYY-MM-DD).
        new_nct_ids_at_date: nct_ids on records whose lastUpdatePostDate equals new_date.
        prior_cursor_date: Existing cursor date in state, or None.
        prior_synced_at_cursor: Set of nct_ids already stored at prior_cursor_date.
    """
    if not new_date:
        return
    if prior_cursor_date and new_date < prior_cursor_date:
        return  # Never move the cursor backwards.
    if prior_cursor_date and new_date == prior_cursor_date:
        merged = list(prior_synced_at_cursor.union(new_nct_ids_at_date))
        state["last_update_post_date"] = new_date
        state["synced_nct_ids_at_cursor"] = merged
        return
    # new_date is strictly newer than prior cursor (or we had no cursor).
    state["last_update_post_date"] = new_date
    state["synced_nct_ids_at_cursor"] = list(new_nct_ids_at_date)


def fetch_single_trial(session, nct_id):
    """
    Fetch a single trial by NCT ID from ClinicalTrials.gov API.

    Args:
        session: Authenticated requests.Session
        nct_id: NCT identifier (e.g., "NCT06085833")

    Returns:
        Study dictionary, or None if not found
    """
    url = f"{__CT_BASE_URL}/{nct_id}"
    try:
        return fetch_data_with_retry(session, url)
    except RuntimeError as e:
        log.warning(f"Failed to fetch trial {nct_id}: {e}")
        return None


def upsert_trials(studies):
    """
    Upsert trial records from raw study data.

    Args:
        studies: List of raw study dictionaries from the API

    Returns:
        Tuple of (upserted_count, dict mapping nct_id to flat trial records)
    """
    count = 0
    trial_records = {}

    for study in studies:
        record = build_trial_record(study)
        if not record:
            log.warning("Skipping trial record without nct_id")
            continue

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="trials", data=record)
        trial_records[record["nct_id"]] = record
        count += 1

    return count, trial_records


def _create_cortex_session(configuration):
    """
    Create a requests.Session for Cortex API calls with connection pooling.

    Separate from the ClinicalTrials.gov session since it carries different auth headers.

    Args:
        configuration: Configuration dictionary with Snowflake credentials

    Returns:
        requests.Session configured for Cortex API
    """
    cortex_session = requests.Session()
    pat_token = configuration.get("snowflake_pat_token")
    cortex_session.headers.update(
        {
            "Authorization": f"Bearer {pat_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    return cortex_session


def call_cortex_agent(configuration, prompt, cortex_session=None):
    """
    Call Snowflake Cortex Agent via REST API for clinical trial analysis.

    Uses SSE streaming response parsing with bounded retry/backoff for
    transient failures. Accepts an optional session for connection pooling
    across multiple calls.

    Args:
        configuration: Configuration dictionary with Snowflake credentials
        prompt: Analysis prompt for the agent
        cortex_session: Optional requests.Session for connection reuse

    Returns:
        Parsed JSON response as dictionary, or None if all retry attempts fail
    """
    snowflake_account = configuration.get("snowflake_account")
    # Fall back to defaults when the config value is missing or left as a placeholder;
    # otherwise a literal "<CORTEX_MODEL>" would be forwarded to the Snowflake API.
    cortex_model = _optional_str(configuration, "cortex_model", __DEFAULT_CORTEX_MODEL)
    timeout = _optional_int(configuration, "cortex_timeout", __DEFAULT_CORTEX_TIMEOUT)

    url = f"https://{snowflake_account}{__CORTEX_AGENT_ENDPOINT}"

    payload = {
        "model": cortex_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    for attempt in range(__MAX_RETRIES):
        agent_response = ""
        try:
            if cortex_session:
                response = cortex_session.post(url, json=payload, timeout=timeout, stream=True)
            else:
                pat_token = configuration.get("snowflake_pat_token")
                headers = {
                    "Authorization": f"Bearer {pat_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                response = requests.post(
                    url, headers=headers, json=payload, timeout=timeout, stream=True
                )
            response.raise_for_status()

            try:
                for line in response.iter_lines():
                    if line:
                        line_text = line.decode("utf-8")
                        if line_text.startswith("data: "):
                            try:
                                data = json.loads(line_text[6:])
                                if not isinstance(data, dict):
                                    continue

                                choices = data.get("choices", [])
                                for choice in choices:
                                    delta = choice.get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        agent_response += content

                            except json.JSONDecodeError:
                                continue

                        elif line_text.startswith("event: done"):
                            break
            finally:
                response.close()

            if not agent_response:
                log.warning("Empty response from Cortex Agent")
                return None

            # Parse the JSON response, handling potential markdown fences
            cleaned = agent_response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            return json.loads(cleaned)

        except requests.exceptions.Timeout:
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Cortex Agent timeout after {timeout}s, "
                    f"retrying in {delay_seconds}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.warning(f"Cortex Agent timeout after {__MAX_RETRIES} attempts")
                return None

        except requests.exceptions.HTTPError as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )
            error_body = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_body = e.response.text[:500]
                except (AttributeError, TypeError):
                    pass

            # Only retry on transient status codes
            if status_code in __RETRYABLE_STATUS_CODES and attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Cortex Agent HTTP {status_code}, "
                    f"retrying in {delay_seconds}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.warning(f"Cortex Agent HTTP error: {e}")
                if error_body:
                    log.warning(f"Response body: {error_body}")
                return None

        except requests.exceptions.ConnectionError as e:
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Cortex Agent connection error: {e}, "
                    f"retrying in {delay_seconds}s "
                    f"(attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.warning(f"Cortex Agent connection failed after {__MAX_RETRIES} attempts: {e}")
                return None

        except json.JSONDecodeError as e:
            log.warning(f"Failed to parse Cortex Agent response as JSON: {e}")
            if agent_response:
                log.warning(f"Raw response: {agent_response[:500]}")
            return None

        except requests.exceptions.RequestException as e:
            log.warning(f"Cortex Agent request error: {e}")
            return None

    return None


def build_discovery_prompt(trial_records):
    """
    Build the Discovery Agent prompt to analyze seed trials and recommend related trials.

    The agent identifies competing therapies, same drug class, same patient population,
    and recommends specific NCT IDs or search terms to discover related trials.

    Args:
        trial_records: Dict mapping nct_id to flat trial records

    Returns:
        Formatted prompt string for the discovery agent
    """
    # Build a summary of seed trials for the agent
    trial_summaries = []
    for nct_id, record in list(trial_records.items())[:10]:
        summary = (
            f"- {nct_id}: {record.get('brief_title', 'N/A')}\n"
            f"  Status: {record.get('overall_status', 'N/A')}, "
            f"Phase: {record.get('phases', 'N/A')}\n"
            f"  Interventions: {record.get('interventions', 'N/A')[:200]}\n"
            f"  Sponsor: {record.get('lead_sponsor_name', 'N/A')}"
        )
        trial_summaries.append(summary)

    trials_text = "\n".join(trial_summaries)

    return (
        "You are a clinical research intelligence analyst. Analyze these clinical "
        "trials and identify related trials that should be monitored. Look for:\n"
        "1. Competing therapies targeting the same condition with different mechanisms\n"
        "2. Trials using the same drug class but for different indications\n"
        "3. Trials from competing sponsors in the same therapeutic area\n"
        "4. Trials with similar patient populations that could affect recruitment\n\n"
        f"SEED TRIALS:\n{trials_text}\n\n"
        "Based on your analysis, recommend 3-5 search terms to discover related trials. "
        "Focus on interventions, drug names, or specific conditions that would surface "
        "trials not already in the seed set.\n\n"
        "IMPORTANT: Be concise. Keep analysis_summary under 200 words. "
        "Return JSON only, no markdown fences, no other text:\n"
        "{\n"
        '  "analysis_summary": "...",\n'
        '  "recommended_searches": [\n'
        '    {"search_term": "...", "search_type": "intervention|condition|sponsor", '
        '"rationale": "..."}\n'
        "  ],\n"
        '  "competing_therapies_identified": ["..."],\n'
        '  "recruitment_overlap_risk": "HIGH|MEDIUM|LOW",\n'
        '  "therapeutic_landscape_gaps": ["..."]\n'
        "}"
    )


def build_optimist_prompt(trial_record):
    """
    Build the Optimist Agent prompt for a clinical trial.

    Evaluates trial design strengths: sample size, randomization, blinding,
    endpoint selection, and sponsor track record.

    Args:
        trial_record: Flat trial record dictionary

    Returns:
        Formatted prompt string for the optimist analyst
    """
    return (
        "You are an optimistic clinical trial design expert. Your job is to identify "
        "the STRENGTHS of this trial's design and why it is likely to succeed. "
        "Evaluate with a focus on what makes this trial well-designed.\n\n"
        f"NCT ID: {trial_record.get('nct_id')}\n"
        f"Title: {trial_record.get('brief_title', 'N/A')}\n"
        f"Summary: {trial_record.get('brief_summary', 'N/A')[:500]}\n"
        f"Phase: {trial_record.get('phases', 'N/A')}\n"
        f"Study Type: {trial_record.get('study_type', 'N/A')}\n"
        f"Allocation: {trial_record.get('allocation', 'N/A')}\n"
        f"Intervention Model: {trial_record.get('intervention_model', 'N/A')}\n"
        f"Masking: {trial_record.get('masking', 'N/A')}\n"
        f"Primary Purpose: {trial_record.get('primary_purpose', 'N/A')}\n"
        f"Enrollment: {trial_record.get('enrollment_count', 'N/A')} "
        f"({trial_record.get('enrollment_type', 'N/A')})\n"
        f"Sponsor: {trial_record.get('lead_sponsor_name', 'N/A')} "
        f"({trial_record.get('lead_sponsor_class', 'N/A')})\n"
        f"Status: {trial_record.get('overall_status', 'N/A')}\n"
        f"Conditions: {trial_record.get('conditions', 'N/A')}\n"
        f"Interventions: {trial_record.get('interventions', 'N/A')[:300]}\n\n"
        "Evaluate this trial's design strengths:\n"
        "1. Is the sample size adequate for the study type and phase?\n"
        "2. Is the randomization and blinding approach appropriate?\n"
        "3. Are the endpoints well-chosen for regulatory approval?\n"
        "4. Does the sponsor have a strong track record?\n"
        "5. What is the overall probability of success?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "design_strength_score": <1-10>,\n'
        '  "sample_size_assessment": "ADEQUATE|BORDERLINE|UNDERPOWERED|OVERPOWERED",\n'
        '  "randomization_quality": "EXCELLENT|GOOD|ACCEPTABLE|POOR",\n'
        '  "blinding_quality": "DOUBLE_BLIND|SINGLE_BLIND|OPEN_LABEL_JUSTIFIED|'
        'OPEN_LABEL_CONCERN",\n'
        '  "endpoint_quality": "STRONG|MODERATE|WEAK",\n'
        '  "sponsor_strength": "ESTABLISHED|EMERGING|UNKNOWN",\n'
        '  "success_probability": "HIGH|MODERATE|LOW",\n'
        '  "key_strengths": ["..."],\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_skeptic_prompt(trial_record):
    """
    Build the Skeptic Agent prompt for a clinical trial.

    Flags methodology risks: dropout potential, endpoint concerns, statistical
    power, and regulatory hurdles.

    Args:
        trial_record: Flat trial record dictionary

    Returns:
        Formatted prompt string for the skeptic analyst
    """
    return (
        "You are a skeptical clinical trial methodology reviewer. Your job is to "
        "identify RISKS and WEAKNESSES in this trial's design. Be critical and "
        "flag concerns that could lead to failure, rejection, or misleading results.\n\n"
        f"NCT ID: {trial_record.get('nct_id')}\n"
        f"Title: {trial_record.get('brief_title', 'N/A')}\n"
        f"Summary: {trial_record.get('brief_summary', 'N/A')[:500]}\n"
        f"Phase: {trial_record.get('phases', 'N/A')}\n"
        f"Study Type: {trial_record.get('study_type', 'N/A')}\n"
        f"Allocation: {trial_record.get('allocation', 'N/A')}\n"
        f"Intervention Model: {trial_record.get('intervention_model', 'N/A')}\n"
        f"Masking: {trial_record.get('masking', 'N/A')}\n"
        f"Primary Purpose: {trial_record.get('primary_purpose', 'N/A')}\n"
        f"Enrollment: {trial_record.get('enrollment_count', 'N/A')} "
        f"({trial_record.get('enrollment_type', 'N/A')})\n"
        f"Sponsor: {trial_record.get('lead_sponsor_name', 'N/A')} "
        f"({trial_record.get('lead_sponsor_class', 'N/A')})\n"
        f"Status: {trial_record.get('overall_status', 'N/A')}\n"
        f"Conditions: {trial_record.get('conditions', 'N/A')}\n"
        f"Interventions: {trial_record.get('interventions', 'N/A')[:300]}\n"
        f"Eligibility: {trial_record.get('eligibility_criteria', 'N/A')[:300]}\n\n"
        "Critically evaluate this trial's methodology risks:\n"
        "1. What is the dropout risk given the patient population and treatment?\n"
        "2. Are there endpoint concerns (surrogate vs. hard endpoints)?\n"
        "3. Is the statistical power sufficient for the enrollment size?\n"
        "4. What regulatory hurdles could block approval even if results are positive?\n"
        "5. Are there ethical or recruitment concerns?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "methodology_risk_score": <1-10>,\n'
        '  "dropout_risk": "HIGH|MODERATE|LOW",\n'
        '  "endpoint_concerns": "SIGNIFICANT|MINOR|NONE",\n'
        '  "statistical_power_risk": "UNDERPOWERED|ADEQUATE|WELL_POWERED",\n'
        '  "regulatory_hurdle_risk": "HIGH|MODERATE|LOW",\n'
        '  "recruitment_feasibility": "CHALLENGING|FEASIBLE|EASY",\n'
        '  "failure_probability": "HIGH|MODERATE|LOW",\n'
        '  "key_risks": ["..."],\n'
        '  "reasoning": "..."\n'
        "}"
    )


def build_consensus_prompt(trial_record, optimist_result, skeptic_result):
    """
    Build the Consensus synthesizer prompt that reads both analyst assessments.

    Produces a balanced final evaluation with a disagreement flag highlighting
    trials where the Optimist and Skeptic significantly disagree.

    Args:
        trial_record: Flat trial record dictionary
        optimist_result: Optimist Agent JSON result
        skeptic_result: Skeptic Agent JSON result

    Returns:
        Formatted prompt string for the neutral synthesizer
    """
    return (
        "You are a neutral clinical research director synthesizing two analyst "
        "assessments of the same clinical trial. One analyst (Optimist) focused on "
        "design strengths; the other (Skeptic) focused on methodology risks. "
        "Your job is to produce a balanced final assessment.\n\n"
        f"NCT ID: {trial_record.get('nct_id')}\n"
        f"Title: {trial_record.get('brief_title', 'N/A')}\n"
        f"Phase: {trial_record.get('phases', 'N/A')}\n\n"
        "OPTIMIST ASSESSMENT:\n"
        f"{json.dumps(optimist_result, indent=2)}\n\n"
        "SKEPTIC ASSESSMENT:\n"
        f"{json.dumps(skeptic_result, indent=2)}\n\n"
        "Synthesize these perspectives:\n"
        "1. Where do the analysts AGREE? Where do they DISAGREE?\n"
        "2. Which analyst's assessment is MORE PERSUASIVE overall and why?\n"
        "3. What is the balanced overall trial quality assessment?\n"
        "4. Does this trial need human expert review due to significant disagreement?\n"
        "5. What is the key investment/monitoring recommendation?\n\n"
        "Return JSON only, no other text:\n"
        "{\n"
        '  "overall_quality": "EXCELLENT|GOOD|FAIR|POOR",\n'
        '  "consensus_score": <1-10>,\n'
        '  "debate_winner": "OPTIMIST|SKEPTIC|DRAW",\n'
        '  "winner_rationale": "...",\n'
        '  "agreement_areas": ["..."],\n'
        '  "disagreement_areas": ["..."],\n'
        '  "disagreement_flag": true/false,\n'
        '  "disagreement_severity": "NONE|MINOR|SIGNIFICANT|FUNDAMENTAL",\n'
        '  "human_review_recommended": true/false,\n'
        '  "monitoring_priority": "WATCH_CLOSELY|PERIODIC_REVIEW|LOW_PRIORITY",\n'
        '  "recommended_action": "...",\n'
        '  "executive_summary": "..."\n'
        "}"
    )


def upsert_assessment(table_name, nct_id, assessment, assessment_type):
    """
    Upsert an AI assessment record to the specified table.

    Args:
        table_name: Destination table name
        nct_id: NCT identifier
        assessment: Parsed JSON assessment from Cortex Agent
        assessment_type: Type label (discovery, optimist, skeptic, consensus)

    Returns:
        bool: True if upserted, False if assessment was None
    """
    if assessment is None:
        log.warning(f"Skipping {assessment_type} assessment for {nct_id}: no response")
        return False

    record = {"nct_id": nct_id, "assessment_type": assessment_type}
    record.update(flatten_dict(assessment))
    record["assessed_at"] = datetime.now(timezone.utc).isoformat()

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=table_name, data=record)
    return True


def run_discovery_phase(session, configuration, trial_records, state):
    """
    Phase 2: Agent-Driven Discovery.

    Cortex Agent analyzes seed trials and recommends related trials to fetch.
    The connector then fetches those discovered trials from the API.

    Args:
        session: ClinicalTrials.gov requests.Session
        configuration: Configuration dictionary
        trial_records: Dict mapping nct_id to flat trial records from seed phase
        state: State dictionary for checkpointing

    Returns:
        Tuple of (discovered_studies, discovery_result_dict)
    """
    max_discoveries = int(configuration.get("max_discoveries", str(__DEFAULT_MAX_DISCOVERIES)))

    if not trial_records:
        log.info("No seed trials to analyze for discovery")
        return [], None

    log.info(
        f"Running Discovery Agent on {len(trial_records)} seed trials "
        f"(max discoveries: {max_discoveries})"
    )

    # Ask Cortex Agent to analyze seed trials and recommend searches
    cortex_session = _create_cortex_session(configuration)
    discovery_prompt = build_discovery_prompt(trial_records)
    discovery_result = call_cortex_agent(configuration, discovery_prompt, cortex_session)
    cortex_session.close()

    if not discovery_result:
        log.warning("Discovery Agent returned no results")
        return [], None

    # Upsert the discovery insight with a synthetic nct_id for the analysis
    discovery_record = {
        "nct_id": "DISCOVERY_ANALYSIS",
        "assessment_type": "discovery",
        "assessed_at": datetime.now(timezone.utc).isoformat(),
    }
    discovery_record.update(flatten_dict(discovery_result))

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="discovery_insights", data=discovery_record)

    # Execute the recommended searches to discover new trials
    recommended_searches = discovery_result.get("recommended_searches", [])
    if not isinstance(recommended_searches, list):
        log.warning(
            f"Expected list for recommended_searches, "
            f"got {type(recommended_searches).__name__}. Skipping discovery."
        )
        return [], discovery_result

    discovered_studies = []
    existing_nct_ids = set(trial_records.keys())

    log.info(f"Discovery Agent recommended {len(recommended_searches)} searches")

    for search in recommended_searches:
        if not isinstance(search, dict):
            continue
        if len(discovered_studies) >= max_discoveries:
            break

        search_term = search.get("search_term", "")
        search_type = search.get("search_type", "condition")

        if not search_term:
            continue

        # Build search params based on search type
        params = {"pageSize": min(max_discoveries, __DEFAULT_PAGE_SIZE)}
        if search_type == "intervention":
            params["query.intr"] = search_term
        elif search_type == "sponsor":
            params["query.spons"] = search_term
        else:
            params["query.cond"] = search_term

        try:
            data = fetch_data_with_retry(session, __CT_BASE_URL, params=params)
            studies = data.get("studies", [])

            for study in studies:
                if len(discovered_studies) >= max_discoveries:
                    break
                protocol = study.get("protocolSection", {})
                nct_id = protocol.get("identificationModule", {}).get("nctId")
                if nct_id and nct_id not in existing_nct_ids:
                    discovered_studies.append(study)
                    existing_nct_ids.add(nct_id)

        except RuntimeError as e:
            log.warning(f"Discovery search failed for '{search_term}': {e}")
            continue

    log.info(f"Discovered {len(discovered_studies)} new trials via agent recommendations")

    return discovered_studies, discovery_result


def run_debate_phase(configuration, trial_records, state):
    """
    Phase 3: Multi-Agent Debate.

    Two Cortex Agent personas (Optimist + Skeptic) evaluate each trial, followed
    by a Consensus synthesizer. Checkpoints after each trial to prevent data loss.

    Args:
        configuration: Configuration dictionary
        trial_records: Dict mapping nct_id to flat trial records to debate
        state: State dictionary for checkpointing

    Returns:
        Tuple of (debate_count, disagreement_count)
    """
    max_debates = _optional_int(configuration, "max_debates", __DEFAULT_MAX_DEBATES)
    debate_count = 0
    disagreement_count = 0

    log.info(
        f"Starting Multi-Agent Debate for up to {max_debates} trials "
        f"(3 Cortex calls per trial)"
    )

    cortex_session = _create_cortex_session(configuration)

    for nct_id, trial_record in trial_records.items():
        if debate_count >= max_debates:
            log.info(f"Reached max_debates limit ({max_debates}), stopping debate")
            break

        # Agent 1: Optimist
        optimist_prompt = build_optimist_prompt(trial_record)
        optimist_result = call_cortex_agent(configuration, optimist_prompt, cortex_session)
        upsert_assessment("optimist_assessments", nct_id, optimist_result, "optimist")

        # Agent 2: Skeptic
        skeptic_prompt = build_skeptic_prompt(trial_record)
        skeptic_result = call_cortex_agent(configuration, skeptic_prompt, cortex_session)
        upsert_assessment("skeptic_assessments", nct_id, skeptic_result, "skeptic")

        # Agent 3: Consensus (only if both agents returned results)
        if optimist_result and skeptic_result:
            consensus_prompt = build_consensus_prompt(
                trial_record, optimist_result, skeptic_result
            )
            consensus_result = call_cortex_agent(configuration, consensus_prompt, cortex_session)
            upsert_assessment("debate_consensus", nct_id, consensus_result, "consensus")

            if consensus_result and consensus_result.get("disagreement_flag"):
                disagreement_count += 1
        else:
            log.warning(
                f"Skipping consensus for {nct_id}: " f"missing optimist or skeptic assessment"
            )

        debate_count += 1

        # Save the progress by checkpointing the state. This is important for ensuring
        # that the sync process can resume from the correct position in case of next sync
        # or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells
        # Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at
        # the end.
        # Learn more about how and where to checkpoint by reading our best practices
        # documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

    cortex_session.close()
    return debate_count, disagreement_count


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
    log.warning(
        "Example: all_things_ai/tutorials " ": snowflake-cortex-code-clinical-trial-intelligence"
    )

    validate_configuration(configuration)
    session = create_session()

    # The ClinicalTrials.gov session is used across all three phases. Wrap the
    # sync body in try/finally so the session is always closed even when an
    # unexpected error propagates out of Cortex enrichment.
    try:
        # ---------------------------------------------------------------------
        # Phase 1: Fetch, upsert, and checkpoint seed trials page by page
        # ---------------------------------------------------------------------
        log.info("Phase 1: Fetching seed trials from ClinicalTrials.gov API")
        seed_records = fetch_and_upsert_seed_trials(session, configuration, state)

        if not seed_records:
            log.info("No new or modified trials found")
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            return

        log.info(f"Phase 1 complete: {len(seed_records)} seed trial records upserted")

        # Check if Cortex is enabled for Phases 2 and 3
        is_cortex_enabled = _parse_bool(configuration.get("enable_cortex"), default=False)

        if not is_cortex_enabled:
            log.info("Cortex enrichment disabled, skipping Discovery and Debate phases")
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            log.info("Sync complete")
            return

        # ---------------------------------------------------------------------
        # Phase 2: Agent-Driven Discovery
        # ---------------------------------------------------------------------
        log.info("Phase 2: Running Agent-Driven Discovery with Cortex")
        discovered_studies, discovery_result = run_discovery_phase(
            session, configuration, seed_records, state
        )

        all_records = dict(seed_records)

        if discovered_studies:
            disc_count, disc_records = upsert_trials(discovered_studies)
            log.info(f"Upserted {disc_count} discovered trial records")
            all_records.update(disc_records)

            # Upsert per-trial discovery insights for discovered trials
            if discovery_result:
                for nct_id in disc_records:
                    insight_record = {
                        "nct_id": nct_id,
                        "assessment_type": "discovery",
                        "discovery_source": "agent_recommended",
                        "assessed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The first argument is the name of the destination table.
                    # The second argument is a dictionary containing the record to be upserted.
                    op.upsert(table="discovery_insights", data=insight_record)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # ---------------------------------------------------------------------
        # Phase 3: Multi-Agent Debate
        # ---------------------------------------------------------------------
        log.info("Phase 3: Running Multi-Agent Debate with Cortex")
        debate_count, disagreement_count = run_debate_phase(configuration, all_records, state)
        log.info(
            f"Multi-Agent Debate complete: {debate_count} trials debated, "
            f"{disagreement_count} with significant disagreements"
        )

        # Final checkpoint
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info("Sync complete")
    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from
# the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug
# command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during
# development, such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in
# production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
