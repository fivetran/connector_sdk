"""Bright Data Web Scraper helper functions."""

# For parsing JSON responses from the Bright Data API
import json

# For adding delays between retry attempts (exponential backoff)
import time

# For type hints in function signatures
from typing import Any, Dict, List, Optional, Union

# For making HTTP requests to the Bright Data API
import requests

# For catching network and HTTP request exceptions
from requests import RequestException, Response

# For logging connector operations, errors, and status updates
from fivetran_connector_sdk import Logging as log

# Shared constants and utilities from the common module
from .common import (
    BRIGHT_DATA_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    RETRY_STATUS_CODES,
    extract_error_detail,
    parse_response_payload,
)

MAX_RESPONSE_SIZE_BYTES = 100 * 1024 * 1024
CHUNK_SIZE_BYTES = 8192


def _parse_large_json_array_streaming(response, max_size_bytes: int = MAX_RESPONSE_SIZE_BYTES):
    """
    Parse a large JSON array response using chunked reading to manage memory.

    For very large responses (>100MB), this reads the response in chunks and parses
    incrementally. However, JSON arrays still require the full response for parsing.

    Note: For truly large datasets, JSONL format is recommended as it allows
    line-by-line streaming without loading the entire response.

    Args:
        response: requests.Response object to parse
        max_size_bytes: Threshold for using chunked reading (default 100MB)

    Returns:
        List of parsed JSON objects, or None if not applicable/parse failed
    """
    content_length = response.headers.get("Content-Length")

    # Only attempt chunked parsing for responses larger than threshold
    if not content_length or int(content_length) < max_size_bytes:
        return None

    try:
        # Read response in chunks to monitor progress and manage memory pressure
        buffer = ""
        chunk_count = 0
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE_BYTES, decode_unicode=True):
            if chunk:
                buffer += chunk
                chunk_count += 1
                # Log progress for very large responses
                if chunk_count % 1000 == 0:
                    log.info(
                        f"Reading large response: {len(buffer)} bytes read "
                        f"({chunk_count} chunks)"
                    )

        # Verify it looks like a JSON array
        buffer_stripped = buffer.strip()
        if not buffer_stripped.startswith("["):
            # Not a JSON array, fall back to standard parsing
            return None

        # Parse the accumulated JSON array
        # Note: We still need to load it all for JSON array parsing
        # JSONL format would be better for true streaming
        parsed_data = json.loads(buffer_stripped)

        if isinstance(parsed_data, list):
            log.info(
                f"Successfully parsed large JSON array with {len(parsed_data)} records "
                f"({len(buffer)} bytes)"
            )
            return parsed_data

    except (json.JSONDecodeError, ValueError, MemoryError) as e:
        log.warning(
            f"Failed to parse large JSON response: {str(e)}. "
            f"Consider using JSONL format for very large datasets."
        )
        return None
    except Exception as e:
        log.info(f"Chunked parse encountered error: {str(e)}, falling back to standard parsing")
        return None

    return None


