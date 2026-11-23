"""Client for the Omni REST API, used by connector.py.

Omni serves its semantic model as YAML documents over JSON: GET /v1/models lists the models and
GET /v1/models/{id}/yaml returns a "files" map of file path to raw YAML. Turning that YAML into
rows is the job of omni_model_parser.py; this module only speaks HTTP.
"""

# For validating the scheme of the Omni URL
import re

# For pausing between retry attempts
import time

# For holding the connection settings of an Omni client
from dataclasses import dataclass

# For encoding model ids into the request path
from urllib.parse import quote

# For making HTTP requests to the Omni API
import requests

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

__SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
__MODELS_PATH = "/v1/models"
__DOCUMENTS_PATH = "/v1/documents"
__FIRST_SUCCESS_STATUS = 200
__FIRST_REDIRECT_STATUS = 300
__TOO_MANY_REQUESTS = 429
__FIRST_SERVER_ERROR_STATUS = 500
__MAX_ERROR_BODY_CHARS = 512
__INITIAL_BACKOFF_SECONDS = 2
__MAX_BACKOFF_SECONDS = 60
__MAX_BACKOFF_EXPONENT = 5

# Omni's list endpoints have used more than one envelope key for the page's items.
__RECORD_LIST_KEYS = ("records", "models", "data")

SYNC_TIMEOUT_SECONDS = 60
SYNC_MAX_ATTEMPTS = 5

# A setup test exists to tell someone whether their URL and token work, so it gets one attempt and
# a short timeout. On the sync budget an unreachable host would spend five 60s timeouts plus backoff,
# about five and a half minutes, before reporting anything, which looks like a hung form.
SETUP_TEST_TIMEOUT_SECONDS = 10
SETUP_TEST_MAX_ATTEMPTS = 1


class OmniApiError(Exception):
    """
    A failed Omni API call. Rate limits, server errors and dropped connections are retriable;
    every other failure, such as a rejected token or a missing model, fails the same way next time.
    """

    def __init__(self, message, status_code=None, retry_after_seconds=None, is_retriable=False):
        """
        Create an Omni API error.
        Args:
            message: description of the failure, including a bounded excerpt of the response body.
            status_code: HTTP status, or None when the request never produced one.
            retry_after_seconds: the Retry-After value Omni sent, or None when it sent none.
            is_retriable: whether another attempt can succeed.
        """
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.is_retriable = is_retriable


@dataclass
class OmniClient:
    """Connection settings shared by every request: the API root, the session and the retry budget."""

    api_root: str
    session: requests.Session
    timeout_seconds: int
    max_attempts: int


def create_client(
    base_url: str,
    api_token: str,
    timeout_seconds=SYNC_TIMEOUT_SECONDS,
    max_attempts=SYNC_MAX_ATTEMPTS,
):
    """
    Create an Omni client that authenticates every request with the bearer token.
    Args:
        base_url: the Omni URL from the configuration.
        api_token: Organization API key or Personal Access Token.
        timeout_seconds: connect and read timeout for each request.
        max_attempts: attempts per request, including the first one.
    Returns:
        An OmniClient.
    """
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_token}", "Accept": "application/json"})
    return OmniClient(api_base_url(base_url), session, timeout_seconds, max_attempts)


def api_base_url(base_url: str):
    """
    Return the API root for the Omni URL people sign in with. Omni's API lives under /api on the
    same host, so a URL that already ends in /api is accepted as-is. People reasonably enter the
    host without a scheme, so https is assumed when none is given.
    Args:
        base_url: the Omni URL from the configuration, e.g. acme.omniapp.co.
    Returns:
        The API root, e.g. https://acme.omniapp.co/api.
    Raises:
        ValueError: if the URL uses a scheme other than http or https.
    """
    trimmed = base_url.strip()
    if not __SCHEME.match(trimmed):
        trimmed = "https://" + trimmed
    elif not trimmed.startswith(("https://", "http://")):
        raise ValueError(f"Omni URL must be an http or https URL, got: {base_url}")
    trimmed = trimmed.rstrip("/")
    return trimmed if trimmed.endswith("/api") else trimmed + "/api"


