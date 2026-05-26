"""CourseMill LMS v7.5 Fivetran Connector.

Syncs 10 tables from the CourseMill LMS REST API:
organizations, users, courses, curricula, curriculum_courses,
sessions, course_prerequisites, enrollments, transcripts, certificates.

Transcripts support incremental sync via date-range filtering.
All other tables use full-pull with upsert deduplication.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta

import requests

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
__PAGE_SIZE = 200
__MAX_RETRIES = 5
__REQUEST_TIMEOUT = 60
__CHECKPOINT_INTERVAL = 500
__INITIAL_SYNC_LOOKBACK_DAYS = 365


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _camel_to_snake(name: str) -> str:
    """Convert a camelCase or PascalCase string to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _snake_keys(record: dict) -> dict:
    """Return a new dict with all top-level keys converted to snake_case."""
    return {_camel_to_snake(k): v for k, v in record.items()}


def _serialize_value(value):
    """Serialize lists and dicts to JSON strings; pass scalars through."""
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def _clean_record(record: dict) -> dict:
    """Convert keys to snake_case and serialize complex values."""
    out = {}
    for k, v in record.items():
        out[_camel_to_snake(k)] = _serialize_value(v)
    return out


def _today_yyyymmdd() -> int:
    """Return today's date as an integer in yyyymmdd format."""
    return int(datetime.now(timezone.utc).strftime("%Y%m%d"))