def perform_scrape(
    api_token: str,
    dataset_id: str,
    url: Union[str, List[str]],
    poll_interval: int = 30,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 3,
    backoff_factor: float = 1.5,
    extra_query_params: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    Scrape URLs using Bright Data's Web Scraper REST API.

    This function triggers a scrape job via POST /datasets/v3/trigger, receives a snapshot_id,
    and polls GET /datasets/v3/snapshot/{snapshot_id} until the status is "ready" or "failed".
    The endpoint handles polling internally, so we poll indefinitely until we receive a ready/failed status.

    Args:
        api_token: Bright Data API token
        dataset_id: ID of the dataset to use for scraping
        url: Single URL or list of URLs to scrape
        poll_interval: Interval between polling attempts in seconds
        timeout: Request timeout in seconds
        retries: Number of retries for failed requests
        backoff_factor: Backoff factor for exponential backoff
        extra_query_params: Optional dictionary of additional query parameters to include
                          in the scrape trigger request (e.g., {"discover_by": "profile_url", "type": "discover_new"})

    Returns:
        List of scraped results (each result is a dictionary)

    Raises:
        ValueError: If API token, dataset_id, or URL is invalid
        RuntimeError: If scrape trigger or polling fails
    """
    if not api_token or not isinstance(api_token, str):
        raise ValueError("A valid Bright Data API token is required")

    if not dataset_id or not isinstance(dataset_id, str):
        raise ValueError("dataset_id must be a non-empty string")

    if not url:
        raise ValueError("URL cannot be empty")

    if not isinstance(url, (str, list)):
        raise TypeError("URL must be a string or list of strings")

    # Normalize URLs to list
    urls: List[str]
    if isinstance(url, list):
        urls = [item.strip() for item in url if isinstance(item, str) and item.strip()]
    else:
        urls = [url.strip()]

    if not urls:
        raise ValueError("At least one non-empty URL must be provided")

    # Build payload for trigger request
    # Convert list of URL strings to API-required format:
    # [{"url": "https://example.com/1"}, {"url": "https://example.com/2"}, ...]
    # This matches the Bright Data API endpoint structure which accepts a list of objects
    payload = [{"url": single_url} for single_url in urls]

    # Trigger scrape job
    snapshot_id = _trigger_scrape(
        api_token=api_token,
        dataset_id=dataset_id,
        payload=payload,
        timeout=timeout,
        retries=retries,
        backoff_factor=backoff_factor,
        extra_query_params=extra_query_params or {},
    )

    if not snapshot_id:
        raise RuntimeError("Failed to trigger scrape job - no snapshot_id returned")

    # Poll snapshot until ready or failed
    results = _poll_snapshot(
        api_token=api_token,
        snapshot_id=snapshot_id,
        poll_interval=poll_interval,
        timeout=timeout,
    )

    # Normalize results to always be a list
    if not isinstance(results, list):
        results = [results] if results else []

    result_count = len(results)
    log.info(f"Scrape completed successfully. Retrieved {result_count} result(s)")

    return results


def _trigger_scrape(
    api_token: str,
    dataset_id: str,
    payload: List[Dict[str, Any]],
    timeout: int,
    retries: int,
    backoff_factor: float,
    extra_query_params: Dict[str, Any] = None,
) -> str:
    """
    Trigger a scrape job via POST /datasets/v3/trigger.

    Returns:
        snapshot_id string from the response

    Raises:
        ValueError: For 400/422 errors (invalid input)
        RuntimeError: For other API errors or network failures
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    # Build query parameters
    # According to Bright Data API docs, trigger endpoint accepts:
    # dataset_id, format, and include_errors as query parameters
    params: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "format": "json",
        "include_errors": "true",  # Include errors report with the results
    }

    # Add any additional query parameters from configuration
    # This allows dataset-specific parameters to be configured rather than hardcoded
    if extra_query_params:
        params.update(extra_query_params)

    # Build request body - according to Bright Data API docs, body should be:
    # [{"url": "https://..."}, {"url": "https://..."}, ...]
    # The API documentation shows that the body should only contain URL objects
    # as shown in the API examples
    body_payload = payload.copy()

    url_count = len(payload)
    log.info(
        f"Triggering Bright Data scrape for {url_count} URL{'s' if url_count > 1 else ''} "
        f"using dataset_id: {dataset_id}"
    )

    attempt = 0
    backoff = backoff_factor

    while attempt <= retries:
        try:
            # Log request details for debugging (without sensitive data)
            log.info(
                f"Sending POST request to {BRIGHT_DATA_BASE_URL}/datasets/v3/trigger "
                f"with params: {params}, payload containing {url_count} URL(s)"
            )

            response = requests.post(
                f"{BRIGHT_DATA_BASE_URL}/datasets/v3/trigger",
                headers=headers,
                params=params,
                json=body_payload,
                timeout=timeout,
            )

            if response.status_code == 200:
                response_data = parse_response_payload(response)
                if isinstance(response_data, dict):
                    snapshot_id = response_data.get("snapshot_id")
                    if snapshot_id:
                        log.info(
                            f"Scrape job triggered successfully. Snapshot ID: {snapshot_id[:8]}..."
                        )
                        return str(snapshot_id)
                    raise RuntimeError("Trigger response missing snapshot_id field")
                raise RuntimeError(f"Unexpected trigger response format: {response_data}")

            # Handle 400/422 as ValueError (invalid input)
            if response.status_code in (400, 422):
                error_detail = extract_error_detail(response)
                # Log the full response for debugging
                try:
                    response_json = response.json()
                    log.info(
                        f"Invalid scrape request (status {response.status_code}): {error_detail}. "
                        f"Request URL: {response.url}, "
                        f"Request payload (first URL): {body_payload[0] if body_payload else 'empty'}, "
                        f"Full response: {response_json}"
                    )
                except ValueError:
                    log.info(
                        f"Invalid scrape request (status {response.status_code}): {error_detail}. "
                        f"Request URL: {response.url}, "
                        f"Request payload (first URL): {body_payload[0] if body_payload else 'empty'}, "
                        f"Response text: {response.text[:500]}"
                    )
                raise ValueError(f"Invalid scrape request: {error_detail}")

            # Retry on certain status codes
            if response.status_code in RETRY_STATUS_CODES and attempt < retries:
                log.info(
                    f"Bright Data scrape trigger retry {attempt + 1}/{retries} "
                    f"(status code: {response.status_code})"
                )
                attempt += 1
                time.sleep(backoff)
                backoff *= backoff_factor
                continue

            # For other errors, raise with details
            error_detail = extract_error_detail(response)
            log.info(
                f"Bright Data scrape trigger failed (status {response.status_code}): "
                f"{error_detail}"
            )
            response.raise_for_status()

        except RequestException as exc:
            if attempt < retries:
                log.info(
                    f"Error contacting Bright Data Scraper API: {str(exc)}. "
                    f"Retrying ({attempt + 1}/{retries})"
                )
                attempt += 1
                time.sleep(backoff)
                backoff *= backoff_factor
                continue
            raise RuntimeError(
                f"Failed to trigger Bright Data scrape after {retries} retries: {str(exc)}"
            ) from exc

    raise RuntimeError("Failed to trigger Bright Data scrape after retries")


