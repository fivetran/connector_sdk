import os

from fivetran_connector_sdk.protos import common_pb2

TESTER_VERSION = "2.26.0908.001"

WIN_OS = "windows"
ARM_64 = "arm64"
X64 = "x64"

OS_MAP = {
    "darwin": "mac",
    "linux": "linux",
    WIN_OS: WIN_OS
}

ARCH_MAP = {
    "x86_64": X64,
    "amd64": X64,
    ARM_64: ARM_64,
    "aarch64": ARM_64
}

# Constants and cache for operations.py
UNSPECIFIED_COLUMNS_TYPE = common_pb2.DataType.UNSPECIFIED
UPSERT_TYPE = common_pb2.RecordType.UPSERT
UPDATE_TYPE = common_pb2.RecordType.UPDATE
TRUNCATE_TYPE = common_pb2.RecordType.TRUNCATE
DELETE_TYPE = common_pb2.RecordType.DELETE
TABLES_COLUMNS_TYPES = {}

# Global constants - use constants.<Global_variable> to access them as they can be overridden in the
DEBUGGING = False
EXECUTED_VIA_CLI = False
TABLES = {}

TESTER_FILENAME = "sdk_connector_tester.jar"
VERSION_FILENAME = "version.txt"
UPLOAD_FILENAME = "code.zip"
CONFIGURATION_FORM_FILENAME = "configuration_form.pb"
LAST_VERSION_CHECK_FILE = "_last_version_check"
ROOT_LOCATION = os.path.join(".fivetran", "connector_sdk")
TESTER_LOCATION = "tester"
CONFIG_FILE = "_config.json"
CONFIG_ENCRYPTION_KEY_FILE = "config_encryption_key"
ENCRYPTED_VALUE_PREFIX = "fivetran_encrypted:"
OUTPUT_FILES_DIR = "files"
REQUIREMENTS_TXT = "requirements.txt"
PYPROJECT_TOML = "pyproject.toml"
PYPROJECT_SKIP_VALIDATION_MESSAGE = "using pyproject.toml; skipping dependency validation"
RECOMMEND_STABLE_VERSION_MESSAGE = "We recommend using the current stable version for the following libraries:"
CONFIGURATION_JSON = "configuration.json"
FIVETRAN_API_KEY_ENV = "FIVETRAN_API_KEY"
FIVETRAN_DESTINATION_NAME_ENV = "FIVETRAN_DESTINATION_NAME"
FIVETRAN_CONNECTION_NAME_ENV = "FIVETRAN_CONNECTION_NAME"
PYPI_PACKAGE_DETAILS_URL = "https://pypi.org/pypi/fivetran_connector_sdk/json"
SIX_HOUR_IN_SEC = 6 * 60 * 60
MEMORY_LIMIT_BYTES = 4 * 1024 ** 3  # 4 GB memory limit to simulate memory constraints during local debug
CHECKPOINT_OP_TIMEOUT_IN_SEC = 120 # seconds
FIFO_READ_TIMEOUT_SECONDS = 30 # seconds - timeout for reading from FIFOs (named pipes)
MAX_RETRIES = 3
SDK_LOGGING_PREFIX = "⚡ sdk "
DEBUGGER_LOGGING_PREFIX = "⚡ debugger"
CONNECTOR_LOGGING_PREFIX = "⚡ connector"
VIRTUAL_ENV_CONFIG = "pyvenv.cfg"
GITIGNORE_FILENAME = ".gitignore"
ROOT_FILENAME = "connector.py"
MAX_RECORDS_IN_BATCH = 100
MAX_BATCH_SIZE_IN_BYTES = 100000 # Default 100 KB
QUEUE_SIZE = 100
CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC = "CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC"
FILE_UPLOAD_CHUNK_SIZE_BYTES = int(2 * 1024 * 1024) # 2 MB
FILE_UPLOAD_READ_TIMEOUT_SEC = int(300) # 5 minutes
FIVETRAN_FILE_PATH_COLUMN = "_fivetran_file_path"

ALWAYS_INCLUDED_FILES = [GITIGNORE_FILENAME]
EXCLUDED_DIRS = ["__pycache__", "lib", "include", OUTPUT_FILES_DIR]
EXCLUDED_PIPREQS_DIRS = ["bin,etc,include,lib,Lib,lib64,Scripts,share"]
VALID_COMMANDS = ["version", "init", "debug", "deploy", "reset", "package", "configuration", "help"]
DEPRECATED_FORCE_FLAG_WARNING = (
    "--force and -f are deprecated and will be removed in a future release. "
    "Use --non-interactive or --yes instead. See help for more details."
)
MAX_ALLOWED_EDIT_DISTANCE_FROM_VALID_COMMAND = 3
COMMANDS_AND_SYNONYMS = {
    "debug": {"test", "verify", "diagnose", "check"},
    "deploy": {"upload", "ship", "launch", "release"},
    "reset": {"reinitialize", "reinitialise", "re-initialize", "re-initialise", "restart", "restore"},
}