def _date_str_to_yyyymmdd(date_str: str) -> int:
    """Convert an ISO date string or yyyymmdd string to integer yyyymmdd."""
    clean = date_str.replace("-", "").replace("T", "")[:8]
    return int(clean)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class CoursemillClient:
    """Wraps CourseMill API calls with authentication, pagination, and retry."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v1"
        self.username = username
        self.password = password
        self.token = None
        self.session = requests.Session()

    def authenticate(self):
        """Obtain a JWT token from the CourseMill auth endpoint."""
        url = f"{self.api_base}/auth"
        payload = {"username": self.username, "password": self.password}
        log.info("Authenticating with CourseMill API")

        for attempt in range(__MAX_RETRIES + 1):
            try:
                resp = self.session.post(url, json=payload, timeout=__REQUEST_TIMEOUT)
                resp.raise_for_status()
                body = resp.json()

                if body.get("status") != "OK":
                    raise ValueError(f"Authentication failed: status={body.get('status')}")

                self.token = body["token"]
                log.info("Authentication successful")
                return

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status and status >= 500 and attempt < __MAX_RETRIES:
                    wait = 2**attempt
                    log.warning(
                        f"Auth server error {status}, retrying in {wait}s (attempt {attempt + 1})"
                    )
                    time.sleep(wait)
                else:
                    log.severe(f"Authentication failed after {attempt + 1} attempts: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < __MAX_RETRIES:
                    wait = 2**attempt
                    log.warning(f"Auth request error, retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    log.severe(f"Authentication failed after {attempt + 1} attempts: {e}")
                    raise

    def _headers(self) -> dict:
        """Return request headers with the current auth token."""
        return {
            "X-Auth-Token": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self, method: str, path: str, params: dict = None, json_body: dict = None
    ) -> dict:
        """
        Execute an API request with retry logic and automatic re-authentication on 401.

        Args:
            method: HTTP method (GET, PUT, POST).
            path: API path relative to api_base (e.g., '/orgs').
            params: Query parameters.
            json_body: JSON body for PUT/POST requests.

        Returns:
            Parsed JSON response as a dict.
        """
        url = f"{self.api_base}{path}"

        for attempt in range(__MAX_RETRIES + 1):
            try:
                if self.token is None:
                    self.authenticate()

                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                    timeout=__REQUEST_TIMEOUT,
                )

                # Re-authenticate on 401 and retry
                if resp.status_code == 401:
                    log.warning("Received 401, re-authenticating")
                    self.authenticate()
                    resp = self.session.request(
                        method=method,
                        url=url,
                        headers=self._headers(),
                        params=params,
                        json=json_body,
                        timeout=__REQUEST_TIMEOUT,
                    )

                resp.raise_for_status()
                body = resp.json()

                # Refresh token if the response includes a new one
                if "token" in body and body["token"]:
                    self.token = body["token"]

                return body

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                is_retryable = status and (status >= 500 or status == 429)

                if is_retryable and attempt < __MAX_RETRIES:
                    wait = min(2**attempt, 30)
                    log.warning(
                        f"HTTP {status} on {method} {path}, retrying in {wait}s (attempt {attempt + 1})"
                    )
                    time.sleep(wait)
                else:
                    log.severe(f"Request failed: {method} {path} -> {e}")
                    raise

            except requests.exceptions.RequestException as e:
                if attempt < __MAX_RETRIES:
                    wait = min(2**attempt, 30)
                    log.warning(f"Request error on {method} {path}, retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    log.severe(
                        f"Request failed after {__MAX_RETRIES + 1} attempts: {method} {path} -> {e}"
                    )
                    raise

    def get(self, path: str, params: dict = None) -> dict:
        """Convenience wrapper for GET requests."""
        return self._request("GET", path, params=params)

    def put(self, path: str, json_body: dict = None, params: dict = None) -> dict:
        """Convenience wrapper for PUT requests."""
        return self._request("PUT", path, params=params, json_body=json_body)

    def get_paginated(self, path: str, params: dict = None):
        """
        Fetch all pages from a paginated endpoint and yield records as they are received.

        Args:
            path: API path.
            params: Additional query parameters.

        Yields:
            Individual records across all pages.
        """
        query_params = dict(params) if params is not None else {}
        query_params["size"] = __PAGE_SIZE
        query_params["page"] = 0

        while True:
            log.fine(f"Fetching {path} page={query_params['page']} size={query_params['size']}")
            body = self.get(path, params=query_params)

            data = body.get("data", [])
            if data is None:
                data = []

            if isinstance(data, dict):
                # Single-object response wrapped in data. Yield immediately to avoid
                # materializing all pages into memory before processing.
                yield data
                break

            # Stream each record from the current page immediately so large tables do
            # not accumulate in memory across the full pagination loop.
            for record in data:
                yield record

            is_last = body.get("last", True)
            if is_last:
                break

            query_params["page"] = query_params["page"] + 1


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": "organizations", "primary_key": ["org_id"]},
        {"table": "users", "primary_key": ["student_id"]},
        {"table": "courses", "primary_key": ["course_id"]},
        {"table": "curricula", "primary_key": ["curriculum_id"]},
        {"table": "curriculum_courses", "primary_key": ["curriculum_id", "course_id"]},
        {"table": "sessions", "primary_key": ["session_id"]},
        {"table": "course_prerequisites", "primary_key": ["course_id", "prerequisite_course_id"]},
        {"table": "enrollments", "primary_key": ["student_id", "course_id", "session_id"]},
        {"table": "transcripts", "primary_key": ["student_id", "course_id", "session_id"]},
        {"table": "certificates", "primary_key": ["student_id", "course_id", "curriculum_id"]},
    ]


# ---------------------------------------------------------------------------
# Table sync functions
# ---------------------------------------------------------------------------


def sync_organizations(client: CoursemillClient, state: dict):
    """Sync all organizations from GET /api/v1/orgs."""
    log.info("Syncing organizations")
    records = client.get_paginated("/orgs")
    count = 0
    for record in records:
        op.upsert("organizations", _clean_record(record))
        count += 1
        if count % __CHECKPOINT_INTERVAL == 0:
            op.checkpoint(state)
    log.info(f"Organizations synced: {count} records")
    op.checkpoint(state)


def sync_users(client: CoursemillClient, state: dict):
    """Sync all users from GET /api/v1/user."""
    log.info("Syncing users")
    records = client.get_paginated("/user")
    count = 0
    for record in records:
        op.upsert("users", _clean_record(record))
        count += 1
        if count % __CHECKPOINT_INTERVAL == 0:
            op.checkpoint(state)
    log.info(f"Users synced: {count} records")
    op.checkpoint(state)


def sync_courses(client: CoursemillClient, state: dict) -> list:
    """
    Sync all courses from GET /api/v1/courses.

    Returns:
        List of course records (raw, before cleaning) for use by child-table syncs.
    """
    log.info("Syncing courses")
    records = list(client.get_paginated("/courses"))  # collect before iterating
    count = 0
    for record in records:
        op.upsert("courses", _clean_record(record))
        count += 1
        if count % __CHECKPOINT_INTERVAL == 0:
            op.checkpoint(state)
    log.info(f"Courses synced: {count} records")
    op.checkpoint(state)
    return records


def sync_curricula(client: CoursemillClient, state: dict) -> list:
    """
    Sync all curricula from GET /api/v1/curricula.

    Returns:
        List of curriculum records (raw) for extracting curriculum_courses.
    """
    log.info("Syncing curricula")
    records = list(client.get_paginated("/curricula"))  # collect before iterating
    count = 0
    for record in records:
        op.upsert("curricula", _clean_record(record))
        count += 1
        if count % __CHECKPOINT_INTERVAL == 0:
            op.checkpoint(state)
    log.info(f"Curricula synced: {count} records")
    op.checkpoint(state)
    return records


def sync_curriculum_courses(client: CoursemillClient, state: dict, curricula: list):
    """
    Sync curriculum-course relationships by fetching detail for each curriculum.

    Each curriculum detail response at GET /api/v1/curricula/{curriculumId} contains
    a nested 'courses' array.
    """
    log.info("Syncing curriculum_courses")
    count = 0
    last_processed = state.get("curriculum_courses_last_id")
    skip = last_processed is not None

    for curriculum in curricula:
        curriculum_id = str(curriculum.get("curriculumId", curriculum.get("curriculum_id", "")))

        if skip:
            if curriculum_id == last_processed:
                skip = False
            continue

        try:
            detail = client.get(f"/curricula/{curriculum_id}")
        except requests.RequestException as error:
            log.warning(f"Failed to fetch courses for curriculum {curriculum_id}: {error}")
            continue

        if not isinstance(detail, dict):
            log.warning(
                f"Failed to parse courses for curriculum {curriculum_id}: response is not a dictionary"
            )
            continue

        data = detail.get("data", {})
        if not isinstance(data, dict):
            log.warning(
                f"Failed to parse courses for curriculum {curriculum_id}: 'data' is not a dictionary"
            )
            continue

        courses = data.get("courses", [])
        if not isinstance(courses, list):
            log.warning(
                f"Failed to parse courses for curriculum {curriculum_id}: 'courses' is not a list"
            )
            continue

        for course in courses:
            row = _clean_record(course)
            row["curriculum_id"] = curriculum_id
            if "course_id" not in row:
                row["course_id"] = row.get("courseId", row.get("id", ""))
            op.upsert("curriculum_courses", row)
            count += 1
        state["curriculum_courses_last_id"] = curriculum_id
        if count % __CHECKPOINT_INTERVAL == 0 and count > 0:
            op.checkpoint(state)

    # Clear resume cursor after full completion
    state.pop("curriculum_courses_last_id", None)
    log.info(f"Curriculum courses synced: {count} records")
    op.checkpoint(state)


def sync_sessions(client: CoursemillClient, state: dict, courses: list):
    """
    Sync sessions by iterating per course: GET /api/v1/sessions/course/{courseId}.
    Tracks last processed course_id in state for resume.
    """
    log.info("Syncing sessions")
    count = 0
    last_processed = state.get("sessions_last_course_id")
    skip = last_processed is not None

    for course in courses:
        course_id = str(course.get("courseId", course.get("course_id", "")))

        if skip:
            if course_id == last_processed:
                skip = False
            continue

        try:
            records = client.get_paginated(f"/sessions/course/{course_id}")
            for record in records:
                op.upsert("sessions", _clean_record(record))
                count += 1
        except Exception as e:
            log.warning(f"Failed to fetch sessions for course {course_id}: {e}")

        state["sessions_last_course_id"] = course_id
        if count % __CHECKPOINT_INTERVAL == 0 and count > 0:
            op.checkpoint(state)

    state.pop("sessions_last_course_id", None)
    log.info(f"Sessions synced: {count} records")
    op.checkpoint(state)


def sync_course_prerequisites(client: CoursemillClient, state: dict, courses: list):
    """
    Sync course prerequisites by iterating per course:
    GET /api/v1/courses/{courseId}/prerequisites.
    """
    log.info("Syncing course_prerequisites")
    count = 0
    last_processed = state.get("prerequisites_last_course_id")
    skip = last_processed is not None

    for course in courses:
        course_id = str(course.get("courseId", course.get("course_id", "")))

        if skip:
            if course_id == last_processed:
                skip = False
            continue

        try:
            body = client.get(f"/courses/{course_id}/prerequisites")
            data = body.get("data", [])
            if data is None:
                data = []
            if isinstance(data, dict):
                data = [data]

            for prereq in data:
                row = _clean_record(prereq)
                row["course_id"] = course_id
                if "prerequisite_course_id" not in row:
                    # Try common field names for the prerequisite ID
                    row["prerequisite_course_id"] = row.get(
                        "prereq_course_id", row.get("prerequisite_id", row.get("id", ""))
                    )
                op.upsert("course_prerequisites", row)
                count += 1
        except Exception as e:
            log.warning(f"Failed to fetch prerequisites for course {course_id}: {e}")

        state["prerequisites_last_course_id"] = course_id
        if count % __CHECKPOINT_INTERVAL == 0 and count > 0:
            op.checkpoint(state)

    state.pop("prerequisites_last_course_id", None)
    log.info(f"Course prerequisites synced: {count} records")
    op.checkpoint(state)


def sync_enrollments(client: CoursemillClient, state: dict, courses: list):
    """
    Sync enrollments (class roster) by iterating per course:
    GET /api/v1/reports/{courseId}/classRoster.
    """
    log.info("Syncing enrollments")
    count = 0
    last_processed = state.get("enrollments_last_course_id")
    skip = last_processed is not None

    for course in courses:
        course_id = str(course.get("courseId", course.get("course_id", "")))

        if skip:
            if course_id == last_processed:
                skip = False
            continue

        try:
            records = client.get_paginated(f"/reports/{course_id}/classRoster")
            for record in records:
                row = _clean_record(record)
                row["course_id"] = course_id
                op.upsert("enrollments", row)
                count += 1
        except Exception as e:
            log.warning(f"Failed to fetch enrollments for course {course_id}: {e}")

        state["enrollments_last_course_id"] = course_id
        if count % __CHECKPOINT_INTERVAL == 0 and count > 0:
            op.checkpoint(state)

    state.pop("enrollments_last_course_id", None)
    log.info(f"Enrollments synced: {count} records")
    op.checkpoint(state)


def sync_transcripts(client: CoursemillClient, state: dict):
    """
    Sync transcripts with incremental date-range filtering.

    GET /api/v1/transcript supports startDate and endDate params in yyyymmdd integer format.
    State tracks 'transcript_last_sync_date' to enable incremental syncs.
    """
    log.info("Syncing transcripts (incremental)")

    today = _today_yyyymmdd()
    last_sync = state.get("transcript_last_sync_date")

    if last_sync:
        start_date = int(last_sync)
    else:
        # First sync: look back one year
        one_year_ago = datetime.now(timezone.utc) - timedelta(days=__INITIAL_SYNC_LOOKBACK_DAYS)
        start_date = int(one_year_ago.strftime("%Y%m%d"))

    log.info(f"Transcript date range: {start_date} to {today}")

    params = {
        "startDate": start_date,
        "endDate": today,
    }

    records = client.get_paginated("/transcript", params=params)
    count = 0
    for record in records:
        op.upsert("transcripts", _clean_record(record))
        count += 1
        if count % __CHECKPOINT_INTERVAL == 0:
            state["transcript_last_sync_date"] = str(today)
            op.checkpoint(state)

    state["transcript_last_sync_date"] = str(today)
    log.info(f"Transcripts synced: {count} records")
    op.checkpoint(state)


def sync_certificates(client: CoursemillClient, state: dict):
    """
    Sync certificates via PUT /api/v1/users/certificates.
    Note: CourseMill uses PUT (not GET) for this endpoint.
    """
    log.info("Syncing certificates")

    body = client.put("/users/certificates")
    data = body.get("data", [])
    if data is None:
        data = []
    if isinstance(data, dict):
        data = [data]

    count = 0
    for record in data:
        op.upsert("certificates", _clean_record(record))
        count += 1
        if count % __CHECKPOINT_INTERVAL == 0:
            op.checkpoint(state)

    log.info(f"Certificates synced: {count} records")
    op.checkpoint(state)


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


def validate_configuration(configuration: dict):
    """
    Validate that all required configuration fields are present and non-empty.

    Args:
        configuration: Connector configuration dictionary.

    Raises:
        ValueError: If a required field is missing or empty.
    """
    required_fields = ["base_url", "username", "password"]
    for field in required_fields:
        if not configuration.get(field):
            raise ValueError(f"Missing required configuration field: '{field}'")


# ---------------------------------------------------------------------------
# Update (main sync entry point)
# ---------------------------------------------------------------------------


def update(configuration: dict, state: dict):
    """
    Main sync function called by Fivetran on each sync run.

    Sync order: organizations -> users -> courses -> curricula ->
    curriculum_courses -> sessions -> course_prerequisites ->
    enrollments -> transcripts -> certificates.

    Args:
        configuration: Connector configuration with base_url, username, password.
        state: Persistent state dictionary for incremental syncs and resume.
    """
    log.warning("Example: <CATEGORY> : <EXAMPLE_NAME>")
    log.info("CourseMill LMS connector sync starting")
    validate_configuration(configuration)

    client = CoursemillClient(
        base_url=configuration["base_url"],
        username=configuration["username"],
        password=configuration["password"],
    )
    client.authenticate()

    # 1. Organizations (standalone)
    sync_organizations(client, state)

    # 2. Users (standalone)
    sync_users(client, state)

    # 3. Courses (returns raw records for child tables)
    courses = sync_courses(client, state)

    # 4. Curricula (returns raw records for curriculum_courses)
    curricula = sync_curricula(client, state)

    # 5. Curriculum-Course relationships
    sync_curriculum_courses(client, state, curricula)

    # 6. Sessions (per-course iteration)
    sync_sessions(client, state, courses)

    # 7. Course prerequisites (per-course iteration)
    sync_course_prerequisites(client, state, courses)

    # 8. Enrollments (per-course iteration)
    sync_enrollments(client, state, courses)

    # 9. Transcripts (incremental via date range)
    sync_transcripts(client, state)

    # 10. Certificates
    sync_certificates(client, state)

    log.info("CourseMill LMS connector sync complete")


# ---------------------------------------------------------------------------
# Connector object
# ---------------------------------------------------------------------------

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
