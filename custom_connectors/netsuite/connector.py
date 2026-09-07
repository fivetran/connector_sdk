"""NetSuite connector using SuiteQL via SuiteTalk REST Web Services (no SuiteAnalytics required).

Full architecture, setup, and design rationale: see README.md. Quick orientation:
- Auth: NetSuite Token-Based Authentication (OAuth 1.0a, HMAC-SHA256) via `requests_oauthlib`.
- Table list/columns/joins are hardcoded (__TABLES) - only date range and subsidiaries configure.
- Full re-sync every run: no incremental cursor, no delete detection.
- NetSuite caps SuiteQL at 100,000 rows/query - date-filtered tables use adaptive
  multi-dimensional window splitting to guarantee full coverage regardless of account size.
  See sync_windowed_table's docstring for the algorithm; see README's "Handling large accounts"
  for the full rationale and verification results.

Docs: https://fivetran.com/docs/connector-sdk/technical-reference
"""

import json  # configuration.json (local debug entry point only)
import time  # retry/backoff delays

from datetime import date, datetime, timedelta, timezone  # date-window arithmetic
import requests as rq  # HTTP requests to the NetSuite SuiteQL REST endpoint

try:
    from requests_oauthlib import OAuth1  # OAuth 1.0a (HMAC-SHA256) signing for NetSuite TBA
except ImportError as import_error:  # pragma: no cover - defensive import guard
    raise ImportError(
        "The 'requests_oauthlib' package is required for NetSuite OAuth 1.0a (HMAC-SHA256) "
        "authentication but is not installed. Ensure 'requests_oauthlib' is listed in "
        "requirements.txt."
    ) from import_error

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector, Logging as log, Operations as op, ConfigurationForm, Test
from fivetran_connector_sdk import form_field  # setup form field types (TextField, etc.)

# NetSuite SuiteQL REST endpoint path, appended to the account-specific host.
__SUITEQL_PATH = "/services/rest/query/v1/suiteql"

__PAGE_LIMIT = 1000  # max rows/page allowed by the SuiteQL REST endpoint

# NetSuite's hard cap on rows a single SuiteQL query can page through (enforced server-side).
# See README "Handling large accounts" for how this connector works around it.
__MAX_ROWS_PER_TABLE = 100_000

# Safety margin below __MAX_ROWS_PER_TABLE for deciding a window is safe to fetch directly.
__SAFE_ROW_THRESHOLD = __MAX_ROWS_PER_TABLE - 10_000

# Retry/backoff for transient HTTP errors (429, 5xx, network errors).
__MAX_RETRIES = 5
__BASE_RETRY_DELAY_SECONDS = 1
__MAX_RETRY_DELAY_SECONDS = 30
__REQUEST_TIMEOUT_SECONDS = 60  # page fetches
__AGGREGATE_REQUEST_TIMEOUT_SECONDS = 150  # COUNT/MIN/MAX - always 1 row, so more room to wait

# Literal 'date_to' value meaning "today, re-resolved every sync" - see resolve_date_to.
__TODAY_PLACEHOLDER = "TODAY"

# Hardcoded table/column/join list this connector syncs - not configurable. Tables with neither
# 'date_column' nor 'filter_via' (the 3 dimension tables) sync unfiltered every run; the rest are
# filtered by date/subsidiary and use adaptive window splitting (see table_has_date_filter,
# sync_windowed_table). 'columns' is narrowed to the GL/Trial-Balance field subset per table.
# 'transaction_id_column' is the last-resort split dimension (see split_id_range).
# Schema quirks and join rationale behind this config: see README "What's synced".
__TABLES = [
    {
        "table": "subsidiary",
        "primary_key": ["id"],
    },
    {
        "table": "account",
        "columns": ["id", "acctnumber", "accountsearchdisplayname", "accttype", "subsidiary", "isinactive"],
        "primary_key": ["id"],
    },
    {
        "table": "accountingperiod",
        "primary_key": ["id"],
    },
    {
        "table": "transactionline",
        "alias": "tl",
        "columns": ["transaction", "linesequencenumber", "subsidiary", "department", "class", "location", "memo"],
        "primary_key": ["transaction", "linesequencenumber"],
        "joins": [{"table": "transaction", "alias": "t", "on": "t.id = tl.transaction"}],
        "date_column": "t.trandate",
        "subsidiary_column": "tl.subsidiary",
        # NOT 'transactionline.id' - empirically not a real per-row identifier here. See README.
        "transaction_id_column": "tl.transaction",
    },
    {
        "table": "transaction",
        "alias": "t",
        "columns": ["id", "tranid", "trandate", "type", "entity", "memo", "status"],
        "primary_key": ["id"],
        "transaction_id_column": "t.id",
        # No 'subsidiary'/usable date of its own - filtered via membership in transactionline's
        # matching rows instead (see build_from_joins_where's filter_via handling).
        "filter_via": {
            "table": "transactionline",
            "alias": "tl",
            "join_column": "id",
            "select_column": "tl.transaction",
            "joins": [{"table": "transaction", "alias": "t2", "on": "t2.id = tl.transaction"}],
            "date_column": "t2.trandate",
            "subsidiary_column": "tl.subsidiary",
        },
    },
    {
        "table": "transactionaccountingline",
        "alias": "tal",
        "columns": [
            "transaction",
            "transactionline",
            "account",
            "accountingbook",
            "debit",
            "credit",
            "amount",
            "netamount",
            "posting",
        ],
        "primary_key": ["transaction", "transactionline", "accountingbook"],
        "joins": [
            {"table": "transaction", "alias": "t", "on": "t.id = tal.transaction"},
            {
                "table": "transactionline",
                "alias": "tl2",
                "on": "tl2.transaction = tal.transaction AND tl2.linesequencenumber = tal.transactionline",
            },
        ],
        "date_column": "t.trandate",
        "subsidiary_column": "tl2.subsidiary",
        "transaction_id_column": "tal.transaction",
    },
]


