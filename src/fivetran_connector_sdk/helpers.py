import os
import select
import stat
import shutil
import sys
import json
import traceback
import importlib.util
from datetime import datetime
from enum import Enum
from pathlib import Path
from prompt_toolkit import prompt
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion, PathCompleter, merge_completers

from fivetran_connector_sdk.logger import Logging
from fivetran_connector_sdk import constants
from fivetran_connector_sdk.configuration_decryption import decrypt_configuration_values
from fivetran_connector_sdk.constants import (
    SDK_LOGGING_PREFIX,
    ROOT_FILENAME,
    MAX_CONFIG_FIELDS,
    MAX_ALLOWED_EDIT_DISTANCE_FROM_VALID_COMMAND,
    COMMANDS_AND_SYNONYMS,
    VALID_COMMANDS,
    OUTPUT_FILES_DIR,
    UTF_8,
    FIFO_READ_TIMEOUT_SECONDS
)


class PromptMode(Enum):
    INTERACTIVE = None
    DEFAULT_ANSWER = "--non-interactive"
    YES = "--yes"
    FORCE = "--force"

    @property
    def is_non_interactive_mode(self) -> bool:
        return self != PromptMode.INTERACTIVE

    @classmethod
    def from_args(cls, non_interactive: bool, force: bool, yes: bool) -> 'PromptMode':
        active = [
            (cls.DEFAULT_ANSWER, non_interactive),
            (cls.FORCE, force),
            (cls.YES, yes),
        ]
        active_modes = [mode for mode, val in active if val]
        if len(active_modes) > 1:
            flags = " and ".join(m.value for m in active_modes)
            raise ValueError(f"{flags} cannot be used together")
        return active_modes[0] if active_modes else cls.INTERACTIVE

def _validate_table_name(table: str) -> None:
    if not isinstance(table, str):
        raise TypeError(f"Table name must be a string, got {type(table).__name__}")
    if not table.strip():
        raise ValueError("Table name must be a non-empty string")


def _validate_message(message: str) -> None:
    if not isinstance(message, str):
        raise TypeError(f"Message must be a string, got {type(message).__name__}")
    if not message.strip():
        raise ValueError("Message must be a non-empty string")


def _validate_trace(trace) -> None:
    # trace is optional -- None means no trace was provided, which is valid.
    if trace is not None and not isinstance(trace, str):
        raise TypeError(f"Trace must be a string, got {type(trace).__name__}")


def is_regular_file_or_fifo(filepath):
    """Check if the given path is a regular file or a FIFO (named pipe).

    Args:
        filepath (str): The path to check.

    Returns:
        bool: True if the path is a regular file or FIFO, False otherwise.
    """
    try:
        file_stat = os.stat(filepath)
        mode = file_stat.st_mode
        return stat.S_ISREG(mode) or stat.S_ISFIFO(mode)
    except (FileNotFoundError, NotADirectoryError):
        # Path does not exist or an intermediate component is not a directory.
        # In these cases, treat it as "not a regular file or FIFO".
        return False