def _poll_snapshot(
    api_token: str,
    snapshot_id: str,
    poll_interval: int,
    timeout: int,
    max_attempts: int = 1000,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Poll the snapshot endpoint until status is "ready" or "failed".

    According to API docs: GET /datasets/v3/snapshot/{snapshot_id}?format=json

    Args:
        api_token: Bright Data API token
        snapshot_id: Snapshot ID to poll
        poll_interval: Interval between polling attempts in seconds
        timeout: Request timeout in seconds
        max_attempts: Maximum number of polling attempts before raising an error (default: 1000)

    Returns:
        Snapshot data when ready (dict or list)

    Raises:
        RuntimeError: If snapshot fails or request errors occur, or if max_attempts is exceeded
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
    }

    params: Dict[str, Any] = {
        "format": "json",
        "include_errors": "true",
    }

    attempt = 0
    while attempt < max_attempts:
        attempt += 1

        try:
            response = requests.get(
                f"{BRIGHT_DATA_BASE_URL}/datasets/v3/snapshot/{snapshot_id}",
                headers=headers,
                params=params,
                timeout=timeout,
            )

            if response.status_code == 200:
                # Log response details only on first attempt
                if attempt == 1:
                    _log_initial_response_info(response, snapshot_id)

                # Parse and handle the response
                snapshot_data = _parse_snapshot_response(response, snapshot_id, attempt)

                if snapshot_data is not None:
                    # Snapshot is ready, return the data
                    log.info(f"Snapshot {snapshot_id[:8]}... ready after {attempt} attempt(s)")
                    return snapshot_data
                else:
                    # Snapshot is still processing, continue polling
                    _log_polling_progress(snapshot_id, attempt, response)
                    time.sleep(poll_interval)
                    continue

            elif response.status_code == 404:
                error_msg = f"Snapshot {snapshot_id[:8]}... not found"
                log.info(error_msg)
                raise RuntimeError(error_msg)
            else:
                _handle_non_200_response(response, snapshot_id, attempt)

        except RequestException as exc:
            # Log network errors every 5 attempts to reduce log volume
            if attempt % 5 == 0:
                log.info(
                    f"Error polling snapshot {snapshot_id[:8]}...: {str(exc)}. "
                    f"Retrying (attempt {attempt})"
                )

            time.sleep(poll_interval)

    raise RuntimeError(
        f"Snapshot {snapshot_id[:8]} polling timed out after {max_attempts} attempts"
    )


