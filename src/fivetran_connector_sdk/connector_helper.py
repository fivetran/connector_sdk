import os
import re
import ast
import json
import sys
import stat
import time
import socket
import shutil
import platform
import traceback
import subprocess
import requests as rq
import pathspec
from enum import Enum
from tqdm import tqdm

from typing import Callable, Optional, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

from fivetran_connector_sdk.protos import common_pb2

from fivetran_connector_sdk import constants
from fivetran_connector_sdk.logger import Logging
from fivetran_connector_sdk.helpers import (
    print_library_log,
    get_input_from_cli,
    validate_and_load_state,
    validate_and_load_configuration,
    _validate_table_name,
    PromptMode,
    resolve_confirmation,
)
from fivetran_connector_sdk.constants import (
    OS_MAP,
    ARCH_MAP,
    WIN_OS,
    TESTER_FILENAME,
    UPLOAD_FILENAME,
    LAST_VERSION_CHECK_FILE,
    ROOT_LOCATION,
    TESTER_LOCATION,
    CONFIG_FILE,
    OUTPUT_FILES_DIR,
    REQUIREMENTS_TXT,
    PYPROJECT_TOML,
    PYPROJECT_SKIP_VALIDATION_MESSAGE,
    CONFIGURATION_JSON,
    FIVETRAN_API_KEY_ENV,
    FIVETRAN_DESTINATION_NAME_ENV,
    FIVETRAN_CONNECTION_NAME_ENV,
    PYPI_PACKAGE_DETAILS_URL,
    SIX_HOUR_IN_SEC,
    MAX_RETRIES,
    VIRTUAL_ENV_CONFIG,
    ROOT_FILENAME,
    ALWAYS_INCLUDED_FILES,
    EXCLUDED_DIRS,
    EXCLUDED_PIPREQS_DIRS,
    INSTALLATION_SCRIPT,
    INSTALLATION_SCRIPT_MISSING_MESSAGE,
    DRIVERS,
    UTF_8,
    CONNECTION_SCHEMA_NAME_PATTERN,
    TABLES,
    UNDERSCORE_NAMING,
    FIVETRAN_NAMING_ENV,
    SOURCE_NAMING_VALUE,
    FIVETRAN_NAMING_VALUE,
    REDACTED_VALUE,
    VERSION_FILENAME,
    TESTER_VERSION,
    CONFIGURATION_FORM_FILENAME,
    RECOMMEND_STABLE_VERSION_MESSAGE,
)

SETUP_TESTS_RUNNING_MESSAGE = (
    "Running setup tests can take up to a few minutes; "
    "custom tests may take longer depending on your code and external APIs."
)


class NetworkingMethod(str, Enum):
    PROXY_AGENT = "ProxyAgent"
    DIRECTLY = "Directly"


def log_setup_tests_running() -> None:
    print_library_log(SETUP_TESTS_RUNNING_MESSAGE, log_icon=Logging.LogIcon.STEP)


def get_destination_group(args):
    ft_group = args.destination if args.destination else None
    if not ft_group:
        ft_group = os.getenv("FIVETRAN_DESTINATION_NAME", None)
        if ft_group:
            print_library_log(
                "reading destination name from FIVETRAN_DESTINATION_NAME environment variable",
                Logging.Level.INFO,
                log_icon=Logging.LogIcon.INFO,
            )
    if ft_group and ft_group.strip() == "":
        return None
    return ft_group


def get_connection_name(args):
    ft_connection = args.connection if args.connection else None
    if not ft_connection:
        ft_connection = os.getenv("FIVETRAN_CONNECTION_NAME", None)
        if ft_connection:
            print_library_log(
                "reading connection name from FIVETRAN_CONNECTION_NAME environment variable",
                Logging.Level.INFO,
                log_icon=Logging.LogIcon.INFO,
            )
    if ft_connection and not is_connection_name_valid(ft_connection):
        print_library_log(f"invalid connection name: '{ft_connection}'", Logging.Level.SEVERE)
        print_library_log(
            "connection names must use only [a-z0-9_] and begin with '_' or a lowercase letter",
            Logging.Level.SEVERE,
        )
        sys.exit(1)
    return ft_connection


def get_api_key(args):
    ft_deploy_key = args.api_key if args.api_key else None
    if not ft_deploy_key:
        ft_deploy_key = os.getenv("FIVETRAN_API_KEY", None)
        if ft_deploy_key:
            print_library_log(
                "reading api key from FIVETRAN_API_KEY environment variable",
                Logging.Level.INFO,
                log_icon=Logging.LogIcon.INFO,
            )
    if ft_deploy_key and ft_deploy_key.strip() == "":
        return None
    return ft_deploy_key


def get_python_version(args, prompt_mode: PromptMode):
    python_version = args.python_version if args.python_version else None
    env_python_version = os.getenv("FIVETRAN_PYTHON_VERSION", None)
    if env_python_version and not python_version and not prompt_mode.is_non_interactive_mode:
        python_version = get_input_from_cli("Provide your python version", env_python_version)
    return python_version


def get_hd_agent_id(args, prompt_mode: PromptMode):
    hd_agent_id = args.hybrid_deployment_agent_id if args.hybrid_deployment_agent_id else None
    env_hd_agent_id = os.getenv("FIVETRAN_HD_AGENT_ID", None)

    if env_hd_agent_id and not hd_agent_id and not prompt_mode.is_non_interactive_mode:
        hd_agent_id = get_input_from_cli("Provide the Hybrid Deployment Agent ID", env_hd_agent_id)
    return hd_agent_id


def get_proxy_id(args):
    proxy_id = getattr(args, "proxy_id", None)
    if proxy_id is None:
        return None
    if not proxy_id.strip():
        print_library_log(
            "--proxy-id was provided with an empty value; please provide a valid Proxy Agent ID.",
            Logging.Level.SEVERE,
        )
        sys.exit(1)
    return proxy_id.strip()


def get_proxy_host_config_key(args):
    proxy_host_config_key = getattr(args, "proxy_host_config_key", None)
    if proxy_host_config_key is None:
        return None
    return proxy_host_config_key.strip() or None


def get_state(args):
    if args.command.lower() == "deploy" and args.state:
        print_library_log(
            "unrecognised argument: '--state'; not supported by 'deploy'\nmanage connection state using the Fivetran API instead\nreference:https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/state-management",
            Logging.Level.WARNING,
        )
        sys.exit(1)
    state = args.state if args.state else os.getenv("FIVETRAN_STATE", None)
    state = validate_and_load_state(args, state)
    return state


def validate_naming(naming):
    """Validate naming value, return uppercase or exit on error.

    Args:
        naming (str): The naming strategy value to validate.

    Returns:
        str: Uppercase validated naming value, or None if input is None.
    """
    if not naming:
        return None
    value_upper = naming.strip().upper()
    if value_upper in (SOURCE_NAMING_VALUE, FIVETRAN_NAMING_VALUE):
        return value_upper
    print_library_log(
        f"Invalid naming strategy: '{naming}'. Must be 'FIVETRAN' or 'SOURCE' (case-insensitive).",
        Logging.Level.SEVERE,
    )
    sys.exit(1)


def get_naming(args):
    """Fetch, validate, and format naming field from args or environment.

    Args:
        args: The command-line arguments namespace.

    Returns:
        str: The formatted naming strategy (e.g., "FIVETRAN_NAMING" or "SOURCE_NAMING"),
             or None if not explicitly set via CLI or environment variable.
    """
    naming = args.naming if hasattr(args, "naming") else None
    if not naming:
        naming = os.getenv(FIVETRAN_NAMING_ENV, None)

    validated = validate_naming(naming)
    return validated + UNDERSCORE_NAMING if validated else None


