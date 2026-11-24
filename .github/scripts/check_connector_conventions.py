"""
Check the structural connector conventions from python-review.instructions.md.

It checks that required elements exist (docstring links, first log line, comments above
operations and the main block, the connector object), not their exact wording, so docs or
comment text changes do not require changing this script.

It also checks the Getting started section of a README: a Fivetran docs link, and with
`--require-init` a `fivetran init` command.

Usage: python .github/scripts/check_connector_conventions.py [--require-init] path/to/file [...]
Each path is a connector `.py` file or an example `README.md`.

Prints one line per finding as `path:line: SEVERITY: message` and exits 1 if any BLOCKER is found.
"""

import ast
import re
import sys

BLOCKER = "BLOCKER"


def is_connector_assignment(node):
    """Return True for a module-level `<name> = Connector(...)` assignment, however formatted."""
    value = getattr(node, "value", None)
    if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(value, ast.Call):
        return False
    function = value.func
    return getattr(function, "id", getattr(function, "attr", None)) == "Connector"


def is_main_guard(node):
    """Return True for `if __name__ == "__main__":` in either quote style or operand order."""
    if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
        return False
    operands = [node.test.left, *node.test.comparators]
    names = [o.id for o in operands if isinstance(o, ast.Name)]
    strings = [o.value for o in operands if isinstance(o, ast.Constant)]
    is_single_equality = len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)
    return is_single_equality and names == ["__name__"] and strings == ["__main__"]


def has_comment_above(lines, lineno):
    """Return True if the nearest non-blank line above a 1-based line number is a comment."""
    index = lineno - 2
    while index >= 0 and not lines[index].strip():
        index -= 1
    return index >= 0 and lines[index].strip().startswith("#")


def check_docstring_url(function, name, findings):
    """Check that schema() and update() docstrings link to a Fivetran docs page for the method."""
    docstring = ast.get_docstring(function) or ""
    if not re.search(rf"https://fivetran\.com/docs/\S*#{name}\b", docstring):
        findings.append(
            (
                function.lineno,
                BLOCKER,
                f"{name}() docstring must link to its Fivetran docs section",
            )
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
    """Check that every op.upsert() and op.checkpoint() has a comment directly above it."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        owner = node.func.value
        is_operation = isinstance(owner, ast.Name) and owner.id == "op"
        if is_operation and node.func.attr in ("upsert", "checkpoint"):
            if not has_comment_above(lines, node.lineno):
                findings.append(
                    (node.lineno, BLOCKER, f"op.{node.func.attr}() has no comment above it")
                )


def check_file(path):
    """Run all checks on one file and return a sorted list of (line, severity, message)."""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [(error.lineno or 1, BLOCKER, f"file does not parse: {error.msg}")]
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

    if not any(is_connector_assignment(node) for node in tree.body):
        findings.append((1, BLOCKER, "missing module-level `connector = Connector(...)`"))

    main_blocks = [node for node in tree.body if is_main_guard(node)]
    if not main_blocks:
        findings.append((len(lines), BLOCKER, 'missing `if __name__ == "__main__":` block'))
    elif not has_comment_above(lines, main_blocks[0].lineno):
        findings.append((main_blocks[0].lineno, BLOCKER, "main block has no comment above it"))

    return sorted(findings)


def check_readme(path, require_init):
    """Check the Getting started section of a README and return (line, severity, message) tuples."""
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    starts = [
        i for i, line in enumerate(lines) if re.match(r"##\s+Getting started\s*$", line, re.I)
    ]
    if not starts:
        return [(1, BLOCKER, "README has no `## Getting started` section")]
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = "\n".join(lines[start:end])

    findings = []
    if not re.search(r"https://fivetran\.com/docs/\S+", section):
        findings.append((start + 1, BLOCKER, "Getting started has no link to the Fivetran docs"))
    if require_init and not re.search(r"^\s*fivetran init\b", section, re.M):
        findings.append((start + 1, BLOCKER, "Getting started has no `fivetran init` command"))
    return findings


def main(arguments):
    """Print findings for each path and return the process exit code.

    `.md` paths get the README check, other paths get the connector checks.
    `--require-init` makes the README check require a `fivetran init` command.
    """
    require_init = "--require-init" in arguments
    paths = [argument for argument in arguments if argument != "--require-init"]
    has_blocker = False
    for path in paths:
        if path.lower().endswith(".md"):
            findings = check_readme(path, require_init)
        else:
            findings = check_file(path)
        for line, severity, message in findings:
            print(f"{path}:{line}: {severity}: {message}")
            has_blocker = has_blocker or severity == BLOCKER
    return 1 if has_blocker else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