def validate_configuration(configuration: dict):
    """
    Fail fast if any required configuration value is missing. See README "Configuration".
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = [
        "account_id",
        "consumer_key",
        "consumer_secret",
        "token_key",
        "token_secret",
        "date_from",
        "subsidiaries",
    ]
    missing = [key for key in required_configs if not configuration.get(key)]
    if missing:
        raise ValueError(f"Missing required configuration value(s): {', '.join(missing)}")


def parse_subsidiaries(configuration: dict) -> list:
    """
    Parse configuration's comma-separated 'subsidiaries' (e.g. "1,2,3") into a list of ID strings.
    Raises:
        ValueError: if no subsidiary IDs remain after parsing.
    """
    raw_value = configuration.get("subsidiaries", "")
    subsidiary_ids = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not subsidiary_ids:
        raise ValueError(
            "Configuration value 'subsidiaries' must be a non-empty comma-separated list of "
            f"subsidiary internal IDs (e.g. '1,2,3'). Got: {raw_value!r}"
        )
    return subsidiary_ids


def build_account_host(account_id: str) -> str:
    """Derive the SuiteTalk host from an account id, e.g. 'TSTDRV2028961' -> 'tstdrv2028961.suitetalk.api.netsuite.com'."""
    normalized = account_id.strip().lower().replace("_", "-")
    return f"{normalized}.suitetalk.api.netsuite.com"


def get_oauth1_auth(configuration: dict):
    """Build the OAuth1 (HMAC-SHA256) auth handler for NetSuite TBA - see README "Authentication setup"."""
    return OAuth1(
        client_key=configuration["consumer_key"],
        client_secret=configuration["consumer_secret"],
        resource_owner_key=configuration["token_key"],
        resource_owner_secret=configuration["token_secret"],
        signature_method="HMAC-SHA256",
        realm=configuration["account_id"].strip().upper(),
    )


def resolve_date_to(configuration: dict):
    """Resolve optional 'date_to': None if omitted (open-ended range), __TODAY_PLACEHOLDER -> today, else passed through."""
    raw_value = configuration.get("date_to")
    if not raw_value:
        return None
    if raw_value == __TODAY_PLACEHOLDER:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return raw_value


def parse_date(value: str) -> date:
    """Parse a 'YYYY-MM-DD' string into a date object."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_date(value: date) -> str:
    """Format a date object back into 'YYYY-MM-DD'."""
    return value.strftime("%Y-%m-%d")


def split_window(window_start: str, window_end, today: str):
    """
    Bisect a date window by calendar midpoint - see sync_windowed_table's docstring/README
    "Handling large accounts" for the full splitting algorithm.
    Args:
        window_end: inclusive upper bound, or None for open-ended (date_to not configured).
        today: current date, used only as the effective bound for splitting an open-ended
        window - the right half stays open-ended (end=None), never written as a filter value.
    Returns:
        ((left_start, left_end), (right_start, right_end)), or None if unsplittable (single day).
    """
    start_date = parse_date(window_start)
    effective_end_date = parse_date(window_end) if window_end is not None else parse_date(today)

    if start_date >= effective_end_date:
        return None

    midpoint_date = start_date + (effective_end_date - start_date) // 2
    left = (window_start, format_date(midpoint_date))
    right_start = format_date(midpoint_date + timedelta(days=1))
    right = (right_start, window_end)  # preserve None (open-ended) on the right half
    return left, right


