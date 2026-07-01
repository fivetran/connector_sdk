"""Bright Data SERP (search) helper functions."""

import time
from typing import Any, Union
from urllib.parse import quote_plus

import requests
from requests import RequestException, Response

from fivetran_connector_sdk import Logging as log

__BRIGHT_DATA_BASE_URL = "https://api.brightdata.com"
__DEFAULT_SERP_ZONE = "serp_api1"
__DEFAULT_TIMEOUT_SECONDS = 120
__DEFAULT_RESPONSE_FORMAT = "json"
__RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}
__VALID_SEARCH_ENGINES = {"google", "bing", "yandex"}


def _parse_response_payload(response: Response) -> Any:
    """Return JSON payload when available, otherwise raw text."""
    try:
        return response.json()
    except ValueError:
        return response.text


def _extract_error_detail(response: Response) -> str:
    """Extract a concise error description from a failed Bright Data response."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("error", "message", "detail", "details"):
                if key in payload:
                    return str(payload[key])
            return str(payload)
        return str(payload)
    except ValueError:
        return response.text


def perform_search(
    api_token: str,
    query: Union[str, list],
    search_engine: str | None = "google",
    country: str | None = "us",
    response_format: str | None = __DEFAULT_RESPONSE_FORMAT,
    zone: str | None = __DEFAULT_SERP_ZONE,
    timeout: int = __DEFAULT_TIMEOUT_SECONDS,
    retries: int = 3,
    backoff_factor: float = 1.5,
) -> Union[dict, list]:
    """Perform a search using Bright Data's SERP REST endpoint."""
    if not api_token or not isinstance(api_token, str):
        raise ValueError("A valid Bright Data API token is required")

    if not query:
        raise ValueError("Query cannot be empty")

    if not isinstance(query, (str, list)):
        raise TypeError("Query must be a string or list of strings")

    if isinstance(query, list):
        if not all(isinstance(item, str) for item in query):
            raise TypeError("All queries must be strings")
        queries = [item.strip() for item in query if item and item.strip()]
    else:
        queries = [query.strip()]

    if not queries:
        raise ValueError("At least one non-empty query must be provided")

    selected_engine = (search_engine or "google").lower()
    if selected_engine not in __VALID_SEARCH_ENGINES:
        log.warning(f"Invalid search engine '{search_engine}'. Using default 'google'")
        selected_engine = "google"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    zone_identifier = zone or __DEFAULT_SERP_ZONE

    log.info(
        f"Executing Bright Data REST search for {len(queries)} query"
        f"{'ies' if len(queries) != 1 else ''} using zone '{zone_identifier}'"
    )

    results: list = []

    for single_query in queries:
        search_url = _build_search_url(single_query, selected_engine)
        payload: dict = {
            "zone": zone_identifier,
            "url": search_url,
            "format": response_format or __DEFAULT_RESPONSE_FORMAT,
            "method": "GET",
        }

        if country:
            payload["country"] = country.lower()

        response_payload = _execute_search_request(
            headers=headers,
            payload=payload,
            single_query=single_query,
            timeout=timeout,
            retries=retries,
            backoff_factor=backoff_factor,
        )
        results.append(_normalize_search_results(response_payload))

    if len(queries) == 1:
        return results[0]

    return results


def _execute_search_request(
    headers: dict,
    payload: dict,
    single_query: str,
    timeout: int,
    retries: int,
    backoff_factor: float,
) -> Any:
    """Execute a single SERP API request with retry logic."""
    attempt = 0
    backoff = backoff_factor

    while attempt <= retries:
        try:
            response = requests.post(
                f"{__BRIGHT_DATA_BASE_URL}/request?async=true",
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            if response.status_code == 200:
                return _parse_response_payload(response)

            if response.status_code in __RETRY_STATUS_CODES and attempt < retries:
                attempt += 1
                log.warning(
                    f"Bright Data SERP request retry {attempt}/{retries} for query "
                    f"'{single_query}' (status code: {response.status_code})"
                )
                time.sleep(backoff)
                backoff *= backoff_factor
                continue

            error_detail = _extract_error_detail(response)
            raise RuntimeError(
                f"Bright Data SERP request failed for query '{single_query}': {error_detail}"
            )

        except RequestException as exc:
            if attempt < retries:
                attempt += 1
                log.warning(
                    f"Error contacting Bright Data SERP API for query '{single_query}': "
                    f"{str(exc)}. Retrying ({attempt}/{retries})"
                )
                time.sleep(backoff)
                backoff *= backoff_factor
                continue
            raise RuntimeError(
                f"Failed to execute Bright Data SERP request for query "
                f"'{single_query}' after {retries} retries: {str(exc)}"
            ) from exc

    raise RuntimeError(
        f"Bright Data SERP request did not return a response for query '{single_query}'"
    )


def _build_search_url(query: str, search_engine: str) -> str:
    """Build the target URL for a given search engine and query."""
    encoded_query = quote_plus(query)
    search_engine = search_engine.lower()

    engine_templates = {
        "google": "https://www.google.com/search?q={query}&brd_json=1",
        "bing": "https://www.bing.com/search?q={query}&brd_json=1",
        "yandex": "https://yandex.com/search/?text={query}",
    }

    template = engine_templates.get(search_engine, engine_templates["google"])
    return template.format(query=encoded_query)


def _normalize_search_results(payload: Any) -> list:
    """Normalize the variety of SERP response structures into a list of dictionaries."""
    if isinstance(payload, list):
        return [
            item if isinstance(item, dict) else {"raw_response": str(item)} for item in payload
        ]

    if isinstance(payload, dict):
        for candidate_key in (
            "results",
            "organic_results",
            "organic",
            "data",
            "items",
            "serp",
        ):
            candidate_value = payload.get(candidate_key)
            if isinstance(candidate_value, list):
                return [
                    item if isinstance(item, dict) else {"raw_response": str(item)}
                    for item in candidate_value
                ]

        data_field = payload.get("data")
        if isinstance(data_field, dict):
            for candidate_key in (
                "results",
                "organic_results",
                "organic",
                "items",
            ):
                candidate_value = data_field.get(candidate_key)
                if isinstance(candidate_value, list):
                    return [
                        item if isinstance(item, dict) else {"raw_response": str(item)}
                        for item in candidate_value
                    ]

        return [payload]

    return [{"raw_response": str(payload)}]