def is_fifo(filepath):
    """Check if the given path is a FIFO (named pipe).

    Args:
        filepath (str): The path to check.

    Returns:
        bool: True if the path is a FIFO, False otherwise.
    """
    try:
        file_stat = os.stat(filepath)
        return stat.S_ISFIFO(file_stat.st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False


def safe_read_file(filepath, timeout_seconds=FIFO_READ_TIMEOUT_SECONDS):
    """Read contents from a file, with special handling for FIFOs to avoid indefinite blocking.

    For regular files, reads normally.
    For FIFOs (named pipes), uses non-blocking I/O with a timeout to prevent
    hanging indefinitely when a writer is delayed or crashes.

    Args:
        filepath (str): Path to the file to read.
        timeout_seconds (int): Timeout in seconds for FIFO reads (default: 30).

    Returns:
        str: The file contents.

    Raises:
        TimeoutError: If FIFO read times out waiting for a writer.
        OSError: If the file cannot be read.
    """
    if not is_fifo(filepath):
        # Regular file - open normally
        with open(filepath, 'r', encoding=UTF_8) as f:
            return f.read()

    # FIFO - use non-blocking open with timeout
    fd = None
    try:
        # Open FIFO in non-blocking mode to avoid blocking on open()
        fd = os.open(filepath, os.O_RDONLY | os.O_NONBLOCK)

        # Wait for data to be available with timeout
        readable, _, _ = select.select([fd], [], [], timeout_seconds)

        if not readable:
            raise TimeoutError(
                f"Timed out after {timeout_seconds} seconds waiting for data from FIFO: {filepath}. "
                "Ensure the writer process is running and producing data."
            )

        # Switch back to blocking mode so read() waits for complete data until EOF.
        # Without this, read() on a non-blocking fd returns only currently buffered
        # bytes, which can cause truncated reads if the writer emits data in chunks.
        import fcntl  # Unix-only, imported lazily to avoid breaking Windows for non-FIFO paths
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

        # Read all data - fdopen takes ownership of fd
        with os.fdopen(fd, 'r', encoding=UTF_8) as f:
            fd = None  # Prevent double-close in finally block
            return f.read()
    finally:
        if fd is not None:
            os.close(fd)


def print_library_log(message: str, level: Logging.Level = Logging.Level.INFO, dev_log: bool = False, log_icon: Logging.LogIcon = Logging.LogIcon.NONE, indent: bool = False):
    """Logs a library message with the specified logging level.
    Args:
        level (Logging.Level): The logging level.
        message (str): The message to log.
        dev_log (bool): Boolean value to check if it is dev log and shouldn't be visible to customer
        log_icon (Logging.LogIcon): The type of log icon to add.
        indent (bool): Whether to indent the message.
    """
    message = add_icon_to_log_message(message, log_icon)
    if indent:
        message = f"  {message}"
    if constants.DEBUGGING:
        # Debug mode: verbose format with timestamp
        if dev_log:
            return
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
        log_origin = Logging.get_aligned_log_origin(SDK_LOGGING_PREFIX.strip())
        prefix = f"{current_time} {Logging.get_aligned_level_name(level)} {log_origin} "
        
        if "\n" in message:
            lines = message.split('\n')
            continuation_indent = Logging.get_display_width(prefix)
            message = f"\n{' ' * continuation_indent}".join(lines)
        
        print(Logging.colorize(f"{prefix}{message}", level))
    elif constants.EXECUTED_VIA_CLI:
        # Other CLI commands (deploy, init, etc.): concise format with icons and colors
        if dev_log:
            return
        print(Logging.colorize(message, level))
    else:
        message_origin = "library_dev" if dev_log else "library"
        escaped_message = json.dumps(SDK_LOGGING_PREFIX + message)
        log_message = f'{{"level":"{level.name}", "message": {escaped_message}, "message_origin": "{message_origin}"}}'
        print(log_message)


def add_icon_to_log_message(message: str, log_icon: Logging.LogIcon):
    """Adds an icon to the log message based on the specified log icon type.
    Args:
        message (str): The message to log.
        log_icon (Logging.LogIcon): The type of log icon to add.
    Returns:
        str: The log message with the added icon.
    """
    match log_icon:
        case Logging.LogIcon.INFO:
            return f"ℹ️ {message}"
        case Logging.LogIcon.SUCCESS:
            return f"✓ {message}"
        case Logging.LogIcon.FAILURE:
            return f"✗ {message}"
        case Logging.LogIcon.STEP:
            return f"› {message}"
        case Logging.LogIcon.LIGHTNING:
            return f"⚡ {message}"
        case _:
            return message


# Functions used by main method only

def find_connector_object(project_path):
    """Finds the connector object in the given project path.
    Args:
        project_path (str): The path to the project.
    """

    sys.path.append(project_path)  # Allows python interpreter to search for modules in this path
    module_name = "connector_connector_code"
    connector_py = os.path.join(project_path, ROOT_FILENAME)
    try:
        spec = importlib.util.spec_from_file_location(module_name, connector_py)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        # Use type name + module check instead of isinstance to avoid circular import
        # (Connector is defined in __init__.py which imports this file).
        connector_instances = {}
        for obj, obj_attr in vars(module).items():
            if not obj.startswith('__'):  # Exclude built-in attributes
                obj_type = type(obj_attr)
                if obj_type.__name__ == 'Connector' and obj_type.__module__ == 'fivetran_connector_sdk':
                    connector_instances[obj] = obj_attr
        # The variable must be named 'connector' because production runs: from connector import connector
        if 'connector' in connector_instances:
            return connector_instances['connector']
        if connector_instances:
            names_str = ', '.join(f"'{n}'" for n in sorted(connector_instances.keys()))
            print_library_log(
                f"Connector object must be named 'connector', but found: {names_str}\n"
                f"rename it to 'connector' in connector.py\n"
                f"example: connector = Connector(update=update, schema=schema)\n"
                f"reference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector",
                Logging.Level.SEVERE)
            return None

    except TypeError as e:
        tb = traceback.extract_tb(e.__traceback__)
        last_frame = tb[-1] if tb else None
        location = f"at {last_frame.filename}, line {last_frame.lineno}\n" if last_frame else ""
        print_library_log(
            f"error in connector.py {location}"
            f"{e}\n"
            f"reference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector",
            Logging.Level.SEVERE)
        return None
    except FileNotFoundError:
        print_library_log(
            f"connector.py not found in {project_path}\nthis file is required to start a sync\nreference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector",
            Logging.Level.SEVERE)
        return None

    print_library_log(
        "connector object not found\ndefine a Connector object in connector.py\nreference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector",
        Logging.Level.SEVERE)
    return None


def suggest_correct_command(input_command: str) -> bool:
    # for typos
    # calculate the edit distance of the input command (lowercased) with each of the valid commands
    edit_distances_of_commands = sorted(
        [(command, edit_distance(command, input_command.lower())) for command in VALID_COMMANDS], key=lambda x: x[1])

    if edit_distances_of_commands[0][1] <= MAX_ALLOWED_EDIT_DISTANCE_FROM_VALID_COMMAND:
        # if the closest command is within the max allowed edit distance, we suggest that command
        # threshold is kept to prevent suggesting a valid command for an obvious wrong command like `fivetran iknowthisisntacommandbuttryanyway`
        print_suggested_command_message(edit_distances_of_commands[0][0], input_command)
        return True

    # for synonyms
    for (command, synonyms) in COMMANDS_AND_SYNONYMS.items():
        # check if the input command (lowercased) is a recognised synonym of the valid commands, if yes, suggest that command
        if input_command.lower() in synonyms:
            print_suggested_command_message(command, input_command)
            return True

    return False


def print_suggested_command_message(valid_command: str, input_command: str) -> None:
    print_library_log(f"unknown command: {input_command}", Logging.Level.SEVERE)
    print_library_log(f"did you mean `fivetran {valid_command}`?", Logging.Level.SEVERE)
    print_library_log("use `fivetran --help` for more details", Logging.Level.SEVERE)


def edit_distance(first_string: str, second_string: str) -> int:
    first_string_length: int = len(first_string)
    second_string_length: int = len(second_string)

    # Initialize the previous row of distances (for the base case of an empty first string) 'previous_row[j]' holds
    # the edit distance between an empty prefix of 'first_string' and the first 'j' characters of 'second_string'.
    # The first row is filled with values [0, 1, 2, ..., second_string_length]
    previous_row: list[int] = list(range(second_string_length + 1))

    # Rest of the rows
    for first_string_index in range(1, first_string_length + 1):
        # Start the current row with the distance for an empty second string
        current_row: list[int] = [first_string_index]

        # Iterate over each character in the second string
        for second_string_index in range(1, second_string_length + 1):
            if first_string[first_string_index - 1] == second_string[second_string_index - 1]:
                # If characters match, no additional cost
                current_row.append(previous_row[second_string_index - 1])
            else:
                # Minimum cost of insertion, deletion, or substitution
                current_row.append(
                    1 + min(current_row[-1], previous_row[second_string_index], previous_row[second_string_index - 1]))

        # Move to the next row
        previous_row = current_row

    # The last value in the last row is the edit distance
    return previous_row[second_string_length]

class EnvironmentVariableCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith('$'):
            # Get the variable name part (text after the '$')
            var_name = text[1:]

            # Suggest all environment variables that start with the typed name
            for env_var in os.environ:
                if env_var.startswith(var_name):
                    yield Completion(
                        f'${env_var}',
                        start_position=-len(text)
                    )

class EnvVarPathCompleter(Completer):
    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        expanded_text = os.path.expandvars(text_before_cursor)

        # Create a new document for the PathCompleter to use
        expanded_document = Document(
            text=expanded_text, cursor_position=len(expanded_text)
        )

        # Use a standard PathCompleter on our new, temporary document
        path_completer = PathCompleter(expanduser=True)
        yield from path_completer.get_completions(expanded_document, complete_event)


def get_input_from_cli(prompt_txt: str, default_value: str, hide_value = False) -> str:
    """
    Prompts the user for input.
    """
    final_completer = merge_completers([EnvironmentVariableCompleter(), EnvVarPathCompleter()])
    history = FileHistory(os.path.join(os.path.expanduser('~'), '.fivetran_history'))
    if default_value:
        if hide_value:
            default_value_hidden = default_value[0:8] + "********"
            value = prompt(f"{prompt_txt} [Default : {default_value_hidden}]: ",
                           completer=final_completer, history=history, complete_while_typing=False, complete_style='readline_like'
                           ).strip() or default_value
        else:
            value = prompt(f"{prompt_txt} [Default : {default_value}]: ",
                           completer=final_completer, history=history, complete_while_typing=False, complete_style='readline_like'
                           ).strip() or default_value
    else:
        value = prompt(f"{prompt_txt}: ",
                       completer=final_completer, history=history, complete_while_typing=False, complete_style='readline_like'
                       ).strip()

    if not value:
        raise ValueError("Missing required input: Expected a value but received None")
    return os.path.expandvars(value)

def _resolve_existing_project_path(project_path: str) -> str:
    if project_path is None or not str(project_path).strip():
        raise ValueError("Invalid project path: path cannot be empty or contain only whitespace.")
    resolved_project_path = Path(str(project_path).strip()).expanduser().resolve()
    if not resolved_project_path.is_dir():
        raise ValueError(
            f"Invalid project path: '{project_path}' does not exist or is not a directory."
        )
    return str(resolved_project_path)


def validate_and_load_configuration(project_path, configuration):
    if not configuration:
        print_library_log("no configuration file passed", Logging.Level.INFO)
        return {}

    configuration = os.path.expanduser(configuration)
    json_filepath = os.path.abspath(
        configuration if os.path.isabs(configuration)
        else os.path.join(project_path, configuration)
    )

    if not os.path.exists(json_filepath) or not is_regular_file_or_fifo(json_filepath):
        raise ValueError(
            f"Configuration path is incorrect, cannot find file at the location {json_filepath}"
        )

    try:
        content = safe_read_file(json_filepath)
    except OSError as e:
        raise ValueError(
            str(e) if isinstance(e, TimeoutError)
            else f"Cannot read configuration file at {json_filepath}: {e}"
        ) from e

    try:
        configuration = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(
            "Configuration must be provided as a JSON file. Please check your input. Reference: "
            "https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json#workingwithconfigurationjson"
        )

    if len(configuration) > MAX_CONFIG_FIELDS:
        raise ValueError(
            f"Configuration field count exceeds maximum of {MAX_CONFIG_FIELDS}. Reduce the field count."
        )

    return decrypt_configuration_values(configuration)


def validate_and_load_state(args, state):
    if state:
        json_filepath = os.path.abspath(os.path.join(args.project_path, args.state))
    else:
        json_filepath = os.path.join(args.project_path, "files", "state.json")

    if os.path.exists(json_filepath):
        # Support both regular files and pipes/FIFOs (os.path.isfile returns False for pipes)
        if is_regular_file_or_fifo(json_filepath):
            try:
                content = safe_read_file(json_filepath)
                state = json.loads(content)
            except TimeoutError as e:
                raise ValueError(str(e)) from e
            except OSError as e:
                raise ValueError(
                    f"Cannot read state file at {json_filepath}: {e}") from e
        else:
            raise ValueError(
                f"State path is incorrect, cannot find file at the location {json_filepath}")
    else:
        state = {}
    return state


def reset_local_file_directory(args, prompt_mode: PromptMode):
    files_path = os.path.join(args.project_path, OUTPUT_FILES_DIR)
    if not resolve_confirmation("This will delete your current state and `warehouse.db` files. Do you want to continue? (Y/n): ",
                                default=True, prompt_mode=prompt_mode):
        print_library_log("reset cancelled")
        return
    try:
        print_library_log(f"resetting project {args.project_path}", log_icon=Logging.LogIcon.STEP)
        if os.path.exists(files_path) and os.path.isdir(files_path):
            shutil.rmtree(files_path)
            print_library_log("reset successful", log_icon=Logging.LogIcon.SUCCESS)
        else:
            print_library_log(
                "No files were deleted. Ensure you are in the project root directory.",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE)
    except Exception as e:
        print_library_log("reset failed", level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        raise e


def resolve_confirmation(prompt: str, default: bool, prompt_mode: PromptMode) -> bool:
    if prompt_mode == PromptMode.YES or prompt_mode == PromptMode.FORCE:
        return True
    if prompt_mode == PromptMode.DEFAULT_ANSWER:
        return default
    # interactive mode
    answer = input(prompt).strip().lower()
    if answer == "y":
        return True
    elif answer == "n":
        return False
    else:
        # Invalid input or empty, return default
        return default

def enable_debugging_for_verbose_commands(command: str):
    if command is not None and command.lower() in ("debug", "configuration"):
        constants.DEBUGGING = True