CONNECTION_SCHEMA_NAME_PATTERN = r'^[_a-z][_a-z0-9]*$'
PRODUCTION_BASE_URL = "https://api.fivetran.com"
INSTALLATION_SCRIPT_MISSING_MESSAGE = "installation.sh not found in the drivers directory; this file is required to configure custom drivers"
INSTALLATION_SCRIPT = "installation.sh"
DRIVERS = "drivers"
JAVA_LONG_MAX_VALUE = 9223372036854775807
MAX_CONFIG_FIELDS = 100
SUPPORTED_PYTHON_VERSIONS = ["3.14", "3.13", "3.12", "3.11", "3.10"]
DEFAULT_PYTHON_VERSION = "3.14"
FIVETRAN_HD_AGENT_ID = "FIVETRAN_HD_AGENT_ID"
FIVETRAN_NAMING_ENV = "FIVETRAN_NAMING"  # Environment variable name for setting naming strategy
FIVETRAN_NAMING_VALUE = "FIVETRAN"  # Fivetran naming strategy value
SOURCE_NAMING_VALUE = "SOURCE"  # Source naming strategy value
UNDERSCORE_NAMING = "_NAMING"  # Suffix for sending naming to Fivetran API
UTF_8 = "utf-8"
REDACTED_VALUE = "****"
EXAMPLES_GITHUB_REPO = "fivetran/connector_sdk"
GITHUB_BRANCH = "main"
CONNECTORS_GITHUB_REPO = "fivetran/community_connectors"
CONNECTORS_TEMPLATE_PREFIX = "connectors/"
TOOLS_GITHUB_REPO = "fivetran/connector_sdk_tools"
TOOLS_GITHUB_REPO_URL = f"https://github.com/{TOOLS_GITHUB_REPO}"
AI_TOOLS_INSTALLATION_DOCS_URL = (
    "https://fivetran.com/docs/connector-sdk/building-connectors/ai-tools#installingtheplugin"
)
TOOLS_PLUGIN_ID = "fivetran-connector-sdk-ai"
TOOLS_PLUGIN_NAME = f"fivetran-connector-sdk@{TOOLS_PLUGIN_ID}"
AGENT_PLUGINS = {
    "claude": {
        "display_name": "Claude Code",
        "cli_command": "claude",
        "install_commands": [
            ["claude", "plugin", "marketplace", "add", TOOLS_GITHUB_REPO],
            ["claude", "plugin", "install", TOOLS_PLUGIN_NAME],
        ],
        "update_commands": [
            ["claude", "plugin", "update", TOOLS_PLUGIN_NAME],
        ],
    },
    "codex": {
        "display_name": "Codex CLI",
        "cli_command": "codex",
        "min_supported_version": (0, 131, 0),
        "install_commands": [
            ["codex", "plugin", "marketplace", "add", TOOLS_GITHUB_REPO],
            ["codex", "plugin", "add", TOOLS_PLUGIN_NAME],
        ],
        "update_commands": [
            ["codex", "plugin", "marketplace", "upgrade", TOOLS_PLUGIN_ID],
        ],
    },
    "gemini": {
        "display_name": "Gemini CLI",
        "cli_command": "gemini",
        "install_commands": [
            ["gemini", "extensions", "install", TOOLS_GITHUB_REPO_URL, "--consent", "--skip-settings", "--auto-update"],
        ],
    },
    "copilot": {
        "display_name": "GitHub Copilot CLI",
        "cli_command": "copilot",
        "install_commands": [
            ["copilot", "plugin", "marketplace", "add", TOOLS_GITHUB_REPO],
            ["copilot", "plugin", "install", TOOLS_PLUGIN_NAME],
        ],
        "update_commands": [
            ["copilot", "plugin", "update", TOOLS_PLUGIN_NAME],
        ],
    },
}
SUPPORTED_AGENT_DISPLAY_NAMES = ", ".join(config["display_name"] for config in AGENT_PLUGINS.values())
TEMPLATE_CONNECTOR_PATH = "_template_connector"
