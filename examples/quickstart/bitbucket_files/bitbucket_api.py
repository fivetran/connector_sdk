"""Client for the Bitbucket Cloud REST API (v2.0), used by connector.py.

Authenticates with HTTP Basic (Atlassian account email and API token) and is bound to a single
workspace and repository. List endpoints are paginated through Bitbucket's absolute "next" URL.
"""

# For pausing between retry attempts
import time

# For encoding the workspace, repository and file path into request URLs
from urllib.parse import quote

# For making HTTP requests to the Bitbucket Cloud REST API
import requests

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

__BASE_URL = "https://api.bitbucket.org/2.0"
__PAGE_LENGTH = 100
__MAX_DEPTH = 100
# Files larger than this many bytes are skipped server-side.
__MAX_FILE_SIZE_BYTES = 1_048_576
__FIRST_SUCCESS_STATUS = 200
__FIRST_REDIRECT_STATUS = 300
__TOO_MANY_REQUESTS = 429
__FIRST_SERVER_ERROR_STATUS = 500
__INITIAL_BACKOFF_SECONDS = 2
__MAX_BACKOFF_SECONDS = 60

# Connect and read timeout for every request, matching a slow raw file download.
REQUEST_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 3
SETUP_TEST_MAX_ATTEMPTS = 1


class BitbucketApiError(Exception):
    """A failed Bitbucket API call; status_code is None when no HTTP response was received."""

    def __init__(self, message, status_code=None, is_retriable=False):
        """
        Create a Bitbucket API error.
        Args:
            message: description of the failure.
            status_code: HTTP status, or None when the request never produced one.
            is_retriable: whether another attempt can succeed.
        """
        super().__init__(message)
        self.status_code = status_code
        self.is_retriable = is_retriable


def create_session(email: str, api_token: str):
    """
    Create an HTTP session that authenticates every request with HTTP Basic.
    Args:
        email: the Atlassian account email, used as the HTTP Basic username.
        api_token: the Atlassian API token, used as the HTTP Basic password.
    Returns:
        A requests.Session.
    """
    session = requests.Session()
    session.auth = (email, api_token)
    return session


def repository_url(workspace: str, repository_slug: str):
    """
    Return the URL of the configured repository.
    Args:
        workspace: the Bitbucket workspace ID.
        repository_slug: the repository slug within the workspace.
    Returns:
        The repository URL.
    """
    return (
        f"{__BASE_URL}/repositories/{quote(workspace, safe='')}/{quote(repository_slug, safe='')}"
    )


def source_url(repository_full_name: str, branch: str, path: str):
    """
    Return the URL of a file, or of the file listing when path is empty, on a branch.
    Args:
        repository_full_name: the repository's "workspace/slug" name.
        branch: the branch to read from.
        path: the file path within the repository, or "" for the listing.
    Returns:
        The /src URL.
    """
    return (
        f"{__BASE_URL}/repositories/{quote(repository_full_name, safe='/')}/src/"
        f"{quote(branch, safe='/')}/{quote(path, safe='/')}"
    )


def file_query(include_path_pattern):
    """
    Build the Bitbucket q filter: files only (not directories), capped at 1 MB, and narrowed by
    the optional include path glob.
    Args:
        include_path_pattern: the configured glob, or None or blank for all files.
    Returns:
        The q filter string.
    """
    query = f'type="commit_file" AND size <= {__MAX_FILE_SIZE_BYTES}'
    if include_path_pattern and include_path_pattern.strip():
        query += f' AND path ~ "{include_path_pattern.strip()}"'
    return query


def fetch_repository(session, workspace: str, repository_slug: str, max_attempts=MAX_ATTEMPTS):
    """
    Fetch the configured repository.
    Args:
        session: the authenticated HTTP session.
        workspace: the Bitbucket workspace ID.
        repository_slug: the repository slug within the workspace.
        max_attempts: attempts for the request, including the first one.
    Returns:
        The repository as a dictionary.
    """
    response = get(session, repository_url(workspace, repository_slug), {}, max_attempts)
    return parse_json(response)


