# NetSuite Connector (SuiteQL, No SuiteAnalytics Required)

This Fivetran Connector SDK connector extracts data from NetSuite using **SuiteQL** via
**SuiteTalk REST Web Services**. It does **not** require a SuiteAnalytics Connect license.

## How it works

- Every table is extracted by executing a SuiteQL `SELECT` statement against:

  ```
  POST https://{account}.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql
  ```

  The account-specific host is derived automatically from `account_id` (lowercased, with any
  underscores converted to hyphens) - e.g. account id `TSTDRV2028961` becomes host
  `tstdrv2028961.suitetalk.api.netsuite.com`. Each request sends `{"q": "<SELECT ...>"}` (plus
  a `"params"` array for bind values) and includes the `Prefer: transient` header, which tells
  NetSuite not to persist the ad-hoc query as a saved search.
- **Authentication** is NetSuite Token-Based Authentication (TBA) - OAuth 1.0a signed with
  HMAC-SHA256. This connector uses the `requests_oauthlib` library (`OAuth1`, HMAC-SHA256,
  auth-header signing) rather than hand-rolled signing code. The OAuth `realm` is the NetSuite
  account id in uppercase, per NetSuite's TBA spec.
- **Table list, columns, and join logic are all hardcoded** in `connector.py`'s `__TABLES` -
  none of that is configurable. The only two things a user can configure are a **date range**
  and a **list of subsidiaries** (see Configuration below), both of which apply to the
  transaction-related tables. Each date-filtered table has a curated column list scoped to
  General Ledger/Trial Balance use cases (see What's synced below) rather than every column.
- **Pagination** uses SuiteQL's `limit`/`offset` query parameters, at the maximum page size of
  1000 rows/page. NetSuite hard-caps how far a single *distinct query* can page - 100,000 rows
  (100 pages x 1000 rows) - without SuiteAnalytics Connect. Since this connector is reused
  across many customer accounts of very different sizes, it can't assume any table's filtered
  result set stays under that cap for every account. See **Handling large accounts** below for
  how this is actually handled (adaptive date-window splitting, not just a warning).
- **No incremental replication and no delete detection.** This connector always performs a
  full re-extraction of every table on every sync. State is checkpointed after every page that
  isn't the last one for its window/table, purely so an *interrupted* sync can resume mid-table
  without re-fetching pages it already wrote - it does **not** implement a `lastmodifieddate`
  cursor. If a previous sync of a table completed successfully, the next sync starts that table
  over from offset 0 for a fresh full extraction, as intended. A completed table's state is
  pruned to a minimal marker once done, rather than retaining its (by-then-irrelevant) window
  history for the rest of the sync.
- **One shared HTTP connection for the whole sync.** Every SuiteQL request - every page fetch,
  every pre-flight `COUNT`, every MIN/MAX id-range lookup - reuses a single `requests.Session`,
  so the underlying TCP/TLS connection to NetSuite's host stays alive instead of being
  renegotiated on every call. This changes nothing about how many requests are sent, only how
  cheap each one is.
- **Schema**: only table names and primary keys are declared in `schema()`. Column data types
  are left undeclared so the Connector SDK can infer them from the SuiteQL row data returned
  during `update()`.

## Logging

A non-obvious fact about the Connector SDK's `Logging` class, verified by reading the installed
package's source directly rather than assumed: `log.debug()` (and the deprecated `log.fine()`)
are gated behind `constants.DEBUGGING` and are **silent in production** - visible only during
local `fivetran debug`. `log.info()`, `log.warning()`, and `log.error()` are **not** gated that
way - they print in production too. That distinction drives everything below.

- **Per-page progress is DEBUG, not INFO.** Every page fetch used to log an INFO line ("synced N
  row(s) so far") - for a 300,000-row table at 1,000 rows/page, that's 300 production log lines
  from one table. These are now `log.debug()`: full per-page detail is still there when you
  actually run `fivetran debug` to troubleshoot locally, but production logs stay quiet. Verified
  directly: a forced-low-threshold run producing 112 separate windows generated zero per-page
  INFO lines and 334 DEBUG-only lines that would previously have been INFO.
- **One INFO line per window, not per page**, gives volume visibility that scales with sync
  *complexity* (number of windows - inherently small, since splitting is logarithmic) rather
  than sync *size* (number of rows, which could be in the millions): `"window X - N row(s),
  fetching"` when a window is confirmed safe, and `"window X complete - N row(s)"` when it
  finishes. This directly surfaces the row counts the splitting strategy discovers via `COUNT`,
  without per-page noise.
- **Every table logs elapsed time on completion** ("Completed sync for table X in Ys. Total rows
  upserted: N") - a genuine health signal, since a table taking unusually long is worth noticing
  even when nothing has technically failed. Verified: a forced-split run made this concretely
  useful, showing `transactionaccountingline` (135.2s) taking noticeably longer than
  `transactionline` (96.9s) for a comparable row count, which line-per-page logging couldn't
  have surfaced as clearly.
- **A grand-total summary closes out the sync**: `update()` now captures each table's returned
  row count (previously discarded) and logs one final line - total rows and total elapsed time
  across the whole sync - instead of the previous bare `"NetSuite SuiteQL sync complete"` with no
  numbers at all.
- **`sync_windowed_table` now logs a "Starting sync" line**, matching `sync_simple_table` (which
  already had one) - previously there was no way to tell when a windowed table's sync began, or
  whether it was resuming mid-window from an interrupted prior attempt.
- The two deprecated `log.fine()` calls were replaced with `log.debug()`, per the SDK's own
  deprecation notice.
- Split-decision logs (date/subsidiary/transaction-ID splits) and retry/error logs were left
  unchanged at INFO/WARNING/ERROR - they're inherently rare (splitting is self-limiting;
  retries/errors are exceptional), so they were never the noise source.

**Net effect**, measured directly: a table needing 26 pages previously produced 26 INFO lines;
now it produces 2 (one when its window is confirmed safe, one on completion), with the 25
per-page details demoted to `fivetran debug`-only. For a much larger account needing many more
pages per window, the reduction scales accordingly, while the number of per-window summary lines
stays governed by how many windows splitting actually needed - not by row count.

## Authentication setup (NetSuite Token-Based Authentication)

1. In NetSuite, enable **Token-based Authentication** and **REST Web Services** under
   *Setup > Company > Enable Features > SuiteCloud*.
2. Create (or reuse) an **Integration** record (*Setup > Integration > Manage Integrations >
   New*) with **Token-Based Authentication** enabled. Note the generated **Consumer
   Key**/**Consumer Secret**.
3. Create a **dedicated custom role** for this integration - **do not use the Administrator
   role**. NetSuite rejects Administrator-role TBA logins in some accounts with a generic 401
   (`EntityOrRoleDisabled` in the Login Audit Trail detail), and it's not recommended practice
   regardless. The role needs, at minimum:
   - Setup -> **Log in using Access Tokens** (Full)
   - Setup -> **REST Web Services** (Full)
   - Setup -> **Manage Accounting Periods** (View) - required for the `accountingperiod` table
   - **Reports** subtab -> **SuiteAnalytics Workbook** (Edit) - despite the name, this is
     **required for any SuiteQL query to execute at all** (confirmed: even a bare
     `SELECT 1 FROM dual` fails with `INVALID_PARAMETER` / "does not have permission" without
     it), and is unrelated to the paid SuiteAnalytics Connect add-on. It's a normal, standard
     permission, but only shows up on a role once the account-wide **SuiteAnalytics Workbook**
     feature (*Setup > Company > Enable Features*) is enabled - if you don't see it as an
     assignable permission, check that feature is on first.
   - Lists -> View on **Accounts** and **Subsidiaries**
   - **Transactions subtab -> View on each specific transaction type present in your data**
     (e.g. Sales Order, Invoice, Journal Entry). This is the actual data-visibility gate for
     the `transaction`/`transactionline`/`transactionaccountingline` tables - the generic
     **Find Transaction** permission only controls the UI global-search feature and does
     **not** grant SuiteQL row visibility; a role with only `Find Transaction` will see zero
     transaction rows via SuiteQL even when the underlying data exists. A role with **zero**
     Transactions permissions makes NetSuite report the table as not existing at all
     (`Record 'transaction' was not found`), rather than returning zero rows.
4. Assign the role to a (non-interactive) integration user (*Setup > Users/Roles > Manage
   Users > [user] > Access tab* - check **Give Access** and add the role).
5. Create an **Access Token** for that Integration + user + role combination
   (*Setup > Users/Roles > Access Tokens > New*). Note the generated **Token ID**/**Token
   Secret**. If you change the role's permissions significantly after the token already
   exists, regenerating the token is a reasonable first troubleshooting step if something that
   should work still doesn't - but in practice permission changes took effect immediately on
   the existing token during development of this connector, without needing regeneration.

For full setup steps, see NetSuite's own documentation on Token-Based Authentication and
SuiteTalk REST Web Services (search NetSuite Help Center for "Token-based Authentication" and
"SuiteQL").

## Configuration (`configuration.json`)

| Field | Required | Description |
|---|---|---|
| `account_id` | yes | NetSuite account id, e.g. `TSTDRV2028961`. Used both to derive the SuiteQL host and as the OAuth `realm`. |
| `consumer_key` / `consumer_secret` | yes | Integration record's Consumer Key/Secret. |
| `token_key` / `token_secret` | yes | Access Token's Token ID/Secret. |
| `date_from` | yes | Lower bound (`YYYY-MM-DD`) of the date range applied to every transaction-related table (`transactionline`, `transaction`, `transactionaccountingline`), filtered on `transaction.trandate`. |
| `date_to` | no | Upper bound (`YYYY-MM-DD`) of the date range. If omitted (or blank), no upper bound is applied at all - the filter is an open-ended `>= date_from`. Also accepts the literal string `"TODAY"` for an explicit, self-updating upper bound that resolves to the current UTC date at sync time. |
| `subsidiaries` | yes | Comma-separated list of subsidiary internal IDs to include, e.g. `"1"` or `"1,2,3"`. Applied to the same three transaction-related tables. |

That's the entire configuration surface. There is no `tables`/`columns`/`joins` configuration
field - the table list, column selection, and all join logic are hardcoded in `connector.py`'s
`__TABLES` constant. This is a deliberate simplification: the only things expected to vary per
deployment are the date window and which subsidiaries to include, so those are the only two
knobs exposed.

### Setup form

`connector.py` defines a `configuration_form()` (registered via `Connector(..., configuration_form=configuration_form)`), so the Fivetran setup form shows each field above as a labeled input with a description, rather than the SDK's bare default (every `configuration.json` key as an unlabeled plain-text box). `consumer_secret` and `token_secret` are declared as `form_field.TextField.password` (masked input) - every other field is plain text, including `consumer_key`/`token_key`, which are the public-identifier half of NetSuite's TBA credential pairs, not secrets themselves.

A **setup test** is registered (`config_form.add_test(label="Test connection", func=connection_test)`) - Fivetran runs it when the user clicks **Test Connection** in the setup form, and it's runnable locally via `fivetran configuration --test`. Rather than just checking that fields are non-empty, it executes the cheapest real SuiteQL query possible (`SELECT id FROM subsidiary`, one row) - so a bad key/secret/token, or a role missing REST Web Services/SuiteAnalytics Workbook/subsidiary access, is caught at setup time instead of on the first real sync. Verified directly (bypassing the interactive CLI prompt) against the live account: succeeds with valid credentials, fails fast with the actual NetSuite `401 INVALID_LOGIN` error text on a bad `token_secret` (no wasted retries, since `execute_suiteql` treats 401 as non-retryable), and fails with a clear message on a missing required field.

## What's synced

Six tables, all hardcoded in `__TABLES`:

| Table | Filtered by date+subsidiary? | Columns synced | Notes |
|---|---|---|---|
| `subsidiary` | No - full table every sync | All (no `columns` list - unfiltered dimension tables aren't narrowed) | Dimension table |
| `account` | No - full table every sync | `id`, `acctnumber`, `accountsearchdisplayname`, `accttype`, `subsidiary`, `isinactive` | Dimension table (chart of accounts) |
| `accountingperiod` | No - full table every sync | All (no `columns` list) | Dimension table |
| `transactionline` | Yes, directly | `transaction`, `linesequencenumber`, `subsidiary`, `department`, `class`, `location`, `memo` | Has its own `subsidiary` column; joined to `transaction` to filter on `trandate` (see below) |
| `transaction` | Yes, indirectly via `transactionline` | `id`, `tranid`, `trandate`, `type`, `entity`, `memo`, `status` | Has neither `subsidiary` nor a usable date column of its own for this filter path - see the join-filter explanation below |
| `transactionaccountingline` | Yes, indirectly via `transactionline` | `transaction`, `transactionline`, `account`, `accountingbook`, `debit`, `credit`, `amount`, `netamount`, `posting` | GL posting detail per transaction line - the actual Trial Balance/GL fact table; has neither `subsidiary` nor `trandate` |

Every date-filtered table's column list is curated to what's needed for General Ledger/Trial
Balance reconstruction (measured ~48% sync-time reduction vs. selecting every column) - not the
full ~20-176 columns each of these tables actually has in NetSuite. The two unfiltered dimension
tables (`subsidiary`, `accountingperiod`) are small enough that narrowing wasn't worth doing.

### Why `transaction` and `transactionaccountingline` need indirect (join-filter) filtering

Two confirmed NetSuite schema quirks drive this:

- `transaction` has no `subsidiary` column directly.
- `transactionline.postingperiod` (which might look like the natural date field) **cannot be
  selected or filtered via SuiteQL REST at all** in the account this was built against - any
  query touching it returns a generic `500 UNEXPECTED_ERROR`. It's an internal reference to
  the `accountingperiod` record, not a literal date. `transaction.trandate` is used instead.

So filtering `transaction` by date+subsidiary requires: joining `transactionline` to
`transaction` (to reach `trandate`), filtering that by `trandate` + `subsidiary`, taking the
distinct transaction IDs from that result, then filtering the outer `transaction` query by that
ID list - all in one server-side round trip via a subquery, not two separate queries:

```sql
SELECT t.* FROM transaction t
WHERE t.id IN (
    SELECT DISTINCT tl.transaction FROM transactionline tl
    JOIN transaction t2 ON t2.id = tl.transaction
    WHERE t2.trandate BETWEEN TO_DATE(?, 'YYYY-MM-DD') AND TO_DATE(?, 'YYYY-MM-DD')
      AND tl.subsidiary IN (?)
)
ORDER BY t.id
```

Verified against a live account: the resulting `transaction` rows are exactly the distinct
transaction IDs produced by the filtered `transactionline` subquery - not just "the query ran
without erroring."

`transactionaccountingline` has the same problem one level further removed - it has neither
`subsidiary` nor `trandate`, and its own `transactionline` column is a plain line-sequence
number, not a foreign key - so it needs a **two-column join** back to `transactionline` (on
`transaction` + line sequence number) to reach `subsidiary`, plus a join to `transaction` for
the date:

```sql
SELECT tal.* FROM transactionaccountingline tal
JOIN transaction t ON t.id = tal.transaction
JOIN transactionline tl2 ON tl2.transaction = tal.transaction
                         AND tl2.linesequencenumber = tal.transactionline
WHERE t.trandate BETWEEN TO_DATE(?, 'YYYY-MM-DD') AND TO_DATE(?, 'YYYY-MM-DD')
  AND tl2.subsidiary IN (?)
ORDER BY tal.transaction, tal.transactionline, tal.accountingbook
```

### Why every `SELECT` is alias-qualified, never a bare `*`

Confirmed empirically: a bare `SELECT *` on a query that includes a `JOIN` merges **both**
tables' columns into one flat result (e.g. `transactionline` joined to `transaction` would
return `transaction`'s columns too, with no indication of which table each field came from,
and risk of silently-colliding column names). Every column reference in this connector is
therefore qualified with the primary table's alias - either `{alias}.*` (the two tables with no
narrowed `columns` list) or `{alias}.col1, {alias}.col2, ...` (the four tables with a curated
column list, see **What's synced** above) - so joined tables' columns never leak into the
result, since every join in this connector exists purely to reach a filter column (`trandate`,
`subsidiary`), not to widen the result set.

## Handling large accounts: adaptive multi-dimensional splitting

This connector is built to be reused across many different customer accounts, not just this
one demo account - and there will definitely be accounts where a table's filtered result set
exceeds NetSuite's 100,000-row SuiteQL cap. Rather than warn and silently stop at 100,000 rows
(what an earlier version of this connector did), every date-filtered table now guarantees full
coverage via **adaptive splitting across three independent filter dimensions, tried in order**:
date, then subsidiary, then transaction-ID range.

1. Before fetching a window (initially, the whole configured `date_from`/`date_to` range across
   all configured subsidiaries), run a cheap `SELECT COUNT(*)` using the *exact same* filters
   and joins as the real data query (`build_count_query` shares its FROM/JOIN/WHERE logic with
   `build_query` via `build_from_joins_where`, so the two can never disagree with each other).
2. If the count is at or under a safe threshold (`__SAFE_ROW_THRESHOLD = 90,000` - comfortably
   below the true 100,000 cap), the window is fetched directly, paginated as normal.
3. **Stage 1 - date.** If the count exceeds the threshold, the window is split into two halves
   by calendar date (`split_window`, bisecting at the midpoint) and each half is counted and
   processed the same way - recursively, so a window keeps splitting until every resulting
   sub-window is safe.
4. **Stage 2 - subsidiary.** If a window is split all the way down to a **single day** and still
   exceeds the threshold, date-splitting is exhausted (a day can't be split further). If more
   than one subsidiary is configured, the window is instead split into one window per
   subsidiary - each single-subsidiary window is then re-counted and, if still too large, can
   fall through to stage 3.
5. **Stage 3 - transaction-ID range.** If a window is down to a single day *and* a single
   subsidiary and still exceeds the threshold, both the date and subsidiary dimensions are
   exhausted. As a last resort, the connector fetches the MIN/MAX transaction ID for that exact
   window (`get_id_range`) and bisects that numeric range (`split_id_range`), the same way
   `split_window` bisects dates. Each half is re-counted and, if still too large, is bisected
   again recursively - this repeats until every sub-range is safe. The ID column used is each
   table's own FK to `transaction.id` (`t.id` on `transaction`, `tl.transaction` on
   `transactionline`, `tal.transaction` on `transactionaccountingline`), not
   `transactionline.id` - that field is **not** a genuine per-row identifier in this account
   (empirically verified: only 131 distinct values across 25,607 rows, max value 158), whereas
   `transaction.id` and its FK columns are well-distributed sequential integers safe to bisect.
6. Only if a window is simultaneously a single day, a single subsidiary, *and* an unsplittable
   single transaction ID, and still exceeds the threshold, does this connector **raise an error
   rather than silently truncate** - at that point all three independent filter dimensions are
   exhausted and full coverage can no longer be guaranteed for that window.

State tracks a list of windows per table (each with its own `start`/`end`/`subsidiary_ids`/
optional `id_range`/offset/completed) rather than a single offset, so an interrupted sync
resumes mid-window without redoing already-completed windows or re-deciding whether an
already-safe window needs splitting.

**Verified against this live account**, at every stage, by temporarily lowering the threshold
far below its real value to force real splitting on real data:

- At threshold 5,000, all three transaction-related tables split into a total of 22 windows
  (stage 1 only, down to single days in the densest period), and the reassembled row counts
  were **exactly identical** to the unsplit, single-query baseline (25,607 / 4,436 / 23,714) -
  confirming no gaps or double-counting at window boundaries.
- At threshold 1,000, `transactionline`'s real 2018-11-30 spike (4,151 rows, single day, single
  subsidiary - evidently a bulk-loaded batch of demo data) correctly fell through stages 1 and 2
  and triggered **stage 3**, splitting by transaction ID (e.g. `348-3213` / `3214-6078`), with
  the still-oversized half correctly re-splitting recursively (`3214-6078` → `3214-4646` /
  `4647-6078`, and so on) until every sub-range was safe - 18 transaction-ID splits fired in
  total across the run. The sync completed with zero errors/warnings and, once again, row counts
  **exactly identical** to the unsplit baseline.
- A full run at the restored production threshold (90,000, where none of this splitting logic
  actually engages against this account's data volume) was re-verified clean immediately after
  restoring the threshold, confirming no regression: `SYNC SUCCEEDED`, zero errors/warnings,
  identical row counts.

The dimension tables (`subsidiary`, `account`, `accountingperiod`) aren't date-filtered at all,
so this doesn't apply to them - they're synced via the simpler unwindowed path
(`sync_simple_table`), on the basis that a chart of accounts, subsidiary list, or accounting
period list realistically never approaches 100,000 rows for any real NetSuite account.

### Other schema quirks worth knowing

- `transactionline.line` is **not** a valid field name - the real line-sequence field is
  `linesequencenumber`.
- `ORDER BY` must be qualified with the primary table's alias (e.g. `tal.transaction`, not bare
  `transaction`) once a query joins in another table that happens to share a column name -
  `transactionaccountingline` and `transactionline` both have a `transaction` column, which
  produces an "Ambiguous column" error if `ORDER BY` isn't qualified.

## Simplification and performance review

Once the splitting cascade above was complete and verified, this connector went through a
structured review pass aimed specifically at removing unnecessary complexity and reducing sync
duration without increasing load on NetSuite or risking memory/timeout stability. Four
independent reviewers each analyzed the code from a different angle (query/network efficiency,
code structure, memory/timeout stability, and sync-duration strategy), and a fifth "master"
reviewer critiqued every submitted suggestion - checking each one against the actual code rather
than taking it on faith - before deciding what to implement. Adopted:

- **One shared `requests.Session()` for the whole sync**, instead of opening a fresh connection
  (`requests.post`) for every single SuiteQL call. Same number of requests sent to NetSuite, just
  cheaper transport - the underlying TCP/TLS connection is reused instead of renegotiated on
  every page fetch, COUNT, and MIN/MAX call.
- **A longer, distinct timeout for COUNT/MIN-MAX ("aggregate") queries** (150s vs. 60s for page
  fetches) - these always return exactly one row regardless of how large the underlying window
  is, so a slow response is virtually always still working, not hung.
- **The same overflow safety net `sync_windowed_table` already had, added to `sync_simple_table`
  too** - the three dimension tables (`subsidiary`, `account`, `accountingperiod`) previously had
  no cap-detection at all, relying purely on the assumption that they'd never approach 100,000
  rows. They now raise rather than silently truncate if that assumption is ever wrong.
- **Leaner checkpoint state**: a completed window is now removed from the active windows list
  instead of being flagged and skipped over, and a completed table's state collapses to a
  minimal `{"completed": true}` marker instead of retaining its full (by-then-irrelevant) window
  history - both existed only to make interrupted-sync resume possible, and neither needs to be
  carried once no longer relevant. The redundant back-to-back checkpoint on a window/table's
  final page was also removed (checkpoint once, right after recording completion, not once
  mid-loop and again immediately after).
- **Accurate cumulative row counts across a resumed sync**: a table's "Total rows upserted"
  completion log now reads from a running total persisted in state, rather than a
  per-invocation-local counter that understated the true total if an earlier attempt at the same
  table had been interrupted and resumed.
- **`__SAFE_ROW_THRESHOLD` derived from `__MAX_ROWS_PER_TABLE`** (`100,000 - 10,000`) instead of
  two independently-maintained literals whose relationship existed only in comment prose.
- **A `table_alias()` helper** replacing the same `table_config.get("alias", table_config["table"])`
  lookup that had been copy-pasted across `build_query`, `build_count_query`, and
  `build_id_range_query`.
- **The three splitting stages' shared "apply this split, checkpoint, continue" tail** extracted
  into one small closure (`replace_window_with`) inside `sync_windowed_table`, called by all
  three stages - narrowly scoped to that repeated tail only, deliberately leaving each stage's
  own gating conditions and split computations untouched, since those are exactly the
  already-verified, safety-critical logic this review was told not to casually alter.
- **One authoritative explanation of the splitting algorithm** - previously restated (and prone
  to drifting out of sync) across the module docstring, the `__TABLES` comment, and
  `sync_windowed_table`'s own docstring. A later pass (see "Comment cleanup" below) made this
  README the single authoritative source and condensed every one of those in-code explanations
  to a one-line summary plus a pointer here, instead of the other way around.

Explicitly **rejected or deferred** by the master reviewer, and why: adding concurrency (parallel
tables/windows/pages) was rejected outright - it would increase load on NetSuite's
shared-governance endpoint, directly against this connector's stated priority, for an
unpredictable net benefit. A handful of higher-effort, higher-risk ideas were deferred as
dedicated follow-up projects rather than bundled into this pass - each would need the same
rigorous live-account, multi-threshold verification this splitting cascade has already been put
through before it could be trusted: replacing recursive date bisection with an up-front per-day
COUNT histogram, keyset/seek pagination instead of `LIMIT`/`OFFSET`, caching a proven-safe window
plan across syncs, and true incremental replication via `lastmodifieddate` (the single biggest
possible wall-clock win, but a major, opt-in project of its own). Two further suggestions -
having `transaction` skip its own COUNT/split cascade by reusing `transactionline`'s
already-proven windows, and seeding `transactionaccountingline`'s split search with
`transactionline`'s window boundaries - were accepted by the master reviewer but not implemented
here: doing so safely turned out to require persisting a table's complete finished-window history
across a possible mid-sync crash/resume, which risks silently handing a downstream table an
*incomplete* seed list (and therefore a silent data gap) if not built carefully - the same class
of risk the master reviewer already flagged for window-plan caching across syncs. Deferred for
the same dedicated-verification treatment rather than implemented under time pressure.

**Verified after implementing the above**: a clean run at the restored production threshold
(90,000) reproduced the exact same row counts as every prior baseline, and a forced run at
threshold 1,000 (the same methodology used to originally verify the splitting cascade) re-fired
all three splitting stages correctly (87 date splits, 2 subsidiary splits, 18 transaction-ID
splits) with, again, zero errors/warnings and exact row-count reassembly - confirming the
`replace_window_with` refactor didn't change the cascade's behavior, only its structure.

### Concurrency experiment: measured, then reverted

After the review above rejected adding concurrency by default, a bounded (max 4 concurrent
requests) version was still built and measured directly, to replace the reviewers' prediction
with an actual result rather than leave it untested. Scope was kept narrow and safe by
construction: only the network fetch of pages *within an already-confirmed-safe window* was
parallelized (via a bounded `ThreadPoolExecutor`), sized to an estimate of how many pages
remained so a wave near a window's end wouldn't speculatively over-fetch; `has_more` on the
actual response stayed the authoritative stop condition throughout, never the count-based
estimate. The splitting-decision cascade and every `op.upsert`/`op.checkpoint` call were left
strictly single-threaded regardless - only raw HTTP fetches ran concurrently.

**Measured result: no benefit.** Two runs at each setting, same account, same production
configuration:

| Setting | Run 1 | Run 2 |
|---|---|---|
| Sequential (1 at a time) | 1:11 | 1:08 |
| Concurrent (4 at a time) | 1:13 | 1:10 |

Wall-clock was statistically indistinguishable. More tellingly, individual wave timings in the
concurrent runs showed each 4-page wave taking ~4.5-4.9s (~1.1-1.2s per page-equivalent) - the
same per-page latency as the sequential run, not divided by ~4 as genuine parallel execution
would produce. This points to NetSuite serializing requests from this account/token
server-side regardless of client-side concurrency, consistent with NetSuite's documented
per-integration/role concurrency governance (trial/sandbox accounts commonly default to a low
limit). Sending 4 requests at once here just means 3 of them queue on NetSuite's side and get
worked through one at a time anyway - the exact risk the master reviewer's rejection of default
concurrency was based on, now confirmed empirically rather than just predicted.

Given zero measured benefit against the real added complexity (thread pool machinery,
wave-sizing logic, an extra resume-path `COUNT` call), the concurrency code was fully reverted
rather than kept disabled-by-default - carrying inert complexity for a change that measurably
doesn't help isn't worth it. A different NetSuite account with a higher concurrency governance
limit configured *might* see a different result, but that would need to be measured against that
specific account before reintroducing this, not assumed from this one's data.

### Comment and docstring cleanup

Once the functional work above was complete and verified, `connector.py`'s comments and
docstrings - which had accumulated multi-paragraph rationale for every design decision as the
connector was built up incrementally - were cut down to short, one- or two-line summaries that
say *what's happening where*, with the detailed *why* relocated here rather than duplicated (and
left to drift out of sync) in two places. This cut the file from 1,206 to 777 lines (~36%) with
zero behavior change - verified with a full regression run (`SYNC SUCCEEDED`, zero
errors/warnings, exact baseline row counts) immediately after.

