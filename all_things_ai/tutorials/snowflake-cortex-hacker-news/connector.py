"""
Hacker News + Snowflake Cortex Connector Example - Syncs top stories from Hacker News
and enriches them with AI-powered sentiment analysis and topic classification
using the Snowflake Cortex REST API.

This connector fetches top stories from the Hacker News API and optionally enriches each
story with real-time AI analysis via Snowflake Cortex during ingestion. Enrichments include
sentiment analysis (positive/negative/neutral with confidence scores) and topic classification
(AI, Security, Startups, Programming, Hardware, Science, Business, Other) with keyword extraction.
The connector supports incremental syncing using story ID as a cursor and checkpoints progress
after each batch for reliable resumable syncs.

See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Hacker News API Configuration Constants
__BASE_URL_HN = "https://hacker-news.firebaseio.com/v0"
__API_TIMEOUT_SECONDS = 10

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__HN_RATE_LIMIT_DELAY = 0.1

# Default Configuration Values
__DEFAULT_MAX_STORIES = 50
__DEFAULT_BATCH_SIZE = 10
__DEFAULT_CORTEX_MODEL = "mistral-large2"
__DEFAULT_CORTEX_TIMEOUT = 30
__DEFAULT_MAX_ENRICHMENTS = 50

# Cortex API Configuration
__CORTEX_INFERENCE_ENDPOINT = "/api/v2/cortex/inference:complete"
__CORTEX_RATE_LIMIT_DELAY = 0.1


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


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    # Validate numeric parameters if present
    numeric_params = {
        "max_stories": "max_stories must be a positive integer",
        "batch_size": "batch_size must be a positive integer",
        "cortex_timeout": "cortex_timeout must be a positive integer",
        "max_enrichments": "max_enrichments must be a positive integer",
    }

    for param, error_msg in numeric_params.items():
        if param in configuration:
            try:
                value = int(configuration[param])
            except (TypeError, ValueError):
                raise ValueError(error_msg)
            if value < 1:
                raise ValueError(error_msg)

    # Validate Snowflake credentials when Cortex enrichment is enabled
    is_cortex_enabled = configuration.get("enable_cortex", "true").lower() == "true"
    if is_cortex_enabled:
        snowflake_account = configuration.get("snowflake_account", "")
        snowflake_pat_token = configuration.get("snowflake_pat_token", "")

        if not snowflake_account:
            raise ValueError("snowflake_account is required when enable_cortex is true")
        if not snowflake_pat_token:
            raise ValueError("snowflake_pat_token is required when enable_cortex is true")
        if snowflake_account.startswith(("http://", "https://")):
            raise ValueError(
                "snowflake_account must be a hostname (no scheme), " f"got: {snowflake_account}"
            )
        if not snowflake_account.endswith("snowflakecomputing.com"):
            raise ValueError("snowflake_account must end with 'snowflakecomputing.com'")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [{"table": "stories_enriched", "primary_key": ["id"]}]


def create_session():
    """
    Create a requests session with a descriptive User-Agent header.

    Returns:
        requests.Session configured for Hacker News API requests
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Fivetran-HackerNews-Cortex-Connector/2.0"})
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
                url, params=params, headers=headers, timeout=__API_TIMEOUT_SECONDS
            )
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

            # Handle authentication/authorization errors immediately
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


def parse_cortex_streaming_response(response):
    """
    Parse SSE streaming response from Snowflake Cortex inference API.

    Cortex returns Server-Sent Events with JSON payloads containing
    incremental content in choices[0].delta.content fields.

    Args:
        response: requests.Response object with SSE streaming content

    Returns:
        Concatenated content string from all SSE data events
    """
    content = ""
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if "choices" in data and len(data["choices"]) > 0:
                    delta = data["choices"][0].get("delta", {})
                    content += delta.get("content", "")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    return content


def extract_json_from_content(content):
    """
    Extract a JSON object from a string that may contain surrounding text.

    Args:
        content: String potentially containing a JSON object

    Returns:
        Parsed dictionary if JSON found, or None
    """
    if "{" in content and "}" in content:
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        try:
            return json.loads(content[json_start:json_end])
        except json.JSONDecodeError:
            return None
    return None


def call_cortex_sentiment(session, account, title, pat_token, model, timeout):
    """
    Call Snowflake Cortex API for sentiment analysis on a story title.

    Args:
        session: requests.Session object for connection pooling
        account: Snowflake account identifier (full domain)
        title: Story title text to analyze
        pat_token: Snowflake Programmatic Access Token
        model: Cortex LLM model name to use
        timeout: API request timeout in seconds

    Returns:
        Dictionary with sentiment, score, and reasoning keys, or None on error
    """
    url = f"https://{account}{__CORTEX_INFERENCE_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {pat_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    prompt = (
        "Analyze the sentiment of this Hacker News story title and respond "
        "ONLY with a JSON object in this exact format:\n"
        '{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, '
        '"reasoning": "brief explanation"}\n\n'
        f"Title: {title}\n\nJSON:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 200,
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()

        content = parse_cortex_streaming_response(response)
        return extract_json_from_content(content)

    except requests.exceptions.Timeout:
        log.warning(f"Cortex sentiment timeout after {timeout}s")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Cortex sentiment API error: {str(e)}")
        return None


