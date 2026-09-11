"""Stand-in for the real `fivetran` console script, installed into the fixture
connector's venv instead of fivetran-connector-sdk (see ../connector/pyproject.toml).

deploy_connector.py only cares about this process's exit code and stdout --
it greps the output for "connection id:", "configuration is required", and
"setup tests failed" (see FIRST_DEPLOY_ERROR / SETUP_TESTS_FAILED in
deploy_connector.py) -- so faking just those is enough to drive every branch
of its retry/decision logic through the real composite action, with no
Fivetran account or credentials involved.

Controlled by env vars, set per scenario by
.github/workflows/test-deploy-action.yml's matrix:
  FAKE_FIVETRAN_OUTPUT / FAKE_FIVETRAN_EXIT
      Used for calls without --configuration (a code-only deploy attempt).
  FAKE_FIVETRAN_OUTPUT_WITH_CONFIG / FAKE_FIVETRAN_EXIT_WITH_CONFIG
      Used for calls with --configuration (either configuration_json was
      pushed, or this is deploy_connector.py's placeholder-config retry).
      Falls back to the pair above if unset.
"""

import os
import sys


def main() -> int:
    with_config = "--configuration" in sys.argv
    if with_config:
        output = os.environ.get(
            "FAKE_FIVETRAN_OUTPUT_WITH_CONFIG", os.environ.get("FAKE_FIVETRAN_OUTPUT", "")
        )
        exit_code = int(
            os.environ.get("FAKE_FIVETRAN_EXIT_WITH_CONFIG", os.environ.get("FAKE_FIVETRAN_EXIT", "0"))
        )
    else:
        output = os.environ.get("FAKE_FIVETRAN_OUTPUT", "")
        exit_code = int(os.environ.get("FAKE_FIVETRAN_EXIT", "0"))

    if output:
        sys.stdout.write(output if output.endswith("\n") else output + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