def _log_initial_response_info(response: Response, snapshot_id: str) -> None:
    """Log initial response details."""
    content_length = response.headers.get("Content-Length")
    content_type = response.headers.get("Content-Type", "").lower()

    size_info = f", size: {content_length} bytes" if content_length else ""
    log.info(
        f"Snapshot {snapshot_id[:8]}... poll response "
        f"Content-Type: {content_type or 'unknown'}{size_info}"
    )


def _parse_snapshot_response(
    response: Response, snapshot_id: str, attempt: int
) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Parse snapshot response and return data if ready, None if still processing.

    Returns:
        Snapshot data if ready, None if still processing.
    """
    content_type = response.headers.get("Content-Type", "").lower()

    # Handle JSONL format
    if "jsonl" in content_type or "json-lines" in content_type:
        return _parse_jsonl_response(response, snapshot_id, attempt)

    # Check for large responses
    content_length = response.headers.get("Content-Length")
    max_size_bytes = MAX_RESPONSE_SIZE_BYTES
    if content_length and int(content_length) > max_size_bytes:
        log.warning(
            f"Snapshot {snapshot_id[:8]}... response size ({content_length} bytes) exceeds "
            f"maximum recommended size ({max_size_bytes} bytes). "
            f"Consider using JSONL format for large datasets."
        )

        # Try chunked parsing for large JSON arrays
        chunked_data = _parse_large_json_array_streaming(response, max_size_bytes)
        if chunked_data is not None:
            log.info(
                f"Snapshot {snapshot_id[:8]}... ready (chunked parse with {len(chunked_data)} records) "
                f"after {attempt} attempt(s)"
            )
            return chunked_data

    # Parse standard JSON response
    return _parse_json_response(response, snapshot_id, attempt)


def _parse_jsonl_response(
    response: Response, snapshot_id: str, attempt: int
) -> Optional[List[Dict[str, Any]]]:
    """
    Parse JSON Lines format response.

    Returns:
        List of parsed objects if data is ready, None if still processing.
    """
    results = []
    parse_errors = []

    for line_num, line in enumerate(response.iter_lines(decode_unicode=True), 1):
        line = line.strip()
        if not line:
            continue
        try:
            parsed_obj = json.loads(line)
            results.append(parsed_obj)
        except json.JSONDecodeError as e:
            parse_errors.append((line_num, str(e), line[:200]))

    if parse_errors:
        log.warning(
            f"Snapshot {snapshot_id[:8]}... JSONL parse errors on {len(parse_errors)} line(s). "
            f"First error: line {parse_errors[0][0]}: {parse_errors[0][1]}"
        )

    if results:
        log.info(
            f"Snapshot {snapshot_id[:8]}... ready (JSONL format with {len(results)} records) "
            f"after {attempt} attempt(s)"
        )
        return results

    return None


def _parse_json_response(
    response: Response, snapshot_id: str, attempt: int
) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Parse standard JSON response (array, object, or string).

    Returns:
        Snapshot data if ready, None if still processing.
    """
    # Try to parse response as JSON
    try:
        response_data = response.json()
    except (ValueError, json.JSONDecodeError):
        # If standard parsing fails, try raw text
        return _parse_text_response(response.text, snapshot_id, attempt)

    # Handle based on response type
    if isinstance(response_data, list):
        log.info(
            f"Snapshot {snapshot_id[:8]}... ready (array response with {len(response_data)} records) "
            f"after {attempt} attempt(s)"
        )
        return response_data

    elif isinstance(response_data, dict):
        return _parse_dict_response(response_data, snapshot_id, attempt)

    elif isinstance(response_data, str):
        return _parse_text_response(response_data, snapshot_id, attempt)

    # Unknown type - treat as data
    return [response_data] if response_data else []


