# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

A public collection of Python example connectors for the Fivetran Connector SDK. There is **no top-level application to build or run** — each subdirectory under `connectors/`, `examples/`, `template_connector/`, and `fivetran_platform_features/` is an independent, self-contained connector project.

## Repository layout

- `template_connector/` — canonical starting point (`connector.py`, `configuration.json`, `requirements.txt`, `README_template.md`). Used by `fivetran init` when no `--template` flag is given. Match its structure when scaffolding new examples.
- `connectors/` — community connectors for specific data sources (databases, APIs, message queues). Nearly 100 entries; each is a self-contained example.
- `examples/quickstart_examples/` — minimal getting-started examples (hello world, first REST API connector).
- `examples/common_patterns_for_connectors/` — reusable building blocks: authentication, pagination, cursors, incremental sync, error handling, schema changes, server-side cursors, etc. Reference these before reinventing patterns.
- `examples/private_preview_features/` and `examples/workflows/` — preview features and CI/CD examples.
- `fivetran_platform_features/` — examples for native platform features (e.g., schema evolution).
- `all_things_ai/` — AI-assisted development guides and agent configs.
- `.github/instructions/` — authoritative review rules for Python (`python-review.instructions.md`), JSON config (`configuration-review.instructions.md`), and READMEs (`readme-markdown.instructions.md`). When making edits, treat these as ground truth.
- `.github/copilot-instructions.md` — Copilot reviewer guide; concise summary of SDK rules.
- `PYTHON_CODING_STANDARDS.md`, `FIVETRAN_CODING_PRINCIPLES.md` — naming, structure, and review principles.

## Common commands

Operate from the **specific connector's directory**, not the repo root:

```bash
# Set up pre-commit hooks (run once from repo root)
.github/scripts/setup-hooks.sh

# Local debug run for a connector (must be in connector's directory)
fivetran debug
fivetran debug --configuration=configuration.json   # if connector has config

# Lint a connector
flake8 .

# Format the entire repo (Black, line length 99)
.github/scripts/fix-python-formatting.sh
# or manually:
black --line-length 99 .
```

There is no monorepo-wide test runner. Validation is per-connector via `fivetran debug`, which produces a local `warehouse.db` to inspect.

## Connector structure (mandatory)

Every `connector.py` must follow this shape — these are review **blockers**, not style preferences:

1. **Imports (verbatim form):**
   ```python
   import json
   from fivetran_connector_sdk import Connector
   from fivetran_connector_sdk import Logging as log
   from fivetran_connector_sdk import Operations as op
   ```
   Comment every third-party import with its purpose.

2. **`validate_configuration(configuration: dict)`** — always defined, called at the top of `update()`, raises `ValueError` for missing/invalid values.

3. **`schema(configuration: dict)`** — returns a list of table dicts. Always specify `primary_key`. Define column types only when precision matters (let Fivetran infer the rest to allow schema evolution). Allowed types: `BOOLEAN, SHORT, INT, LONG, DECIMAL, FLOAT, DOUBLE, NAIVE_DATE, NAIVE_DATETIME, UTC_DATETIME, BINARY, XML, STRING, JSON`.

4. **`update(configuration: dict, state: dict)`** — required entry point. **First log statement must be** `log.warning("Example: <CATEGORY> : <EXAMPLE_NAME>")`.

5. **Module-level instantiation:** `connector = Connector(update=update, schema=schema)`.

6. **`if __name__ == "__main__":`** block that loads `configuration.json` and calls `connector.debug()`.

The exact docstrings for `schema()` and `update()` are mandated verbatim — copy from `template_connector/connector.py`.

## SDK v2+: no `yield`

Since SDK v2.0.0 (August 2025), operations are **synchronous direct calls**, not generators:

- ✅ `op.upsert(table, data)` / `op.checkpoint(state)` / `op.update(...)` / `op.delete(...)`
- ❌ `yield op.upsert(...)` / `yield op.checkpoint(...)`

Old v1 connectors with `yield` still work (backward compatible), but **all new code must not use `yield`** with operations. Flag and fix any `yield op.*` in modified files.

## Required comment boilerplate

