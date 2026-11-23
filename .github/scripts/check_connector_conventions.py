"""
Check the deterministic connector conventions from python-review.instructions.md.

Usage: python .github/scripts/check_connector_conventions.py path/to/connector.py [...]

Prints one line per finding as `path:line: SEVERITY: message` and exits 1 if any BLOCKER is found.
"""

import ast
import re
import sys

BLOCKER = "BLOCKER"
SUGGESTION = "SUGGESTION"

DOCS = "https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods"
LEGACY_DOCS = "https://fivetran.com/docs/connectors/connector-sdk/technical-reference"
UPSERT_COMMENT = (
    "The 'upsert' operation is used to insert or update data in the destination table."
)
CHECKPOINT_COMMENT = "Save the progress by checkpointing the state."
MAIN_COMMENT = (
    "IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:"
)
INIT_PATTERN = re.compile(r"^connector = Connector\(update=update(, schema=schema)?\)\s*$", re.M)


def comment_block_above(lines, lineno):
    """Return the text of the contiguous comment lines directly above a 1-based line number."""
    block = []
    index = lineno - 2
    while index >= 0 and lines[index].strip().startswith("#"):
        block.append(lines[index])
        index -= 1
    return "\n".join(block)


def check_docstring_url(function, name, findings):
    """Check that schema() and update() docstrings link to the methods documentation."""
    docstring = ast.get_docstring(function) or ""
    anchor = f"#{name}"
    if f"{DOCS}{anchor}" in docstring:
        return
    if f"{LEGACY_DOCS}{anchor}" in docstring:
        findings.append(
            (
                function.lineno,
                SUGGESTION,
                f"{name}() docstring uses the legacy docs URL; use {DOCS}{anchor}",
            )
        )
    else:
        findings.append(
            (function.lineno, BLOCKER, f"{name}() docstring must link to {DOCS}{anchor}")
        )


def check_first_log(update, findings):
    """Check that update() starts with log.warning("Example: <CATEGORY> : <EXAMPLE_NAME>")."""
    body = update.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # skip docstring
    first = body[0] if body else None
    call = (
        first.value if isinstance(first, ast.Expr) and isinstance(first.value, ast.Call) else None
    )
    argument = call.args[0] if call is not None and call.args else None
    is_warning_call = call is not None and getattr(call.func, "attr", None) == "warning"
    message = argument.value if isinstance(argument, ast.Constant) else None
    if not (
        is_warning_call and isinstance(message, str) and re.match(r"Example: .+ : .+", message)
    ):
        findings.append(
            (
                update.lineno,
                BLOCKER,
                'update() must start with log.warning("Example: <CATEGORY> : <EXAMPLE_NAME>")',
            )
        )


def check_operation_comments(tree, lines, findings):
    """Check the required comment before every op.upsert() and op.checkpoint()."""
    required = {"upsert": UPSERT_COMMENT, "checkpoint": CHECKPOINT_COMMENT}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "op" and node.func.attr in required:
            if required[node.func.attr] not in comment_block_above(lines, node.lineno):
                findings.append(
                    (
                        node.lineno,
                        BLOCKER,
                        f"op.{node.func.attr}() is missing the required comment block above it",
                    )
                )


def check_file(path):
    """Run all checks on one file and return a sorted list of (line, severity, message)."""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    lines = source.splitlines()
    tree = ast.parse(source)
    findings = []

    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("schema", "update"):
        if name in functions:
            check_docstring_url(functions[name], name, findings)
    if "update" in functions:
        check_first_log(functions["update"], findings)
    else:
        findings.append((1, BLOCKER, "update() function is missing"))

    check_operation_comments(tree, lines, findings)

    if not INIT_PATTERN.search(source):
        findings.append(
            (
                1,
                BLOCKER,
                "missing `connector = Connector(update=update, schema=schema)` at module level",
            )
        )

    main_lines = [
        i for i, line in enumerate(lines, 1) if line.startswith('if __name__ == "__main__"')
    ]
    if not main_lines:
        findings.append((len(lines), BLOCKER, 'missing `if __name__ == "__main__":` block'))
    elif MAIN_COMMENT not in comment_block_above(lines, main_lines[0]):
        findings.append(
            (main_lines[0], BLOCKER, "main block is missing the required comment above it")
        )

    return sorted(findings)


def main(paths):
    """Print findings for each path and return the process exit code."""
    has_blocker = False
    for path in paths:
        for line, severity, message in check_file(path):
            print(f"{path}:{line}: {severity}: {message}")
            has_blocker = has_blocker or severity == BLOCKER
    return 1 if has_blocker else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