def file_pages(session, repository_full_name: str, branch: str, include_path_pattern):
    """
    Yield pages of the branch's file listing, filtered server-side and following the absolute
    "next" URL until a page has none.
    Args:
        session: the authenticated HTTP session.
        repository_full_name: the repository's "workspace/slug" name.
        branch: the branch to list.
        include_path_pattern: the configured glob, or None or blank for all files.
    Returns:
        A generator of lists of file dictionaries, one list per page.
    """
    params = {
        "pagelen": __PAGE_LENGTH,
        "max_depth": __MAX_DEPTH,
        "q": file_query(include_path_pattern),
    }
    url = source_url(repository_full_name, branch, "")
    while url:
        page = parse_json(get(session, url, params, MAX_ATTEMPTS))
        yield page.get("values") or []
        url = page.get("next")
        # The next URL already carries every query parameter.
        params = {}


def open_file_content(session, repository_full_name: str, branch: str, path: str):
    """
    Open a streaming request for a file's raw bytes. The caller reads response.raw and must close
    the response.
    Args:
        session: the authenticated HTTP session.
        repository_full_name: the repository's "workspace/slug" name.
        branch: the branch to read from.
        path: the file path within the repository.
    Returns:
        The streaming requests.Response.
    """
    response = get(
        session, source_url(repository_full_name, branch, path), {}, MAX_ATTEMPTS, stream=True
    )
    # Hand over the bytes exactly as stored, without HTTP content decoding surprises.
    response.raw.decode_content = True
    return response


def get(session, url: str, params: dict, max_attempts: int, stream=False):
    """
    Perform a GET, retrying rate limits, server errors and dropped connections with exponential
    backoff. Any other failure, such as a rejected token or a missing repository, is raised on the
    first attempt.
    Args:
        session: the authenticated HTTP session.
        url: the request URL.
        params: query parameters.
        max_attempts: attempts for the request, including the first one.
        stream: whether to stream the response body instead of reading it.
    Returns:
        The successful requests.Response.
    Raises:
        BitbucketApiError: when the call fails permanently or attempts are exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return attempt_get(session, url, params, stream)
        except BitbucketApiError as error:
            if not error.is_retriable or attempt == max_attempts:
                raise
            wait_seconds = min(
                __INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)), __MAX_BACKOFF_SECONDS
            )
            log.warning(
                f"Retrying Bitbucket API call after attempt {attempt} "
                f"(status {error.status_code or 'n/a'}); waiting {wait_seconds}s"
            )
            time.sleep(wait_seconds)
    raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")


def attempt_get(session, url: str, params: dict, stream: bool):
    """
    Perform a single GET and translate the outcome into a response or a BitbucketApiError.
    Args:
        session: the authenticated HTTP session.
        url: the request URL.
        params: query parameters.
        stream: whether to stream the response body instead of reading it.
    Returns:
        The successful requests.Response.
    Raises:
        BitbucketApiError: on a connection failure or a non-2xx status.
    """
    try:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS, stream=stream)
    except (requests.ConnectionError, requests.Timeout) as error:
        raise BitbucketApiError(f"Bitbucket request failed: {error}", is_retriable=True) from error
    if __FIRST_SUCCESS_STATUS <= response.status_code < __FIRST_REDIRECT_STATUS:
        return response
    status = response.status_code
    reason = response.reason or ""
    response.close()
    raise BitbucketApiError(
        f"HTTP {status} {reason}".strip(),
        status_code=status,
        is_retriable=status == __TOO_MANY_REQUESTS or status >= __FIRST_SERVER_ERROR_STATUS,
    )


def parse_json(response):
    """
    Parse a JSON response body.
    Args:
        response: the successful requests.Response.
    Returns:
        The parsed JSON.
    Raises:
        BitbucketApiError: when the body is not valid JSON.
    """
    try:
        return response.json()
    except ValueError as error:
        raise BitbucketApiError("Bitbucket response was not valid JSON") from error
