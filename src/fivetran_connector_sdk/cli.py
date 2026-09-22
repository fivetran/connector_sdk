"""Direct Connector SDK CLI entrypoint."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None):
    """Run the SDK CLI directly, optionally with an explicit argv."""
    original_argv = list(sys.argv)
    if argv is not None:
        sys.argv = [original_argv[0] if original_argv else "fivetran", *argv]
    try:
        from fivetran_connector_sdk import main as sdk_main

        return sdk_main()
    finally:
        sys.argv = original_argv
