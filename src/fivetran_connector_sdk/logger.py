import json
import sys
import traceback
import unicodedata
from enum import IntEnum
from datetime import datetime
from typing_extensions import deprecated

from fivetran_connector_sdk import constants

class Logging:
    class Level(IntEnum):
        DEBUG = 1
        FINE = 2
        INFO = 3
        WARNING = 4
        ERROR = 5
        SEVERE = 6
        CRITICAL = 7

    class LogIcon(IntEnum):
        NONE = 1
        STEP = 2
        INFO = 3
        FAILURE = 4
        SUCCESS = 5
        LIGHTNING = 6

    LOG_LEVEL = None

    @staticmethod
    def __log(level: Level, message: str):
        """Logs a message with the specified logging level.

        Args:
            level (Logging.Level): The logging level.
            message (str): The message to log.
        """
        if constants.DEBUGGING:
            now = datetime.now()
            current_time = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
            log_origin = Logging.get_aligned_log_origin(constants.CONNECTOR_LOGGING_PREFIX)
            prefix = f"{current_time} {Logging.get_aligned_level_name(level)} {log_origin} "
            message = Logging.get_formatted_log(message, prefix)
            print(Logging.colorize(f"{prefix}{message}", level))
        else:
            escaped_message = json.dumps(message)
            log_message = f'{{"level":"{level.name}", "message": {escaped_message}, "message_origin": "connector_sdk"}}'
            print(log_message)

    @staticmethod
    def get_formatted_log(message, prefix):
        lines = message.split('\n')
        padding = "\n" + " " * Logging.get_display_width(prefix)
        return padding.join(lines)

    @staticmethod
    def _should_use_colors() -> bool:
        """Check if ANSI colors should be used.
        Colors are only safe when output goes to a terminal (TTY).
        When redirected to files or pipes, color codes become garbage text.
        """
        
        # Use colors only if running via CLI AND output is a terminal
        return constants.EXECUTED_VIA_CLI and sys.stdout.isatty()

    @staticmethod
    def get_aligned_level_name(level: Level) -> str:
        return level.name.ljust(len(Logging.Level.CRITICAL.name))

    @staticmethod
    def get_aligned_log_origin(origin: str) -> str:
        known_origins = (
            constants.SDK_LOGGING_PREFIX.strip(),
            constants.DEBUGGER_LOGGING_PREFIX,
            constants.CONNECTOR_LOGGING_PREFIX,
        )
        target_width = max(Logging.get_display_width(known_origin) for known_origin in known_origins)
        padding = target_width - Logging.get_display_width(origin)
        return origin + " " * max(0, padding)

    @staticmethod
    def get_display_width(value: str) -> int:
        return sum(
            2 if unicodedata.east_asian_width(character) in ("W", "F") else 1
            for character in value
        )

    @staticmethod
    def get_color(level):
        if not Logging._should_use_colors():
            return ""
        
        if level == Logging.Level.WARNING:
            # 38;5; = 256-color mode (required for color codes 108-255)
            return "\033[38;5;130m"  # ANSI Orange-like color #af5f00
        elif level in (Logging.Level.SEVERE, Logging.Level.ERROR, Logging.Level.CRITICAL):
            return "\033[38;5;196m"  # ANSI Red color #ff0000
        return ""

    @staticmethod
    def reset_color(level):
        # Only emit reset if this level actually applies a color; avoids no-op noise
        if not Logging.get_color(level):
            return ""
        return " \033[0m"

    @staticmethod
    def colorize(text: str, level) -> str:
        """Wrap text with the color for the given level, and reset it afterward.

        Returns text unchanged if the level has no color or colors are disabled.
        """
        color = Logging.get_color(level)
        if not color:
            return text
        return f"{color}{text}{Logging.reset_color(level)}"

    @staticmethod
    def debug(message: str):
        """Logs a debug-level message.

        Args:
            message (str): The message to log.
        """
        if constants.DEBUGGING and Logging.LOG_LEVEL <= Logging.Level.DEBUG:
            Logging.__log(Logging.Level.DEBUG, message)

    @staticmethod
    @deprecated("fine() is deprecated, use debug() instead for Python-style logging")
    def fine(message: str):
        """Logs a fine-level message.

        Args:
            message (str): The message to log.
        """
        if constants.DEBUGGING and Logging.LOG_LEVEL <= Logging.Level.FINE:
            Logging.__log(Logging.Level.FINE, message)

    @staticmethod
    def info(message: str):
        """Logs an info-level message.

        Args:
            message (str): The message to log.
        """
        if Logging.LOG_LEVEL <= Logging.Level.INFO:
            Logging.__log(Logging.Level.INFO, message)

    @staticmethod
    def warning(message: str):
        """Logs a warning-level message.

        Args:
            message (str): The message to log.
        """
        if Logging.LOG_LEVEL <= Logging.Level.WARNING:
            Logging.__log(Logging.Level.WARNING, message)

    @staticmethod
    def error(message: str, exception: Exception = None):
        """Logs an error-level message.

        Args:
            message (str): The message to log.
            exception (Exception, optional): Exception to be logged if provided.
        """
        if Logging.LOG_LEVEL <= Logging.Level.ERROR:
            if exception:
                exc_type, exc_value, exc_traceback = type(exception), exception, exception.__traceback__
                tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback, limit=1))
                message += "\n" + tb_str
            Logging.__log(Logging.Level.ERROR, message)

    @staticmethod
    @deprecated("severe() is deprecated, use error() or critical() instead for Python-style logging")
    def severe(message: str, exception: Exception = None):
        """Logs a severe-level message.

        Args:
            message (str): The message to log.
            exception (Exception, optional): Exception to be logged if provided.
        """
        if Logging.LOG_LEVEL <= Logging.Level.SEVERE:
            if exception:
                exc_type, exc_value, exc_traceback = type(exception), exception, exception.__traceback__
                tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback, limit=1))
                message += "\n" + tb_str
            Logging.__log(Logging.Level.SEVERE, message)


    @staticmethod
    def critical(message: str, exception: Exception = None):
        """Logs a critical-level message.

        Args:
            message (str): The message to log.
            exception (Exception, optional): Exception to be logged if provided.
        """
        if Logging.LOG_LEVEL <= Logging.Level.CRITICAL:
            if exception:
                exc_type, exc_value, exc_traceback = type(exception), exception, exception.__traceback__
                tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback, limit=1))
                message += "\n" + tb_str
            Logging.__log(Logging.Level.CRITICAL, message)