def build_from_clause(table_name: str, alias: str = None) -> str:
    """Build 'table_name' or 'table_name alias' (only qualifies when an alias differs from the table name)."""
    if alias and alias != table_name:
        return f"{table_name} {alias}"
    return table_name


def build_joins_clause(joins: list) -> str:
    """Build zero or more 'JOIN <table> <alias> ON <condition>' clauses from a __TABLES 'joins' list."""
    if not joins:
        return ""
    return " ".join(f"JOIN {j['table']} {j['alias']} ON {j['on']}" for j in joins)


def build_filter_clause(filter_config: dict, date_from: str, date_to, subsidiary_ids: list):
    """
    Build the WHERE fragment + bind params for a config with 'date_column'/'subsidiary_column'
    (either key absent -> no filter for it; both absent -> unfiltered, used by dimension tables).
    Returns:
        (where_clause_string_or_None, bind_params_list).
    """
    conditions = []
    params = []

    date_column = filter_config.get("date_column")
    if date_column:
        if date_to is not None:
            conditions.append(f"{date_column} BETWEEN TO_DATE(?, 'YYYY-MM-DD') AND TO_DATE(?, 'YYYY-MM-DD')")
            params.extend([date_from, date_to])
        else:
            conditions.append(f"{date_column} >= TO_DATE(?, 'YYYY-MM-DD')")
            params.append(date_from)

    subsidiary_column = filter_config.get("subsidiary_column")
    if subsidiary_column:
        placeholders = ", ".join(["?"] * len(subsidiary_ids))
        conditions.append(f"{subsidiary_column} IN ({placeholders})")
        params.extend(subsidiary_ids)

    if not conditions:
        return None, params
    return " AND ".join(conditions), params


def table_has_date_filter(table_config: dict) -> bool:
    """True if a table is date-filtered (directly or via 'filter_via') and needs sync_windowed_table."""
    if table_config.get("date_column"):
        return True
    filter_via = table_config.get("filter_via")
    return bool(filter_via and filter_via.get("date_column"))


def build_from_joins_where(table_config: dict, alias: str, date_from: str, date_to, subsidiary_ids: list, id_range=None):
    """
    Build the 'FROM ... [JOIN ...] [WHERE ...]' portion of a query. Shared by build_query and
    build_count_query so the row-count check and the actual data fetch can never disagree - see
    README "What's synced" for the join-filter rationale (especially the 'filter_via' subquery
    case, used by 'transaction', which has no subsidiary/date column of its own).
    Args:
        id_range: optional (min_id, max_id) transaction-ID bound, ANDed onto the outer query
        (outside any filter_via subquery) - the last-resort split dimension, see split_id_range.
    Returns:
        (sql_fragment, bind_params_list) - sql_fragment starts with 'FROM'.
    """
    from_clause = build_from_clause(table_config["table"], alias)
    joins_clause = build_joins_clause(table_config.get("joins"))
    sql = f"FROM {from_clause}"
    if joins_clause:
        sql += f" {joins_clause}"

    filter_via = table_config.get("filter_via")
    if filter_via:
        subquery_table = filter_via["table"]
        subquery_alias = filter_via.get("alias", subquery_table)
        select_column = filter_via["select_column"]
        join_column = filter_via["join_column"]
        subquery_from_clause = build_from_clause(subquery_table, subquery_alias)
        subquery_joins_clause = build_joins_clause(filter_via.get("joins"))
        subquery_where, params = build_filter_clause(filter_via, date_from, date_to, subsidiary_ids)

        subquery = f"SELECT DISTINCT {select_column} FROM {subquery_from_clause}"
        if subquery_joins_clause:
            subquery += f" {subquery_joins_clause}"
        if subquery_where:
            subquery += f" WHERE {subquery_where}"

        sql += f" WHERE {alias}.{join_column} IN ({subquery})"
    else:
        where_clause, params = build_filter_clause(table_config, date_from, date_to, subsidiary_ids)
        if where_clause:
            sql += f" WHERE {where_clause}"

    transaction_id_column = table_config.get("transaction_id_column")
    if id_range is not None and transaction_id_column:
        id_condition = f"{transaction_id_column} BETWEEN ? AND ?"
        sql += f" AND {id_condition}" if "WHERE" in sql else f" WHERE {id_condition}"
        params = params + list(id_range)

    return sql, params


def table_alias(table_config: dict) -> str:
    """Return a table's configured alias, or its own table name if none was set."""
    return table_config.get("alias", table_config["table"])