def model_pages(client: OmniClient):
    """
    Yield pages of shared models, following cursor pagination. Only SHARED models are listed:
    Omni's model list is dominated by per-query and per-workbook models (a real instance returned
    83,864 models, of which exactly one was SHARED), and the shared model is the published
    semantic layer.
    Args:
        client: the Omni client.
    Returns:
        A generator of lists of {"id", "name", "connection_id"} dictionaries, one list per page.
    """
    for page_records in record_pages(client, __MODELS_PATH, {"modelKind": "SHARED"}):
        models = []
        for record in page_records:
            model_id = text(record, "id")
            if model_id is not None:
                models.append(
                    {
                        "id": model_id,
                        "name": text(record, "name"),
                        "connection_id": text(record, "connectionId"),
                    }
                )
        yield models


def document_pages(client: OmniClient):
    """
    Yield pages of raw document records: workbooks, dashboards and apps. No filtering is needed,
    because the count is bounded by what the organisation authors rather than by query activity.
    Args:
        client: the Omni client.
    Returns:
        A generator of lists of raw document records, one list per page.
    """
    yield from record_pages(client, __DOCUMENTS_PATH, {})


def fetch_model_yaml(client: OmniClient, model_id: str):
    """
    Fetch one model's YAML documents and Omni's own file path to view name mapping. The
    as-authored form is requested rather than fullyResolved=true: on a real model, resolving
    extends added only 24 dimensions out of 60,341.
    Args:
        client: the Omni client.
        model_id: the model to fetch.
    Returns:
        A tuple of (files, view_names), each a dictionary keyed by file path.
    """
    payload = get_json(client, f"{__MODELS_PATH}/{quote(model_id, safe='')}/yaml", {})
    return text_map(payload.get("files")), text_map(payload.get("viewNames"))


def record_pages(client: OmniClient, path: str, params: dict):
    """
    Yield the record list of each page of a cursor-paginated list endpoint. Pagination stops when
    a page carries no pageInfo.nextCursor, which also covers an empty first page.
    Args:
        client: the Omni client.
        path: endpoint path under the API root.
        params: query parameters sent with every page.
    Returns:
        A generator of record lists.
    """
    cursor = None
    while True:
        page_params = dict(params)
        if cursor is not None:
            page_params["cursor"] = cursor
        payload = get_json(client, path, page_params)
        yield records(payload)
        page_info = payload.get("pageInfo")
        cursor = text(page_info, "nextCursor")
        if cursor is None:
            return


def get_json(client: OmniClient, path: str, params: dict):
    """
    Perform one GET, retrying rate limits, transient server errors and dropped connections.
    A failure that retrying cannot fix is raised on the first attempt.
    Args:
        client: the Omni client.
        path: endpoint path under the API root.
        params: query parameters.
    Returns:
        The parsed JSON response body.
    Raises:
        OmniApiError: when the call fails permanently or attempts are exhausted.
    """
    for attempt in range(1, client.max_attempts + 1):
        try:
            return attempt_get_json(client, path, params)
        except OmniApiError as error:
            if not error.is_retriable or attempt == client.max_attempts:
                raise
            wait_seconds = retry_wait_seconds(error, attempt)
            log.warning(
                f"Retrying Omni API call after attempt {attempt} "
                f"(status {error.status_code or 'n/a'}); waiting {wait_seconds}s"
            )
            time.sleep(wait_seconds)
    raise ValueError(f"max_attempts must be at least 1, got {client.max_attempts}")