def call_cortex_classification(session, account, title, pat_token, model, timeout):
    """
    Call Snowflake Cortex API for topic classification on a story title.

    Args:
        session: requests.Session object for connection pooling
        account: Snowflake account identifier (full domain)
        title: Story title text to classify
        pat_token: Snowflake Programmatic Access Token
        model: Cortex LLM model name to use
        timeout: API request timeout in seconds

    Returns:
        Dictionary with category, confidence, and keywords keys, or None on error
    """
    url = f"https://{account}{__CORTEX_INFERENCE_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {pat_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    prompt = (
        "Classify this Hacker News story title into ONE primary category and "
        "respond ONLY with a JSON object:\n"
        '{"category": "AI|Security|Startups|Programming|Hardware|Science|Business|Other", '
        '"confidence": 0.0-1.0, "keywords": ["key1", "key2", "key3"]}\n\n'
        f"Title: {title}\n\nJSON:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 200,
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()

        content = parse_cortex_streaming_response(response)
        return extract_json_from_content(content)

    except requests.exceptions.Timeout:
        log.warning(f"Cortex classification timeout after {timeout}s")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Cortex classification API error: {str(e)}")
        return None


def enrich_story(session, configuration, title):
    """
    Orchestrate Cortex AI enrichment for a single story title.

    Calls both sentiment analysis and topic classification, then combines
    results into a single enrichment dictionary.

    Args:
        session: requests.Session object for connection pooling
        configuration: Configuration dictionary with Cortex settings
        title: Story title text to enrich

    Returns:
        Dictionary with all cortex enrichment fields populated
    """
    account = configuration.get("snowflake_account")
    pat_token = configuration.get("snowflake_pat_token")
    model = configuration.get("cortex_model", __DEFAULT_CORTEX_MODEL)
    timeout = int(configuration.get("cortex_timeout", str(__DEFAULT_CORTEX_TIMEOUT)))

    enrichment = {
        "cortex_sentiment": None,
        "cortex_sentiment_score": None,
        "cortex_sentiment_reasoning": None,
        "cortex_category": None,
        "cortex_category_confidence": None,
        "cortex_keywords": None,
        "cortex_model_used": model,
    }

    # Sentiment analysis
    sentiment_result = call_cortex_sentiment(session, account, title, pat_token, model, timeout)
    if sentiment_result:
        enrichment["cortex_sentiment"] = sentiment_result.get("sentiment")
        enrichment["cortex_sentiment_score"] = sentiment_result.get("score")
        enrichment["cortex_sentiment_reasoning"] = sentiment_result.get("reasoning")

    # Topic classification
    class_result = call_cortex_classification(session, account, title, pat_token, model, timeout)
    if class_result:
        enrichment["cortex_category"] = class_result.get("category")
        enrichment["cortex_category_confidence"] = class_result.get("confidence")
        enrichment["cortex_keywords"] = json.dumps(class_result.get("keywords", []))

    time.sleep(__CORTEX_RATE_LIMIT_DELAY)
    return enrichment


def fetch_story(session, story_id):
    """
    Fetch a single story from the Hacker News API with retry logic.

    Distinguishes between fetch failures (which should halt state advancement
    so the failed story is retried next sync) and legitimate skip cases such
    as non-story item types or deleted items (which should be skipped without
    halting the sync).

    Args:
        session: requests.Session object for connection pooling
        story_id: Hacker News story ID to fetch

    Returns:
        Story data dictionary if the item is a valid story, or None if the
        item is a legitimate skip (deleted, missing, or not type "story").

    Raises:
        RuntimeError: If the API request fails after all retry attempts.
            Callers should treat this as a fetch failure and stop advancing
            the state cursor past this story_id.
    """
    url = f"{__BASE_URL_HN}/item/{story_id}.json"

    # Let RuntimeError propagate from fetch_data_with_retry — fetch failures
    # are distinct from legitimate skips and must halt state advancement.
    story_data = fetch_data_with_retry(session, url)

    # Deleted or missing items return null/empty from the HN API. These are
    # legitimate skips, not failures, and the cursor may advance past them.
    if not story_data or "id" not in story_data:
        return None

    # Filter to only story type items. Comments, jobs, and polls are
    # legitimate skips that the cursor may advance past.
    if story_data.get("type") != "story":
        return None

    return story_data


