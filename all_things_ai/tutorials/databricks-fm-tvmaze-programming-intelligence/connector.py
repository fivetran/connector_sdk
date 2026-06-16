"""
TVMaze Programming Intelligence Connector

This connector syncs TV show metadata from the TVMaze API and enriches each show with
AI-powered multi-agent debate using Databricks ai_query(). A Programming Optimist and
Programming Skeptic debate each show's renewal probability and programming value; a
Consensus agent synthesizes a renewal rating and sets a disagreement_flag for shows
that warrant human programming team review.

The disagreement_flag is the product: pre-computed analyst contention flags shows for
human review without requiring dashboards or scheduled jobs.

Data provided by TVmaze (https://www.tvmaze.com), licensed under CC BY-SA 4.0.

See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For generating unique identifiers for Genie Space sample questions
import uuid

# For ISO-8601 enrichment timestamps
from datetime import datetime, timezone

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# TVMaze API base URL — no authentication required
__TVMAZE_BASE_URL = "https://api.tvmaze.com"
__API_TIMEOUT_SECONDS = 30

# Retry and rate limiting constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

# TVMaze returns up to 250 shows per page; checkpoint every 5 pages during initial sync
__CHECKPOINT_EVERY_N_PAGES = 5

# Databricks SQL Statement API async polling constants
__SQL_POLL_INTERVAL_SECONDS = 3
__SQL_MAX_POLL_ATTEMPTS = 40

# Sync defaults — overridden by configuration
__DEFAULT_MAX_PAGES = 10
__DEFAULT_MAX_ENRICHMENTS = 50
__DEFAULT_DATABRICKS_TIMEOUT = 120

# Number of cast members to include in the debate context string
__MAX_CAST_CONTEXT = 5

# TVMaze rate limit is 20 req/10s; 0.6s sleep keeps us safely under 2 req/s
__TVMAZE_RATE_LIMIT_SLEEP = 0.6


def _is_placeholder(value):
    """Return True if value is None, empty, or an angle-bracket placeholder."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped == "" or (stripped.startswith("<") and stripped.endswith(">"))