def build_query(table_config: dict, date_from: str, date_to, subsidiary_ids: list, id_range=None):
    """
    Build the full SuiteQL SELECT + bind params for one __TABLES entry over a date window
    (possibly a sub-window from adaptive splitting). Columns are always alias-qualified
    ('{alias}.*' or the table's narrowed 'columns' list) - a bare '*' would also pull in any
    joined table's columns. Bind params, never string interpolation, for filter values.
    Args:
        id_range: optional (min_id, max_id) restriction - see build_from_joins_where.
    Returns:
        (query_string, bind_params_list).
    """
    alias = table_alias(table_config)
    primary_key = table_config["primary_key"]
    order_by_clause = ", ".join(f"{alias}.{col}" for col in primary_key)

    columns = table_config.get("columns")
    select_list = ", ".join(f"{alias}.{col}" for col in columns) if columns else f"{alias}.*"

    from_joins_where, params = build_from_joins_where(table_config, alias, date_from, date_to, subsidiary_ids, id_range)
    query = f"SELECT {select_list} {from_joins_where} ORDER BY {order_by_clause}"
    return query, params


def build_count_query(table_config: dict, date_from: str, date_to, subsidiary_ids: list, id_range=None):
    """Build 'SELECT COUNT(*)' via the same build_from_joins_where as build_query, so count and fetch never disagree."""
    alias = table_alias(table_config)
    from_joins_where, params = build_from_joins_where(table_config, alias, date_from, date_to, subsidiary_ids, id_range)
    query = f"SELECT COUNT(*) AS cnt {from_joins_where}"
    return query, params


def build_id_range_query(table_config: dict, date_from: str, date_to, subsidiary_ids: list):
    """Build 'SELECT MIN/MAX(transaction_id_column)' for the last-resort ID-range split (see split_id_range)."""
    alias = table_alias(table_config)
    id_column = table_config["transaction_id_column"]
    from_joins_where, params = build_from_joins_where(table_config, alias, date_from, date_to, subsidiary_ids)
    query = f"SELECT MIN({id_column}) AS min_id, MAX({id_column}) AS max_id {from_joins_where}"
    return query, params


def compute_backoff_delay(attempt: int, retry_after_header=None) -> float:
    """Seconds to sleep before the next retry: honors Retry-After if present, else capped exponential backoff."""
    if retry_after_header is not None:
        try:
            return float(retry_after_header)
        except (TypeError, ValueError):
            pass
    return min(__MAX_RETRY_DELAY_SECONDS, __BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))


def execute_suiteql(
    session, base_url: str, auth, query: str, params: list, limit: int, offset: int,
    timeout: int = __REQUEST_TIMEOUT_SECONDS,
) -> dict:
    """
    Execute one SuiteQL request, retrying transient failures (429, 5xx, network errors) with
    exponential backoff. `session` is shared across the whole sync for connection reuse.
    Returns:
        Parsed JSON response body ('items', 'hasMore', etc.).
    Raises:
        RuntimeError: after __MAX_RETRIES attempts, or on a non-retryable HTTP error.
    """
    url = f"{base_url}?limit={limit}&offset={offset}"
    headers = {
        "Content-Type": "application/json",
        "Prefer": "transient",  # don't persist this ad-hoc query as a saved search
    }
    body = {"q": query}
    if params:
        body["params"] = params

    last_error_message = None
    for attempt in range(1, __MAX_RETRIES + 1):
        try:
            response = session.post(
                url, auth=auth, headers=headers, json=body, timeout=timeout
            )
        except rq.exceptions.RequestException as request_error:
            last_error_message = f"Request error: {request_error}"
            if attempt == __MAX_RETRIES:
                break
            delay = compute_backoff_delay(attempt)
            log.warning(
                f"SuiteQL request failed (attempt {attempt}/{__MAX_RETRIES}): {request_error}. "
                f"Retrying in {delay:.1f}s"
            )
            time.sleep(delay)
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429 or 500 <= response.status_code < 600:
            last_error_message = f"HTTP {response.status_code}: {response.text[:500]}"
            if attempt == __MAX_RETRIES:
                break
            delay = compute_backoff_delay(attempt, response.headers.get("Retry-After"))
            log.warning(
                f"SuiteQL request returned HTTP {response.status_code} "
                f"(attempt {attempt}/{__MAX_RETRIES}). Retrying in {delay:.1f}s"
            )
            time.sleep(delay)
            continue

        # Non-retryable client error (4xx other than 429) - fail fast rather than retrying.
        raise RuntimeError(
            f"SuiteQL request failed with a non-retryable error: HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    raise RuntimeError(
        f"SuiteQL request failed after {__MAX_RETRIES} attempts at offset {offset}: "
        f"{last_error_message}"
    )