def process_batch(
    session, configuration, story_ids, is_cortex_enabled, enriched_count, max_enrichments, state
):
    """
    Process a batch of story IDs: fetch details, enrich, flatten, and upsert.

    Args:
        session: requests.Session object for connection pooling
        configuration: Configuration dictionary
        story_ids: List of story IDs to process in this batch
        is_cortex_enabled: Whether Cortex enrichment is active
        enriched_count: Current count of enrichments performed
        max_enrichments: Maximum enrichments allowed per sync
        state: State dictionary for checkpointing

    Returns:
        Tuple of (synced_count, enriched_count, highest_synced_id)
    """
    synced_count = 0
    highest_synced_id = state.get("last_synced_id", 0)

    for story_id in story_ids:
        try:
            story_data = fetch_story(session, story_id)
        except RuntimeError as e:
            # A fetch failure on a lower-ID story must halt the loop so that
            # highest_synced_id never advances past it. The failed story will
            # be retried on the next sync. Returning here preserves the state
            # cursor at the last contiguously synced ID.
            log.warning(
                f"Halting batch at story_id={story_id} due to fetch failure: "
                f"{str(e)}. State cursor will not advance past this story."
            )
            return synced_count, enriched_count, highest_synced_id

        # None means the item is a legitimate skip (deleted item, or not a
        # "story" type such as comment/job/poll). The cursor may safely
        # advance past these because they will never become stories.
        if story_data is None:
            highest_synced_id = max(highest_synced_id, story_id)
            continue

        # Enrich with Cortex if enabled and within enrichment limit
        title = story_data.get("title", "")
        if is_cortex_enabled and title and enriched_count < max_enrichments:
            enrichment = enrich_story(session, configuration, title)
            story_data.update(enrichment)
            # Count each enrichment attempt toward the max_enrichments limit,
            # regardless of which specific enrichment fields are present.
            enriched_count += 1

        # Rename HN's `by` field to `submitted_by`. `BY` is a reserved SQL
        # keyword in DuckDB and most warehouses; emitting it as a column name
        # produces a CREATE TABLE parser error at sync time. The HN API field
        # itself is named `by`, but the warehouse column needs an unreserved
        # identifier.
        if "by" in story_data:
            story_data["submitted_by"] = story_data.pop("by")

        # Flatten nested data structures for Fivetran compatibility
        flattened = flatten_dict(story_data)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="stories_enriched", data=flattened)

        synced_count += 1
        highest_synced_id = max(highest_synced_id, story_id)

        time.sleep(__HN_RATE_LIMIT_DELAY)

    return synced_count, enriched_count, highest_synced_id


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
    log.warning("Example: all_things_ai/tutorials : snowflake-cortex-hacker-news")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration)

    # Read configuration with defaults
    max_stories = int(configuration.get("max_stories", str(__DEFAULT_MAX_STORIES)))
    batch_size = int(configuration.get("batch_size", str(__DEFAULT_BATCH_SIZE)))
    is_cortex_enabled = configuration.get("enable_cortex", "true").lower() == "true"
    max_enrichments = int(configuration.get("max_enrichments", str(__DEFAULT_MAX_ENRICHMENTS)))

    if is_cortex_enabled:
        log.info(
            f"Cortex enrichment ENABLED: "
            f"model={configuration.get('cortex_model', __DEFAULT_CORTEX_MODEL)}, "
            f"max_enrichments={max_enrichments}"
        )
    else:
        log.info("Cortex enrichment DISABLED")

    # Retrieve state for incremental sync
    last_synced_id = state.get("last_synced_id", 0)
    log.info(f"Last synced story ID: {last_synced_id}")

    # Create session for connection pooling
    session = create_session()

    try:
        # Fetch list of top story IDs from Hacker News
        log.info("Fetching top stories list from Hacker News")
        top_stories_url = f"{__BASE_URL_HN}/topstories.json"
        all_story_ids = fetch_data_with_retry(session, top_stories_url)
        log.info(f"Retrieved {len(all_story_ids)} story IDs from HN API")

        # Filter to only new stories, sort ascending for contiguous state advancement,
        # and limit to max_stories. Sorting ensures that if a lower-ID story fails,
        # the state cursor does not skip past it to a higher-ID success.
        new_story_ids = sorted([sid for sid in all_story_ids if sid > last_synced_id])
        story_ids_to_sync = new_story_ids[:max_stories]

        log.info(
            f"Syncing {len(story_ids_to_sync)} new stories "
            f"(filtered from {len(new_story_ids)} new)"
        )

        if not story_ids_to_sync:
            log.info("No new stories to sync")
            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            return

        # Process stories in batches with checkpointing
        total_synced = 0
        enriched_count = 0

        for i in range(0, len(story_ids_to_sync), batch_size):
            batch = story_ids_to_sync[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(story_ids_to_sync) + batch_size - 1) // batch_size

            log.info(f"Processing batch {batch_num}/{total_batches} " f"({len(batch)} stories)")

            synced, enriched_count, highest_id = process_batch(
                session,
                configuration,
                batch,
                is_cortex_enabled,
                enriched_count,
                max_enrichments,
                state,
            )

            total_synced += synced
            state["last_synced_id"] = highest_id

            # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
            # from the correct position in case of next sync or interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)

            log.info(f"Checkpointed at story ID {highest_id}")

        log.info(
            f"Sync complete: {total_synced} stories synced, "
            f"{enriched_count} enriched with Cortex"
        )

    except Exception as e:
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
    connector.debug()