def attempt_get_json(client: OmniClient, path: str, params: dict):
    """
    Perform a single GET and translate the outcome into parsed JSON or an OmniApiError.
    Args:
        client: the Omni client.
        path: endpoint path under the API root.
        params: query parameters.
    Returns:
        The parsed JSON response body.
    Raises:
        OmniApiError: on a connection failure, a non-2xx status or a body that is not JSON.
    """
    try:
        response = client.session.get(
            client.api_root + path, params=params, timeout=client.timeout_seconds
        )
    except (requests.ConnectionError, requests.Timeout) as error:
        # Connection resets and read timeouts are worth another attempt.
        raise OmniApiError(
            f"Omni API request to {path} failed: {error}", is_retriable=True
        ) from error
    if not __FIRST_SUCCESS_STATUS <= response.status_code < __FIRST_REDIRECT_STATUS:
        status = response.status_code
        raise OmniApiError(
            f"Omni API request to {path} failed with HTTP {status}: {summarize(response.text)}",
            status_code=status,
            retry_after_seconds=retry_after(response),
            is_retriable=status == __TOO_MANY_REQUESTS or status >= __FIRST_SERVER_ERROR_STATUS,
        )
    try:
        return response.json()
    except ValueError as error:
        raise OmniApiError(f"Omni API response from {path} was not valid JSON") from error


def retry_wait_seconds(error: OmniApiError, attempt: int):
    """
    Return how long to wait before the next attempt: Retry-After when Omni supplied it, otherwise
    an exponential backoff from 2s. Both are capped at 60s so one throttled endpoint cannot stall
    a sync indefinitely.
    Args:
        error: the failure from the previous attempt.
        attempt: the 1-based number of the attempt that just failed.
    Returns:
        The wait in seconds.
    """
    if error.retry_after_seconds is not None and error.retry_after_seconds >= 0:
        return min(error.retry_after_seconds, __MAX_BACKOFF_SECONDS)
    backoff = __INITIAL_BACKOFF_SECONDS * (2 ** min(attempt - 1, __MAX_BACKOFF_EXPONENT))
    return min(backoff, __MAX_BACKOFF_SECONDS)


def retry_after(response):
    """
    Read Retry-After, which Omni sends in seconds on 429.
    Args:
        response: the failed HTTP response.
    Returns:
        The wait in seconds, or None when the header is absent or unparsable.
    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def summarize(body):
    """
    Bound an error body before it becomes an exception message. Successful payloads run to
    megabytes and a gateway can answer with a full HTML page, so the untrimmed body would be
    repeated into the log on every retry. Omni's own errors are short JSON, so they stay intact.
    Args:
        body: the response body text.
    Returns:
        The body, truncated to 512 characters.
    """
    if not body:
        return "(empty response body)"
    collapsed = body.strip()
    if len(collapsed) <= __MAX_ERROR_BODY_CHARS:
        return collapsed
    return f"{collapsed[:__MAX_ERROR_BODY_CHARS]}... ({len(collapsed)} chars truncated)"


def records(payload):
    """
    Return the item list of one page. An unrecognised envelope fails loudly rather than returning
    nothing: treating a shape change as "no rows" would let a successful-looking sync mark every
    table's rows deleted.
    Args:
        payload: the parsed JSON page.
    Returns:
        The list of records on the page.
    Raises:
        OmniApiError: when the page has none of the known record list keys.
    """
    if isinstance(payload, dict):
        for key in __RECORD_LIST_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
    field_names = ", ".join(payload) if isinstance(payload, dict) and payload else "no fields"
    raise OmniApiError(
        "Omni API response contained no recognised record list; expected one of records, models "
        f"or data but found {field_names}"
    )


def text(node, field: str):
    """
    Return a stripped string field, treating missing, non-string and blank values as None.
    Args:
        node: a JSON object, or anything else.
        field: the field name.
    Returns:
        The stripped string, or None.
    """
    value = node.get(field) if isinstance(node, dict) else None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def text_map(node):
    """
    Keep only the string-valued entries of a JSON object.
    Args:
        node: a JSON object, or anything else.
    Returns:
        A dictionary of the string entries; empty when node is not an object.
    """
    if not isinstance(node, dict):
        return {}
    return {key: value for key, value in node.items() if isinstance(value, str)}
