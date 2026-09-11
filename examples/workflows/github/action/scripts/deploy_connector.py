#!/usr/bin/env python3
"""Existence-aware wrapper around `fivetran deploy`, driven entirely by env vars.

Used by action/action.yml (the composite action) -- see action/README.md for the
behavior this implements. In short:

- CONFIGURATION_JSON, if non-empty, is pushed as-is -- whether that creates a
  connection or updates an existing one. Its mere presence is the only signal:
  don't compute/pass it unless you actually want it pushed to the live
  connection right now (the caller workflow controls that, e.g. by only
  running its "assemble config" step on a deliberate manual trigger).
- If CONFIGURATION_JSON is empty, this is a code-only deploy. The `fivetran`
  CLI itself already knows whether CONNECTION_NAME exists -- we don't
  re-detect that. If the CLI rejects the code-only deploy because the
  connection doesn't exist yet (a first deploy needs *some* configuration),
  retry once with a placeholder file (EMPTY_CONFIG_PATH, default
  configuration.example.json) so the connection still gets created -- paused,
  "needs attention" -- with its setup form ready for someone to fill in via
  the dashboard.
- The `fivetran deploy` CLI always creates new connections paused -- it
  hardcodes that and exposes no flag to change it. ACTIVATE_ON_CREATE is a
  one-time switch, not an ongoing desired state: if it's true and *this run*
  just created the connection with real configuration (status "created", not
  "created_needs_setup"), we unpause it afterwards with a direct call to the
  Fivetran API. It has no effect on any other run -- a redeploy of an
  existing connection (status "updated") never touches its current
  paused/active state, whatever that is.
- Regardless of ACTIVATE_ON_CREATE, whenever a connection ID is known we
  read the connection's *current* paused state back from the Fivetran API
  and report it as the "active" output. This is independent of what this run
  did, so it's the only way to learn whether an existing connection is
  active on a plain redeploy.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests

FIRST_DEPLOY_ERROR = "configuration is required"
SETUP_TESTS_FAILED = "setup tests failed"
FIVETRAN_API_BASE_URL = "https://api.fivetran.com/v1"
API_TIMEOUT_SECONDS = 30


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if not value:
        return default
    return value.lower() in ("1", "true", "yes")


def gha_notice(message: str, level: str = "notice") -> None:
    print(f"::{level}::{message}")


def write_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with open(output_file, "a") as f:
        f.write(f"{name}={value}\n")


def derive_connection_name(connector_dir: Path) -> str:
    # Mirrors the naming rule the SDK itself enforces: only [a-z0-9_], starting
    # with '_' or a lowercase letter.
    slug = re.sub(r"[^a-z0-9_]", "_", connector_dir.name.lower())
    if not re.match(r"^[a-z_]", slug):
        slug = f"_{slug}"
    return slug


def fivetran_executable() -> str:
    """Resolve the `fivetran` console script installed next to this interpreter.

    This script is invoked as `<connector_dir>/.venv/bin/python deploy_connector.py`
    (see action.yml) rather than via `source .venv/bin/activate`, so the venv's
    bin/ directory was never added to PATH -- a bare "fivetran" would only
    resolve by coincidence. sys.executable always points into that same venv.
    """
    candidate = Path(sys.executable).parent / "fivetran"
    return str(candidate) if candidate.is_file() else "fivetran"


def activate_connection(api_key: str, connection_id: str) -> None:
    """Unpauses a newly created connection via the Fivetran API.

    The `fivetran deploy` CLI has no flag for this -- it hardcodes new
    connections to paused=True -- so activation is a separate API call.
    """
    try:
        response = requests.patch(
            f"{FIVETRAN_API_BASE_URL}/connectors/{connection_id}",
            headers={"Authorization": f"Basic {api_key}"},
            json={"paused": False},
            timeout=API_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        gha_notice(
            f"connection {connection_id} was created but activation failed: {exc}",
            level="warning",
        )
        return
    if response.ok:
        gha_notice(f"connection {connection_id} activated")
    else:
        gha_notice(
            f"connection {connection_id} was created but activation failed "
            f"({response.status_code}): {response.text}",
            level="warning",
        )


def report_active_state(api_key: str, connection_id: str) -> None:
    """Reads the connection's current paused state and writes it as the `active` output.

    Done with a fresh GET rather than inferred from what this run did, so it's
    accurate for every status -- including "updated", where this run may not
    have touched the connection's paused/active state at all.
    """
    try:
        response = requests.get(
            f"{FIVETRAN_API_BASE_URL}/connectors/{connection_id}",
            headers={"Authorization": f"Basic {api_key}"},
            timeout=API_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        gha_notice(
            f"could not read connection {connection_id}'s current state: {exc}", level="warning"
        )
        return
    if not response.ok:
        gha_notice(
            f"could not read connection {connection_id}'s current state "
            f"({response.status_code}): {response.text}",
            level="warning",
        )
        return

    active = not response.json()["data"]["paused"]
    write_output("active", "true" if active else "false")
    gha_notice(f"connection {connection_id} is currently {'active' if active else 'paused'}")


def run_deploy(cmd: list[str], cwd: Path) -> tuple[int, str]:
    print(f"::group::Running: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    assert process.stdout is not None  # guaranteed by stdout=PIPE above
    lines = []
    for line in process.stdout:
        print(line, end="")
        lines.append(line)
    process.wait()
    print("::endgroup::")
    return process.returncode, "".join(lines)


def main() -> int:
    connector_dir = Path(env("CONNECTOR_DIR")).resolve()
    if not connector_dir.is_dir():
        raise SystemExit(f"connector_dir '{connector_dir}' does not exist")

    destination = env("DESTINATION")
    connection_name = env("CONNECTION_NAME") or derive_connection_name(connector_dir)
    configuration_json = env("CONFIGURATION_JSON")
    empty_config_path = env("EMPTY_CONFIG_PATH", "configuration.example.json")
    python_version = env("PYTHON_VERSION")
    activate_on_create = env_bool("ACTIVATE_ON_CREATE")
    fivetran_api_key = env("FIVETRAN_API_KEY")
    # `fivetran deploy` reads FIVETRAN_API_KEY from the environment itself (it's
    # already exported by action.yml) -- this is just a fail-fast check.
    if not fivetran_api_key:
        raise SystemExit("FIVETRAN_API_KEY is required")

    use_config = bool(configuration_json)
    config_path = connector_dir / "configuration.json"

    base_cmd = [fivetran_executable(), "deploy", "--connection", connection_name, "--yes"]
    if destination:
        base_cmd += ["--destination", destination]
    if python_version:
        base_cmd += ["--python-version", python_version]

    wrote_config = False
    try:
        if use_config:
            config_path.write_text(configuration_json)
            wrote_config = True
        else:
            # Defend against a stray configuration.json already sitting in the project
            # folder -- `fivetran deploy` auto-loads it even without --configuration,
            # which would silently overwrite the live connection's stored config.
            config_path.unlink(missing_ok=True)

        cmd = base_cmd + (["--configuration", str(config_path)] if wrote_config else [])
        returncode, output = run_deploy(cmd, connector_dir)

        retried_as_first_deploy = False
        if returncode != 0 and not use_config and FIRST_DEPLOY_ERROR in output:
            retried_as_first_deploy = True
            placeholder = connector_dir / empty_config_path
            if placeholder.is_file():
                shutil.copyfile(placeholder, config_path)
            else:
                config_path.write_text("{}")
            wrote_config = True
            cmd = base_cmd + ["--configuration", str(config_path)]
            returncode, output = run_deploy(cmd, connector_dir)

        connection_id = None
        connection_id_match = re.search(r"connection id:\s*(\S+)", output)
        if connection_id_match:
            connection_id = connection_id_match.group(1)
            write_output("connection_id", connection_id)
            write_output(
                "dashboard_url",
                f"https://fivetran.com/dashboard/connections/{connection_id}/status",
            )

        if returncode != 0 and retried_as_first_deploy and SETUP_TESTS_FAILED in output:
            write_output("status", "created_needs_setup")
            gha_notice(
                "Connection created with placeholder configuration, but setup tests failed as "
                "expected (placeholder values aren't real credentials). Enter real values in the "
                "Fivetran dashboard's Setup tab to finish onboarding.",
                level="warning",
            )
            if activate_on_create:
                gha_notice(
                    "activate_on_create was requested, but the connection only has "
                    "placeholder configuration -- leaving it paused until real values are "
                    "entered in the dashboard.",
                )
            if connection_id:
                report_active_state(fivetran_api_key, connection_id)
            return 0

        if returncode != 0:
            gha_notice(f"fivetran deploy failed (exit {returncode})", level="error")
            return returncode

        status = "created" if "connection created" in output else "updated"
        write_output("status", status)

        if activate_on_create and status == "created" and connection_id:
            activate_connection(fivetran_api_key, connection_id)

        if connection_id:
            report_active_state(fivetran_api_key, connection_id)

        return 0
    finally:
        if wrote_config:
            config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
