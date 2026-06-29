#!/usr/bin/env bash
# Canonical pre-submission gate for Fivetran Connector SDK contributions.
# Run from the connector directory. Exits non-zero if any check fails.
#
# Three "gate must reproduce CI exactly, not approximate it" lessons baked in
# (PRs #570 + #562 fallout):
#   1. flake8 runs on `connector.py + tests/` (whole connector dir, not just
#      connector.py) — CI runs flake8 on every changed `.py` file.
#   2. flake8 runs from REPO ROOT with full paths so the repo's
#      `.flake8 per-file-ignores = tests/*:F401` pattern matches the way CI
#      sees it. Running from the connector dir relativizes paths to
#      `tests/...`, which silently ignores F401 — but CI sees full paths.
#   3. black is upgraded to latest before running so the local check matches
#      CI's unpinned `pip install black` (CI gets whatever's current; local
#      may have an older pinned version that diverges on edge-case rules).
set -euo pipefail

cd "$(dirname "$0")/.."

LINE_LEN=99  # matches repo's .flake8 (max-line-length=99) + .github/git_hooks/pre-commit

echo "=== 0/7 pin black to latest (matches CI's unpinned pip install) ==="
python3 -m pip install --upgrade --break-system-packages -q black

echo "=== 1/7 flake8 (run from REPO ROOT with full paths so per-file-ignores match CI) ==="
REPO_ROOT="$(git rev-parse --show-toplevel)"
# python3 stand-in for `realpath --relative-to` (macOS realpath lacks it).
CONNECTOR_REL="$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$PWD" "$REPO_ROOT")"
(
    cd "$REPO_ROOT"
    if [ -d "$CONNECTOR_REL/tests" ]; then
        python3 -m flake8 "$CONNECTOR_REL/connector.py" "$CONNECTOR_REL/tests/"
    else
        python3 -m flake8 "$CONNECTOR_REL/connector.py"
    fi
)

echo "=== 2/7 black --check (formatting, line-length=$LINE_LEN) ==="
python3 -m black --check --line-length=$LINE_LEN connector.py
if [ -d tests ]; then
    python3 -m black --check --line-length=$LINE_LEN tests/
fi

echo "=== 3/7 dead module-level constants ==="
# Catch class of issue raised on PR #570 (__STATE_ADJACENCY defined but unused).
DEAD_CONSTS=""
while IFS= read -r const; do
    [ -z "$const" ] && continue
    occurrences=$(grep -cE "\b${const}\b" connector.py)
    if [ "$occurrences" -le 1 ]; then
        DEAD_CONSTS="$DEAD_CONSTS\n  - $const"
    fi
done < <(grep -oE '^__[A-Z][A-Z0-9_]+\s*=' connector.py | tr -d '= ')
if [ -n "$DEAD_CONSTS" ]; then
    echo -e "ERROR: dead module-level constants (defined but never referenced):$DEAD_CONSTS"
    exit 1
fi
echo "clean"

echo "=== 4/7 PII scan (non-role-based emails, embedded tokens) ==="
# Allowlist role-based addresses (developers@, noreply@, hello@, etc.) plus
# canonical API issuer addresses some connectors must include verbatim.
FLAGGED_EMAILS=$(grep -En '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' connector.py \
    | grep -vE '(developers|noreply|hello|support|api|admin|security)@' \
    | grep -vE 'cve@mitre\.org|nvd@nist\.gov' || true)
if [ -n "$FLAGGED_EMAILS" ]; then
    echo "ERROR: possible personal email found in connector.py:"
    echo "$FLAGGED_EMAILS"
    echo "Hint: use a role-based address (e.g., developers@fivetran.com)."
    exit 1
fi
if grep -En 'dapi[a-f0-9]{20,}|Bearer\s+[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{30,}' connector.py ; then
    echo "ERROR: embedded secret pattern found in connector.py"
    exit 1
fi
echo "clean"

echo "=== 5/7 pytest (unit + integration) ==="
if [ -d tests ]; then
    python3 -m pytest tests/ -v --tb=short
else
    echo "WARN: no tests/ directory — every connector should ship a test harness."
fi

echo "=== 6/7 README/config drift check ==="
if [ -f configuration.json ]; then
    python3 - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path("configuration.json").read_text())
readme = Path("README.md").read_text()
missing = [k for k in cfg if k not in readme]
if missing:
    print(f"ERROR: config keys missing from README: {missing}")
    raise SystemExit(1)
# Also fail if any value is NOT an angle-bracket placeholder.
non_placeholders = [
    f"{k}={v!r}" for k, v in cfg.items()
    if not (isinstance(v, str) and v.startswith("<") and v.endswith(">"))
]
if non_placeholders:
    print(f"ERROR: non-placeholder values in configuration.json: {non_placeholders}")
    raise SystemExit(1)
print(f"All {len(cfg)} configuration keys are placeholders and documented in README.")
PY
fi

echo "=== 7/7 root README link integrity ==="
ROOT_README="$(git rev-parse --show-toplevel)/README.md"
if [ -f "$ROOT_README" ]; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
    BROKEN=""
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        last_segment="${path##*/}"
        case "$last_segment" in
            *.md|*.py|*.json|*.txt|*.yaml|*.yml|*.sh) continue ;;
        esac
        if [ ! -d "$REPO_ROOT/$path" ] && [ ! -f "$REPO_ROOT/$path" ]; then
            BROKEN="$BROKEN\n  - $path"
        fi
    done < <(grep -oE 'tree/main/all_things_ai/tutorials/[a-zA-Z0-9_./-]+' "$ROOT_README" \
                | sed 's|tree/main/||' | sort -u)
    if [ -n "$BROKEN" ]; then
        echo -e "ERROR: root README links to tutorial dirs missing on this branch:$BROKEN"
        echo "Each PR adds only its own connector link; siblings add their own when they merge."
        exit 1
    fi
    echo "All tutorial links resolve to dirs present in this branch."
fi

echo ""
echo "All pre-submission checks passed."