def split_id_range(min_id: str, max_id: str):
    """
    Bisect a transaction-ID range - split_window's integer analogue, the last-resort split
    dimension (see README "Handling large accounts").
    Returns:
        ((left_min, left_max), (right_min, right_max)), or None if unsplittable (min == max).
    """
    min_val = int(min_id)
    max_val = int(max_id)
    if min_val >= max_val:
        return None
    midpoint = min_val + (max_val - min_val) // 2
    left = (str(min_val), str(midpoint))
    right = (str(midpoint + 1), str(max_val))
    return left, right


def get_id_range(session, base_url: str, auth, table_config: dict, date_from: str, date_to, subsidiary_ids: list):
    """
    Discover MIN/MAX transaction id for a window - starting point for ID-range splitting.
    Returns:
        (min_id, max_id) strings, or None if the window has no rows (defensive; shouldn't
        normally happen since this is only called after a COUNT already found rows).
    """
    query, params = build_id_range_query(table_config, date_from, date_to, subsidiary_ids)
    page = execute_suiteql(
        session, base_url, auth, query, params, limit=1, offset=0,
        timeout=__AGGREGATE_REQUEST_TIMEOUT_SECONDS,
    )
    items = page.get("items", [])
    if not items or items[0].get("min_id") is None:
        return None
    return items[0]["min_id"], items[0]["max_id"]


def get_row_count(
    session, base_url: str, auth, table_config: dict, date_from: str, date_to, subsidiary_ids: list, id_range=None
) -> int:
    """Exact row count for a window, used by sync_windowed_table to decide whether it's safe to fetch or must split."""
    query, params = build_count_query(table_config, date_from, date_to, subsidiary_ids, id_range)
    page = execute_suiteql(
        session, base_url, auth, query, params, limit=1, offset=0,
        timeout=__AGGREGATE_REQUEST_TIMEOUT_SECONDS,
    )
    items = page.get("items", [])
    if not items:
        return 0
    return int(items[0]["cnt"])


def sync_simple_table(session, base_url: str, auth, table_config: dict, state: dict) -> int:
    """
    Fully sync one unfiltered dimension table ('subsidiary'/'account'/'accountingperiod') - a
    single query, paged until exhausted. No splitting mechanism applies here (no date column to
    split by), so the overflow check below raises rather than silently truncating if this table
    ever unexpectedly reaches the row cap.
    Returns:
        Total rows upserted.
    Raises:
        RuntimeError: if __MAX_ROWS_PER_TABLE is reached with more rows still available.
    """
    table_name = table_config["table"]
    query, params = build_query(table_config, date_from=None, date_to=None, subsidiary_ids=[])

    tables_state = state.setdefault("tables", {})
    table_state = tables_state.get(table_name)
    if table_state is None or table_state.get("completed"):
        table_state = {"offset": 0, "completed": False}
    tables_state[table_name] = table_state

    total_rows = table_state["offset"]
    started_at = time.time()
    log.info(
        f"Starting sync for table '{table_name}' "
        f"({'resuming at offset ' + str(total_rows) if total_rows else 'starting fresh'})"
    )
    log.debug(f"Table '{table_name}' SuiteQL query: {query}")

    while True:
        offset = table_state["offset"]
        page = execute_suiteql(session, base_url, auth, query, params, limit=__PAGE_LIMIT, offset=offset)
        items = page.get("items", [])

        for row in items:
            op.upsert(table=table_name, data=row)

        total_rows += len(items)
        has_more = bool(page.get("hasMore"))
        table_state["offset"] = offset + __PAGE_LIMIT

        if not has_more:
            break

        if total_rows >= __MAX_ROWS_PER_TABLE:
            raise RuntimeError(
                f"Table '{table_name}' has reached {total_rows} row(s) with more still available "
                f"from NetSuite (hard cap: {__MAX_ROWS_PER_TABLE}). This table is synced as an "
                "unfiltered whole (no date/subsidiary splitting applies to it), so this cap "
                "cannot be worked around the way it is for the transaction-related tables - "
                "raising rather than silently truncating."
            )

        op.checkpoint(state)
        # DEBUG (not INFO): fires once per 1,000 rows - would be excessive at production-visible
        # INFO level for a large table. Full per-page detail is still available via `fivetran debug`.
        log.debug(f"Table '{table_name}': synced {total_rows} row(s) so far (next offset {table_state['offset']})")

    tables_state[table_name] = {"completed": True}
    op.checkpoint(state)
    log.info(f"Completed sync for table '{table_name}' in {time.time() - started_at:.1f}s. Total rows upserted: {total_rows}")
    return total_rows