One consequence worth being explicit about: this README is now the single authoritative source
for design rationale, not the code. A docstring like `sync_windowed_table`'s says only "see
README" for the full splitting algorithm rather than restating it - so if this file and the code
ever diverge, trust the code for *what it does* and treat this file's explanations as needing a
refresh, not the other way around.

## Testing

```bash
fivetran debug --configuration configuration.json
```

This produces a local `warehouse.db` (DuckDB) file you can query to validate row counts and
schema for each table.

**Verified against a live NetSuite trial account** - clean `SYNC SUCCEEDED`, zero errors or
warnings, with all subsidiaries and an open-ended (`date_to` omitted) date range:

| Table | Rows |
|---|---|
| `subsidiary` | 3 |
| `account` | 173 |
| `accountingperiod` | 289 |
| `transactionline` | 25,607 |
| `transaction` | 4,436 |
| `transactionaccountingline` | 23,714 |

Five of these six totals have been independently reproduced, unchanged, across every run made
against this account throughout this connector's development - the original unsplit
single-query version, a run with a deliberately narrowed role, forced splitting at multiple
thresholds exercising all three splitting dimensions (see **Handling large accounts** above and
**Simplification and performance review** below), and every regression run since - all agreeing
to the row, which is strong evidence against both silent data loss and duplication.
`accountingperiod` is the one exception: it's an unfiltered dimension table (see **What's
synced** above), and its count has drifted upward over the course of development (255 → 289) as
NetSuite's own sandbox data changed between sessions - unrelated to any code in this connector.