def get_configuration(args):
    configuration = args.configuration if args.configuration else None

    if not configuration:
        env_configuration = os.getenv("FIVETRAN_CONFIGURATION", None)
        if env_configuration:
            print_library_log(
                "reading configuration from FIVETRAN_CONFIGURATION environment variable",
                Logging.Level.INFO,
                log_icon=Logging.LogIcon.INFO,
            )
            configuration = env_configuration
        else:
            json_filepath = os.path.join(args.project_path, CONFIGURATION_JSON)
            if os.path.exists(json_filepath):
                print_library_log(
                    "reading configuration from configuration.json found in project folder",
                    Logging.Level.INFO,
                    log_icon=Logging.LogIcon.INFO,
                )
                configuration = CONFIGURATION_JSON
            else:
                print_library_log("no configuration provided", Logging.Level.INFO)
                return None, None

    try:
        config_values = validate_and_load_configuration(args.project_path, configuration)
        return config_values, configuration
    except ValueError as e:
        print_library_log(
            f"invalid configuration error: {e}",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        sys.exit(1)


def check_newer_version(version: str):
    """Periodically checks for a newer version of the SDK and notifies the user if one is available."""
    try:
        config_root_dir = config_root_dir_helper()
        last_check_file_path = os.path.join(config_root_dir, LAST_VERSION_CHECK_FILE)
        if not os.path.isdir(config_root_dir):
            os.makedirs(config_root_dir, exist_ok=True)

        if os.path.isfile(last_check_file_path):
            # Is it time to check again?
            with open(last_check_file_path, "r", encoding=UTF_8) as f_in:
                timestamp = int(f_in.read())
                if (int(time.time()) - timestamp) < SIX_HOUR_IN_SEC:
                    return

        for index in range(MAX_RETRIES):
            try:
                # check version and save current time
                response = rq.get(PYPI_PACKAGE_DETAILS_URL, timeout=10)
                response.raise_for_status()
                data = json.loads(response.text)
                latest_version = data["info"]["version"]
                if tuple(int(x) for x in version.split(".")) < tuple(
                    int(x) for x in latest_version.split(".")
                ):
                    print_library_log(
                        f"fivetran-connector-sdk {latest_version} is available. (a newer release exists)",
                        log_icon=Logging.LogIcon.LIGHTNING,
                        level=Logging.Level.WARNING,
                    )
                    print_library_log(
                        "run 'pip install --upgrade fivetran-connector-sdk' to update",
                        log_icon=Logging.LogIcon.LIGHTNING,
                        level=Logging.Level.WARNING,
                    )

                with open(last_check_file_path, "w", encoding=UTF_8) as f_out:
                    f_out.write(f"{int(time.time())}")
                break
            except Exception:
                retry_after = 2**index
                print_library_log(
                    "unable to check for a newer version of `fivetran-connector-sdk`",
                    Logging.Level.WARNING,
                )
                print_library_log(f"retrying after {retry_after} seconds", Logging.Level.WARNING)
                time.sleep(retry_after)
    except Exception:
        # version check is advisory; never abort commands due to unexpected error
        pass


def config_root_dir_helper() -> str:
    """Returns the root directory for connector_sdk-wide (non-tester) local state, e.g. `~/.fivetran/connector_sdk`."""
    return os.path.join(os.path.expanduser("~"), ROOT_LOCATION)


def tester_root_dir_helper() -> str:
    """Returns the root directory for the tester, nested under the connector_sdk config root."""
    return os.path.join(config_root_dir_helper(), TESTER_LOCATION)


def _warn_exit_usage(filename, line_no, func):
    print_library_log(
        f"avoid using {func} to exit from python code\nthis may cause the connector to hang\nraise an error instead at: {filename}:{line_no}\nreference: https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-logs#exceptionhandling",
        Logging.Level.WARNING,
    )


def _check_and_warn_attribute_exit(node):
    """Checks for the presence of 'exit()' in the AST node and warns if found."""
    if isinstance(node.func, ast.Name) and node.func.id == "exit":
        _warn_exit_usage(ROOT_FILENAME, node.lineno, "exit()")
    elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        if node.func.attr == "_exit" and node.func.value.id == "os":
            _warn_exit_usage(ROOT_FILENAME, node.lineno, "os._exit()")
        if node.func.attr == "exit" and node.func.value.id == "sys":
            _warn_exit_usage(ROOT_FILENAME, node.lineno, "sys.exit()")


def exit_check(project_path):
    """Checks for the presence of 'exit()' in the calling code.
    Args:
        project_path: The absolute project_path to check exit in the connector.py file in the project.
    """
    # We expect the connector.py to catch errors or throw exceptions
    # This is a warning shown to let the customer know that we expect either the yield call or error thrown
    # exit() or sys.exit() in between some yields can cause the connector to be stuck without processing further upsert calls

    filepath = os.path.join(project_path, ROOT_FILENAME)
    with open(filepath, "r", encoding=UTF_8) as f:
        try:
            tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    _check_and_warn_attribute_exit(node)
        except SyntaxError as e:
            print_library_log(f"SyntaxError in {ROOT_FILENAME}: {e}", Logging.Level.SEVERE)


def check_dict(incoming: dict, string_only: bool = False, exempt_keys: set = None) -> dict:
    """Validates the incoming dictionary.
    Args:
        incoming (dict): The dictionary to validate.
        string_only (bool): Whether to allow only string values.
        exempt_keys (set): Keys whose values are exempt from the string-only check. Used for proxy
            host key that may hold a list of endpoints instead of a plain string.

    Returns:
        dict: The validated dictionary.
    """

    if not incoming:
        return {}

    if not isinstance(incoming, dict):
        raise ValueError(
            "invalid configuration file; must be a valid JSON object\nreference: https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json#workingwithconfigurationjson"
        )

    if string_only:
        exempt = exempt_keys or set()
        for k, v in incoming.items():
            if k in exempt:
                if not isinstance(v, (str, list)):
                    print_library_log(
                        f"invalid configuration file; value for '{k}' must be a string or a list of strings\nreference: https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json#workingwithconfigurationjson",
                        Logging.Level.SEVERE,
                    )
                    sys.exit(1)
            elif not isinstance(v, str):
                print_library_log(
                    "invalid configuration file; all values must be strings\nreference: https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json#workingwithconfigurationjson",
                    Logging.Level.SEVERE,
                )
                sys.exit(1)

    return incoming


def _fail_proxy_validation(message):
    print_library_log(message, Logging.Level.SEVERE)
    sys.exit(1)


def _resolve_proxy_host_key(configuration, proxy_host_config_key):
    proxy_host_key = proxy_host_config_key.strip()
    if proxy_host_key not in configuration:
        return _fail_proxy_validation(
            "The specified --proxy-host-config-key does not exist in configuration.json."
        )
    return proxy_host_key


def _detect_default_proxy_host_key(configuration):
    for key in ("host", "hosts"):
        if key in configuration:
            return key
    return _fail_proxy_validation(
        "Unable to determine the endpoint to proxy. "
        "Please specify the configuration key containing the host details using --proxy-host-config-key "
        "or add a 'host' or 'hosts' entry in configuration.json."
    )


def validate_proxy_configuration(configuration, proxy_id, proxy_host_config_key, hd_agent_id=None):
    """Validates deploy-time proxy configuration and resolves the proxy host config key.

    Args:
        configuration (dict): Parsed configuration.json contents.
        proxy_id (str): Proxy Agent ID supplied via --proxy-id.
        proxy_host_config_key (str): Optional key whose value holds host:port details.
        hd_agent_id (str): Optional Hybrid Deployment Agent ID; incompatible with proxy_id.

    Returns:
        str | None: The resolved proxy host key when proxying is enabled, otherwise None.
    """
    if proxy_id and hd_agent_id:
        return _fail_proxy_validation(
            "Proxy Agent is not supported in Hybrid Deployment connections."
        )

    if not proxy_id:
        if proxy_host_config_key:
            return _fail_proxy_validation(
                "--proxy-host-config-key is only supported when --proxy-id is provided."
            )
        return None

    if proxy_host_config_key:
        return _resolve_proxy_host_key(configuration, proxy_host_config_key)

    return _detect_default_proxy_host_key(configuration)


def is_connection_name_valid(connection: str):
    """Validates if the incoming connection schema name is valid or not.
    Args:
        connection (str): The connection schema name being validated.

    Returns:
        bool: True if connection name is valid.
    """

    pattern = re.compile(CONNECTION_SCHEMA_NAME_PATTERN)
    return pattern.match(connection)


def is_port_in_use(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_available_port():
    for port in range(50049, 50061):
        if not is_port_in_use(port):
            return port
    return None


def update_base_url_if_required():
    config_file_path = os.path.join(config_root_dir_helper(), CONFIG_FILE)
    if os.path.isfile(config_file_path):
        with open(config_file_path, "r", encoding=UTF_8) as f:
            data = json.load(f)
            base_url = data.get("production_base_url")
            if base_url is not None:
                constants.PRODUCTION_BASE_URL = base_url
                print_library_log(
                    f"using custom production url: {base_url}", log_icon=Logging.LogIcon.INFO
                )


def fetch_requirements_from_file(file_path: str) -> list[str]:
    """Reads the requirements file and returns a list of dependencies.

    Args:
        file_path (str): The path to the requirements file.

    Returns:
        list[str]: A list of dependencies as strings.
    """
    with open(file_path, "r", encoding=UTF_8) as f:
        return f.read().splitlines()


def fetch_requirements_as_dict(file_path: str) -> dict:
    """Converts a list of dependencies from the requirements file into a dictionary.

    Args:
        file_path (str): The path to the requirements file.

    Returns:
        dict: A dictionary where keys are package names (lowercase) and
        values are the full dependency strings.
    """
    requirements_dict = {}
    if not os.path.exists(file_path):
        return requirements_dict
    for requirement in fetch_requirements_from_file(file_path):
        requirement = requirement.strip()
        if not requirement or requirement.startswith("#"):  # Skip empty lines and comments
            continue
        try:
            key = re.split(r"==|>=|<=|>|<", requirement)[0]
            requirements_dict[key.lower().replace("-", "_")] = requirement.lower()
        except ValueError:
            print_library_log(f"Invalid requirement format: '{requirement}'", Logging.Level.SEVERE)
    return requirements_dict


def validate_requirements_file(
    project_path: str,
    is_deploy: bool,
    version: str,
    prompt_mode: PromptMode = PromptMode.INTERACTIVE,
):
    """Validates the `requirements.txt` file against the project's actual dependencies.

    This method generates a temporary requirements file using `pipreqs`, compares
    it with the existing `requirements.txt`, and checks for version mismatches,
    missing dependencies, and unused dependencies. It will issue warnings, errors,
    or even terminate the process depending on whether it's being run for deployment.

    Args:
        project_path (str): The path to the project directory containing the `requirements.txt`.
        is_deploy (bool): If `True`, the method will exit the process on critical errors.
        version (str): The current version of the connector.
        prompt_mode (PromptMode): Controls how prompts are answered. Defaults to INTERACTIVE.

    """
    requirements_file_path = os.path.join(project_path, REQUIREMENTS_TXT)
    requirements_file_exists = os.path.exists(requirements_file_path)
    requirements = load_or_add_requirements_file(requirements_file_path)

    # copying packages of requirements file to tmp file to handle pipreqs fail use-case
    tmp_requirements_file_path = os.path.join(project_path, "tmp_requirements.txt")
    copy_requirements_file_to_tmp_requirements_file(
        requirements_file_path, tmp_requirements_file_path
    )

    # Run the pipreqs command and capture stderr
    try:
        run_pipreqs_with_retries(is_deploy, project_path, tmp_requirements_file_path)
        tmp_requirements = fetch_requirements_as_dict(tmp_requirements_file_path)
        remove_unwanted_packages(tmp_requirements)
    finally:
        delete_file_if_exists(tmp_requirements_file_path)

    # remove corrupt requirements listed by pipreqs
    corrupt_requirements = [key for key in tmp_requirements if key.startswith("~")]
    for requirement in corrupt_requirements:
        del tmp_requirements[requirement]

    if not requirements_file_exists:
        if not tmp_requirements:
            delete_file_if_exists(requirements_file_path)
            return
        else:
            print_library_log(
                "`requirements.txt` file not found in your project folder", Logging.Level.WARNING
            )

    update_version_requirements = verify_version_mismatch_deps(
        is_deploy, requirements, tmp_requirements, prompt_mode
    )
    update_missing_requirements = verify_missing_deps(
        is_deploy, requirements, tmp_requirements, prompt_mode
    )
    log_unused_deps_if_present(is_deploy, requirements, tmp_requirements)

    if update_version_requirements or update_missing_requirements:
        with open(requirements_file_path, "w", encoding=UTF_8) as file:
            file.write("\n".join(requirements.values()))
            print_library_log(f"`{REQUIREMENTS_TXT}` has been updated successfully.")
    elif not requirements:
        delete_file_if_exists(requirements_file_path)

    if is_deploy:
        print_library_log(f"Validation of {REQUIREMENTS_TXT} completed.")


def log_unused_deps_if_present(
    is_deploy, requirements, tmp_requirements, file_name=REQUIREMENTS_TXT
):

    unused_deps = list(
        requirements.keys()
        - tmp_requirements.keys()
        - {"fivetran_connector_sdk", "fivetran-connector-sdk", "requests"}
    )
    if not unused_deps:
        return

    log_unused_deps(unused_deps, is_deploy, file_name)


def verify_missing_deps(
    is_deploy, requirements, tmp_requirements, prompt_mode: PromptMode = PromptMode.INTERACTIVE
):
    missing_deps = {
        key: tmp_requirements[key] for key in (tmp_requirements.keys() - requirements.keys())
    }
    if not missing_deps:
        return False

    handle_missing_deps(missing_deps, is_deploy)
    if not is_deploy:
        return False

    if resolve_confirmation(
        f"Would you like us to update {REQUIREMENTS_TXT} to add missing dependent libraries? (y/N): ",
        default=False,
        prompt_mode=prompt_mode,
    ):
        for requirement in missing_deps:
            requirements[requirement] = tmp_requirements[requirement]
        print_library_log(f"Successfully added missing dependencies to {REQUIREMENTS_TXT}.")
        return True
    print_library_log(
        f"Changes identified as missing dependencies for libraries have been ignored. These changes have NOT been made to {REQUIREMENTS_TXT}."
    )
    return False


def verify_version_mismatch_deps(
    is_deploy, requirements, tmp_requirements, prompt_mode: PromptMode = PromptMode.INTERACTIVE
):
    version_mismatch_deps = {
        key: tmp_requirements[key]
        for key in (requirements.keys() & tmp_requirements.keys())
        if requirements[key] != tmp_requirements[key]
    }
    if not version_mismatch_deps:
        return False
    if not is_deploy:
        print_library_log(RECOMMEND_STABLE_VERSION_MESSAGE, Logging.Level.INFO)
        print(version_mismatch_deps)
        return False

    print_library_log(RECOMMEND_STABLE_VERSION_MESSAGE, Logging.Level.WARNING)
    print(version_mismatch_deps)
    if resolve_confirmation(
        f"Would you like us to update {REQUIREMENTS_TXT} to the current stable versions of the dependent libraries? (y/N): ",
        default=False,
        prompt_mode=prompt_mode,
    ):
        for requirement in version_mismatch_deps:
            requirements[requirement] = tmp_requirements[requirement]
        print_library_log(
            f"Successfully updated {REQUIREMENTS_TXT} to the current stable versions of the dependent libraries."
        )
        return True
    print_library_log(
        f"Changes identified for libraries with version conflicts have been ignored. These changes have NOT been made to {REQUIREMENTS_TXT}."
    )
    return False


def run_pipreqs_with_retries(is_deploy, project_path, tmp_requirements_file_path):
    # Detect and exclude virtual environment directories
    venv_dirs = [
        name
        for name in os.listdir(project_path)
        if os.path.isdir(os.path.join(project_path, name))
        and VIRTUAL_ENV_CONFIG in os.listdir(os.path.join(project_path, name))
    ]

    ignored_dirs = EXCLUDED_PIPREQS_DIRS + venv_dirs if venv_dirs else EXCLUDED_PIPREQS_DIRS

    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        result = subprocess.run(
            [
                "pipreqs",
                project_path,
                "--savepath",
                tmp_requirements_file_path,
                "--ignore",
                ",".join(ignored_dirs),
            ],
            stderr=subprocess.PIPE,
            text=True,  # Ensures output is in string format
        )

        if result.returncode == 0:
            break

        print_library_log(f"attempt {attempt}: pipreqs check failed", Logging.Level.WARNING)

        if attempt < MAX_RETRIES:
            retry_after = 3**attempt
            print_library_log(f"retrying after {retry_after} seconds", Logging.Level.WARNING)
            time.sleep(retry_after)
        else:
            print_library_log(f"pipreqs failed after {MAX_RETRIES} attempts", Logging.Level.SEVERE)
            if result.stderr:
                print_library_log(
                    f"pipreqs failed with error: {result.stderr.strip()}", Logging.Level.SEVERE
                )
            print_library_log(
                f"skipping requirements.txt validation; continuing with {'deploy' if is_deploy else 'debug'}",
                Logging.Level.WARNING,
            )


def log_unused_deps(unused_deps, is_deploy, file_name=REQUIREMENTS_TXT):
    level = Logging.Level.WARNING if is_deploy else Logging.Level.INFO
    print_library_log(
        "The following dependencies are not needed, "
        f"they are already installed or not in use. Remove them from {file_name}:\n"
        + " ".join(unused_deps),
        level,
    )


def handle_missing_deps(missing_deps, is_deploy, file_name=REQUIREMENTS_TXT):
    level = Logging.Level.SEVERE if is_deploy else Logging.Level.INFO
    print_library_log(
        f"Include the following dependency libraries in {file_name}, to be used by "
        "Fivetran production. "
        "For more information, see our docs: "
        "https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/project-dependencies\n"
        + " ".join(list(missing_deps.values())),
        level,
    )


def load_or_add_requirements_file(requirements_file_path):
    if os.path.exists(requirements_file_path):
        requirements = fetch_requirements_as_dict(requirements_file_path)
    else:
        with open(requirements_file_path, "w", encoding=UTF_8):
            # Intentional empty block: Creating an empty requirements.txt file
            pass
        requirements = {}
    return requirements


def copy_requirements_file_to_tmp_requirements_file(
    requirements_file_path: str, tmp_requirements_file_path
):
    if os.path.exists(requirements_file_path):
        requirements_file_content = fetch_requirements_from_file(requirements_file_path)
        with open(tmp_requirements_file_path, "w") as file:
            file.write("\n".join(requirements_file_content))


def remove_unwanted_packages(requirements: dict):
    # remove the `fivetran_connector_sdk` and `requests` packages from requirements as we already pre-installed them.
    if requirements.get("fivetran_connector_sdk") is not None:
        requirements.pop("fivetran_connector_sdk")
    if requirements.get("requests") is not None:
        requirements.pop("requests")


def parse_pyproject_dependencies(pyproject_path: str) -> dict:
    """Parse [project.dependencies] from pyproject.toml into the same dict format
    as fetch_requirements_as_dict returns: {normalized_name: full_spec_string}.

    Requires Python 3.11+ (tomllib stdlib). Caller must check version before calling.

    Args:
        pyproject_path (str): Path to the pyproject.toml file.

    Returns:
        dict: {normalized_name: full_spec_string} or empty dict if parsing fails.
    """
    try:
        import tomllib

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        print_library_log(f"failed to parse {PYPROJECT_TOML}", Logging.Level.SEVERE)
        sys.exit(1)

    deps = data.get("project", {}).get("dependencies", [])
    result = {}
    for dep in deps:
        # Split on first PEP 508 delimiter: version operators, extras ([), whitespace,
        # @ (URL refs: pkg @ https://...), ; (markers: pkg; python_version < "3.10")
        name = re.split(r"[\s><=!~\[@;]", dep)[0].strip()
        key = name.lower().replace("-", "_")
        result[key] = dep.strip().lower()
    return result


def validate_pyproject_file(
    project_path: str, is_deploy: bool, prompt_mode: PromptMode = PromptMode.INTERACTIVE
):
    """Validates the `pyproject.toml` file against the project's actual dependencies.

    This method generates a temporary requirements file using `pipreqs`, compares
    it with the dependencies declared in `pyproject.toml`, and checks for version
    mismatches, missing dependencies, and unused dependencies. On deploy/package,
    surfaces `(Y/n)` prompts for version mismatches and missing dependencies —
    default `Y` continues, `n` aborts. Unused dependencies are logged without a
    prompt. The `pyproject.toml` file is never edited; users must fix issues manually.

    Skips validation on Python < 3.11 (`tomllib` not available).

    Args:
        project_path (str): The path to the project directory containing the `pyproject.toml`.
        is_deploy (bool): If `True`, use SEVERE/WARNING levels and prompt per issue category.
        prompt_mode (PromptMode): Controls how prompts are answered. Defaults to INTERACTIVE.
    """
    if sys.version_info < (3, 11):
        print_library_log(PYPROJECT_SKIP_VALIDATION_MESSAGE)
        return

    pyproject_path = os.path.join(project_path, PYPROJECT_TOML)
    requirements = parse_pyproject_dependencies(pyproject_path)

    # copying packages of pyproject.toml to tmp file
    tmp_requirements_file_path = os.path.join(project_path, "tmp_requirements.txt")
    with open(tmp_requirements_file_path, "w", encoding=UTF_8) as f:
        f.write("\n".join(requirements.values()))

    # Run the pipreqs command and capture stderr
    try:
        run_pipreqs_with_retries(is_deploy, project_path, tmp_requirements_file_path)
        tmp_requirements = fetch_requirements_as_dict(tmp_requirements_file_path)
        remove_unwanted_packages(tmp_requirements)
    finally:
        delete_file_if_exists(tmp_requirements_file_path)

    # remove corrupt requirements listed by pipreqs
    corrupt_requirements = [key for key in tmp_requirements if key.startswith("~")]
    for requirement in corrupt_requirements:
        del tmp_requirements[requirement]

    verify_pyproject_version_mismatch_deps(is_deploy, requirements, tmp_requirements, prompt_mode)
    verify_pyproject_missing_deps(is_deploy, requirements, tmp_requirements, prompt_mode)
    log_unused_deps_if_present(is_deploy, requirements, tmp_requirements, PYPROJECT_TOML)

    if is_deploy:
        print_library_log(f"Validation of {PYPROJECT_TOML} completed.")


def verify_pyproject_missing_deps(
    is_deploy, requirements, tmp_requirements, prompt_mode: PromptMode = PromptMode.INTERACTIVE
):
    missing_deps = {
        key: tmp_requirements[key] for key in (tmp_requirements.keys() - requirements.keys())
    }
    if not missing_deps:
        return

    handle_missing_deps(missing_deps, is_deploy, PYPROJECT_TOML)
    if not is_deploy:
        return

    prompt_pyproject_continue_or_abort(
        f"Some libraries are imported but not declared in {PYPROJECT_TOML}. Continue? (Y/n):",
        prompt_mode,
    )


def verify_pyproject_version_mismatch_deps(
    is_deploy, requirements, tmp_requirements, prompt_mode: PromptMode = PromptMode.INTERACTIVE
):
    version_mismatch_deps = {
        key: tmp_requirements[key]
        for key in (requirements.keys() & tmp_requirements.keys())
        if requirements[key] != tmp_requirements[key]
    }
    if not version_mismatch_deps:
        return

    level = Logging.Level.WARNING if is_deploy else Logging.Level.INFO
    print_library_log(RECOMMEND_STABLE_VERSION_MESSAGE, level)
    print(version_mismatch_deps)
    if not is_deploy:
        return

    prompt_pyproject_continue_or_abort(
        f"Some libraries in {PYPROJECT_TOML} are not at the current stable version. Continue? (Y/n):",
        prompt_mode,
    )


def prompt_pyproject_continue_or_abort(
    prompt_message: str, prompt_mode: PromptMode = PromptMode.INTERACTIVE
):
    """Prompts the user to continue (default Y) or abort (n).

    Pressing Enter or any input other than `n`/`N` continues. Only an explicit
    `n`/`N` aborts the process. The pyproject.toml file is never edited.

    Args:
        prompt_message (str): The full prompt text to display, including the (Y/n) suffix.
        prompt_mode (PromptMode): Controls how prompts are answered. Defaults to INTERACTIVE.
    """
    if not resolve_confirmation(prompt_message, default=True, prompt_mode=prompt_mode):
        print_library_log(f"Aborting. Fix {PYPROJECT_TOML} and try again.", Logging.Level.SEVERE)
        sys.exit(1)


def package_project(
    project_path: str, deploy_key: str, configuration_form_method: Optional[Callable] = None
) -> str:
    """Packages the project for deployment.

    Args:
        project_path (str): The path to the project directory.
        deploy_key (str): The deployment key.
        configuration_form_method: Optional callable returning a ConfigurationForm instance.

    Returns:
        str: The uploaded package ID.
    """
    # Create a new package for both new and existing connections.
    package_file_path = create_package(project_path, configuration_form_method)
    try:
        uploaded_package_id = upload_package(
            package_file_path,
            deploy_key,
        )
        if not uploaded_package_id:
            sys.exit(1)
        print_library_log(f"package id: {uploaded_package_id}", indent=True)
        return uploaded_package_id
    finally:
        delete_file_if_exists(package_file_path)
        # Clean up the auto-created files/ dir if deploy left it empty so user
        # content (e.g. state.json from prior debug runs) is preserved.
        remove_dir_if_empty(os.path.join(project_path, OUTPUT_FILES_DIR))


def cleanup_uploaded_project(deploy_key: str, package_id: str):
    """Cleans up an orphaned package when connection creation fails.

    Args:
        deploy_key (str): The deployment key.
        package_id (str): The package ID to delete.
    """
    cleanup_result = cleanup_uploaded_code(deploy_key, package_id)
    if not cleanup_result:
        sys.exit(1)


def log_connection_success(
    response: rq.Response, is_new_connection: bool, connection_id: Optional[str]
) -> None:
    """Logs connection creation or update success details.

    Args:
        response: The successful HTTP response from the API.
        is_new_connection: True if creating a new connection, False if updating.
        connection_id: The connection ID (provided for updates, extracted for creates).
    """
    data = response.json()["data"]
    # Extract connection_id from response if not provided (create case)
    conn_id = connection_id if connection_id else data["id"]
    # Determine operation text and dashboard action based on flag
    operation = "created" if is_new_connection else "updated"
    dashboard_action = (
        "to start the initial sync" if is_new_connection else "to manage the connection"
    )
    print_library_log(f"connection {operation}", log_icon=Logging.LogIcon.SUCCESS)
    print_library_log(f"connection id: {conn_id}", indent=True)
    print_library_log(
        f"runtime python version: {data['config']['python_version']}",
        level=Logging.Level.INFO,
        indent=True,
    )
    print_library_log(
        f"naming strategy: {data['destination_schema_names']}",
        level=Logging.Level.INFO,
        indent=True,
    )
    print_library_log(f"visit the Fivetran dashboard {dashboard_action}:")
    print_library_log(f"https://fivetran.com/dashboard/connections/{conn_id}/status")


def handle_connection_response(
    response: rq.Response,
    package_id: str,
    deploy_key: str,
    expected_status: int,
    is_new_connection: bool,
    connection_id: Optional[str] = None,
) -> None:
    """Common handler for create/update connection responses.

    Args:
        response: The HTTP response from create/update connection API call.
        package_id: The package ID to cleanup if operation fails.
        deploy_key: The deployment key for cleanup operations.
        expected_status: The expected HTTP status code for success (e.g., 200 or 201).
        is_new_connection: True if creating a new connection, False if updating existing.
        connection_id: The connection ID (required for update, extracted from response for create).
    """
    if response.ok and response.status_code == expected_status:
        if are_setup_tests_failing(response):
            operation = "created" if is_new_connection else "updated"
            handle_failing_tests_message_and_exit(
                response, f"connection {operation} but setup tests failed"
            )
        else:
            log_connection_success(response, is_new_connection, connection_id)
    else:
        action = "create" if is_new_connection else "update"
        print_library_log(
            f"failed to {action} connection error: {response.json()['message']}",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        cleanup_uploaded_project(deploy_key, package_id)
        sys.exit(1)


def update_connection(
    id: str,
    name: str,
    group: str,
    config: dict,
    package_id: str,
    deploy_key: str,
    hd_agent_id: str,
    proxy_agent_id: str = None,
):
    """Updates the connection with the given ID, name, group, configuration, and deployment key.

    Args:
        id (str): The connection ID.
        name (str): The connection name.
        group (str): The group name.
        config (dict): The configuration dictionary.
        package_id (str): The package ID.
        deploy_key (str): The deployment key.
        hd_agent_id (str): The hybrid deployment agent ID within the Fivetran system.
        proxy_agent_id (str): The Proxy Agent ID. Pass None to clear an existing proxy association.

    Returns:
        rq.Response: The response object.
    """
    if not config.get("secrets_list"):
        del config["secrets_list"]

    config["package_id"] = package_id
    json_payload = {
        "config": config,
        "run_setup_tests": True,
        "proxy_agent_id": proxy_agent_id,
    }

    # hybrid_deployment_agent_id is optional when redeploying your connection.
    # Customer can use it to change existing hybrid_deployment_agent_id.
    if hd_agent_id:
        json_payload["hybrid_deployment_agent_id"] = hd_agent_id
    if proxy_agent_id:
        json_payload["networking_method"] = NetworkingMethod.PROXY_AGENT.value
    else:
        json_payload["networking_method"] = NetworkingMethod.DIRECTLY.value
        # Clear any stale proxy_host_config_key on the server so the connection
        # fully reverts to direct networking.
        config["proxy_host_config_key"] = None

    log_setup_tests_running()
    response = rq.patch(
        f"{constants.PRODUCTION_BASE_URL}/v1/connectors/{id}",
        headers={"Authorization": f"Basic {deploy_key}", "User-Agent": get_user_agent()},
        json=json_payload,
    )

    return response


def handle_failing_tests_message_and_exit(resp, log_message):
    print_library_log(log_message, Logging.Level.SEVERE)
    print_failing_setup_tests(resp)
    connection_id = resp.json().get("data", {}).get("id")
    print_library_log(f"connection id: {connection_id}")
    sys.exit(1)


def are_setup_tests_failing(response) -> bool:
    """Checks for failed setup tests in the response and returns True if any test has failed, otherwise False."""
    response_json = response.json()
    setup_tests = response_json.get("data", {}).get("setup_tests", [])

    # Return True if any test has "FAILED" status, otherwise False
    return any(
        test.get("status") == "FAILED" or test.get("status") == "JOB_FAILED"
        for test in setup_tests
    )


def print_failing_setup_tests(response):
    """Checks for failed setup tests in the response and print errors."""
    response_json = response.json()
    setup_tests = response_json.get("data", {}).get("setup_tests", [])

    # Collect failed setup tests
    failed_tests = [
        test
        for test in setup_tests
        if test.get("status") == "FAILED" or test.get("status") == "JOB_FAILED"
    ]

    if failed_tests:
        print_library_log(
            "failed setup tests:", level=Logging.Level.WARNING, log_icon=Logging.LogIcon.FAILURE
        )
        for test in failed_tests:
            print_library_log(
                f"test: {test.get('title')}", level=Logging.Level.WARNING, indent=True
            )
            print_library_log(
                f"status: {test.get('status')}", level=Logging.Level.WARNING, indent=True
            )
            print_library_log(
                f"message: {test.get('message')}", level=Logging.Level.WARNING, indent=True
            )


def get_connection_details(
    name: str, group: str, group_id: str, deploy_key: str
) -> Optional[Tuple[str, str]]:
    """Retrieves the connection ID for the specified connection schema name, group, and deployment key.

    Args:
        name (str): The connection name.
        group (str): The group name.
        group_id (str): The group ID.
        deploy_key (str): The deployment key.

    Returns:
        Optional[Tuple[str, str]]: A tuple of (connection_id, service_type) if found, None otherwise.
    """
    resp = rq.get(
        f"{constants.PRODUCTION_BASE_URL}/v1/groups/{group_id}/connectors",
        headers={"Authorization": f"Basic {deploy_key}", "User-Agent": get_user_agent()},
        params={"schema": name},
    )
    if not resp.ok:
        print_library_log(
            f"failed to list connections for destination '{group}'",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        sys.exit(1)

    if resp.json()["data"]["items"]:
        return resp.json()["data"]["items"][0]["id"], resp.json()["data"]["items"][0]["service"]

    return None


def create_connection(
    deploy_key: str,
    group_id: str,
    config: dict,
    hd_agent_id: str,
    package_id: str,
    naming: str,
    proxy_agent_id: str = None,
) -> rq.Response:
    """Creates a new connection with the given deployment key, group ID, and configuration.

    Args:
        deploy_key (str): The deployment key.
        group_id (str): The group ID.
        config (dict): The configuration dictionary.
        hd_agent_id (str): The hybrid deployment agent ID within the Fivetran system.
        package_id (str): The package ID.
        naming (str): The formatted naming strategy (e.g., "FIVETRAN_NAMING" or "SOURCE_NAMING").
        proxy_agent_id (str): The Proxy Agent ID used for proxy routing.

    Returns:
        rq.Response: The response object.
    """
    print_library_log("creating connection", log_icon=Logging.LogIcon.STEP)
    config["package_id"] = package_id
    log_setup_tests_running()
    json_payload = {
        "group_id": group_id,
        "service": "connector_sdk",
        "config": config,
        "paused": True,
        "run_setup_tests": True,
        "sync_frequency": "360",
        "destination_schema_names": naming or (FIVETRAN_NAMING_VALUE + UNDERSCORE_NAMING),
        "hybrid_deployment_agent_id": hd_agent_id,
    }
    if proxy_agent_id:
        json_payload["proxy_agent_id"] = proxy_agent_id
        json_payload["networking_method"] = NetworkingMethod.PROXY_AGENT.value

    response = rq.post(
        f"{constants.PRODUCTION_BASE_URL}/v1/connectors",
        headers={"Authorization": f"Basic {deploy_key}", "User-Agent": get_user_agent()},
        json=json_payload,
    )
    return response


def create_package(project_path: str, configuration_form_method: Optional[Callable] = None) -> str:
    """Creates a package file for the given project path.

    Args:
        project_path (str): The path to the project directory.
        configuration_form_method: Optional callable returning a ConfigurationForm instance.

    Returns:
        str: The path to the packaged zip file.
    """
    print_library_log("packaging project for upload", log_icon=Logging.LogIcon.STEP)
    extra_files = _generate_configuration_form_bytes(configuration_form_method)
    zip_file_path = zip_folder(project_path, extra_files=extra_files)
    print_library_log("project packaged for upload", log_icon=Logging.LogIcon.SUCCESS)
    return zip_file_path


def _generate_configuration_form_bytes(
    configuration_form_method: Optional[Callable] = None,
) -> dict:
    """Generates the serialized ConfigurationFormResponse bytes for bundling into the package.

    Returns a dict of {filename: bytes} to be written into the zip, with an empty
    file sentinel if no configuration_form is defined.

    Args:
        configuration_form_method: Optional callable returning a ConfigurationForm instance.

    Returns:
        dict: {CONFIGURATION_FORM_FILENAME: bytes}.
    """
    if not configuration_form_method:
        return {CONFIGURATION_FORM_FILENAME: b""}
    if Logging.LOG_LEVEL is None:
        Logging.LOG_LEVEL = Logging.Level.INFO
    try:
        return {
            CONFIGURATION_FORM_FILENAME: configuration_form_method()
            ._to_proto()
            .SerializeToString()
        }
    except Exception as e:
        print_library_log(
            f"failed to package configuration form response: {e}", Logging.Level.SEVERE
        )
        sys.exit(1)


def load_gitignore(directory_path: str) -> list[str]:
    """Load pattern lines from a .gitignore file in the specified directory.

    Follows gitignore conventions:
    - Blank lines are ignored
    - Lines starting with # are treated as comments and ignored
    - Leading and trailing whitespace is stripped from patterns

    Args:
        directory_path (str): The directory path to check for .gitignore file.

    Returns:
        list[str]: A list of non-empty, non-comment pattern strings from the .gitignore file.
                   Returns an empty list if the file doesn't exist or cannot be read
                   (OSError is logged as a warning).
    """
    gitignore_path = os.path.join(directory_path, constants.GITIGNORE_FILENAME)
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, "r", encoding=constants.UTF_8) as file:
                patterns = []
                for line in file:
                    # Strip leading/trailing whitespace
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith("#"):
                        patterns.append(line)
                print_library_log(f"loaded .gitignore with {len(patterns)} patterns")
                return patterns
        except OSError as e:
            print_library_log(
                f"failed to read .gitignore at {gitignore_path}: {e}",
                level=Logging.Level.WARNING,
                log_icon=Logging.LogIcon.FAILURE,
            )
            print_library_log("using empty ignore patterns", Logging.Level.WARNING)
            return []
    return []


def get_default_ignore_patterns() -> list[str]:
    """Get default exclusion pattern strings for backwards compatibility.

    These patterns replicate the hardcoded exclusions from the original implementation.

    Returns:
        list[str]: A list of default ignore pattern strings.
    """
    # Convert EXCLUDED_DIRS to pathspec patterns with trailing slashes for directory matching
    default_patterns = [directory + "/" for directory in EXCLUDED_DIRS]
    # Add pattern to exclude hidden files and directories (starting with .)
    default_patterns.append(".*")
    # Exclude configuration.json
    default_patterns.append(CONFIGURATION_JSON)
    return default_patterns


def normalize_path_for_matching(path: str) -> str:
    """Normalize path to POSIX-style for cross-platform pattern matching.

    Converts backslashes to forward slashes to ensure .gitignore patterns
    (which use gitwildmatch/POSIX syntax) work correctly on Windows.

    Args:
        path (str): Path with platform-specific separators

    Returns:
        str: Path with forward slashes (POSIX-style)
    """
    # Replace Windows backslashes with forward slashes
    # This is a no-op on Unix systems where os.sep is already '/'
    if os.sep != "/":
        return path.replace(os.sep, "/")
    return path


def transform_gitignore_patterns(patterns: list[str], directory_rel_path: str) -> list[str]:
    """Transform .gitignore patterns to be relative to project root.

    Patterns in nested .gitignore files are relative to their containing directory.
    This function transforms them to be relative to the project root for correct
    hierarchical pattern matching, following gitignore semantics.

    Args:
        patterns: Pattern strings from a .gitignore file
        directory_rel_path: Relative path from project root to the directory containing the .gitignore
                           (must use forward slashes - call normalize_path_for_matching first)

    Returns:
        Transformed patterns relative to project root

    Examples:
        >>> transform_gitignore_patterns(['/secret.py'], 'src')
        ['src/secret.py']  # Anchored pattern becomes relative to src/

        >>> transform_gitignore_patterns(['*.log'], 'src')
        ['src/**/*.log']  # Unanchored pattern matches recursively under src/

        >>> transform_gitignore_patterns(['!/important.log'], 'src')
        ['!src/important.log']  # Negation with anchored pattern
    """
    if not directory_rel_path or directory_rel_path == ".":
        # At project root, no transformation needed
        return patterns

    transformed = []
    for pattern in patterns:
        if not pattern:
            continue

        # Handle negation patterns
        is_negation = pattern.startswith("!")
        if is_negation:
            pattern = pattern[1:]  # Remove '!' temporarily

        # Transform based on pattern type
        if pattern.startswith("/"):
            # Anchored pattern: /foo -> dirpath/foo
            # Matches only direct children of the directory
            transformed_pattern = f"{directory_rel_path}/{pattern[1:]}"
        else:
            # Unanchored pattern: foo -> dirpath/**/foo
            # Matches anywhere recursively under the directory
            transformed_pattern = f"{directory_rel_path}/**/{pattern}"

        # Re-add negation if present
        if is_negation:
            transformed_pattern = f"!{transformed_pattern}"

        transformed.append(transformed_pattern)

    return transformed


def _collect_zip_contents(zipf, project_path, extra_files, skip_tracker):
    connector_file_exists = False
    custom_drivers_exists = False
    custom_driver_installation_script_exists = False
    configuration_form_pb_exists = False

    for root, files in dir_walker(project_path, skip_tracker=skip_tracker):
        if os.path.basename(root) == DRIVERS:
            custom_drivers_exists = True
        if INSTALLATION_SCRIPT in files:
            custom_driver_installation_script_exists = True
        for file in files:
            if file == ROOT_FILENAME:
                connector_file_exists = True
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, project_path)
            zipf.write(file_path, arcname)

    for arcname, data in (extra_files or {}).items():
        if arcname == CONFIGURATION_FORM_FILENAME:
            configuration_form_pb_exists = True
        zipf.writestr(arcname, data)

    return (
        connector_file_exists,
        custom_drivers_exists,
        custom_driver_installation_script_exists,
        configuration_form_pb_exists,
    )


def _validate_zip_contents(
    connector_file_exists,
    custom_drivers_exists,
    custom_driver_installation_script_exists,
    configuration_form_pb_exists,
):
    if not connector_file_exists:
        print_library_log(
            "connector.py not found in the project root\nthis file is required to start a sync and must be named in lowercase",
            Logging.Level.SEVERE,
        )
        sys.exit(1)

    if custom_drivers_exists and not custom_driver_installation_script_exists:
        print_library_log(INSTALLATION_SCRIPT_MISSING_MESSAGE, Logging.Level.SEVERE)
        sys.exit(1)

    if not configuration_form_pb_exists:
        print_library_log(
            f"{CONFIGURATION_FORM_FILENAME} not found in the package", Logging.Level.SEVERE
        )
        sys.exit(1)


def zip_folder(project_path: str, extra_files: dict = None) -> str:
    """Zips the folder at the given project path.

    Args:
        project_path (str): The path to the project.
        extra_files (dict): Optional mapping of {arcname: bytes} for in-memory files to include.

    Returns:
        str: The path to the zip file.
    """
    # Derive zip filename from project folder name for better local file identification
    # Use absolute path to handle relative paths like '.'
    abs_project_path = os.path.abspath(project_path)
    project_name = os.path.basename(abs_project_path)
    upload_filename = f"{project_name}.zip" if project_name else UPLOAD_FILENAME
    upload_filepath = os.path.join(project_path, OUTPUT_FILES_DIR, upload_filename)
    os.makedirs(os.path.dirname(upload_filepath), exist_ok=True)
    skip_tracker = {"has_skipped": False}

    with ZipFile(upload_filepath, "w", ZIP_DEFLATED) as zipf:
        (
            connector_file_exists,
            custom_drivers_exists,
            custom_driver_installation_script_exists,
            configuration_form_pb_exists,
        ) = _collect_zip_contents(zipf, project_path, extra_files, skip_tracker)

    _validate_zip_contents(
        connector_file_exists,
        custom_drivers_exists,
        custom_driver_installation_script_exists,
        configuration_form_pb_exists,
    )

    if skip_tracker["has_skipped"]:
        print_library_log("ignored files based on .gitignore patterns during packaging")

    return upload_filepath


def _initialize_walker_patterns(top, project_root, parent_patterns):
    """Initialize patterns for directory walking.

    Args:
        top (str): The current directory being processed.
        project_root (str): The root of the project, or None on first call.
        parent_patterns (list[str]): Pattern strings from parent directories, or None on first call.

    Returns:
        tuple: (project_root, combined_patterns, combined_spec, has_negation)
            - project_root (str): The project root directory
            - combined_patterns (list[str]): Combined pattern strings
            - combined_spec (pathspec.PathSpec): Compiled pattern matcher
            - has_negation (bool): True if any negation patterns exist
    """
    if project_root is None:
        project_root = top
        parent_patterns = get_default_ignore_patterns()

    local_patterns = load_gitignore(top)

    if project_root != top:
        directory_rel_path = os.path.relpath(top, project_root)
        directory_rel_path = normalize_path_for_matching(directory_rel_path)
        local_patterns = transform_gitignore_patterns(local_patterns, directory_rel_path)

    combined_patterns = parent_patterns + local_patterns

    try:
        combined_spec = pathspec.PathSpec.from_lines("gitwildmatch", combined_patterns)
    except Exception as e:
        print_library_log(
            f"failed to parse .gitignore error: {e}",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        sys.exit(1)

    has_negation = any(
        pattern.strip().startswith("!") for pattern in combined_patterns if pattern.strip()
    )

    return project_root, combined_patterns, combined_spec, has_negation


def _is_virtual_environment(path):
    """Check if a directory is a virtual environment.

    Treats inaccessible directories (OSError) as virtual environments to ensure they are skipped.

    Args:
        path (str): Path to the directory to check.

    Returns:
        bool: True if the directory is a virtual environment or inaccessible, False otherwise.
    """
    try:
        return VIRTUAL_ENV_CONFIG in os.listdir(path)
    except OSError as e:
        Logging.warning(
            f"Directory '{path}' could not be accessed and will be skipped as a virtual environment. Reason: {e}"
        )
        return True


def _should_include_directory(path, project_root, combined_spec, has_negation):
    """Determine if a directory should be included in traversal.

    Args:
        path (str): Path to the directory.
        project_root (str): The project root directory.
        combined_spec (pathspec.PathSpec): Compiled pattern matcher.
        has_negation (bool): True if negation patterns exist.

    Returns:
        bool: True if the directory should be traversed, False if it should be skipped.
    """
    rel_path = os.path.relpath(path, project_root)
    normalized_rel_path = normalize_path_for_matching(rel_path)
    dir_match_path = normalized_rel_path + "/"

    if combined_spec.match_file(dir_match_path) and not has_negation:
        return False
    return True


def _should_include_file(path, project_root, combined_spec, has_negation):
    """Determine if a file should be included based on patterns.

    Args:
        path (str): Full path to the file.
        project_root (str): The project root directory.
        combined_spec (pathspec.PathSpec): Compiled pattern matcher.
        has_negation (bool): True if negation patterns exist.

    Returns:
        bool: True if the file should be included, False otherwise.
    """
    # Always include files in the allowlist regardless of exclusion patterns
    if os.path.basename(path) in ALWAYS_INCLUDED_FILES:
        return True

    # Check against .gitignore patterns
    rel_path = os.path.relpath(path, project_root)
    normalized_rel_path = normalize_path_for_matching(rel_path)

    if has_negation:
        # When negations exist, use check_file for detailed result
        check_result = combined_spec.check_file(normalized_rel_path)
        if check_result.include is None:
            # No pattern matched, include the file
            return True
        else:
            # pathspec's include field is inverted for gitignore semantics:
            # include=True means "matched exclusion pattern" (exclude file)
            # include=False means "matched negation pattern" (include file)
            return not check_result.include
    else:
        # Fast path when no negations exist
        if combined_spec.match_file(normalized_rel_path):
            # Matched an exclusion pattern
            return False
        # No match, include the file
        return True


def _classify_directory_entries(top, project_root, combined_spec, has_negation, skip_tracker):
    """Classify directory entries into directories to recurse and files to include.

    Args:
        top (str): The current directory being processed.
        project_root (str): The project root directory.
        combined_spec (pathspec.PathSpec): Compiled pattern matcher.
        has_negation (bool): True if negation patterns exist.
        skip_tracker (dict):  Mutable dict to track if files were skipped

    Returns:
        tuple: (dirs, files) - lists of directory and file names to process.
    """
    dirs = []
    files = []

    for name in os.listdir(top):
        path = os.path.join(top, name)
        is_dir = os.path.isdir(path)

        if is_dir:
            if _is_virtual_environment(path):
                continue

            if _should_include_directory(path, project_root, combined_spec, has_negation):
                dirs.append(name)
        else:
            if _should_include_file(path, project_root, combined_spec, has_negation):
                files.append(name)
            elif name != CONFIGURATION_JSON:
                skip_tracker["has_skipped"] = True

    return dirs, files


def dir_walker(top, project_root=None, parent_patterns=None, skip_tracker=None):
    """Walks the directory tree starting at the given top directory with .gitignore support.

    This function supports hierarchical .gitignore files following gitignore behavior.
    Default exclusion patterns are applied automatically for backwards compatibility.

    All file types are included unless excluded by .gitignore patterns.

    Args:
        top (str): The top directory to start the walk.
        project_root (str, optional): Internal use only. Set automatically during recursion.
        parent_patterns (list[str], optional): Internal use only. Set automatically during recursion.
        skip_tracker (dict): Tracks if files were skipped

    Yields:
        tuple: A tuple containing the current directory path and a list of files (root, files).
    """
    if skip_tracker is None:
        skip_tracker = {"has_skipped": False}

    project_root, combined_patterns, combined_spec, has_negation = _initialize_walker_patterns(
        top, project_root, parent_patterns
    )

    dirs, files = _classify_directory_entries(
        top, project_root, combined_spec, has_negation, skip_tracker
    )

    yield top, files

    for name in dirs:
        new_path = os.path.join(top, name)
        yield from dir_walker(new_path, project_root, combined_patterns, skip_tracker)


def upload_package(local_path: str, deploy_key: str) -> Optional[str]:
    """Uploads a connector package to Fivetran's package management system.

    Always creates a new package via POST.

    Args:
        local_path (str): The absolute path to the package zip file.
        deploy_key (str): Base64-encoded Fivetran API key.

    Returns:
        Optional[str]: The package ID if upload succeeded, None if failed.
    """
    print_library_log("uploading package", log_icon=Logging.LogIcon.STEP)
    url = f"{constants.PRODUCTION_BASE_URL}/v1/connector-sdk/packages"

    headers = {"Authorization": f"Basic {deploy_key}", "User-Agent": get_user_agent()}

    with open(local_path, "rb") as f:
        response = rq.post(url, files={"file": f}, headers=headers)

    if response.ok:
        try:
            response_data = response.json()
        except json.JSONDecodeError as e:
            print_library_log(
                f"package upload succeeded but failed to parse response JSON: {e}. Response text: {response.text}",
                Logging.Level.SEVERE,
            )
            return None

        package_id = response_data.get("data", {}).get("id")
        if not package_id:
            print_library_log(
                "package upload succeeded but response missing package ID. Response: "
                + str(response_data),
                Logging.Level.SEVERE,
            )
            return None

        print_library_log("package uploaded", log_icon=Logging.LogIcon.SUCCESS)
        return package_id

    try:
        error_details = json.loads(response.text).get("message", response.text)
    except json.JSONDecodeError:
        error_details = response.text
    error_message = f"{response.reason}: {error_details}"
    print_library_log(
        f"failed to upload the package error: {error_message}",
        level=Logging.Level.SEVERE,
        log_icon=Logging.LogIcon.FAILURE,
    )
    return None


def cleanup_uploaded_code(deploy_key: str, package_id: str) -> bool:
    """Deletes an orphaned package when connection creation fails.

    Args:
        deploy_key (str): The deployment key.
        package_id (str): The package ID to delete.

    Returns:
        bool: True if the cleanup was successful, False otherwise.
    """
    print_library_log(f"cleaning up orphaned package: {package_id}", log_icon=Logging.LogIcon.STEP)
    response = rq.delete(
        f"{constants.PRODUCTION_BASE_URL}/v1/connector-sdk/packages/{package_id}",
        headers={"Authorization": f"Basic {deploy_key}", "User-Agent": get_user_agent()},
    )
    if response.ok:
        print_library_log("cleaned up orphaned package", log_icon=Logging.LogIcon.SUCCESS)
        return True

    print_library_log(
        f"failed to cleanup orphaned package error: {response.reason}",
        level=Logging.Level.SEVERE,
        log_icon=Logging.LogIcon.FAILURE,
    )
    return False


def get_os_arch_suffix() -> str:
    """
    Returns the operating system and architecture suffix for the current operating system.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system not in OS_MAP:
        raise RuntimeError(f"unsupported OS: {system}")

    plat = OS_MAP[system]

    if machine not in ARCH_MAP:
        raise RuntimeError(f"unsupported architecture '{machine}' for {plat}")

    return f"{plat}-{ARCH_MAP[machine]}"


def get_user_agent() -> str:
    """
    Returns the User-Agent string with SDK version, OS and architecture information.

    Returns:
        str: User-Agent string in format "fivetran-connector-sdk/{version}/{os}-{arch}"
    """
    from fivetran_connector_sdk import __version__

    return f"fivetran-connector-sdk/{__version__}/{get_os_arch_suffix()}"


def get_group_info(group: str, deploy_key: str) -> tuple[str, str]:
    """Retrieves the group information for the specified group and deployment key.

    Args:
        group (str): The group name.
        deploy_key (str): The deployment key.

    Returns:
        tuple[str, str]: A tuple containing the group ID and group name.
    """
    groups_url = f"{constants.PRODUCTION_BASE_URL}/v1/groups"

    params = {"limit": 500}
    headers = {"Authorization": f"Basic {deploy_key}", "User-Agent": get_user_agent()}
    resp = rq.get(groups_url, headers=headers, params=params)

    if not resp.ok:
        print_library_log(
            f"request failed error: {resp.status_code}\nensure you're using a valid base64-encoded API key",
            Logging.Level.SEVERE,
        )
        sys.exit(1)

    data = resp.json().get("data", {})
    groups = data.get("items")

    if not groups:
        print_library_log(
            "failed to deploy; no destinations defined in account",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        sys.exit(1)

    if not group:
        if len(groups) == 1:
            return groups[0]["id"], groups[0]["name"]
        else:
            print_library_log(
                "failed to deploy; multiple destinations found and --destination not provided",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )
            sys.exit(1)

    while True:
        for grp in groups:
            if grp["name"] == group:
                return grp["id"], grp["name"]
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            break

        params = {"cursor": next_cursor, "limit": 500}
        resp = rq.get(groups_url, headers=headers, params=params)
        data = resp.json().get("data", {})
        groups = data.get("items", [])

    print_library_log(
        f"failed to deploy; destination '{group}' not found in account",
        level=Logging.Level.SEVERE,
        log_icon=Logging.LogIcon.FAILURE,
    )
    sys.exit(1)


def java_exe_helper(location: str, os_arch_suffix: str) -> str:
    """Returns the path to the Java executable.

    Args:
        location (str): The location of the Java executable.
        os_arch_suffix (str): The name of the operating system and architecture

    Returns:
        str: The path to the Java executable.
    """
    java_exe_base = os.path.join(location, "bin", "java")
    return f"{java_exe_base}.exe" if os_arch_suffix.startswith(f"{WIN_OS}-") else java_exe_base


def process_stream(stream):
    """Processes a stream of text lines, replacing occurrences of a specified pattern.

    This method reads each line from the provided stream, searches for occurrences of
    a predefined pattern, and skips them.

    Args:
        stream (iterable): An iterable stream of text lines, typically from a file or another input source.

    Yields:
        str: Each line from the stream after skipping the matched pattern.
    """
    tester_pattern = r"com\.fivetran\.partner_sdk.*\.tools\.testers\.\S+"
    client_pattern = r"com\.fivetran\.partner_sdk.*\.client\.connector\.PartnerSdkConnectorClient"
    skip_next = False

    for line in iter(stream.readline, ""):
        if skip_next:
            # Skip the line immediately following the client_pattern
            skip_next = False
            continue
        if re.search(tester_pattern, line):
            continue
        if re.search(client_pattern, line):
            skip_next = True
            continue

        yield line


def redact_configuration_values(configuration: dict) -> dict:
    """Redacts all values in a configuration dictionary while preserving keys.

    Args:
        configuration (dict): The configuration dictionary to redact.

    Returns:
        dict: A new dictionary with all string values replaced with REDACTED_VALUE.
    """
    if not configuration:
        return configuration

    redacted = {}
    for key, value in configuration.items():
        # All configuration values should be strings
        redacted[key] = REDACTED_VALUE
    return redacted


def _build_tester_command(java_exe_str: str, root_dir: str, working_dir: str, port: int) -> list:
    """Builds the base command list for running the tester.

    Args:
        java_exe_str (str): The path to the Java executable.
        root_dir (str): The root directory.
        working_dir (str): The working directory for test output.
        port (int): The port number to use for the tester.

    Returns:
        list: The base command list for subprocess execution.
    """
    return [
        java_exe_str,
        "-jar",
        os.path.join(root_dir, TESTER_FILENAME),
        "--connector-sdk=true",
        f"--port={port}",
        f"--working-dir={working_dir}",
        "--tester-type=source",
    ]


def _build_debug_tester_command(
    java_exe_str: str,
    root_dir: str,
    working_dir: str,
    port: int,
    state_json: str,
    configuration_json: str,
    naming: str = None,
) -> list:
    """Builds the command list for running the tester in debug mode.

    Args:
        java_exe_str (str): The path to the Java executable.
        root_dir (str): The root directory.
        working_dir (str): The working directory for test output.
        port (int): The port number to use for the tester.
        state_json (str): The state JSON string to pass to the tester.
        configuration_json (str): The configuration JSON string to pass to the tester.
        naming (str): The naming strategy to pass to the tester.

    Returns:
        list: The command list for subprocess execution.
    """
    cmd = _build_tester_command(java_exe_str, root_dir, working_dir, port)
    cmd += [
        f"--state={state_json}",
        f"--naming={naming or (FIVETRAN_NAMING_VALUE + UNDERSCORE_NAMING)}",
        f"--configuration={configuration_json}",
    ]
    return cmd


def ensure_tester_installed() -> tuple:
    """Ensures the connector tester is downloaded and up to date.

    Returns:
        tuple: (java_exe path, tester_root_dir path)
    """
    os_arch_suffix = get_os_arch_suffix()
    tester_root_dir = tester_root_dir_helper()
    java_exe = java_exe_helper(tester_root_dir, os_arch_suffix)
    version_file = os.path.join(tester_root_dir, VERSION_FILENAME)

    if _should_install_tester(version_file, tester_root_dir):
        os.makedirs(tester_root_dir, exist_ok=True)
        download_filename = f"sdk-connector-tester-{os_arch_suffix}-{TESTER_VERSION}.zip"
        download_filepath = os.path.join(tester_root_dir, download_filename)
        _download_tester(download_filename, download_filepath)
        _extract_tester(download_filepath, tester_root_dir, java_exe)

    return java_exe, tester_root_dir


def _should_install_tester(version_file: str, tester_root_dir: str) -> bool:
    if not os.path.isfile(version_file):
        return True

    with open(version_file, "r", encoding=UTF_8) as fi:
        current_version = fi.readline()
    if current_version == TESTER_VERSION:
        return False

    shutil.rmtree(tester_root_dir)
    return True


def _download_tester(download_filename: str, download_filepath: str):
    try:
        print_library_log(
            f"downloading connector tester version: {TESTER_VERSION}",
            log_icon=Logging.LogIcon.STEP,
        )
        download_url = f"https://github.com/fivetran/fivetran_sdk_tools/releases/download/{TESTER_VERSION}/{download_filename}"
        with rq.get(download_url, stream=True) as r:
            if not r.ok:
                raise RuntimeError(
                    f"failed to download connector tester error: {r.status_code} url:{download_url}"
                )

            total_size = int(r.headers.get("content-length", 0))
            with open(download_filepath, "wb") as fo:
                with tqdm(
                    total=total_size or None,
                    unit="B",
                    unit_scale=True,
                    desc="downloading tester",
                    leave=False,
                    file=sys.stdout,
                ) as pbar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fo.write(chunk)
                            pbar.update(len(chunk))
    except RuntimeError:
        raise RuntimeError(
            f"failed to download connector tester\ntraceback:\n{traceback.format_exc()}"
        )


def _extract_tester(download_filepath: str, tester_root_dir: str, java_exe: str):
    try:
        with ZipFile(download_filepath, "r") as z_object:
            z_object.extractall(path=tester_root_dir)
        delete_file_if_exists(download_filepath)
        st = os.stat(java_exe)
        os.chmod(java_exe, st.st_mode | stat.S_IEXEC)
        print_library_log("tester download complete", log_icon=Logging.LogIcon.SUCCESS)
    except Exception:
        shutil.rmtree(tester_root_dir)
        raise RuntimeError(
            f"failed to download connector tester\ntraceback:\n{traceback.format_exc()}"
        )


def run_tester(
    java_exe_str: str,
    root_dir: str,
    project_path: str,
    port: int,
    state_json: str,
    configuration: dict,
    naming: str = None,
):
    """Runs the connector tester.

    Args:
        java_exe_str (str): The path to the Java executable.
        root_dir (str): The root directory.
        project_path (str): The path to the project.
        port (int): The port number to use for the tester.
        state_json (str): The state JSON string to pass to the tester.
        configuration (dict): The configuration dictionary to pass to the tester.
        naming (str): The formatted naming strategy (e.g., "FIVETRAN_NAMING" or "SOURCE_NAMING").

    Yields:
        str: The log messages from the tester.
    """
    working_dir = os.path.join(project_path, OUTPUT_FILES_DIR)
    try:
        os.mkdir(working_dir)
    except FileExistsError:
        pass

    cmd = _build_debug_tester_command(
        java_exe_str, root_dir, working_dir, port, state_json, json.dumps(configuration), naming
    )
    configuration_redacted = redact_configuration_values(configuration)
    redacted_cmd = _build_debug_tester_command(
        java_exe_str,
        root_dir,
        working_dir,
        port,
        state_json,
        json.dumps(configuration_redacted),
        naming,
    )
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    for line in process_stream(popen.stderr):
        yield _maybe_colorize_jar_output(line)
    for line in process_stream(popen.stdout):
        yield _maybe_colorize_jar_output(line)
    popen.stdout.close()
    return_code = popen.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, redacted_cmd)


def run_configuration_tester(
    java_exe_str: str,
    root_dir: str,
    project_path: str,
    port: int,
    run_tests: bool,
    disable_encryption: bool = False,
):
    """Runs the connector tester in configuration mode.

    Runs the tester with stdin/stdout/stderr inherited from the terminal so that
    interactive prompts are visible and user input works correctly.

    Args:
        java_exe_str (str): The path to the Java executable.
        root_dir (str): The root directory.
        project_path (str): The path to the project.
        port (int): The port number to use for the tester.
        run_tests (bool): If True, run setup tests instead of collecting configuration.
        disable_encryption (bool): If True, skip encryption of sensitive fields. Defaults to False.
    """
    cmd = _build_configuration_tester_command(
        java_exe_str, root_dir, project_path, port, run_tests, disable_encryption
    )
    return_code = subprocess.run(cmd).returncode
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, cmd)


def _build_configuration_tester_command(
    java_exe_str: str,
    root_dir: str,
    working_dir: str,
    port: int,
    run_tests: bool,
    disable_encryption: bool = False,
) -> list:
    """Builds the command list for running the tester in configuration mode."""
    cmd = _build_tester_command(java_exe_str, root_dir, working_dir, port)
    cmd.append("configuration")
    if run_tests:
        cmd.append("--test")
    if disable_encryption:
        cmd.append("--disable-encryption")
    return cmd


def _maybe_colorize_jar_output(line: str) -> str:
    if not constants.DEBUGGING:
        return line

    if "SEVERE" in line or "ERROR" in line or "Exception" in line or "FAILED" in line:
        return f"\033[196m{line}\033[0m"  # ANSI Red color #ff0000
    elif "WARN" in line or "WARNING" in line:
        return f"\033[130m{line}\033[0m"  # ANSI Orange-like color #af5f00
    return line


def process_tables(response, table_list):
    for entry in response:
        if "table" not in entry:
            raise ValueError("Entry missing table name: " + entry)

        table_name = entry["table"]

        _validate_table_name(table_name)

        if table_name in table_list:
            raise ValueError("Table already defined: " + table_name)

        table = common_pb2.Table(name=table_name)
        columns = {}

        if "primary_key" in entry:
            process_primary_keys(columns, entry)

        if "columns" in entry:
            process_columns(columns, entry)

        table.columns.extend(columns.values())
        TABLES[table_name] = table
        table_list[table_name] = table


def process_primary_keys(columns, entry):
    for column_name in entry["primary_key"]:
        column = (
            columns[column_name] if column_name in columns else common_pb2.Column(name=column_name)
        )
        column.primary_key = True
        columns[column_name] = column


def process_columns(columns, entry):
    for column_name, type in entry["columns"].items():
        column = (
            columns[column_name] if column_name in columns else common_pb2.Column(name=column_name)
        )

        if isinstance(type, str):
            process_data_type(column, type)

        elif isinstance(type, dict):
            if type["type"].upper() != "DECIMAL":
                error_message = (
                    f"Expecting DECIMAL data type for dictionary column entry, but got: {type['type']} in entry: {entry} "
                    f"for column: {column_name}. "
                    "Dictionary type is only allowed for DECIMAL columns with 'precision' and 'scale' fields, "
                    "as in: {'type': 'DECIMAL', 'precision': <int>, 'scale': <int>}. "
                    "For all other data types, use a string as the column type."
                )
                raise ValueError(error_message)
            column.type = common_pb2.DataType.DECIMAL
            column.params.decimal.precision = type["precision"]
            column.params.decimal.scale = type["scale"]

        else:
            raise ValueError(
                f"Unrecognized column type for column: {column_name} in entry: {entry}. Got: {str(type)}"
            )

        if "primary_key" in entry and column_name in entry["primary_key"]:
            column.primary_key = True

        columns[column_name] = column


def process_data_type(column, type):
    if type.upper() == "BOOLEAN":
        column.type = common_pb2.DataType.BOOLEAN
    elif type.upper() == "SHORT":
        column.type = common_pb2.DataType.SHORT
    elif type.upper() == "INT":
        column.type = common_pb2.DataType.INT
    elif type.upper() == "LONG":
        column.type = common_pb2.DataType.LONG
    elif type.upper() == "DECIMAL":
        raise ValueError(
            "DECIMAL data type missing precision and scale. "
            "Use a dictionary for DECIMAL column type like: "
            """"col_name": {  # Decimal data type with precision and scale.\n"""
            """    "type": "DECIMAL",\n"""
            """    "precision": 15,\n"""
            """    "scale": 2\n"""
            """}"""
        )
    elif type.upper() == "FLOAT":
        column.type = common_pb2.DataType.FLOAT
    elif type.upper() == "DOUBLE":
        column.type = common_pb2.DataType.DOUBLE
    elif type.upper() == "NAIVE_DATE":
        column.type = common_pb2.DataType.NAIVE_DATE
    elif type.upper() == "NAIVE_DATETIME":
        column.type = common_pb2.DataType.NAIVE_DATETIME
    elif type.upper() == "UTC_DATETIME":
        column.type = common_pb2.DataType.UTC_DATETIME
    elif type.upper() == "BINARY":
        column.type = common_pb2.DataType.BINARY
    elif type.upper() == "XML":
        column.type = common_pb2.DataType.XML
    elif type.upper() == "STRING":
        column.type = common_pb2.DataType.STRING
    elif type.upper() == "JSON":
        column.type = common_pb2.DataType.JSON
    else:
        raise ValueError("Unrecognized column type encountered:: ", str(type))


def delete_file_if_exists(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)


def remove_dir_if_empty(dir_path):
    """Remove a directory only if it exists and is empty.
    Best-effort: silently ignores OSError if the removal cannot be completed.
    """
    try:
        if os.path.isdir(dir_path) and not os.listdir(dir_path):
            os.rmdir(dir_path)
    except OSError:
        pass


def _build_missing_param_msg(flag_name: str, env_var_name: str) -> str:
    """Build error message for a missing required parameter.

    Args:
        flag_name (str): The CLI flag name (e.g., '--destination')
        env_var_name (str): The environment variable name (e.g., 'FIVETRAN_DESTINATION_NAME')

    Returns:
        str: Formatted error message for the missing parameter
    """
    return f"{flag_name} is required; provide it via the {flag_name} flag or the {env_var_name} environment variable."


def validate_required_deploy_params(ft_group: str, ft_connection: str, ft_deploy_key: str) -> None:
    """Validate resolved deployment parameters and exit with errors if any are missing.

    Collects all missing required parameters, logs each error message, then exits once if any are missing.

    Args:
        ft_group (str): Resolved destination group name
        ft_connection (str): Resolved connection name
        ft_deploy_key (str): Resolved API key
    """
    missing = []
    if not ft_group:
        missing.append(_build_missing_param_msg("--destination", FIVETRAN_DESTINATION_NAME_ENV))
    if not ft_connection:
        missing.append(_build_missing_param_msg("--connection", FIVETRAN_CONNECTION_NAME_ENV))
    if not ft_deploy_key:
        missing.append(_build_missing_param_msg("--api-key", FIVETRAN_API_KEY_ENV))
    if missing:
        for msg in missing:
            print_library_log(msg, level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        sys.exit(1)


def validate_configuration(configuration: dict | None):
    if configuration is None:
        print_library_log(
            "configuration is required; provide it via the --configuration flag, the FIVETRAN_CONFIGURATION environment variable, or by placing configuration.json in the project folder."
            "\nIf your connector does not require configuration, pass an empty configuration.json file."
            "\nFor more information, see https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json.",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        sys.exit(1)


def get_update_prompt(
    connection: str, group: str, configuration: dict | None, config_path: str = None
):
    """
    Generates the warning prompt for overwriting an existing Fivetran connection.
    """
    if configuration:
        prompt = (
            f"connection '{connection}' already exists in destination '{group}'.\n"
            f"updating it will overwrite the existing code and replace its configuration with keys and values from {config_path}.\n"
            "please provide the complete configuration, as any missing keys will be deleted.\n"
        )
    else:
        prompt = (
            f"connection '{connection}' already exists in destination '{group}'\n"
            "updating it will overwrite the existing code\n"
        )

    prompt += (
        "tip: consider downloading the existing connector code from the Fivetran dashboard\n"
        "continue with update? (y/N): "
    )

    return prompt