def _parse_text_response(
    text: str, snapshot_id: str, attempt: int
) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Parse text response (could be JSON string or plain text status).

    Returns:
        Snapshot data if ready, None if still processing.
    """
    text_lower = text.lower()

    # Check if it's a "not ready" status message
    if any(phrase in text_lower for phrase in ("not ready", "processing", "pending", "try again")):
        return None

    # Try parsing as JSON
    trimmed_text = text.strip()
    if not (trimmed_text.startswith(("{", "["))):
        # Doesn't look like JSON
        log.info(
            f"Snapshot {snapshot_id[:8]}... string response (not JSON-like): " f"{text[:200]}..."
        )
        return None

    try:
        parsed_data = json.loads(text)
        # Normalize to list format
        if isinstance(parsed_data, list):
            return parsed_data
        elif isinstance(parsed_data, dict):
            return [parsed_data]
        else:
            return [parsed_data] if parsed_data else []
    except json.JSONDecodeError as e:
        # Try parsing as JSONL format
        log.warning(f"Snapshot {snapshot_id[:8]}... JSON decode error: {str(e)}")
        return _parse_text_as_jsonl(text, snapshot_id, attempt)


def _parse_text_as_jsonl(
    text: str, snapshot_id: str, attempt: int
) -> Optional[List[Dict[str, Any]]]:
    """
    Attempt to parse text as JSONL format.
    """
    results = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            parsed_obj = json.loads(line)
            results.append(parsed_obj)
        except json.JSONDecodeError:
            continue

    if results:
        log.info(
            f"Snapshot {snapshot_id[:8]}... ready (detected JSONL format "
            f"with {len(results)} records) after {attempt} attempt(s)"
        )
        return results

    return None


def _parse_dict_response(
    data: Dict[str, Any], snapshot_id: str, attempt: int
) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Parse dictionary response, checking status and extracting data.

    Returns:
        Snapshot data if ready, None if still processing.
    """
    status = data.get("status", "").lower()

    if status == "ready":
        return _extract_data_from_dict(data)

    elif status == "failed":
        error_msg = _extract_error_message(data)
        log.info(f"Snapshot {snapshot_id[:8]}... failed: {error_msg}")
        raise RuntimeError(f"Snapshot {snapshot_id[:8]}... failed: {error_msg}")

    elif status in ("running", "pending", "processing", "scheduled"):
        # Still processing
        return None

    else:
        # No status field or unknown status
        if "status" not in data:
            # Could be data - return it wrapped in list
            return [data] if data else []
        else:
            # Unknown status - continue polling
            return None


def _extract_data_from_dict(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract snapshot data from response dictionary.
    """
    # Try common data keys
    snapshot_data = data.get("data") or data.get("records") or data.get("results") or data

    # If no specific data key, remove metadata fields
    if snapshot_data is data:
        metadata_keys = (
            "status",
            "id",
            "snapshot_id",
            "created",
            "dataset_id",
            "customer_id",
            "cost",
            "initiation_type",
        )
        snapshot_data = {k: v for k, v in data.items() if k not in metadata_keys}

    # Normalize to list format
    if isinstance(snapshot_data, list):
        return snapshot_data
    elif isinstance(snapshot_data, dict):
        return [snapshot_data]
    else:
        return [snapshot_data] if snapshot_data is not None else []


def _extract_error_message(data: Dict[str, Any]) -> str:
    """Extract error message from response dictionary."""
    for key in ("error", "warning", "message", "detail", "details"):
        if key in data:
            error_value = data[key]
            if error_value:
                return str(error_value)
    return "Unknown error"


def _log_polling_progress(snapshot_id: str, attempt: int, response: Response) -> None:
    """Log polling progress based on attempt count."""
    if attempt % 5 == 0:
        try:
            response_data = response.json()
            if isinstance(response_data, dict):
                status = response_data.get("status", "")
                if status:
                    log.info(
                        f"Snapshot {snapshot_id[:8]}... status: {status} " f"(attempt {attempt})"
                    )
        except (ValueError, json.JSONDecodeError):
            log.info(f"Snapshot {snapshot_id[:8]}... still processing (attempt {attempt})")


def _handle_non_200_response(response: Response, snapshot_id: str, attempt: int) -> None:
    """Handle non-200 HTTP responses."""
    error_detail = extract_error_detail(response)
    log.info(
        f"Error polling snapshot {snapshot_id[:8]}... "
        f"(status {response.status_code}): {error_detail}"
    )
    response.raise_for_status()
