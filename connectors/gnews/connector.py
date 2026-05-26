"""
This example shows how to pull recent news articles from the GNews API service
and load them into a destination using the Fivetran Connector SDK.

This Fivetran Connector uses the GNewsAPI search endpoint to retrievea
articles for a given search term and date range. This connector demonstrates:
- Robust API communication with exponential backoff and retries for transient
  HTTP and network errors (e.g., 429, 5xx).
- Data normalization and flattening of nested JSON responses into a clean,
  tabular structure.
- Incremental-style paging with automatic stop conditions once all results
  are fetched or totalResults are reached.
- Idempotent upserts to the destination table (`news_stories`) using a
  composite primary key of `url` and `publishedAt`.
- Configurable parameters for search term, sorting, pagination, and date range.

Refer to GNews API documentation for details:
https://docs.gnews.io/endpoints/search-endpoint

See the Fivetran Connector SDK Technical Reference:
https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

and Best Practices:
https://fivetran.com/docs/connectors/connector-sdk/best-practices
for additional implementation guidance.
"""

from __future__ import annotations

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For type hints and annotations
from typing import Any, Dict, List, Optional, Tuple

# For implementing retry delays in exponential backoff
import time

# For adding jitter to retry delays
import random

# For making HTTP requests to the GNews API
import requests

__GNEWSAPI_ENDPOINT = "https://gnews.io/api/v4/search"

# Default headers for API requests.
# User-Agent and Accept headers prevent 426 (Upgrade Required) responses.
__DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NewsFetcher/1.0; +https://gnews.io)",
    "Accept": "application/json",
}