def _parse_bool(value, default=False):
    """Parse a bool or string representation of a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return default


def _optional_int(configuration, key, default):
    """Read an optional integer from configuration, returning default for placeholders."""
    raw = configuration.get(key)
    if _is_placeholder(raw):
        return default
    try:
        val = int(str(raw).strip())
        return val if val > 0 else default
    except (ValueError, TypeError):
        return default


def _optional_str(configuration, key, default=None):
    """Read an optional string from configuration, returning default for placeholders."""
    raw = configuration.get(key)
    if _is_placeholder(raw):
        return default
    return str(raw).strip() if raw else default


def _extract_json(raw):
    """Strip markdown code fences from model response and return a clean JSON string."""
    if not raw:
        return raw
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]  # drop opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop closing ```
        stripped = "\n".join(lines).strip()
    return stripped


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    for bool_key in ("enable_enrichment", "enable_genie_space"):
        raw = configuration.get(bool_key, "false")
        if not _is_placeholder(raw) and not isinstance(raw, bool):
            if str(raw).strip().lower() not in ("true", "false", "1", "0", "yes", "no"):
                raise ValueError(f"Configuration value for '{bool_key}' must be true or false")

    enable_enrichment = _parse_bool(configuration.get("enable_enrichment", "false"))
    enable_genie_space = _parse_bool(configuration.get("enable_genie_space", "false"))

    if enable_enrichment or enable_genie_space:
        for key in ("databricks_workspace_url", "databricks_token", "databricks_warehouse_id"):
            if key not in configuration or _is_placeholder(configuration.get(key)):
                raise ValueError(
                    f"Missing required configuration value: {key} "
                    f"(required when enable_enrichment or enable_genie_space is true)"
                )

    if enable_genie_space:
        genie_table = configuration.get("genie_table_identifier")
        if _is_placeholder(genie_table):
            raise ValueError(
                "Configuration value 'genie_table_identifier' (e.g. catalog.schema.shows) "
                "is required when enable_genie_space is true"
            )

    max_pages = _optional_int(configuration, "initial_sync_max_pages", __DEFAULT_MAX_PAGES)
    if max_pages > 300:
        raise ValueError(
            f"initial_sync_max_pages={max_pages} exceeds the ceiling of 300 (75,000 shows). "
            f"Reduce this value."
        )

    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    if max_enrichments > 500:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds the ceiling of 500. "
            f"Reduce this value to control AI query costs."
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
        {
            "table": "shows",
            "primary_key": ["show_id"],
            "columns": {
                "show_id": "INT",
                "name": "STRING",
                "type": "STRING",
                "language": "STRING",
                "genres": "STRING",
                "status": "STRING",
                "runtime": "INT",
                "average_runtime": "INT",
                "premiered": "STRING",
                "ended": "STRING",
                "official_site": "STRING",
                "network_name": "STRING",
                "network_country_code": "STRING",
                "web_channel_name": "STRING",
                "schedule_time": "STRING",
                "schedule_days": "STRING",
                "summary": "STRING",
                "image_medium": "STRING",
                "image_original": "STRING",
                "rating_average": "FLOAT",
                "weight": "INT",
                "updated": "INT",
                "optimist_assessment": "STRING",
                "skeptic_assessment": "STRING",
                "renewal_rating": "STRING",
                "disagreement_flag": "BOOLEAN",
                "debate_winner": "STRING",
                "consensus_rationale": "STRING",
                "human_review_recommended": "BOOLEAN",
                "enrichment_timestamp": "STRING",
            },
        }
    ]


def fetch_data_with_retry(session, url, params=None):
    """
    Fetch data from the TVMaze API with exponential backoff retry logic.

    Args:
        session: requests.Session for connection pooling
        url: Full URL to fetch
        params: Optional query parameters dict or list of tuples

    Returns:
        JSON response as dict or list, or None if HTTP 404 (end of pagination)

    Raises:
        RuntimeError: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=__API_TIMEOUT_SECONDS)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.severe(f"Connection failed after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}")

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout for {url}: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay_seconds = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(
                    f"Retrying in {delay_seconds}s (attempt {attempt + 1}/{__MAX_RETRIES})"
                )
                time.sleep(delay_seconds)
            else:
                log.severe(f"Timeout after {__MAX_RETRIES} attempts: {url}")
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}")

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )

            if status_code in (401, 403):
                msg = f"HTTP {status_code}: Check your API credentials. URL: {url}"
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


def flatten_show(show):
    """
    Normalize a TVMaze show record into a flat dictionary suitable for Fivetran upsert.

    Args:
        show: Raw TVMaze show dict from the API

    Returns:
        Flattened dict with scalar values only
    """
    network = show.get("network") or {}
    network_country = network.get("country") or {}
    web_channel = show.get("webChannel") or {}
    schedule = show.get("schedule") or {}
    image = show.get("image") or {}
    rating = show.get("rating") or {}

    return {
        "show_id": show.get("id"),
        "name": show.get("name"),
        "type": show.get("type"),
        "language": show.get("language"),
        "genres": json.dumps(show.get("genres") or []),
        "status": show.get("status"),
        "runtime": show.get("runtime"),
        "average_runtime": show.get("averageRuntime"),
        "premiered": show.get("premiered"),
        "ended": show.get("ended"),
        "official_site": show.get("officialSite"),
        "network_name": network.get("name"),
        "network_country_code": network_country.get("code"),
        "web_channel_name": web_channel.get("name"),
        "schedule_time": schedule.get("time"),
        "schedule_days": json.dumps(schedule.get("days") or []),
        "summary": show.get("summary"),
        "image_medium": image.get("medium"),
        "image_original": image.get("original"),
        "rating_average": rating.get("average"),
        "weight": show.get("weight"),
        "updated": show.get("updated"),
    }