def sync_windowed_table(
    session, base_url: str, auth, table_config: dict, state: dict, date_from: str, date_to, subsidiary_ids: list, today: str
) -> int:
    """
    Fully sync one date-filtered table via adaptive multi-dimensional window splitting, to
    guarantee complete coverage regardless of account size given NetSuite's 100,000-row/query
    cap. Full algorithm, rationale, and live-account verification: README "Handling large
    accounts". In short - per window, recursively: COUNT it; if safe, page and upsert it; if not,
    split by date, then (once date-exhausted) by subsidiary, then (once that's exhausted too) by
    transaction-ID range; if all three dimensions are exhausted and it's still over threshold,
    raise rather than silently truncate.

    State holds a list of windows (date range, subsidiary subset, optional id_range, offset) so
    an interrupted sync resumes mid-window without redoing completed work.
    Returns:
        Total rows upserted (persisted in state across however many attempts it took).
    Raises:
        RuntimeError: a window exhausted all three splitting dimensions and is still oversized.
    """
    table_name = table_config["table"]
    started_at = time.time()

    tables_state = state.setdefault("tables", {})
    table_state = tables_state.get(table_name)
    if table_state is None or table_state.get("completed") or "windows" not in table_state:
        table_state = {
            "windows": [
                {"start": date_from, "end": date_to, "subsidiary_ids": subsidiary_ids, "offset": 0}
            ],
            "completed": False,
            "total_rows": 0,
        }
        tables_state[table_name] = table_state
        op.checkpoint(state)
        log.info(f"Starting sync for table '{table_name}' (starting fresh)")
    else:
        log.info(
            f"Starting sync for table '{table_name}' (resuming with "
            f"{len(table_state['windows'])} window(s) pending)"
        )

    windows = table_state["windows"]
    total_rows = table_state.get("total_rows", 0)
    i = 0
    while i < len(windows):
        window = windows[i]
        if window.get("completed"):
            # Old-format state marked windows completed instead of removing them - drop safely.
            windows[i:i + 1] = []
            continue

        w_start, w_end = window["start"], window["end"]
        # Fall back for state checkpointed before subsidiary/id-range splitting existed.
        w_subsidiary_ids = window.get("subsidiary_ids", subsidiary_ids)
        w_id_range = window.get("id_range")
        window_label = f"{w_start} to {w_end or 'present'}, subsidiaries {w_subsidiary_ids}"
        if w_id_range is not None:
            window_label += f", transaction id {w_id_range[0]} to {w_id_range[1]}"

        def replace_window_with(replacement_windows):
            """Splice replacements in at this window's position and checkpoint - shared tail of each split stage below."""
            windows[i:i + 1] = replacement_windows
            op.checkpoint(state)

        # Only count/decide-to-split a window not yet started (offset 0) - one with progress was
        # already found safe on a prior pass, so just keep paging it.
        if window["offset"] == 0:
            count = get_row_count(session, base_url, auth, table_config, w_start, w_end, w_subsidiary_ids, w_id_range)
            log.debug(f"Table '{table_name}': window {window_label} has {count} row(s)")

            if count > __SAFE_ROW_THRESHOLD:
                # Stage 1: split by date (skip if already id-range splitting - that's post-date).
                split = split_window(w_start, w_end, today) if w_id_range is None else None
                if split is not None:
                    left, right = split
                    log.info(
                        f"Table '{table_name}': window {window_label} has {count} row(s), "
                        f"exceeding the safe threshold of {__SAFE_ROW_THRESHOLD} - splitting by "
                        f"date into {left[0]} to {left[1]} and {right[0]} to {right[1] or 'present'}"
                    )
                    replace_window_with([
                        {"start": left[0], "end": left[1], "subsidiary_ids": w_subsidiary_ids, "offset": 0},
                        {"start": right[0], "end": right[1], "subsidiary_ids": w_subsidiary_ids, "offset": 0},
                    ])
                    continue  # re-examine the new first half at the same index

                # Stage 2: date exhausted (single day) - split by subsidiary instead, if >1 left.
                if w_id_range is None and len(w_subsidiary_ids) > 1:
                    log.info(
                        f"Table '{table_name}': window {window_label} has {count} row(s) and is "
                        f"already a single day - splitting by subsidiary instead into "
                        f"{len(w_subsidiary_ids)} single-subsidiary windows"
                    )
                    replace_window_with([
                        {"start": w_start, "end": w_end, "subsidiary_ids": [sid], "offset": 0}
                        for sid in w_subsidiary_ids
                    ])
                    continue  # re-examine the new first single-subsidiary window at the same index

                # Stage 3: date and subsidiary both exhausted - last resort, split by transaction
                # ID range (different skew profile than date - see README).
                id_bounds = w_id_range if w_id_range is not None else get_id_range(
                    session, base_url, auth, table_config, w_start, w_end, w_subsidiary_ids
                )
                id_split = split_id_range(*id_bounds) if id_bounds is not None else None
                if id_split is not None:
                    left_ids, right_ids = id_split
                    log.info(
                        f"Table '{table_name}': window {window_label} has {count} row(s) and is "
                        "already a single day for a single subsidiary - splitting by transaction "
                        f"id instead into {left_ids[0]}-{left_ids[1]} and {right_ids[0]}-{right_ids[1]}"
                    )
                    replace_window_with([
                        {"start": w_start, "end": w_end, "subsidiary_ids": w_subsidiary_ids, "id_range": left_ids, "offset": 0},
                        {"start": w_start, "end": w_end, "subsidiary_ids": w_subsidiary_ids, "id_range": right_ids, "offset": 0},
                    ])
                    continue  # re-examine the new first id-range half at the same index

                # All dimensions exhausted and still over threshold - raise, don't truncate.
                raise RuntimeError(
                    f"Table '{table_name}': the window {window_label} has {count} row(s), "
                    f"exceeding the safe threshold of {__SAFE_ROW_THRESHOLD} (NetSuite's SuiteQL "
                    "hard cap is 100,000 rows/query), and cannot be split further - it is already "
                    "a single day for a single subsidiary" + (
                        " and a single transaction id" if w_id_range is not None else ""
                    ) + ". Full coverage cannot be guaranteed for this window as configured."
                )

            # Confirmed safe - one INFO line per window (not per page) gives volume visibility
            # that scales with sync complexity (window count, inherently small - splitting is
            # logarithmic) rather than sync size (row count, which could be in the millions).
            log.info(f"Table '{table_name}': window {window_label} - {count} row(s), fetching")

        # Safe to fetch this window directly.
        query, params = build_query(table_config, w_start, w_end, w_subsidiary_ids, w_id_range)
        log.debug(f"Table '{table_name}' SuiteQL query for window {window_label}: {query}")
        window_total = window["offset"]

        while True:
            offset = window["offset"]
            page = execute_suiteql(session, base_url, auth, query, params, limit=__PAGE_LIMIT, offset=offset)
            items = page.get("items", [])

            for row in items:
                op.upsert(table=table_name, data=row)

            window_total += len(items)
            has_more = bool(page.get("hasMore"))
            window["offset"] = offset + __PAGE_LIMIT

            if has_more:
                op.checkpoint(state)
                # DEBUG (not INFO): fires once per 1,000 rows - see sync_simple_table's identical
                # rationale. The per-window INFO lines above/below give production-visible
                # progress without per-page noise.
                log.debug(
                    f"Table '{table_name}' window {window_label}: synced {window_total} row(s) so "
                    f"far (next offset {window['offset']})"
                )
            else:
                break

        total_rows += window_total
        table_state["total_rows"] = total_rows
        log.info(f"Table '{table_name}': window {window_label} complete - {window_total} row(s)")
        windows[i:i + 1] = []  # drop the completed window rather than let state accumulate it
        op.checkpoint(state)

    tables_state[table_name] = {"completed": True}
    op.checkpoint(state)
    log.info(f"Completed sync for table '{table_name}' in {time.time() - started_at:.1f}s. Total rows upserted: {total_rows}")
    return total_rows