def schema(configuration: dict) -> List[Dict[str, Any]]:
    """
    Define the schema function which lets you configure the schema
    your connector delivers.
    See the technical reference documentation
    for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "news_stories",
            "primary_key": ["url", "publishedAt"],
        }
    ]


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = ["api_key", "search_term", "from_date"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")
        if not configuration[key]:
            raise ValueError(f"Configuration value '{key}' cannot be empty")


def normalize_articles(page_json: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
    """
    Convert a GNews response page into scalar-only rows.

    This function flattens nested JSON objects from the GNews response
    and sanitizes fields to make them safe for database upserts.

    Args:
        page_json (dict): JSON response from GNews for one page.
        query (str): The search term used in the API request.

    Returns:
        List of cleaned article rows suitable for upsert.
    """
    rows: List[Dict[str, Any]] = []
    for a in page_json.get("articles") or []:
        src = a.get("source") or {}

        # Build a single record.
        row = {
            "url": a.get("url"),
            "publishedAt": a.get("publishedAt"),
            "source_id": src.get("id"),
            "source_name": src.get("name"),
            "author": a.get("author"),
            "title": a.get("title"),
            "description": a.get("description"),
            "urlToImage": a.get("urlToImage"),
            "content": a.get("content"),
            "query": query,
        }

        # Sanitize nested and non-scalar fields by JSON encoding.
        clean_row: Dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                clean_row[k] = json.dumps(v, ensure_ascii=False)
            elif v is None or isinstance(v, (str, int, float, bool)):
                clean_row[k] = v
            else:
                clean_row[k] = str(v)

        rows.append(clean_row)

    return rows


def upsert_news_stories(rows: List[Dict[str, Any]]) -> int:
    """
    Upserts normalized news stories into the destination table.
    Returns:
        The number of records upserted.
    """
    upserts_count = 0
    for record in rows:
        try:
            # The 'upsert' operation is used to insert or update data
            # in the destination table. The first argument is the
            # name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table="news_stories", data=record)
            upserts_count += 1
        except Exception as e:
            log.error(f"Failed to upsert record: {record}\nError: {e}")
            continue

    return upserts_count


def fetch_news_page(
    query: str,
    from_date: str,
    api_key: str,
    *,
    page: int = 1,
    sort_by: str = "popularity",
    endpoint: str = __GNEWSAPI_ENDPOINT,
    retries: int = 5,
    backoff_factor: float = 0.75,
    status_forcelist: Optional[set] = None,
    timeout: int = 20,
) -> Tuple[int, int]:
    """
    Fetches one page of articles from the GNewsAPI, normalizes the data,
    and performs upserts into the destination table.

    Implements exponential backoff and retry logic for transient
    HTTP errors such as 429 (rate limit) or 5xx server errors.

    Args:
        query (str): Search keyword or phrase.
        from_date (str): Start date (YYYY-MM-DD) for filtering news.
        api_key (str): GNewsAPI authentication key.
        page (int): The current page number to fetch.
        sort_by (str): Sorting method (e.g., 'popularity', 'publishedAt').
        endpoint (str): API endpoint URL.
        retries (int): Max number of retry attempts for transient errors.
        backoff_factor (float): Base factor for exponential backoff delay.
        status_forcelist (set): HTTP status codes that should trigger a retry.
        timeout (int): Request timeout in seconds.

    Returns:
        Tuple containing:
            (upserts_count, total_results)
    """
    if status_forcelist is None:
        status_forcelist = {426, 429, 500, 502, 503, 504}

    # Define request parameters for GNewsAPI query.
    params = {
        "q": query,
        "from": from_date,
        "sortBy": sort_by,
        "apikey": api_key,
        "page": page,
    }

    attempt = 0
    while True:
        attempt += 1
        try:
            # Send the GET request to GNewsAPI.
            resp = requests.get(
                endpoint, headers=__DEFAULT_HEADERS, params=params, timeout=timeout
            )

            # Handle transient error codes with retries.
            if resp.status_code in status_forcelist:
                if attempt <= retries:
                    sleep_s = backoff_factor * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                    log.warning(
                        f"Transient HTTP {resp.status_code}. Retrying in {sleep_s:.2f}s..."
                    )
                    time.sleep(sleep_s)
                    continue
                else:
                    resp.raise_for_status()

            # Raise an error for any non-200 response.
            if resp.status_code != 200:
                resp.raise_for_status()

            data = resp.json()

            # Extract and normalize article data.
            total_results = int(data.get("totalArticles", 0))
            rows = normalize_articles(data, query)
            upserts_count = upsert_news_stories(rows)
            log.info(f"Upserted {upserts_count} " f"from page {page}")
            return upserts_count, total_results

        except (requests.Timeout, requests.ConnectionError) as e:
            # Handle connection/timeout errors with exponential retry.
            if attempt <= retries:
                sleep_s = backoff_factor * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                log.warning(f"Network error: {e}. Retrying in {sleep_s:.2f}s...")
                time.sleep(sleep_s)
                continue
            raise


def fetch_all_news(
    query: str,
    from_date: str,
    api_key: str,
    *,
    sort_by: str = "popularity",
    endpoint: str = __GNEWSAPI_ENDPOINT,
    max_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Iterates through all available pages of results for a given query.

    Stops when:
        - All known results (totalResults) have been fetched.
        - max_pages limit (if specified) has been reached.

    Args:
        query (str): Search keyword or phrase.
        from_date (str): Date filter for results.
        api_key (str): API key for authentication.
        sort_by (str): Sort order.
        endpoint (str): GNewsAPI endpoint.
        max_pages (int | None): Optional hard cap for paging.

    Returns:
        A summary dictionary with pages fetched and total upserts.
    """
    page = 1
    total_upserts = 0
    pages_fetched = 0
    total_results_seen: Optional[int] = None

    while True:
        log.info(f"Fetching page {page}...")

        # Fetch one page of results.
        upserts_count, total_results = fetch_news_page(
            query=query,
            from_date=from_date,
            api_key=api_key,
            page=page,
            sort_by=sort_by,
            endpoint=endpoint,
        )

        # Store total result count after first page.
        if total_results_seen is None:
            total_results_seen = total_results

        # Stop if no data was returned.
        if upserts_count == 0:
            break

        pages_fetched += 1
        total_upserts += upserts_count

        # Stop if we’ve clearly reached the end of the result set.
        if total_results_seen == total_upserts:
            break

        # Stop if max_pages limit reached
        if max_pages is not None and pages_fetched >= max_pages:
            break
        page += 1

    return {
        "status": "ok",
        "pagesFetched": pages_fetched,
        "recordsSynced": total_upserts,
        "totalResults": total_results_seen or 0,
    }


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure
    how your connector fetches data.
    See the technical reference documentation for more details
    on the update function: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

    args:
        configuration: A dictionary containing connection details.
        state: A dictionary containing state information from previous runs.
               The state dictionary is empty for the first sync or for any
               full re-sync.
    """
    log.warning("Example: Connectors - GNews Search")
    validate_configuration(configuration)

    api_key = configuration["api_key"]
    search_term = configuration["search_term"]
    from_date = configuration["from_date"]

    # Perform the GNewsAPI sync and log summary statistics.
    result = fetch_all_news(search_term, from_date, api_key)
    log.info(
        f"Sync finished. pagesFetched={result['pagesFetched']} "
        f"recordsSynced={result['recordsSynced']}"
    )


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