def build_show_context(show, embedded=None):
    """
    Build a structured context string for the multi-agent debate from a show's data.

    Args:
        show: Flattened show dict (output of flatten_show)
        embedded: Optional _embedded dict with cast and episodes from TVMaze embed

    Returns:
        Formatted context string for AI prompt injection
    """
    genres_list = json.loads(show.get("genres") or "[]")
    schedule_days_list = json.loads(show.get("schedule_days") or "[]")
    network = show.get("network_name") or show.get("web_channel_name") or "Unknown"

    lines = [
        f"Show: {show.get('name')} (ID: {show.get('show_id')})",
        f"Type: {show.get('type')} | Language: {show.get('language')}",
        f"Status: {show.get('status')}",
        f"Genres: {', '.join(genres_list) if genres_list else 'Unknown'}",
        f"Network: {network} ({show.get('network_country_code') or 'Unknown'})",
        f"Runtime: {show.get('runtime') or show.get('average_runtime') or 'Unknown'} minutes",
        f"Premiered: {show.get('premiered') or 'Unknown'}",
        f"Ended: {show.get('ended') or 'Still running'}",
        f"Schedule: {', '.join(schedule_days_list) or 'Unknown'} at {show.get('schedule_time') or 'Unknown'}",
        f"Rating: {show.get('rating_average') or 'No rating'}",
        f"Popularity Weight: {show.get('weight') or 0}",
    ]

    if embedded:
        cast_list = embedded.get("cast") or []
        if cast_list:
            top_cast = [
                c.get("person", {}).get("name", "Unknown") for c in cast_list[:__MAX_CAST_CONTEXT]
            ]
            lines.append(f"Top Cast: {', '.join(top_cast)}")

        episodes_list = embedded.get("episodes") or []
        if episodes_list:
            max_season = max((e.get("season", 0) for e in episodes_list), default=0)
            lines.append(f"Total Episodes: {len(episodes_list)} across {max_season} season(s)")

    return "\n".join(lines)