def configuration_form():
    """
    Setup form shown when configuring this connector in Fivetran - mirrors validate_configuration's
    required fields, masking the two OAuth secret halves (consumer_secret, token_secret) and
    registering connection_test as the "Test Connection" check.
    Returns:
        ConfigurationForm: the completed form.
    """
    config_form = ConfigurationForm()

    config_form.add_field(
        form_field.TextField(
            name="account_id",
            label="Account ID",
            description="NetSuite account id, e.g. 'TSTDRV2028961'.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="TSTDRV2028961",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="consumer_key",
            label="Consumer Key",
            description="Integration record's consumer key (Token-Based Authentication).",
            required=True,
            field_type=form_field.TextField.plain_text,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="consumer_secret",
            label="Consumer Secret",
            description="Integration record's consumer secret (Token-Based Authentication).",
            required=True,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="token_key",
            label="Token ID",
            description="Access token's token ID (Token-Based Authentication).",
            required=True,
            field_type=form_field.TextField.plain_text,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="token_secret",
            label="Token Secret",
            description="Access token's token secret (Token-Based Authentication).",
            required=True,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="date_from",
            label="Date From",
            description="Lower bound (inclusive) for transaction data, 'YYYY-MM-DD'.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="2020-01-01",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="date_to",
            label="Date To (optional)",
            description="Upper bound (inclusive), 'YYYY-MM-DD' or 'TODAY'. Leave blank for an open-ended range.",
            required=False,
            field_type=form_field.TextField.plain_text,
            placeholder="TODAY",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="subsidiaries",
            label="Subsidiaries",
            description="Comma-separated subsidiary internal IDs to sync, e.g. '1,2,3'.",
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="1,2,3",
        )
    )

    config_form.add_test(label="Test connection", func=connection_test)

    return config_form


