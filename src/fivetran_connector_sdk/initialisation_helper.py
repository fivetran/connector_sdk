import os
import re
import shutil
import subprocess
import sys

import requests as rq

from fivetran_connector_sdk.logger import Logging
from fivetran_connector_sdk.constants import EXAMPLES_GITHUB_REPO, GITHUB_BRANCH, \
    AGENT_PLUGINS, SUPPORTED_AGENT_DISPLAY_NAMES, AI_TOOLS_INSTALLATION_DOCS_URL, TEMPLATE_CONNECTOR_PATH, \
    CONNECTORS_GITHUB_REPO, CONNECTORS_TEMPLATE_PREFIX, VIRTUAL_ENV_CONFIG, EXCLUDED_DIRS
from fivetran_connector_sdk.helpers import print_library_log, PromptMode, resolve_confirmation


def init(project_dir: str, template: str, prompt_mode: PromptMode):
    existing_project = is_existing_project(project_dir)
    run_project_setup = True
    if existing_project:
        run_project_setup = resolve_confirmation("Overwrite existing project? (y/N): ", False, prompt_mode)
    try:
        if run_project_setup:
            setup_connector(project_dir, template)
            print_library_log("project initialized", log_icon=Logging.LogIcon.SUCCESS)
            print_library_log("Time to make a great connector; Happy coding")
        else:
            print_library_log("skipping project setup; existing files were not overwritten",
                              log_icon=Logging.LogIcon.STEP)
        if prompt_mode == PromptMode.INTERACTIVE:
            setup_ai_agent()
        else:
            print_library_log(f"skipping AI agent setup; {prompt_mode.value} is set", log_icon=Logging.LogIcon.STEP)
        sys.exit(0)
    except Exception as e:
        print_library_log(f"failed to initialize project error: {e}", level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        sys.exit(1)


def is_existing_project(project_dir: str) -> bool:
    if not os.path.isdir(project_dir):
        return False

    with os.scandir(project_dir) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir() and (
                    entry.name in EXCLUDED_DIRS
                    or os.path.isfile(os.path.join(entry.path, VIRTUAL_ENV_CONFIG))):
                continue
            return True

    return False


def setup_connector(project_dir: str, template: str):
    os.makedirs(project_dir, exist_ok=True)
    download_git_directory(template, project_dir)
    print_library_log(f"new project created at: {project_dir}", log_icon=Logging.LogIcon.SUCCESS)


def detect_installed_agents() -> dict:
    return {
        key: config["display_name"]
        for key, config in AGENT_PLUGINS.items()
        if shutil.which(config["cli_command"]) is not None
    }


def _print_plugin_install_guidance():
    print_library_log(
        "To install the plugin later, follow the AI tools guide:",
        log_icon=Logging.LogIcon.STEP,
    )
    print_library_log(AI_TOOLS_INSTALLATION_DOCS_URL, indent=True)


def install_agent_plugin(agent_key: str) -> bool:
    config = AGENT_PLUGINS[agent_key]
    print_library_log(f"installing {config['display_name']} plugin", log_icon=Logging.LogIcon.STEP)
    for cmd in config["install_commands"]:
        try:
            result = subprocess.run(cmd)
        except OSError as e:
            print_library_log(
                f"install command failed: {' '.join(cmd)}: {e}",
                level=Logging.Level.WARNING,
                log_icon=Logging.LogIcon.FAILURE,
            )
            _print_plugin_install_guidance()
            return False
        if result.returncode != 0:
            print_library_log(
                f"install command failed: {' '.join(cmd)}",
                level=Logging.Level.WARNING,
                log_icon=Logging.LogIcon.FAILURE,
            )
            _print_plugin_install_guidance()
            return False
    print_library_log(f"{config['display_name']} plugin installed", log_icon=Logging.LogIcon.SUCCESS)
    update_commands = config.get("update_commands", [])
    for cmd in update_commands:
        print_library_log(
            f"to update the {config['display_name']} plugin, run: {' '.join(cmd)}",
            log_icon=Logging.LogIcon.STEP,
        )
    return True


def is_agent_plugin_install_supported(agent_key: str) -> bool:
    config = AGENT_PLUGINS[agent_key]
    min_supported_version = config.get("min_supported_version")
    if min_supported_version is None:
        return True

    try:
        result = subprocess.run([config["cli_command"], "--version"], capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return True

    if result.returncode != 0:
        return True

    output = result.stdout or result.stderr
    match = re.search(r"(\d{1,5})\.(\d{1,5})\.(\d{1,5})", output)
    if not match:
        return True

    version = tuple(int(part) for part in match.groups())
    if version >= min_supported_version:
        return True

    detected_version = ".".join(str(part) for part in version)
    min_version = ".".join(str(part) for part in min_supported_version)
    print_library_log(
        f"detected {config['display_name']} {detected_version}; plugin setup requires {config['display_name']} {min_version} or newer",
        level=Logging.Level.WARNING,
        log_icon=Logging.LogIcon.FAILURE,
    )
    print_library_log(f"update {config['display_name']} and rerun agent setup", log_icon=Logging.LogIcon.STEP)
    _print_plugin_install_guidance()
    return False


def setup_ai_agent():
    installed = detect_installed_agents()

    if not installed:
        print_library_log(
            f"no supported coding agents detected ({SUPPORTED_AGENT_DISPLAY_NAMES}); skipping plugin setup",
            log_icon=Logging.LogIcon.STEP,
        )
        _print_plugin_install_guidance()
        return

    agent_list = list(installed.items())
    skip_num = len(agent_list) + 1
    menu = (
        "Installed coding agents detected. Which agent should we install the Fivetran plugin for?\n"
        + "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(agent_list, 1))
        + f"\n{skip_num}. Skip AI setup"
    )

    choice = input(f"{menu}\n\nPlease enter your selection: ").strip()
    try:
        choice_num = int(choice)
        if not (1 <= choice_num <= skip_num):
            raise ValueError
    except ValueError:
        print_library_log("invalid choice; skipping agent setup", log_icon=Logging.LogIcon.FAILURE)
        return

    if choice_num == skip_num:
        print_library_log("skipping plugin setup", log_icon=Logging.LogIcon.STEP)
        _print_plugin_install_guidance()
    else:
        agent_key = agent_list[choice_num - 1][0]
        if not is_agent_plugin_install_supported(agent_key):
            return
        if not install_agent_plugin(agent_key):
            print_library_log(
                "agent plugin setup failed; skipping plugin setup",
                level=Logging.Level.WARNING,
                log_icon=Logging.LogIcon.FAILURE,
            )


def validate_example_directory(files_to_download: list, requested_path: str = ""):
    connector_files = [
        f for f in files_to_download
        if f['local_path'].endswith("connector.py")
    ]

    if len(connector_files) > 1:
        matches = sorted({f['github_path'].rsplit('/connector.py', 1)[0] for f in connector_files})
        print_library_log(
            f"no connector found at '{requested_path}'; available connectors with prefix '{requested_path}':",
            Logging.Level.WARNING
        )
        for match in matches:
            print_library_log(f"{match}", log_icon=Logging.LogIcon.STEP, indent=True)
        raise ValueError("re-run with an exact connector name from the list above")

    if len(connector_files) != 1:
        print_library_log(
            "selected directory is not a valid example; missing connector.py",
            Logging.Level.SEVERE
        )
        raise ValueError("Invalid directory passed. Path did not resolve to a valid connector.")

def _resolve_repo_and_path(path_prefix: str) -> tuple:
    """Returns (repo, actual_path) based on template routing rules."""
    if path_prefix.startswith(CONNECTORS_TEMPLATE_PREFIX):
        return CONNECTORS_GITHUB_REPO, path_prefix[len(CONNECTORS_TEMPLATE_PREFIX):]
    if path_prefix.startswith("examples/"):
        return EXAMPLES_GITHUB_REPO, path_prefix
    return CONNECTORS_GITHUB_REPO, path_prefix


def _collect_download_files(tree: list, actual_path: str) -> tuple:
    files_to_download = []
    prefix_matches = set()
    for item in tree:
        if item['type'] != 'blob':
            continue
        # "actual_path + /" ensures exact directory match, preventing prefix collisions (e.g. "github" matching "github_traffic")
        if item['path'].startswith(actual_path + "/"):
            # strip directory prefix and leading "/" to get path relative to project root
            relative_path = item['path'][len(actual_path):].lstrip('/')
            # skip README when downloading the blank starter template (users write their own)
            if actual_path == TEMPLATE_CONNECTOR_PATH and "readme" in relative_path.lower():
                continue
            files_to_download.append({
                'github_path': item['path'],
                'local_path': relative_path,
                'size': item.get('size', 0)
            })
        # prefix match: collect connector dirs for suggestion when exact path not found
        elif item['path'].startswith(actual_path) and item['path'].split('/')[-1] == 'connector.py':
            prefix_matches.add("/".join(item['path'].split('/')[:-1]))
    return files_to_download, prefix_matches


def _collect_nested_prefix_matches(tree: list, actual_path: str) -> set:
    """Find connectors in subdirectories matching the prefix.
    
    For examples/hello, this finds examples/quickstart/hello and examples/advanced/hello_world,
    but not direct children like examples/hello (those are handled by _collect_download_files).
    """
    parent_path, separator, connector_name_prefix = actual_path.rpartition("/")
    if not separator or not connector_name_prefix:
        return set()

    parent_path_prefix = parent_path + "/"
    nested_prefix_matches = set()
    for item in tree:
        if item['type'] != 'blob' or item['path'].split('/')[-1] != 'connector.py':
            continue

        connector_path = item['path'].rsplit('/connector.py', 1)[0]
        if not connector_path.startswith(parent_path_prefix):
            continue

        # Extract path relative to parent (e.g., "quickstart/hello" from "examples/quickstart/hello")
        relative_connector_path = connector_path[len(parent_path_prefix):]
        # Only match nested paths (containing "/"), skip direct children
        if "/" not in relative_connector_path:
            continue

        # Check if the final directory name matches the prefix
        connector_name = relative_connector_path.rsplit('/', 1)[-1]
        if connector_name.startswith(connector_name_prefix):
            nested_prefix_matches.add(connector_path)

    return nested_prefix_matches


def _raise_no_match(prefix_matches: set, requested_path: str, has_nested_matches: bool = False):
    if prefix_matches:
        if has_nested_matches:
            match_message = f"no connector found matching '{requested_path}'; did you mean any of the following:"
        else:
            match_message = (
                f"no connector found at '{requested_path}'; "
                f"available connectors with prefix '{requested_path}':"
            )
        print_library_log(
            match_message,
            Logging.Level.WARNING
        )
        for match in sorted(prefix_matches):
            print_library_log(f"{match}", log_icon=Logging.LogIcon.STEP, indent=True)
        raise ValueError("re-run with an exact connector name from the list above")
    raise ValueError(f"no connector found matching '{requested_path}'")


def download_git_directory(path_prefix: str, project_dir: str):
    repo, actual_path = _resolve_repo_and_path(path_prefix)
    requested_path = path_prefix.rstrip("/")
    actual_path = actual_path.rstrip("/")
    try:
        tree_url = f"https://api.github.com/repos/{repo}/git/trees/{GITHUB_BRANCH}?recursive=1"
        response = rq.get(tree_url, timeout=10)
        response.raise_for_status()

        tree_data = response.json()
        if 'tree' not in tree_data:
            print_library_log("failed to fetch repository from GitHub", level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
            return

        files_to_download, prefix_matches = _collect_download_files(tree_data['tree'], actual_path)

        if not files_to_download:
            # For examples/ repo, also search nested subdirectories (e.g., examples/quickstart/hello)
            nested_prefix_matches = set()
            if repo == EXAMPLES_GITHUB_REPO:
                nested_prefix_matches = _collect_nested_prefix_matches(tree_data['tree'], actual_path)
                prefix_matches.update(nested_prefix_matches)
            _raise_no_match(prefix_matches, requested_path, bool(nested_prefix_matches))

        validate_example_directory(files_to_download, requested_path)

        print_library_log(f"downloading {len(files_to_download)} files from GitHub", log_icon=Logging.LogIcon.STEP)
        download_file_from_github(files_to_download, project_dir, repo)

    except ValueError as e:
        print_library_log(str(e), Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        sys.exit(1)
    except Exception as e:
        print_library_log(f"failed to download files: {e}", Logging.Level.WARNING)
        print_library_log(f"files are available for manual download from: https://github.com/{repo}/tree/{GITHUB_BRANCH}/{actual_path}")


def download_file_from_github(files_to_download: list, project_dir: str, repo: str = EXAMPLES_GITHUB_REPO):
    for file_info in files_to_download:
        # Construct raw download URL
        raw_url = f"https://raw.githubusercontent.com/{repo}/{GITHUB_BRANCH}/{file_info['github_path']}"

        # Create target path
        target_path = os.path.join(project_dir, file_info['local_path'])
        target_dir = os.path.dirname(target_path)

        # Create directory if needed
        if target_dir and not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        # Download file
        try:
            file_response = rq.get(raw_url, timeout=10)
            file_response.raise_for_status()

            with open(target_path, 'wb') as f:
                f.write(file_response.content)

            print_library_log(f"downloaded {file_info['local_path']}", level=Logging.Level.INFO, log_icon=Logging.LogIcon.SUCCESS)
        except Exception as e:
            print_library_log(f"failed to download {file_info['local_path']}: {e}", level=Logging.Level.WARNING, log_icon=Logging.LogIcon.FAILURE)
