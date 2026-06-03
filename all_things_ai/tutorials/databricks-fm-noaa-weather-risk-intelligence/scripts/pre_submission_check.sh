#!/usr/bin/env bash
# Pre-submission gate for the NOAA Weather Intelligence connector.
# Run from the connector directory. Exits non-zero if any check fails.
#
# Reference pattern intended for promotion to the
# fivetran-connector-sdk-submission skill — the skill should invoke this
# (or its equivalent) before any `fivetran deploy`.
set -euo pipefail

cd "$(dirname "$0")/.."

# Line length matches repo's .flake8 (max-line-length=99) and .github/git_hooks/pre-commit (black --line-length=99).
LINE_LEN=99

echo "=== 1/6 flake8 (code quality) ==="
python3 -m flake8 connector.py

echo "=== 2/6 black --check (formatting, line-length=$LINE_LEN) ==="
python3 -m black --check --line-length=$LINE_LEN connector.py

echo "=== 3a/6 dead module-level constants ==="
# Module-level constants prefixed with `__` (the convention in this repo for
# private constants) must be referenced at least once outside their definition.
# Catches the class of issue raised on PR #570 where __STATE_ADJACENCY was
# defined but never used.
DEAD_CONSTS=""
while IFS= read -r const; do
    [ -z "$const" ] && continue
    # Count occurrences. If only 1, it's the definition (dead).
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

echo "=== 3/6 PII scan (emails in source, embedded tokens) ==="
# Flag any email address in connector.py except role-based addresses
# (developers@, noreply@, hello@, support@, api@, admin@, security@).
FLAGGED_EMAILS=$(grep -En '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' connector.py \
    | grep -vE '(developers|noreply|hello|support|api|admin|security)@' || true)
if [ -n "$FLAGGED_EMAILS" ]; then
    echo "ERROR: possible personal email found in connector.py:"
    echo "$FLAGGED_EMAILS"
    echo "Hint: use a role-based address (e.g., developers@fivetran.com)."
    exit 1
fi
if grep -En 'dapi[a-f0-9]{20,}|Bearer\s+[A-Za-z0-9_-]{30,}' connector.py ; then
    echo "ERROR: embedded secret pattern found in connector.py"
    exit 1
fi
echo "clean"

echo "=== 4/6 pytest (unit + integration) ==="
python3 -m pytest tests/ -v --tb=short

echo "=== 5/6 README/config drift check ==="
if [ -f configuration.json ]; then
    python3 - <<'PY'
import json
import re
from pathlib import Path

cfg = json.loads(Path("configuration.json").read_text())
readme = Path("README.md").read_text()
missing = []
for key in cfg:
    if key not in readme:
        missing.append(key)
if missing:
    print(f"ERROR: config keys missing from README: {missing}")
    raise SystemExit(1)
print(f"All {len(cfg)} configuration keys documented in README.")
PY
fi

echo "=== 6/6 root README link integrity ==="
# Catch the case where the root README links to a tutorial dir that doesn't
# exist on this branch (would create a broken link in published docs once
# this branch lands). Resolve any github.com/.../tree/main/all_things_ai/tutorials/X
# link to a local path and verify it exists.
ROOT_README="$(git rev-parse --show-toplevel)/README.md"
if [ -f "$ROOT_README" ]; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
    BROKEN=""
    # Capture full URL paths (including subdirs); filter out file links by extension.
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        # Only check if the link points to what should be a directory (no file extension on last segment).
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
        echo "Each PR should add only its own connector link; siblings add their own when they merge."
        exit 1
    fi
    echo "All tutorial links resolve to dirs present in this branch."
fi

echo ""
echo "✓ All pre-submission checks passed."