def connection_test(configuration: dict):
    """
    Validate NetSuite TBA credentials work before any sync is attempted - Fivetran calls this
    when the user clicks "Test Connection" during setup (see configuration_form/add_test), and
    it's runnable locally via `fivetran configuration --test`. Runs the cheapest possible real
    SuiteQL query (a single-row 'subsidiary' fetch) rather than just checking field presence, so
    a bad key/secret/token or a missing REST Web Services/SuiteAnalytics Workbook permission is
    caught here rather than on the first real sync.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test: success() if the query succeeds and returns a row, failure(message) otherwise.
    """
    test = Test()
    try:
        validate_configuration(configuration)
    except ValueError as validation_error:
        return test.failure(str(validation_error))

    try:
        host = build_account_host(configuration["account_id"])
        base_url = f"https://{host}{__SUITEQL_PATH}"
        auth = get_oauth1_auth(configuration)
        with rq.Session() as session:
            page = execute_suiteql(session, base_url, auth, "SELECT id FROM subsidiary", [], limit=1, offset=0)
    except Exception as test_error:
        return test.failure(f"Could not query NetSuite: {test_error}")

    if not page.get("items"):
        return test.failure(
            "Connected to NetSuite, but the test query returned no rows - check that this "
            "role has access to at least one subsidiary."
        )
    return test.success()


def schema(configuration: dict):
    """Declare table names/primary keys from __TABLES; column types are left for the SDK to infer."""
    return [{"table": table_config["table"], "primary_key": table_config["primary_key"]} for table_config in __TABLES]


def update(configuration: dict, state: dict):
    """
    Sync every table in __TABLES: date-filtered tables via sync_windowed_table, dimension tables
    via sync_simple_table - see README for full architecture. Full re-extraction every run (no
    incremental cursor); `state` is used only to resume an interrupted sync.
    """
    validate_configuration(configuration)

    account_id = configuration["account_id"]
    host = build_account_host(account_id)
    base_url = f"https://{host}{__SUITEQL_PATH}"
    auth = get_oauth1_auth(configuration)

    date_from = configuration["date_from"]
    date_to = resolve_date_to(configuration)
    subsidiary_ids = parse_subsidiaries(configuration)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # split point only, see split_window

    date_range_description = f"{date_from} to {date_to}" if date_to is not None else f"{date_from} onward (no upper bound)"
    log.info(
        f"Starting NetSuite SuiteQL sync for account '{account_id}' across {len(__TABLES)} "
        f"table(s) - date range {date_range_description}, subsidiaries {subsidiary_ids}"
    )

    sync_started_at = time.time()
    rows_by_table = {}
    session = rq.Session()  # shared connection for every SuiteQL request this sync makes
    try:
        for table_config in __TABLES:
            table_name = table_config.get("table", "<unknown>")
            try:
                if table_has_date_filter(table_config):
                    rows_by_table[table_name] = sync_windowed_table(
                        session, base_url, auth, table_config, state, date_from, date_to, subsidiary_ids, today
                    )
                else:
                    rows_by_table[table_name] = sync_simple_table(session, base_url, auth, table_config, state)
            except Exception as sync_error:
                log.error(f"Failed to sync table '{table_name}': {sync_error}")
                raise RuntimeError(f"Failed to sync table '{table_name}': {sync_error}") from sync_error
    finally:
        session.close()

    log.info(
        f"NetSuite SuiteQL sync complete in {time.time() - sync_started_at:.1f}s - "
        f"{sum(rows_by_table.values())} total row(s) across {len(rows_by_table)} table(s)"
    )


connector = Connector(update=update, schema=schema, configuration_form=configuration_form)

# Local debug entry point - not called by Fivetran in production. Prefer `fivetran debug` over
# running this file directly; this is only for IDE breakpoint/step-through debugging.
if __name__ == "__main__":
    with open("configuration.json", "r") as config_file:
        configuration = json.load(config_file)  # never log this - contains live TBA credentials

    connector.debug(configuration=configuration)
