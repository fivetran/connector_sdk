"""Reads repository metadata from the GitHub REST API, used by connector.py.

Only a token can call the REST API, and file content comes over git, so this makes one request per
sync. No retry or rate-limit handling: at one request per sync against a 5,000 per hour limit, it
could never fire, and a failure only leaves the metadata columns of the repository row empty.
"""

# For making HTTP requests to the GitHub REST API
import requests

API_BASE_URL = "https://api.github.com"

__TIMEOUT_SECONDS = 300
__ACCEPT = "application/vnd.github+json"
__API_VERSION = "2022-11-28"
__NOT_FOUND = 404
__UNAUTHORIZED = 401
__FORBIDDEN = 403


def fetch_repository(token: str, repository: str):
    """
    Fetch a repository's metadata.
    Args:
        token: the personal access token.
        repository: the repository as owner/repository.
    Returns:
        The repository payload as a dictionary.
    Raises:
        requests.HTTPError: on a non-2xx response.
        requests.RequestException: on a connection failure or timeout.
    """
    response = requests.get(
        f"{API_BASE_URL}/repos/{repository}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": __ACCEPT,
            "X-GitHub-Api-Version": __API_VERSION,
        },
        timeout=__TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def repository_access_problem(token: str, repository: str):
    """
    Check that a repository exists and the token can read it. Distinguishes a missing repository
    from missing permission, which ls-remote cannot: GitHub denies both the same way over git.
    Args:
        token: the personal access token.
        repository: the repository as owner/repository.
    Returns:
        A message describing the problem, or None when the repository is readable.
    """
    try:
        fetch_repository(token, repository)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        if status == __NOT_FOUND:
            return (
                f'Repository "{repository}" was not found. '
                "Check the name and that the token has access to it."
            )
        if status in (__UNAUTHORIZED, __FORBIDDEN):
            return f'Access to repository "{repository}" was denied.'
        return f"Unable to reach GitHub: {error}"
    except requests.RequestException as error:
        return f"Unable to reach GitHub: {error}"
    return None


def metadata_columns(payload: dict):
    """
    Map the repository payload to the repository table's metadata columns.
    Args:
        payload: the repository payload.
    Returns:
        A dictionary of column name to value.
    """
    owner = payload.get("owner")
    return {
        "github_id": payload.get("id"),
        "node_id": payload.get("node_id"),
        "name": payload.get("name"),
        # As GitHub reports it, so it differs from id after a rename.
        "full_name": payload.get("full_name"),
        "owner": owner.get("login") if isinstance(owner, dict) else None,
        "description": payload.get("description"),
        "html_url": payload.get("html_url"),
        "default_branch": payload.get("default_branch"),
        "is_private": payload.get("private"),
        "is_fork": payload.get("fork"),
        "archived": payload.get("archived"),
        "disabled": payload.get("disabled"),
        # In KB, as GitHub reports it.
        "size": payload.get("size"),
        # Named main_language because language is a reserved SQL keyword.
        "main_language": payload.get("language"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "pushed_at": payload.get("pushed_at"),
    }