def call_ai_query(session, configuration, prompt):
    """
    Execute an AI query via Databricks SQL Statement API with async polling.

    Args:
        session: requests.Session with Databricks Authorization header set
        configuration: connector configuration dict
        prompt: structured prompt string for the AI model

    Returns:
        AI response string, or None if the query times out or fails
    """
    workspace_url = configuration["databricks_workspace_url"].rstrip("/")
    warehouse_id = configuration["databricks_warehouse_id"]
    model = configuration.get("databricks_model", "databricks-claude-sonnet-4-6")

    escaped_prompt = prompt.replace("'", "\\'").replace("\n", "\\n")
    sql = f"SELECT ai_query('{model}', '{escaped_prompt}') AS response"

    payload = {
        "statement": sql,
        "warehouse_id": warehouse_id,
        "wait_timeout": "0s",
        "on_wait_timeout": "CONTINUE",
    }

    try:
        resp = session.post(
            f"{workspace_url}/api/2.0/sql/statements",
            json=payload,
            timeout=__API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.Timeout:
        log.warning("Timeout submitting AI query to Databricks")
        return None
    except requests.exceptions.HTTPError as e:
        log.warning(f"HTTP error submitting AI query: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        log.warning(f"Connection error submitting AI query: {e}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Request error submitting AI query: {e}")
        return None
    except json.JSONDecodeError as e:
        log.warning(f"JSON decode error from AI query response: {e}")
        return None

    statement_id = result.get("statement_id")
    if not statement_id:
        log.warning("No statement_id returned from Databricks SQL API")
        return None

    for poll_attempt in range(__SQL_MAX_POLL_ATTEMPTS):
        state_val = result.get("status", {}).get("state", "")

        if state_val == "SUCCEEDED":
            try:
                rows = result.get("result", {}).get("data_array", [])
                if rows and rows[0]:
                    return rows[0][0]
                return None
            except (IndexError, TypeError, KeyError):
                log.warning("Could not extract result from Databricks SQL response")
                return None

        if state_val in ("FAILED", "CANCELED", "CLOSED"):
            error_msg = result.get("status", {}).get("error", {}).get("message", "Unknown error")
            log.warning(f"AI query {state_val}: {error_msg}")
            return None

        if state_val not in ("PENDING", "RUNNING"):
            log.info(f"Unexpected Databricks SQL state: {state_val}")
            return None

        if poll_attempt == 0:
            log.fine(f"AI query PENDING, polling statement {statement_id}")

        time.sleep(__SQL_POLL_INTERVAL_SECONDS)

        try:
            poll_resp = session.get(
                f"{workspace_url}/api/2.0/sql/statements/{statement_id}",
                timeout=__API_TIMEOUT_SECONDS,
            )
            poll_resp.raise_for_status()
            result = poll_resp.json()
        except requests.exceptions.Timeout:
            log.warning(f"Timeout polling AI query statement {statement_id}")
            return None
        except requests.exceptions.RequestException as e:
            log.warning(f"Error polling AI query statement {statement_id}: {e}")
            return None
        except json.JSONDecodeError as e:
            log.warning(f"JSON decode error polling statement {statement_id}: {e}")
            return None

    log.warning(
        f"AI query timed out after {__SQL_MAX_POLL_ATTEMPTS * __SQL_POLL_INTERVAL_SECONDS}s"
    )
    return None


def run_debate(databricks_session, configuration, show_record, embedded, state):
    """
    Run the three-agent Programming Optimist / Skeptic / Consensus debate for one show.

    Calls ai_query() three times: Optimist, Skeptic, then Consensus. Upserts the enriched
    record and checkpoints state after all three complete so a partial sync can resume
    without re-enriching already-processed shows.

    Args:
        databricks_session: requests.Session with Databricks Authorization header set
        configuration: connector configuration dict
        show_record: flattened show dict with show_id and all source columns
        embedded: optional _embedded dict (cast + episodes) fetched from TVMaze embed endpoint
        state: current sync state dict (mutated in place)

    Returns:
        Enriched show_record dict with AI columns populated
    """
    show_id = show_record.get("show_id")
    show_name = show_record.get("name", f"Show {show_id}")
    log.info(f"Debating: {show_name} (ID: {show_id})")

    context = build_show_context(show_record, embedded)
    enrichment_ts = datetime.now(timezone.utc).isoformat()

    # --- Agent 1: Programming Optimist ---
    optimist_prompt = (
        "You are a Programming Optimist analyst for a TV network. Given the following TV show "
        "profile, argue why this show should be renewed. Consider network positioning, genre "
        "momentum, audience appeal, cast strength, episode trajectory, and any signals that "
        "support continuation. Respond ONLY in valid JSON with these exact keys: "
        "argument (string, 2-3 sentences), key_signals (array of 3 strings), "
        "confidence_score (float 0.0-1.0), renewal_probability (HIGH, MEDIUM, or LOW)."
        f"\\n\\nShow Profile:\\n{context}"
    )
    optimist_raw = call_ai_query(databricks_session, configuration, optimist_prompt)
    optimist_assessment = optimist_raw or json.dumps(
        {
            "argument": "Enrichment unavailable",
            "key_signals": [],
            "confidence_score": 0.5,
            "renewal_probability": "MEDIUM",
        }
    )

    # --- Agent 2: Programming Skeptic ---
    skeptic_prompt = (
        "You are a Programming Skeptic analyst for a TV network. Given the following TV show "
        "profile, argue why this show faces cancellation risk. Consider genre saturation, "
        "declining engagement signals, scheduling challenges, network strategy shifts, cast "
        "churn risk, and any factors that support cautious programming. Respond ONLY in valid "
        "JSON with these exact keys: argument (string, 2-3 sentences), key_risks (array of 3 "
        "strings), confidence_score (float 0.0-1.0), cancellation_risk (HIGH, MEDIUM, or LOW)."
        f"\\n\\nShow Profile:\\n{context}"
    )
    skeptic_raw = call_ai_query(databricks_session, configuration, skeptic_prompt)
    skeptic_assessment = skeptic_raw or json.dumps(
        {
            "argument": "Enrichment unavailable",
            "key_risks": [],
            "confidence_score": 0.5,
            "cancellation_risk": "MEDIUM",
        }
    )

    # --- Agent 3: Consensus ---
    consensus_prompt = (
        "You are a Consensus Moderator synthesizing a debate between two TV programming analysts. "
        "Set disagreement_flag to true if the analysts' confidence scores differ by more than 0.3, "
        "or if their renewal/cancellation assessments meaningfully conflict. "
        "Respond ONLY in valid JSON with these exact keys: "
        "renewal_rating (HIGH, MEDIUM, or LOW), disagreement_flag (boolean), "
        "debate_winner (OPTIMIST, SKEPTIC, or DRAW), "
        "consensus_rationale (string, 1-2 sentences), "
        "human_review_recommended (boolean, true when disagreement_flag is true or renewal_rating is LOW)."
        f"\\n\\nOPTIMIST ASSESSMENT:\\n{optimist_assessment}"
        f"\\n\\nSKEPTIC ASSESSMENT:\\n{skeptic_assessment}"
        f"\\n\\nShow Profile:\\n{context}"
    )
    consensus_raw = call_ai_query(databricks_session, configuration, consensus_prompt)

    renewal_rating = "MEDIUM"
    disagreement_flag = False
    debate_winner = "DRAW"
    consensus_rationale = "Consensus enrichment unavailable"
    human_review_recommended = False

    if consensus_raw:
        try:
            consensus = json.loads(_extract_json(consensus_raw))
            renewal_rating = str(consensus.get("renewal_rating", "MEDIUM")).upper()
            if renewal_rating not in ("HIGH", "MEDIUM", "LOW"):
                renewal_rating = "MEDIUM"
            disagreement_flag = _parse_bool(consensus.get("disagreement_flag", False))
            debate_winner = str(consensus.get("debate_winner", "DRAW")).upper()
            if debate_winner not in ("OPTIMIST", "SKEPTIC", "DRAW"):
                debate_winner = "DRAW"
            consensus_rationale = str(consensus.get("consensus_rationale", ""))
            human_review_recommended = _parse_bool(
                consensus.get("human_review_recommended", False)
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            log.warning(f"Could not parse consensus JSON for show {show_id}")

    enriched = {
        **show_record,
        "optimist_assessment": optimist_assessment,
        "skeptic_assessment": skeptic_assessment,
        "renewal_rating": renewal_rating,
        "disagreement_flag": disagreement_flag,
        "debate_winner": debate_winner,
        "consensus_rationale": consensus_rationale,
        "human_review_recommended": human_review_recommended,
        "enrichment_timestamp": enrichment_ts,
    }

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="shows", data=enriched)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state=state)

    return enriched


def create_genie_space(databricks_session, configuration, state):
    """
    Create a Databricks Genie Space for natural language TV programming analytics.

    Checks state for an existing space_id to avoid recreation on subsequent syncs.

    Args:
        databricks_session: requests.Session with Databricks Authorization header set
        configuration: connector configuration dict
        state: current sync state dict (mutated in place with genie_space_id)
    """
    if state.get("genie_space_id"):
        log.info(f"Genie Space already exists: {state['genie_space_id']}")
        return

    workspace_url = configuration["databricks_workspace_url"].rstrip("/")
    genie_table = configuration.get("genie_table_identifier", "")
    space_title = "TVMaze Programming Intelligence"

    sample_questions = [
        {
            "id": str(uuid.uuid4()),
            "question": "Which running shows have HIGH renewal rating but disagreement_flag = TRUE?",
        },
        {
            "id": str(uuid.uuid4()),
            "question": "Show me crime dramas on broadcast networks that the Skeptic flagged as high cancellation risk",
        },
        {
            "id": str(uuid.uuid4()),
            "question": "Which genres have the most shows with LOW renewal rating?",
        },
        {
            "id": str(uuid.uuid4()),
            "question": "Rank networks by average renewal rating across their running shows",
        },
        {
            "id": str(uuid.uuid4()),
            "question": "Which shows have human_review_recommended = TRUE and status = Running?",
        },
        {
            "id": str(uuid.uuid4()),
            "question": "What percentage of shows have disagreement_flag = TRUE by genre?",
        },
    ]

    serialized_space = json.dumps(
        {
            "title": space_title,
            "description": (
                "Natural language programming analytics for TV show renewal decisions. "
                "The disagreement_flag identifies shows where Programming Optimist and Skeptic "
                "analysts meaningfully disagree, flagging them for human programming team review."
            ),
            "table_identifiers": [genie_table],
            "instructions": (
                "This Genie Space contains TVMaze show metadata enriched with multi-agent AI debate. "
                "Key fields: renewal_rating (HIGH/MEDIUM/LOW), disagreement_flag (true/false), "
                "debate_winner (OPTIMIST/SKEPTIC/DRAW), human_review_recommended (true/false). "
                "Network broadcast shows use network_name; streaming shows use web_channel_name. "
                "Status values: Running, Ended, To Be Determined, In Development. "
                "Filter on disagreement_flag = TRUE or human_review_recommended = TRUE to surface "
                "shows requiring human programming judgment."
            ),
            "sample_questions": sample_questions,
        }
    )

    try:
        resp = databricks_session.post(
            f"{workspace_url}/api/2.0/genie/spaces",
            json={"serialized_space": serialized_space},
            timeout=__API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        space_data = resp.json()
        space_id = space_data.get("id") or space_data.get("space_id")
        if space_id:
            state["genie_space_id"] = space_id
            state["genie_space_name"] = space_title
            log.info(f"Created Genie Space '{space_title}' with ID: {space_id}")
        else:
            log.warning(f"Genie Space created but no ID returned: {space_data}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        log.warning(f"Failed to create Genie Space (HTTP {status_code}): {e}")
    except requests.exceptions.RequestException as e:
        log.warning(f"Failed to create Genie Space: {e}")
    except json.JSONDecodeError as e:
        log.warning(f"JSON decode error creating Genie Space: {e}")


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details and settings for the connector.
        state: A dictionary containing the current state of the sync, used for incremental syncs.
    """
    log.warning("Example: all_things_ai/tutorials : databricks-fm-tvmaze-programming-intelligence")

    validate_configuration(configuration)

    enable_enrichment = _parse_bool(configuration.get("enable_enrichment", "false"))
    enable_genie_space = _parse_bool(configuration.get("enable_genie_space", "false"))
    max_pages = _optional_int(configuration, "initial_sync_max_pages", __DEFAULT_MAX_PAGES)
    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    genre_filter_raw = _optional_str(configuration, "genre_filter")
    status_filter = _optional_str(configuration, "status_filter")

    genre_filter = (
        [g.strip() for g in genre_filter_raw.split(",") if g.strip()] if genre_filter_raw else None
    )

    tvmaze_session = requests.Session()
    tvmaze_session.headers.update({"Accept": "application/json"})

    databricks_session = None

    try:
        # -----------------------------------------------------------------------
        # Phase 1: MOVE — Fetch TV Show Catalog
        # -----------------------------------------------------------------------
        initial_sync_complete = state.get("initial_sync_complete", False)
        shows_this_sync = []

        if not initial_sync_complete:
            start_page = state.get("last_page_synced", -1) + 1
            log.info(f"Initial sync from page {start_page} (max_pages={max_pages})")

            page = start_page
            pages_fetched = 0
            total_shows_synced = state.get("total_shows_synced", 0)

            while pages_fetched < max_pages:
                page_data = fetch_data_with_retry(
                    tvmaze_session,
                    f"{__TVMAZE_BASE_URL}/shows",
                    params={"page": page},
                )

                if page_data is None:
                    log.info(f"Reached end of TVMaze catalog at page {page}")
                    state["initial_sync_complete"] = True
                    initial_sync_complete = True
                    break

                log.info(f"Page {page}: {len(page_data)} shows")

                for show in page_data:
                    flat = flatten_show(show)

                    if genre_filter:
                        show_genres = json.loads(flat.get("genres") or "[]")
                        if not any(g in show_genres for g in genre_filter):
                            continue

                    if status_filter and flat.get("status") != status_filter:
                        continue

                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The first argument is the name of the destination table.
                    # The second argument is a dictionary containing the record to be upserted.
                    op.upsert(table="shows", data=flat)
                    shows_this_sync.append(flat)
                    total_shows_synced += 1

                state["last_page_synced"] = page
                state["total_shows_synced"] = total_shows_synced
                page += 1
                pages_fetched += 1

                if pages_fetched % __CHECKPOINT_EVERY_N_PAGES == 0:
                    log.info(
                        f"Checkpointing after page {page - 1} "
                        f"({total_shows_synced} total shows synced)"
                    )
                    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                    # from the correct position in case of next sync or interruptions.
                    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
                    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
                    # Learn more about how and where to checkpoint by reading our best practices documentation
                    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                    op.checkpoint(state=state)

            if pages_fetched >= max_pages and not initial_sync_complete:
                log.info(
                    f"Reached initial_sync_max_pages limit ({max_pages}). "
                    f"Resuming from page {state['last_page_synced'] + 1} on next sync."
                )

            # Record when initial sync completed so incremental cursor is calibrated
            if initial_sync_complete and not state.get("last_updates_poll"):
                state["last_updates_poll"] = int(time.time())

            log.info(f"Phase 1 complete: {state.get('total_shows_synced', 0)} total shows synced")

        else:
            # Incremental sync: fetch shows updated since last poll
            last_poll = state.get("last_updates_poll", 0)
            log.info(f"Incremental sync: shows updated since timestamp {last_poll}")

            # TVMaze /updates/shows accepts day/week/month — use month (widest window)
            # to avoid missing updates when the connector is paused for up to 30 days.
            # Updates older than last_updates_poll are filtered out client-side below.
            updates_data = fetch_data_with_retry(
                tvmaze_session,
                f"{__TVMAZE_BASE_URL}/updates/shows",
                params={"since": "month"},
            )

            if updates_data:
                updated_show_ids = [
                    int(show_id)
                    for show_id, updated_ts in updates_data.items()
                    if int(updated_ts) > last_poll
                ]
                log.info(f"Found {len(updated_show_ids)} shows updated since last sync")

                new_max_ts = last_poll
                for show_id in updated_show_ids:
                    show_data = fetch_data_with_retry(
                        tvmaze_session,
                        f"{__TVMAZE_BASE_URL}/shows/{show_id}",
                    )
                    if show_data:
                        flat = flatten_show(show_data)

                        if genre_filter:
                            show_genres = json.loads(flat.get("genres") or "[]")
                            if not any(g in show_genres for g in genre_filter):
                                time.sleep(__TVMAZE_RATE_LIMIT_SLEEP)
                                continue

                        if status_filter and flat.get("status") != status_filter:
                            time.sleep(__TVMAZE_RATE_LIMIT_SLEEP)
                            continue

                        # The 'upsert' operation is used to insert or update data in the destination table.
                        # The first argument is the name of the destination table.
                        # The second argument is a dictionary containing the record to be upserted.
                        op.upsert(table="shows", data=flat)
                        shows_this_sync.append(flat)

                        updated_ts_val = int(updates_data.get(str(show_id), 0))
                        if updated_ts_val > new_max_ts:
                            new_max_ts = updated_ts_val

                    time.sleep(__TVMAZE_RATE_LIMIT_SLEEP)

                state["last_updates_poll"] = new_max_ts
                log.info(f"Incremental sync complete: {len(shows_this_sync)} shows updated")
            else:
                log.info("No updates found from TVMaze this sync")

        # Checkpoint after Phase 1
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # -----------------------------------------------------------------------
        # Phase 2: DEBATE — Programming Optimist vs Skeptic vs Consensus
        # -----------------------------------------------------------------------
        if enable_enrichment or enable_genie_space:
            databricks_session = requests.Session()
            databricks_session.headers.update(
                {
                    "Authorization": f"Bearer {configuration.get('databricks_token', '')}",
                    "Content-Type": "application/json",
                }
            )

        if enable_enrichment and shows_this_sync:
            shows_to_enrich = shows_this_sync[:max_enrichments]
            log.info(
                f"Enriching {len(shows_to_enrich)} show(s) " f"(max_enrichments={max_enrichments})"
            )

            enriched_count = 0
            for show_record in shows_to_enrich:
                show_id = show_record["show_id"]

                # Fetch rich embedded data (cast + episodes) for debate context
                rich_data = fetch_data_with_retry(
                    tvmaze_session,
                    f"{__TVMAZE_BASE_URL}/shows/{show_id}?embed[]=cast&embed[]=episodes",
                )
                embedded = rich_data.get("_embedded") if rich_data else None
                time.sleep(__TVMAZE_RATE_LIMIT_SLEEP)

                run_debate(databricks_session, configuration, show_record, embedded, state)
                enriched_count += 1

            log.info(f"Phase 2 complete: {enriched_count} show(s) enriched")

        elif enable_enrichment:
            log.info("Enrichment enabled but no shows to enrich this sync")

        # -----------------------------------------------------------------------
        # Phase 3: AGENT — Create Genie Space
        # -----------------------------------------------------------------------
        if enable_genie_space:
            create_genie_space(databricks_session, configuration, state)

        # Final checkpoint after all phases
        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info(
            f"TVMaze Programming Intelligence sync complete. "
            f"Shows synced: {len(shows_this_sync)}. "
            f"Enrichment: {'enabled' if enable_enrichment else 'disabled'}. "
            f"Genie Space: {'enabled' if enable_genie_space else 'disabled'}."
        )

    finally:
        tvmaze_session.close()
        if databricks_session is not None:
            databricks_session.close()


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