## Known limitations

- **No incremental replication.** Every sync re-extracts the full result set for every table.
  There is no `lastmodifieddate`-based cursor.
- **No delete detection.** Rows removed from NetSuite since the last sync are not marked
  deleted in the destination.
- **A single table row-count that exceeds ~90,000 for one table, on a single day, for a single
  subsidiary, for a single transaction ID cannot be split further.** See **Handling large
  accounts** above - all three splitting dimensions (date, subsidiary, transaction-ID range) are
  exhausted at that point, and this raises an error rather than silently truncating. This is an
  extreme edge case (it would require >90,000 GL posting lines for one transaction on one day),
  not observed in any account tested so far.
- **Sequential, single-threaded.** Tables, windows, and pages are all synced one at a time to
  minimize load on a shared-governance NetSuite account. There is no concurrency/parallelism -
  for a very large account that needs many date-window splits, this means more (small, fast)
  requests in sequence rather than fewer large ones, which is deliberate but does add wall-clock
  time proportional to how many windows are needed. This isn't an unexamined gap: a bounded
  (max 4) concurrent implementation was built and measured against this account and found to
  provide no benefit (see **Concurrency experiment: measured, then reverted** below) - a
  different account with a higher NetSuite concurrency governance limit might see a different
  result, but that would need to be measured, not assumed.
- **Rate-limit handling.** HTTP 429 and 5xx responses are retried with exponential backoff (up
  to 5 attempts, honoring `Retry-After` when present); other 4xx errors fail immediately.
