from unittest.mock import patch
import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from fivetran_connector_sdk import Logging
from fivetran_connector_sdk import constants

class LoggingSpec(unittest.TestCase):
    def setUp(self):
        """Save original global state before each test"""
        self.original_log_level = Logging.LOG_LEVEL
        self.original_debugging = constants.DEBUGGING
        self.original_executed_via_cli = constants.EXECUTED_VIA_CLI

    def tearDown(self):
        """Restore original global state after each test"""
        Logging.LOG_LEVEL = self.original_log_level
        constants.DEBUGGING = self.original_debugging
        constants.EXECUTED_VIA_CLI = self.original_executed_via_cli

    def test_log_levels(self) -> None:
        self.assertEqual(Logging.Level.DEBUG, 1)
        self.assertEqual(Logging.Level.FINE, 2)
        self.assertEqual(Logging.Level.INFO, 3)
        self.assertEqual(Logging.Level.WARNING, 4)
        self.assertEqual(Logging.Level.ERROR, 5)
        self.assertEqual(Logging.Level.SEVERE, 6)
        self.assertEqual(Logging.Level.CRITICAL, 7)

    def test_log_level_names_are_aligned_to_critical(self) -> None:
        expected_names = {
            Logging.Level.DEBUG: "DEBUG   ",
            Logging.Level.FINE: "FINE    ",
            Logging.Level.INFO: "INFO    ",
            Logging.Level.WARNING: "WARNING ",
            Logging.Level.ERROR: "ERROR   ",
            Logging.Level.SEVERE: "SEVERE  ",
            Logging.Level.CRITICAL: "CRITICAL",
        }

        for level, expected_name in expected_names.items():
            with self.subTest(level=level):
                self.assertEqual(Logging.get_aligned_level_name(level), expected_name)

    def test_log_origins_are_aligned_to_debugger(self) -> None:
        self.assertEqual(Logging.get_aligned_log_origin("⚡ sdk"), "⚡ sdk      ")
        self.assertEqual(Logging.get_aligned_log_origin("⚡ debugger"), "⚡ debugger ")
        self.assertEqual(Logging.get_aligned_log_origin("⚡ connector"), "⚡ connector")
        self.assertEqual(Logging.get_display_width("⚡ sdk      "), 12)
        self.assertEqual(Logging.get_display_width("⚡ debugger "), 12)
        self.assertEqual(Logging.get_display_width("⚡ connector"), 12)

    @patch('sys.stdout.isatty', return_value=True)
    def test_get_color_and_reset_color(self, mock_isatty):
        constants.EXECUTED_VIA_CLI = True
        
        self.assertEqual(Logging.get_color(Logging.Level.DEBUG), "")
        self.assertEqual(Logging.get_color(Logging.Level.INFO), "")
        self.assertEqual(Logging.get_color(Logging.Level.WARNING), "\033[38;5;130m")
        self.assertEqual(Logging.get_color(Logging.Level.ERROR), "\033[38;5;196m")
        self.assertEqual(Logging.get_color(Logging.Level.SEVERE), "\033[38;5;196m")
        self.assertEqual(Logging.get_color(Logging.Level.CRITICAL), "\033[38;5;196m")
        # No color applied for DEBUG/INFO, so reset should be a no-op
        self.assertEqual(Logging.reset_color(Logging.Level.DEBUG), "")
        self.assertEqual(Logging.reset_color(Logging.Level.INFO), "")
        self.assertEqual(Logging.reset_color(Logging.Level.WARNING), " \033[0m")
        self.assertEqual(Logging.reset_color(Logging.Level.ERROR), " \033[0m")

    @patch('sys.stdout.isatty', return_value=True)
    def test_colorize(self, mock_isatty):
        constants.EXECUTED_VIA_CLI = True
        
        # No color for DEBUG/INFO: text returned unchanged
        self.assertEqual(Logging.colorize("msg", Logging.Level.DEBUG), "msg")
        self.assertEqual(Logging.colorize("msg", Logging.Level.INFO), "msg")
        # Colored levels: wrapped with color code and reset
        self.assertEqual(Logging.colorize("msg", Logging.Level.WARNING), "\033[38;5;130mmsg \033[0m")
        self.assertEqual(Logging.colorize("msg", Logging.Level.ERROR), "\033[38;5;196mmsg \033[0m")

    @patch('builtins.print')
    def test_escaping_special_characters_from_logs(self, mock_print) -> None:
        from fivetran_connector_sdk import print_library_log
        constants.DEBUGGING = False
        constants.EXECUTED_VIA_CLI = False
        log_message = "[INFO] [2025-01-21 15:45:32] [~!@#$%^&*()_+{}|:\"<>?`-=_] Process started... 🚀💻 📂 [✔️] Valid ✔️ {var1=123, var2=!@#$, var3=~!}{}"
        expected_output = '{"level":"SEVERE", "message": "\\u26a1 sdk [INFO] [2025-01-21 15:45:32] [~!@#$%^&*()_+{}|:\\"<>?`-=_] Process started... \\ud83d\\ude80\\ud83d\\udcbb \\ud83d\\udcc2 [\\u2714\\ufe0f] Valid \\u2714\\ufe0f {var1=123, var2=!@#$, var3=~!}{}", "message_origin": "library"}'
        print_library_log(log_message, Logging.Level.SEVERE)
        mock_print.assert_called_once_with(expected_output)

    @patch('builtins.print')
    def test_log_level_filtering(self, mock_print):
        Logging.LOG_LEVEL = Logging.Level.WARNING
        Logging.fine("Should not print")
        Logging.info("Should not print")
        Logging.warning("Should print warning")
        Logging.severe("Should print severe")
        self.assertEqual(mock_print.call_count, 2)
        args = [call[0][0] for call in mock_print.call_args_list]
        self.assertIn("WARNING", args[0])
        self.assertIn("SEVERE", args[1])

    @patch('builtins.print')
    def test_all_log_methods(self, mock_print):
        Logging.LOG_LEVEL = Logging.Level.FINE
        constants.DEBUGGING = True
        Logging.fine("Fine message")
        Logging.info("Info message")
        Logging.warning("Warning message")
        Logging.severe("Severe message")
        self.assertEqual(mock_print.call_count, 4)
        calls = [call[0][0] for call in mock_print.call_args_list]
        self.assertRegex(calls[0], r"^\d{2}:\d{2}:\d{2}\.\d{3} FINE")
        self.assertIn("FINE     ⚡ connector Fine message", calls[0])
        self.assertIn("INFO     ⚡ connector Info message", calls[1])
        self.assertIn("WARNING  ⚡ connector Warning message", calls[2])
        self.assertIn("SEVERE   ⚡ connector Severe message", calls[3])

    @patch('builtins.print')
    def test_severe_with_exception(self, mock_print):
        Logging.LOG_LEVEL = Logging.Level.SEVERE
        constants.DEBUGGING = False
        try:
            raise ValueError("Test error")
        except Exception as e:
            Logging.severe("Severe with exception", e)
            # Should print a message containing the exception traceback
            args = mock_print.call_args[0][0]
            self.assertIn("Severe with exception", args)
            self.assertIn("ValueError", args)

    def test_get_formatted_log_multiline(self):
        prefix = "PREFIX: "
        message = "Line1\nLine2\nLine3"
        formatted = Logging.get_formatted_log(message, prefix)
        expected_indent = Logging.get_display_width(prefix)
        self.assertIn("\n" + " " * expected_indent, formatted)
        self.assertTrue(formatted.startswith("Line1"))

    @patch('builtins.print')
    def test_fine_level_logging(self, mock_print):
        Logging.LOG_LEVEL = Logging.Level.FINE
        constants.DEBUGGING = True
        Logging.fine("Fine log message")
        mock_print.assert_called()
        self.assertIn("Fine log message", mock_print.call_args[0][0])

    @patch('builtins.print')
    def test_log_level_above_threshold(self, mock_print):
        Logging.LOG_LEVEL = Logging.Level.SEVERE
        Logging.info("Should not print")
        Logging.warning("Should not print")
        # Only severe should print
        Logging.severe("Should print")
        self.assertEqual(mock_print.call_count, 1)
        self.assertIn("Should print", mock_print.call_args[0][0])

    def test_get_color_for_fine(self):
        # FINE is not WARNING or SEVERE, should return ""
        self.assertEqual(Logging.get_color(Logging.Level.FINE), "")

    @patch('builtins.print')
    def test_fine_with_debugging_off(self, mock_print):
        """Test fine level logging when debugging is off"""
        Logging.LOG_LEVEL = Logging.Level.FINE
        constants.DEBUGGING = False
        Logging.fine("Should not print when DEBUG is False")
        # Fine only logs when DEBUG is True
        mock_print.assert_not_called()

    @patch('builtins.print')
    def test_info_with_log_level_above_info(self, mock_print):
        """Test info level logging when log level is WARNING"""
        Logging.LOG_LEVEL = Logging.Level.WARNING
        Logging.info("Should not print when LOG_LEVEL is WARNING")
        mock_print.assert_not_called()

    @patch('builtins.print')
    def test_warning_with_log_level_above_warning(self, mock_print):
        """Test warning level logging when log level is SEVERE"""
        Logging.LOG_LEVEL = Logging.Level.SEVERE
        Logging.warning("Should not print when LOG_LEVEL is SEVERE")
        mock_print.assert_not_called()

    @patch('builtins.print')
    def test_severe_without_exception_debugging_mode(self, mock_print):
        """Test severe level logging without exception in debugging mode"""
        Logging.LOG_LEVEL = Logging.Level.SEVERE
        constants.DEBUGGING = True
        Logging.severe("Severe without exception")
        mock_print.assert_called_once()
        args = mock_print.call_args[0][0]
        self.assertIn("Severe without exception", args)
        self.assertNotIn("Traceback", args)

    @patch('builtins.print')
    def test_log_with_non_debugging_mode(self, mock_print):
        """Test logging in non-debugging mode outputs JSON"""
        Logging.LOG_LEVEL = Logging.Level.INFO
        constants.DEBUGGING = False
        Logging.info("Test message")

        # Should output JSON format
        args = mock_print.call_args[0][0]
        self.assertIn('"level":"INFO"', args)
        self.assertIn('"message":', args)
        self.assertIn('"message_origin": "connector_sdk"', args)

    @patch('builtins.print')
    def test_get_formatted_log_with_single_line(self, mock_print):
        """Test formatted log with single line message"""
        formatted = Logging.get_formatted_log("Single line", "PREFIX: ")
        self.assertEqual(formatted, "Single line")

    @patch('builtins.print')
    def test_severe_with_exception_in_non_debugging_mode(self, mock_print):
        """Test severe logging with exception in non-debugging mode"""
        Logging.LOG_LEVEL = Logging.Level.SEVERE
        constants.DEBUGGING = False

        try:
            raise RuntimeError("Test runtime error")
        except Exception as e:
            Logging.severe("Error occurred", e)

        args = mock_print.call_args[0][0]
        self.assertIn("Error occurred", args)
        self.assertIn("RuntimeError", args)

    def test_log_level_enum_values(self):
        """Test that log level enum values are correct"""
        self.assertLess(Logging.Level.DEBUG, Logging.Level.FINE)
        self.assertLess(Logging.Level.FINE, Logging.Level.INFO)
        self.assertLess(Logging.Level.INFO, Logging.Level.WARNING)
        self.assertLess(Logging.Level.WARNING, Logging.Level.ERROR)
        self.assertLess(Logging.Level.ERROR, Logging.Level.SEVERE)
        self.assertLess(Logging.Level.SEVERE, Logging.Level.CRITICAL)

    @patch('builtins.print')
    def test_fine_with_log_level_above_fine(self, mock_print):
        """Test that fine level logging uses <= comparison"""
        Logging.LOG_LEVEL = Logging.Level.INFO
        constants.DEBUGGING = True
        Logging.fine("Should not print when LOG_LEVEL is INFO")
        mock_print.assert_not_called()

    @patch('builtins.print')
    def test_fine_with_log_level_below_fine(self, mock_print):
        """Test that fine level logging works when LOG_LEVEL <= FINE"""
        Logging.LOG_LEVEL = Logging.Level.DEBUG
        constants.DEBUGGING = True
        # DEBUG (0) <= FINE (1) is True, should print
        Logging.fine("Should print when LOG_LEVEL is DEBUG")
        mock_print.assert_called_once()
        self.assertIn("Should print when LOG_LEVEL is DEBUG", mock_print.call_args[0][0])

    @patch('builtins.print')
    def test_debug_method(self, mock_print):
        """Test debug method works correctly"""
        Logging.LOG_LEVEL = Logging.Level.DEBUG
        constants.DEBUGGING = True
        Logging.debug("Debug message")
        mock_print.assert_called_once()
        self.assertIn("Debug message", mock_print.call_args[0][0])

    @patch('builtins.print')
    def test_debug_requires_debugging_mode(self, mock_print):
        """Test that debug() requires DEBUGGING=True"""
        Logging.LOG_LEVEL = Logging.Level.DEBUG
        constants.DEBUGGING = False
        Logging.debug("Should not print in production")
        mock_print.assert_not_called()

    @patch('builtins.print')
    def test_debug_filtered_by_log_level(self, mock_print):
        """Test that debug() is filtered when LOG_LEVEL > DEBUG"""
        Logging.LOG_LEVEL = Logging.Level.INFO
        constants.DEBUGGING = True
        Logging.debug("Should not print when LOG_LEVEL is INFO")
        mock_print.assert_not_called()

    @patch('builtins.print')
    def test_error_method(self, mock_print):
        """Test error method works correctly"""
        Logging.LOG_LEVEL = Logging.Level.ERROR
        constants.DEBUGGING = False
        Logging.error("Error message")
        mock_print.assert_called_once()
        args = mock_print.call_args[0][0]
        self.assertIn('"level":"ERROR"', args)
        self.assertIn("Error message", args)

    @patch('builtins.print')
    def test_error_with_exception(self, mock_print):
        """Test error method with exception"""
        Logging.LOG_LEVEL = Logging.Level.ERROR
        constants.DEBUGGING = False
        try:
            raise ValueError("Test error")
        except Exception as e:
            Logging.error("Error occurred", e)
        args = mock_print.call_args[0][0]
        self.assertIn("Error occurred", args)
        self.assertIn("ValueError", args)

    @patch('builtins.print')
    def test_critical_method(self, mock_print):
        """Test critical method works correctly"""
        Logging.LOG_LEVEL = Logging.Level.CRITICAL
        constants.DEBUGGING = False
        Logging.critical("Critical message")
        mock_print.assert_called_once()
        args = mock_print.call_args[0][0]
        self.assertIn('"level":"CRITICAL"', args)
        self.assertIn("Critical message", args)

    @patch('builtins.print')
    def test_critical_with_exception(self, mock_print):
        """Test critical method with exception"""
        Logging.LOG_LEVEL = Logging.Level.CRITICAL
        constants.DEBUGGING = False
        try:
            raise RuntimeError("Critical error")
        except Exception as e:
            Logging.critical("System failure", e)
        args = mock_print.call_args[0][0]
        self.assertIn("System failure", args)
        self.assertIn("RuntimeError", args)

    @patch('builtins.print')
    def test_all_new_log_methods(self, mock_print):
        """Test all new log methods print when LOG_LEVEL=DEBUG"""
        Logging.LOG_LEVEL = Logging.Level.DEBUG
        constants.DEBUGGING = True
        Logging.debug("Debug message")
        Logging.info("Info message")
        Logging.warning("Warning message")
        Logging.error("Error message")
        Logging.critical("Critical message")
        self.assertEqual(mock_print.call_count, 5)

    @patch('builtins.print')
    def test_error_and_critical_in_production(self, mock_print):
        """Test that error() and critical() work in production mode"""
        Logging.LOG_LEVEL = Logging.Level.INFO
        constants.DEBUGGING = False
        Logging.error("Production error")
        Logging.critical("Production critical")
        self.assertEqual(mock_print.call_count, 2)
        args = [call[0][0] for call in mock_print.call_args_list]
        self.assertIn('"level":"ERROR"', args[0])
        self.assertIn('"level":"CRITICAL"', args[1])

if __name__ == '__main__':
    unittest.main()