Reviewers expect these specific comments **before every** call (not once per file). Copy them verbatim from `.github/instructions/python-review.instructions.md`:

- Before each `op.upsert(...)` — 3-line comment explaining upsert semantics.
- Before each `op.checkpoint(...)` — 5-line comment explaining checkpointing and linking to best-practices docs.
- Before the `if __name__ == "__main__":` block — explanation that this is for local debugging only.

Skipping or shortening these is a review blocker.

## Memory and state rules (review blockers)

- **Never load unbounded data**: no `cursor.fetchall()`, no `list(api.get_all())`, no `response.content` on large responses, no accumulating lists across pages.
- **Stream/paginate everything**: `cursor.fetchmany(__BATCH_SIZE)` with named server-side cursors; `response.iter_content()` / `iter_lines()`; `pd.read_csv(..., chunksize=...)`.
- **Checkpoint after writes**: process page → upsert records → update state → `op.checkpoint(state)`. Never advance state before successful upsert. Checkpoint after each page in pagination loops; for large datasets define `__CHECKPOINT_INTERVAL` and checkpoint every N records.
- **Retry transient failures only** with exponential backoff (cap at ~60s, 3–5 attempts). Re-raise immediately on 4xx auth/client errors. Catch specific exceptions (`requests.HTTPError, requests.Timeout, ConnectionError`), never bare `except Exception: pass`.

## Logging

Only `from fivetran_connector_sdk import Logging as log`. **Never** use `print()` or stdlib `logging`. Levels: `log.info` (progress), `log.warning` (rate limits, retries), `log.severe` (failures), `log.fine` (deep debug). Never log secrets, full configs, or PII.

## Naming and constants

- Functions/variables: `snake_case`. Classes: `PascalCase`. Constants: `__UPPER_SNAKE_CASE` with **double leading underscore** (private by default), placed immediately after imports. No magic numbers — define constants like `__MAX_RETRIES = 5`, `__BATCH_SIZE = 1000`.
- Boolean variables/methods use `is_/has_/can_/should_` prefixes.
- Variables with units include the unit in the name: `max_wait_time_ms`, `sync_period_min`.
- Directories: `lowercase_with_underscores`.

## requirements.txt rules

- **Never declare** `fivetran_connector_sdk` or `requests` — both are pre-installed in the runtime.
- Pin explicit versions: `pandas==2.0.3`, not `pandas`.
- Keep alphabetical, comment non-obvious dependencies.
- File can be omitted entirely if no external deps.

## configuration.json rules

- All values must be angle-bracket placeholders describing what to fill in: `"api_key": "<YOUR_API_KEY>"`. Never empty strings, never real secrets, never type-only placeholders like `<STRING>`.
- Keys must match exactly what `connector.py` reads via `configuration.get(...)` and what the README documents. No unused keys.
- `snake_case` keys preferred; no abbreviations (`database_url`, not `db_url`).

## README requirements for new connectors

Use `template_connector/README_template.md` as the structural source of truth. Required H2 sections in this order: Connector overview, Requirements, Getting started, Features, [Configuration file], [Requirements file], [Authentication], [Pagination], Data handling, Error handling, Tables created, [Additional files], Additional considerations. Bracketed sections are conditional.

Heading rules: exactly one H1 in Title Case; all other headings in sentence case; no numbered headings (`## 4. Best practices` → `## Best practices`). No bold for emphasis, no Title Case in subheadings, no italicized template placeholders left unreplaced.

When adding a new connector example, **also update the root `README.md`** to list it in the appropriate section — the `README update check` CI job enforces this.

## Linting and formatting

- Flake8 config at repo root (`.flake8`): line length 99, ignores `E203, E501, B008`. Tests get `D102, D104, F401` ignored.
- Black with `--line-length 99`. Pre-commit hook (installed via `.github/scripts/setup-hooks.sh`) enforces formatting.
- CI runs `flake8` and `black --check` only on Python files modified by the PR.

## Commit message format

`type(scope): short description` where `type` is one of `feature, fix, test, cleanup, refactor, doc, flag, tweak, config, security`. Examples: `feature(examples): add smartsheets connector`, `fix(connector_sdk): handle session token expiry`.
