import tempfile
import unittest
from unittest import TestCase
from unittest.mock import patch, MagicMock
import sys
import os
import stat
import threading
from fivetran_connector_sdk.helpers import _validate_table_name, PromptMode, _resolve_existing_project_path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

class TestHelper(TestCase):
   DUMMY_PROJECT_PATH = '/dummy/project'

   def setUp(self):
       from fivetran_connector_sdk import constants
       self.constants = constants
       self.orig_debugging = constants.DEBUGGING
       self.orig_executed = constants.EXECUTED_VIA_CLI

   def tearDown(self):
       self.constants.DEBUGGING = self.orig_debugging
       self.constants.EXECUTED_VIA_CLI = self.orig_executed

   @patch('importlib.util.spec_from_file_location')
   @patch('importlib.util.module_from_spec')
   @patch('fivetran_connector_sdk.helpers.print_library_log')
   def test_find_connector_object_success(self, mock_log, mock_module_from_spec, mock_spec_from_file_location):
       FakeConnector = type('Connector', (), {'__module__': 'fivetran_connector_sdk'})
       mock_connector = FakeConnector()
       mock_module = MagicMock()
       mock_module.connector = mock_connector
       mock_module_from_spec.return_value = mock_module
       mock_loader = MagicMock()
       mock_loader.exec_module = MagicMock()
       mock_spec = MagicMock()
       mock_spec.loader = mock_loader
       mock_spec_from_file_location.return_value = mock_spec
       with patch.object(sys, 'path', new=[]):
           from fivetran_connector_sdk.helpers import find_connector_object
           result = find_connector_object(self.DUMMY_PROJECT_PATH)
           self.assertEqual(result, mock_connector)

   @patch('fivetran_connector_sdk.helpers.print_library_log')
   def test_find_connector_object_file_not_found(self, mock_log):
       with (patch('importlib.util.spec_from_file_location', side_effect=FileNotFoundError)):
           from fivetran_connector_sdk.helpers import find_connector_object
           from fivetran_connector_sdk import Logging
           result = find_connector_object(self.DUMMY_PROJECT_PATH)
           self.assertIsNone(result)
           mock_log.assert_any_call(
               f"connector.py not found in {self.DUMMY_PROJECT_PATH}\nthis file is required to start a sync\nreference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector",
               Logging.Level.SEVERE
           )

   @patch('importlib.util.spec_from_file_location')
   @patch('importlib.util.module_from_spec')
   @patch('fivetran_connector_sdk.helpers.print_library_log')
   def test_find_connector_object_wrong_name(self, mock_log, mock_module_from_spec, mock_spec_from_file_location):
       FakeConnector = type('Connector', (), {'__module__': 'fivetran_connector_sdk'})
       mock_module = MagicMock()
       mock_module.my_connector = FakeConnector()
       mock_module_from_spec.return_value = mock_module
       mock_loader = MagicMock()
       mock_loader.exec_module = MagicMock()
       mock_spec = MagicMock()
       mock_spec.loader = mock_loader
       mock_spec_from_file_location.return_value = mock_spec
       with patch.object(sys, 'path', new=[]):
           from fivetran_connector_sdk.helpers import find_connector_object
           from fivetran_connector_sdk import Logging
           result = find_connector_object(self.DUMMY_PROJECT_PATH)
           self.assertIsNone(result)
           logged_message = mock_log.call_args[0][0]
           self.assertIn("Connector object must be named 'connector'", logged_message)
           self.assertIn("'my_connector'", logged_message)
           self.assertEqual(mock_log.call_args[0][1], Logging.Level.SEVERE)

   @patch('importlib.util.spec_from_file_location')
   @patch('importlib.util.module_from_spec')
   @patch('fivetran_connector_sdk.helpers.print_library_log')
   def test_find_connector_object_no_connector_found(self, mock_log, mock_module_from_spec, mock_spec_from_file_location):
       mock_module = MagicMock()
       mock_module.some_other_object = MagicMock()
       mock_module_from_spec.return_value = mock_module
       mock_loader = MagicMock()
       mock_loader.exec_module = MagicMock()
       mock_spec = MagicMock()
       mock_spec.loader = mock_loader
       mock_spec_from_file_location.return_value = mock_spec

       with patch.object(sys, 'path', new=[]):
           from fivetran_connector_sdk.helpers import find_connector_object
           from fivetran_connector_sdk import Logging
           result = find_connector_object(self.DUMMY_PROJECT_PATH)
           self.assertIsNone(result)
           mock_log.assert_any_call(
               "connector object not found\ndefine a Connector object in connector.py\nreference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference#technicaldetailsrequiredobjectconnector",
               Logging.Level.SEVERE
           )

   @patch('importlib.util.spec_from_file_location')
   @patch('importlib.util.module_from_spec')
   @patch('fivetran_connector_sdk.helpers.print_library_log')
   def test_find_connector_object_type_error(self, mock_log, mock_module_from_spec, mock_spec_from_file_location):
       mock_module_from_spec.return_value = MagicMock()
       mock_loader = MagicMock()
       mock_loader.exec_module.side_effect = TypeError("Connector.__init__() got an unexpected keyword argument 'test'")
       mock_spec = MagicMock()
       mock_spec.loader = mock_loader
       mock_spec_from_file_location.return_value = mock_spec

       with patch.object(sys, 'path', new=[]):
           from fivetran_connector_sdk.helpers import find_connector_object
           from fivetran_connector_sdk import Logging
           result = find_connector_object(self.DUMMY_PROJECT_PATH)
           self.assertIsNone(result)
           logged_message = mock_log.call_args[0][0]
           self.assertIn("error in connector.py", logged_message)
           self.assertIn("Connector.__init__() got an unexpected keyword argument 'test'", logged_message)
           self.assertIn("reference: https://fivetran.com/docs/connectors/connector-sdk/technical-reference", logged_message)
           self.assertEqual(mock_log.call_args[0][1], Logging.Level.SEVERE)

   def test_suggest_correct_command_typo(self):
       from fivetran_connector_sdk.helpers import suggest_correct_command
       # Should suggest 'debug' for 'debig'
       with patch("fivetran_connector_sdk.helpers.print_suggested_command_message") as mock_print:
           self.assertTrue(suggest_correct_command("debig"))
           mock_print.assert_called()

   def test_suggest_correct_command_synonym_branch(self):
       from fivetran_connector_sdk.helpers import suggest_correct_command
       from fivetran_connector_sdk.constants import COMMANDS_AND_SYNONYMS
       for command, synonyms in COMMANDS_AND_SYNONYMS.items():
           if synonyms:
               synonym = next(iter(synonyms))
               result = suggest_correct_command(synonym)
               self.assertTrue(result)
               break
           else:
               self.skipTest("No synonyms defined in COMMANDS_AND_SYNONYMS")

       # Use a string that is not a synonym and not close to any valid command
       result = suggest_correct_command("iknowthisisntacommandbuttryanyway")
       self.assertFalse(result)

       with patch("fivetran_connector_sdk.helpers.print_suggested_command_message") as mock_print:
           assert suggest_correct_command("ship")
           mock_print.assert_called_once()


   def test_suggest_correct_command_invalid(self):
       from fivetran_connector_sdk.helpers import suggest_correct_command
       self.assertFalse(suggest_correct_command("notacommand"))

   def test_print_suggested_command_message(self):
       from fivetran_connector_sdk.helpers import print_suggested_command_message
       with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
           print_suggested_command_message("debug", "debig")
           self.assertEqual(mock_log.call_count, 3)

   def test_edit_distance(self):
       from fivetran_connector_sdk.helpers import edit_distance
       self.assertEqual(edit_distance("kitten", "sitting"), 3)
       self.assertEqual(edit_distance("abc", "abc"), 0)
       self.assertEqual(edit_distance("", "abc"), 3)

   @patch('fivetran_connector_sdk.helpers.prompt')
   def test_get_input_from_cli_with_default(self, mock_prompt):
       from fivetran_connector_sdk.helpers import get_input_from_cli
       mock_prompt.return_value.strip.return_value = ""
       self.assertEqual(get_input_from_cli("Prompt", "default"), "default")

   @patch('fivetran_connector_sdk.helpers.prompt')
   def test_get_input_from_cli_without_default(self, mock_prompt):
       from fivetran_connector_sdk.helpers import get_input_from_cli
       mock_prompt.return_value.strip.return_value = "value"
       self.assertEqual(get_input_from_cli("Prompt", ""), "value")

   @patch('fivetran_connector_sdk.helpers.prompt')
   def test_get_input_from_cli_missing(self, mock_prompt):
       from fivetran_connector_sdk.helpers import get_input_from_cli
       mock_prompt.return_value.strip.return_value = ""
       with self.assertRaises(ValueError):
           get_input_from_cli("Prompt", "")

   def test_validate_and_load_configuration_file(self):
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import tempfile, json
       class Args:
           project_path = ""
           configuration = "config.json"
       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           config_path = os.path.join(tmpdir, "config.json")
           with open(config_path, "w", encoding="utf-8") as f:
               json.dump({"a": 1}, f)
           config = validate_and_load_configuration(args.project_path, "config.json")
           self.assertEqual(config, {"a": 1})


   def test_validate_and_load_configuration_too_many_fields(self):
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import tempfile, json
       class Args:
           project_path = ""
           configuration = "config.json"

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           config_path = os.path.join(tmpdir, "config.json")
           with open(config_path, "w", encoding="utf-8") as f:
               json.dump({str(i): i for i in range(101)}, f)
           with self.assertRaises(ValueError):
               validate_and_load_configuration(args.project_path, "config.json")

   def test_validate_and_load_configuration_no_file(self):
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       class Args:
           project_path = ""
           configuration = "notfound.json"
       args = Args()
       with self.assertRaises(ValueError):
           validate_and_load_configuration(args.project_path, "notfound.json")

   def test_validate_and_load_state_file(self):
       from fivetran_connector_sdk.helpers import validate_and_load_state
       import tempfile, json
       class Args:
           project_path = ""
           state = "state.json"

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           state_path = os.path.join(tmpdir, "state.json")
           with open(state_path, "w", encoding="utf-8") as f:
               json.dump({"cursor": 1}, f)
           state = validate_and_load_state(args, "state.json")
           self.assertEqual(state, {"cursor": 1})


   def test_validate_and_load_state_no_file(self):
       from fivetran_connector_sdk.helpers import validate_and_load_state
       class Args:
           project_path = ""
           state = "notfound.json"

       args = Args()
       state = validate_and_load_state(args, None)
       self.assertEqual(state, {})

   def test_reset_local_file_directory(self):
       from fivetran_connector_sdk.helpers import reset_local_file_directory
       from fivetran_connector_sdk.logger import Logging
       import tempfile
       class Args:
           non_interactive = True
           project_path = ""

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           files_dir = os.path.join(tmpdir, "files")
           os.makedirs(files_dir)
           with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
               reset_local_file_directory(args, PromptMode.FORCE)
               mock_log.assert_any_call("reset successful", log_icon=Logging.LogIcon.SUCCESS)

   def test_reset_local_file_directory_cancel(self):
       from fivetran_connector_sdk.helpers import reset_local_file_directory
       import tempfile
       class Args:
           non_interactive = False
           project_path = ""

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           with patch("builtins.input", return_value="n"):
               with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
                   reset_local_file_directory(args, PromptMode.INTERACTIVE)
                   mock_log.assert_any_call("reset cancelled")


   def test_reset_local_file_directory_exception(self):
       from fivetran_connector_sdk.helpers import reset_local_file_directory
       from fivetran_connector_sdk import Logging
       class Args:
           non_interactive = True
           project_path = ""

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           files_dir = os.path.join(tmpdir, "files")
           os.makedirs(files_dir)
           # Patch shutil.rmtree to raise an exception
           with patch("shutil.rmtree", side_effect=Exception("fail")):
               with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
                   with self.assertRaises(Exception):
                       reset_local_file_directory(args, PromptMode.FORCE)
                   mock_log.assert_any_call("reset failed", level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)


   def test_prompt_mode_enum_values(self):
       """PromptMode values are CLI flag strings (or None for INTERACTIVE)."""
       from fivetran_connector_sdk.helpers import PromptMode
       self.assertIsNone(PromptMode.INTERACTIVE.value)
       self.assertEqual(PromptMode.DEFAULT_ANSWER.value, "--non-interactive")
       self.assertEqual(PromptMode.YES.value, "--yes")
       self.assertEqual(PromptMode.FORCE.value, "--force")

   def test_prompt_mode_is_non_interactive_mode(self):
       """is_non_interactive_mode is False only for INTERACTIVE."""
       from fivetran_connector_sdk.helpers import PromptMode
       self.assertFalse(PromptMode.INTERACTIVE.is_non_interactive_mode)
       self.assertTrue(PromptMode.DEFAULT_ANSWER.is_non_interactive_mode)
       self.assertTrue(PromptMode.YES.is_non_interactive_mode)
       self.assertTrue(PromptMode.FORCE.is_non_interactive_mode)

   def test_prompt_mode_from_args_all_modes(self):
       """from_args returns correct mode for each flag combination."""
       from fivetran_connector_sdk.helpers import PromptMode
       self.assertEqual(PromptMode.from_args(False, False, False), PromptMode.INTERACTIVE)
       self.assertEqual(PromptMode.from_args(True, False, False), PromptMode.DEFAULT_ANSWER)
       self.assertEqual(PromptMode.from_args(False, False, True), PromptMode.YES)
       self.assertEqual(PromptMode.from_args(False, True, False), PromptMode.FORCE)

   def test_prompt_mode_from_args_mutual_exclusion(self):
       """from_args raises ValueError for any two flags together."""
       from fivetran_connector_sdk.helpers import PromptMode
       with self.assertRaises(ValueError):
           PromptMode.from_args(True, False, True)   # --non-interactive + --yes
       with self.assertRaises(ValueError):
           PromptMode.from_args(False, True, True)   # --force + --yes
       with self.assertRaises(ValueError):
           PromptMode.from_args(True, True, False)   # --non-interactive + --force

   def test_reset_with_yes_proceeds(self):
       """reset_local_file_directory with PromptMode.YES proceeds without prompt."""
       from fivetran_connector_sdk.helpers import reset_local_file_directory, PromptMode
       from fivetran_connector_sdk.logger import Logging
       import tempfile
       class Args:
           project_path = ""
       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           files_dir = os.path.join(tmpdir, "files")
           os.makedirs(files_dir)
           with patch("builtins.input") as mock_input, \
                patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
               reset_local_file_directory(args, PromptMode.YES)
               mock_input.assert_not_called()
               mock_log.assert_any_call("reset successful", log_icon=Logging.LogIcon.SUCCESS)

   def test_validate_and_load_state_json_string(self):
       from fivetran_connector_sdk.helpers import validate_and_load_state
       class Args:
           project_path = ""
           state = "state.json"  # Set to a string, not None

       state = '{"foo": 1}'
       args = Args()
       # Patch os.path.exists to False, os.path.isfile to False
       result = validate_and_load_state(args, state)
       assert result == {}

   def test_validate_and_load_state_not_file_raises_error(self):
       from fivetran_connector_sdk.helpers import validate_and_load_state
       class Args:
           project_path = ""
           state = "state.json"

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           # Create a subdirectory to use as state path (neither file nor FIFO)
           state_dir = os.path.join(tmpdir, "state.json")
           os.makedirs(state_dir)
           with self.assertRaises(ValueError) as cm:
               validate_and_load_state(args, "state.json")
           self.assertIn("cannot find file", str(cm.exception).lower())

   @unittest.skipIf(sys.platform == 'win32', "Unix sockets not supported on Windows")
   def test_validate_and_load_state_with_socket_raises_error(self):
       """Test validate_and_load_state raises ValueError for socket paths"""
       from fivetran_connector_sdk.helpers import validate_and_load_state
       import socket

       class Args:
           project_path = ""
           state = "state.sock"

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           socket_path = os.path.join(tmpdir, "state.sock")

           # Create a Unix socket
           sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
           try:
               sock.bind(socket_path)
               # Verify it's a socket (not a regular file or FIFO)
               self.assertTrue(stat.S_ISSOCK(os.stat(socket_path).st_mode))

               with self.assertRaises(ValueError) as cm:
                   validate_and_load_state(args, "state.sock")
               self.assertIn("cannot find file", str(cm.exception).lower())
           finally:
               sock.close()

   @unittest.skipIf(sys.platform == 'win32', "Unix sockets not supported on Windows")
   def test_validate_and_load_configuration_with_socket_raises_error(self):
       """Test validate_and_load_configuration raises ValueError for socket paths"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import socket

       with tempfile.TemporaryDirectory() as tmpdir:
           socket_path = os.path.join(tmpdir, "config.sock")

           # Create a Unix socket
           sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
           try:
               sock.bind(socket_path)
               # Verify it's a socket (not a regular file or FIFO)
               self.assertTrue(stat.S_ISSOCK(os.stat(socket_path).st_mode))

               with self.assertRaises(ValueError) as cm:
                   validate_and_load_configuration(tmpdir, "config.sock")
               self.assertIn("cannot find file", str(cm.exception).lower())
           finally:
               sock.close()

   def test_validate_and_load_configuration_directory_raises_error(self):
       """Test validate_and_load_configuration raises ValueError for directory paths"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration

       with tempfile.TemporaryDirectory() as tmpdir:
           # Create a subdirectory to use as config path (neither file nor FIFO)
           config_dir = os.path.join(tmpdir, "config.json")
           os.makedirs(config_dir)
           with self.assertRaises(ValueError) as cm:
               validate_and_load_configuration(tmpdir, "config.json")
           self.assertIn("cannot find file", str(cm.exception).lower())

   @patch("builtins.print")
   def test_print_library_log_debugging(self, mock_print):
       from fivetran_connector_sdk.helpers import print_library_log
       from fivetran_connector_sdk.logger import Logging
       self.constants.DEBUGGING = True
       self.constants.EXECUTED_VIA_CLI = False
       print_library_log("debug message", Logging.Level.INFO)
       rendered_message = mock_print.call_args.args[0]
       self.assertRegex(rendered_message, r"^\d{2}:\d{2}:\d{2}\.\d{3} INFO")
       self.assertIn("INFO     ⚡ sdk       debug message", rendered_message)

   @patch("builtins.print")
   def test_print_library_log_executed_via_cli(self, mock_print):
       from fivetran_connector_sdk.helpers import print_library_log
       from fivetran_connector_sdk.logger import Logging
       self.constants.DEBUGGING = False
       self.constants.EXECUTED_VIA_CLI = True
       print_library_log("cli message", Logging.Level.WARNING, log_icon=Logging.LogIcon.STEP, indent=True)
       mock_print.assert_called_once_with("  › cli message")

   @patch("builtins.print")
   def test_print_library_log_debug_cli_uses_verbose_format(self, mock_print):
       from fivetran_connector_sdk.helpers import print_library_log
       from fivetran_connector_sdk.logger import Logging
       self.constants.DEBUGGING = True
       self.constants.EXECUTED_VIA_CLI = True
       print_library_log("debug cli message", Logging.Level.WARNING)
       rendered_message = mock_print.call_args.args[0]
       self.assertIn("WARNING  ⚡ sdk       debug cli message", rendered_message)

   @patch("builtins.print")
   def test_print_library_log_else_branch(self, mock_print):
       from fivetran_connector_sdk.helpers import print_library_log
       from fivetran_connector_sdk.logger import Logging
       self.constants.DEBUGGING = False
       self.constants.EXECUTED_VIA_CLI = False
       print_library_log("library message", Logging.Level.SEVERE)
       mock_print.assert_called()

   def test_validate_and_load_configuration_default_file_warning(self):
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       from fivetran_connector_sdk.logger import Logging
       import tempfile, json

       class Args:
           project_path = ""
           configuration = None

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           config_path = os.path.join(tmpdir, "configuration.json")
           with open(config_path, "w", encoding="utf-8") as f:
               json.dump({"foo": "bar"}, f)
           with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
               config = validate_and_load_configuration(args.project_path, "configuration.json")
               self.assertEqual(config, {"foo": "bar"})

           with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
               config = validate_and_load_configuration(args.project_path, None)
               self.assertEqual(config, {})
               mock_log.assert_any_call("no configuration file passed", Logging.Level.INFO)

   @patch("builtins.print")
   def test_print_library_log_with_dev_log_debugging(self, mock_print):
       """Test print_library_log with dev_log=True in debugging mode"""
       from fivetran_connector_sdk.helpers import print_library_log
       from fivetran_connector_sdk.logger import Logging
       self.constants.DEBUGGING = True
       self.constants.EXECUTED_VIA_CLI = False
       # dev_log=True should cause no output in debugging mode
       print_library_log("dev message", Logging.Level.INFO, dev_log=True)
       mock_print.assert_not_called()

   @patch("builtins.print")
   def test_print_library_log_with_dev_log_non_debugging(self, mock_print):
       """Test print_library_log with dev_log=True in non-debugging mode"""
       from fivetran_connector_sdk.helpers import print_library_log
       from fivetran_connector_sdk.logger import Logging
       self.constants.DEBUGGING = False
       self.constants.EXECUTED_VIA_CLI = False
       print_library_log("dev message", Logging.Level.INFO, dev_log=True)
       # Should output as library_dev message_origin
       call_args = mock_print.call_args[0][0]
       self.assertIn('"message_origin": "library_dev"', call_args)

   @patch('fivetran_connector_sdk.helpers.prompt')
   def test_get_input_from_cli_with_hide_value(self, mock_prompt):
       """Test get_input_from_cli with hide_value=True"""
       from fivetran_connector_sdk.helpers import get_input_from_cli
       mock_prompt.return_value.strip.return_value = ""
       result = get_input_from_cli("Prompt", "secretvalue123", hide_value=True)
       # Should use default
       self.assertEqual(result, "secretvalue123")
       # Check that hidden default was shown in prompt
       call_args = mock_prompt.call_args[0][0]
       self.assertIn("secretva********", call_args)

   @patch('fivetran_connector_sdk.helpers.prompt')
   def test_get_input_from_cli_with_env_var_expansion(self, mock_prompt):
       """Test get_input_from_cli with environment variable expansion"""
       from fivetran_connector_sdk.helpers import get_input_from_cli
       mock_prompt.return_value.strip.return_value = "$HOME/test"
       with patch.dict(os.environ, {"HOME": "/home/user"}):
           result = get_input_from_cli("Prompt", "")
           self.assertEqual(result, "/home/user/test")

   def test_validate_and_load_configuration_with_invalid_json(self):
       """Test validate_and_load_configuration with invalid JSON content"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import tempfile

       with tempfile.TemporaryDirectory() as tmpdir:
           config_path = os.path.join(tmpdir, "config.json")
           with open(config_path, "w", encoding="utf-8") as f:
               f.write("{ invalid json")
           with self.assertRaises(ValueError) as cm:
               validate_and_load_configuration(tmpdir, "config.json")
           self.assertIn("Configuration must be provided as a JSON file", str(cm.exception))

   def test_validate_and_load_configuration_with_absolute_path(self):
       """Test validate_and_load_configuration with absolute path"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import tempfile, json

       with tempfile.TemporaryDirectory() as tmpdir:
           config_path = os.path.join(tmpdir, "config.json")
           with open(config_path, "w", encoding="utf-8") as f:
               json.dump({"key": "value"}, f)
           # Pass absolute path
           config = validate_and_load_configuration(tmpdir, config_path)
           self.assertEqual(config, {"key": "value"})

   def test_validate_and_load_configuration_with_expanduser(self):
       """Test validate_and_load_configuration with tilde expansion"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import tempfile, json

       with tempfile.TemporaryDirectory() as tmpdir:
           config_path = os.path.join(tmpdir, "config.json")
           with open(config_path, "w", encoding="utf-8") as f:
               json.dump({"key": "value"}, f)

           # Mock expanduser to return our temp dir
           with patch("os.path.expanduser", return_value=config_path):
               config = validate_and_load_configuration(tmpdir, "~/config.json")
               self.assertEqual(config, {"key": "value"})

   def test_edit_distance_edge_cases(self):
       """Test edit_distance with various edge cases"""
       from fivetran_connector_sdk.helpers import edit_distance
       # Empty strings
       self.assertEqual(edit_distance("", ""), 0)
       # Same string
       self.assertEqual(edit_distance("test", "test"), 0)
       # Complete replacement
       self.assertEqual(edit_distance("abc", "xyz"), 3)
       # Single character difference
       self.assertEqual(edit_distance("cat", "bat"), 1)
       # Longer strings
       self.assertEqual(edit_distance("saturday", "sunday"), 3)

   def test_environment_variable_completer(self):
       """Test EnvironmentVariableCompleter"""
       from fivetran_connector_sdk.helpers import EnvironmentVariableCompleter
       from prompt_toolkit.document import Document

       completer = EnvironmentVariableCompleter()
       with patch.dict(os.environ, {"TEST_VAR": "value", "TEST_VAR2": "value2"}):
           document = Document("$TEST")
           completions = list(completer.get_completions(document, None))
           self.assertGreaterEqual(len(completions), 2)
           completion_texts = [c.text for c in completions]
           self.assertIn("$TEST_VAR", completion_texts)
           self.assertIn("$TEST_VAR2", completion_texts)

   def test_environment_variable_completer_no_dollar(self):
       """Test EnvironmentVariableCompleter when no $ prefix"""
       from fivetran_connector_sdk.helpers import EnvironmentVariableCompleter
       from prompt_toolkit.document import Document

       completer = EnvironmentVariableCompleter()
       document = Document("TEST")
       completions = list(completer.get_completions(document, None))
       self.assertEqual(len(completions), 0)

   def test_env_var_path_completer(self):
       """Test EnvVarPathCompleter"""
       from fivetran_connector_sdk.helpers import EnvVarPathCompleter
       from prompt_toolkit.document import Document

       completer = EnvVarPathCompleter()
       with patch.dict(os.environ, {"HOME": "/home/user"}):
           document = Document("$HOME")
           # Just verify it doesn't crash and returns some completions
           completions = list(completer.get_completions(document, None))
           self.assertIsInstance(completions, list)

   def test_reset_local_file_directory_no_files_dir(self):
       """Test reset_local_file_directory when files directory doesn't exist"""
       from fivetran_connector_sdk.helpers import reset_local_file_directory
       from fivetran_connector_sdk.logger import Logging
       import tempfile

       class Args:
           non_interactive = True
           project_path = ""

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           # Don't create files directory
           with patch("fivetran_connector_sdk.helpers.print_library_log") as mock_log:
               reset_local_file_directory(args, PromptMode.FORCE)
               mock_log.assert_any_call(
                   "No files were deleted. Ensure you are in the project root directory.",
                   level=Logging.Level.SEVERE,
                   log_icon=Logging.LogIcon.FAILURE)

   def test_is_regular_file_or_fifo_with_regular_file(self):
       """Test is_regular_file_or_fifo returns True for regular files"""
       from fivetran_connector_sdk.helpers import is_regular_file_or_fifo

       with tempfile.TemporaryDirectory() as tmpdir:
           file_path = os.path.join(tmpdir, "test.txt")
           with open(file_path, "w", encoding="utf-8") as f:
               f.write("test")
           self.assertTrue(is_regular_file_or_fifo(file_path))

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_is_regular_file_or_fifo_with_fifo(self):
       """Test is_regular_file_or_fifo returns True for FIFOs"""
       from fivetran_connector_sdk.helpers import is_regular_file_or_fifo

       with tempfile.TemporaryDirectory() as tmpdir:
           fifo_path = os.path.join(tmpdir, "test_fifo")
           os.mkfifo(fifo_path)
           self.assertTrue(is_regular_file_or_fifo(fifo_path))

   def test_is_regular_file_or_fifo_with_directory(self):
       """Test is_regular_file_or_fifo returns False for directories"""
       from fivetran_connector_sdk.helpers import is_regular_file_or_fifo

       with tempfile.TemporaryDirectory() as tmpdir:
           self.assertFalse(is_regular_file_or_fifo(tmpdir))

   @unittest.skipIf(sys.platform == 'win32', "Unix sockets not supported on Windows")
   def test_is_regular_file_or_fifo_with_socket(self):
       """Test is_regular_file_or_fifo returns False for sockets"""
       from fivetran_connector_sdk.helpers import is_regular_file_or_fifo
       import socket

       with tempfile.TemporaryDirectory() as tmpdir:
           socket_path = os.path.join(tmpdir, "test.sock")
           sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
           try:
               sock.bind(socket_path)
               self.assertFalse(is_regular_file_or_fifo(socket_path))
           finally:
               sock.close()

   def test_is_regular_file_or_fifo_with_nonexistent_path(self):
       """Test is_regular_file_or_fifo returns False for non-existent paths"""
       from fivetran_connector_sdk.helpers import is_regular_file_or_fifo

       self.assertFalse(is_regular_file_or_fifo("/nonexistent/path/to/file"))

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_validate_and_load_configuration_with_named_pipe(self):
       """Test validate_and_load_configuration reading from a named pipe (FIFO)"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import json

       with tempfile.TemporaryDirectory() as tmpdir:
           pipe_path = os.path.join(tmpdir, "config_pipe")
           os.mkfifo(pipe_path)

           # Verify it's a FIFO (not a regular file)
           self.assertTrue(stat.S_ISFIFO(os.stat(pipe_path).st_mode))
           self.assertFalse(os.path.isfile(pipe_path))

           config_data = {"api_key": "test123", "endpoint": "https://example.com"}

           def write_to_pipe():
               with open(pipe_path, 'w', encoding='utf-8') as f:
                   json.dump(config_data, f)

           writer_thread = threading.Thread(target=write_to_pipe)
           writer_thread.start()

           config = validate_and_load_configuration(tmpdir, "config_pipe")
           writer_thread.join()

           self.assertEqual(config, config_data)

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_validate_and_load_state_with_named_pipe(self):
       """Test validate_and_load_state reading from a named pipe (FIFO)"""
       from fivetran_connector_sdk.helpers import validate_and_load_state
       import json

       class Args:
           project_path = ""
           state = "state_pipe"

       with tempfile.TemporaryDirectory() as tmpdir:
           args = Args()
           args.project_path = tmpdir
           pipe_path = os.path.join(tmpdir, "state_pipe")
           os.mkfifo(pipe_path)

           # Verify it's a FIFO (not a regular file)
           self.assertTrue(stat.S_ISFIFO(os.stat(pipe_path).st_mode))
           self.assertFalse(os.path.isfile(pipe_path))

           state_data = {"cursor": "2024-01-01", "offset": 100}

           def write_to_pipe():
               with open(pipe_path, 'w', encoding='utf-8') as f:
                   json.dump(state_data, f)

           writer_thread = threading.Thread(target=write_to_pipe)
           writer_thread.start()

           state = validate_and_load_state(args, "state_pipe")
           writer_thread.join()

           self.assertEqual(state, state_data)

   def test_is_fifo_with_regular_file(self):
       """Test is_fifo returns False for regular files"""
       from fivetran_connector_sdk.helpers import is_fifo

       with tempfile.TemporaryDirectory() as tmpdir:
           file_path = os.path.join(tmpdir, "test.txt")
           with open(file_path, "w", encoding="utf-8") as f:
               f.write("test")
           self.assertFalse(is_fifo(file_path))

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_is_fifo_with_fifo(self):
       """Test is_fifo returns True for FIFOs"""
       from fivetran_connector_sdk.helpers import is_fifo

       with tempfile.TemporaryDirectory() as tmpdir:
           fifo_path = os.path.join(tmpdir, "test_fifo")
           os.mkfifo(fifo_path)
           self.assertTrue(is_fifo(fifo_path))

   def test_is_fifo_with_nonexistent_path(self):
       """Test is_fifo returns False for non-existent paths"""
       from fivetran_connector_sdk.helpers import is_fifo

       self.assertFalse(is_fifo("/nonexistent/path/to/file"))

   def test_safe_read_file_regular_file(self):
       """Test safe_read_file reads regular files normally"""
       from fivetran_connector_sdk.helpers import safe_read_file

       with tempfile.TemporaryDirectory() as tmpdir:
           file_path = os.path.join(tmpdir, "test.txt")
           with open(file_path, "w", encoding="utf-8") as f:
               f.write("test content")
           content = safe_read_file(file_path)
           self.assertEqual(content, "test content")

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_safe_read_file_fifo_with_writer(self):
       """Test safe_read_file reads from FIFO when writer is present"""
       from fivetran_connector_sdk.helpers import safe_read_file

       with tempfile.TemporaryDirectory() as tmpdir:
           fifo_path = os.path.join(tmpdir, "test_fifo")
           os.mkfifo(fifo_path)

           def write_to_pipe():
               with open(fifo_path, 'w', encoding='utf-8') as f:
                   f.write('{"key": "value"}')

           writer_thread = threading.Thread(target=write_to_pipe)
           writer_thread.start()

           content = safe_read_file(fifo_path)
           writer_thread.join()

           self.assertEqual(content, '{"key": "value"}')

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_safe_read_file_fifo_timeout(self):
       """Test safe_read_file raises TimeoutError when no writer connects to FIFO"""
       from fivetran_connector_sdk.helpers import safe_read_file

       with tempfile.TemporaryDirectory() as tmpdir:
           fifo_path = os.path.join(tmpdir, "test_fifo")
           os.mkfifo(fifo_path)

           # Use a very short timeout to speed up the test
           with self.assertRaises(TimeoutError) as cm:
               safe_read_file(fifo_path, timeout_seconds=0.1)
           self.assertIn("Timed out", str(cm.exception))
           self.assertIn(fifo_path, str(cm.exception))

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_safe_read_file_fifo_chunked_writes(self):
       """Test safe_read_file correctly reads all data when writer emits in chunks"""
       from fivetran_connector_sdk.helpers import safe_read_file
       import time

       with tempfile.TemporaryDirectory() as tmpdir:
           fifo_path = os.path.join(tmpdir, "test_fifo")
           os.mkfifo(fifo_path)

           def write_in_chunks():
               with open(fifo_path, 'w', encoding='utf-8') as f:
                   # Write JSON in multiple chunks with delays
                   f.write('{"key1": ')
                   f.flush()
                   time.sleep(0.05)
                   f.write('"value1", ')
                   f.flush()
                   time.sleep(0.05)
                   f.write('"key2": "value2"}')
                   f.flush()

           writer_thread = threading.Thread(target=write_in_chunks)
           writer_thread.start()

           content = safe_read_file(fifo_path)
           writer_thread.join()

           # Should get complete JSON, not truncated
           self.assertEqual(content, '{"key1": "value1", "key2": "value2"}')

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_safe_read_file_fifo_writer_crashes_no_data(self):
       """Test safe_read_file returns empty string when writer opens but crashes without writing"""
       from fivetran_connector_sdk.helpers import safe_read_file
       import time

       with tempfile.TemporaryDirectory() as tmpdir:
           fifo_path = os.path.join(tmpdir, "test_fifo")
           os.mkfifo(fifo_path)

           def open_and_close_immediately():
               # Simulate producer crash: open write end then close without writing
               fd = os.open(fifo_path, os.O_WRONLY)
               time.sleep(0.05)  # Brief delay to ensure reader is waiting
               os.close(fd)

           writer_thread = threading.Thread(target=open_and_close_immediately)
           writer_thread.start()

           content = safe_read_file(fifo_path)
           writer_thread.join()

           # When writer crashes without writing, we get empty string
           self.assertEqual(content, "")

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_validate_and_load_configuration_fifo_writer_crashes(self):
       """Test validate_and_load_configuration raises ValueError when writer crashes (empty/invalid JSON)"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       import time

       with tempfile.TemporaryDirectory() as tmpdir:
           pipe_path = os.path.join(tmpdir, "config_pipe")
           os.mkfifo(pipe_path)

           def open_and_close_immediately():
               # Simulate producer crash: open write end then close without writing
               fd = os.open(pipe_path, os.O_WRONLY)
               time.sleep(0.05)
               os.close(fd)

           writer_thread = threading.Thread(target=open_and_close_immediately)
           writer_thread.start()

           # Empty content causes JSONDecodeError which is wrapped in ValueError
           with self.assertRaises(ValueError) as cm:
               validate_and_load_configuration(tmpdir, "config_pipe")
           writer_thread.join()

           self.assertIn("Configuration must be provided as a JSON file", str(cm.exception))

   @unittest.skipIf(sys.platform == 'win32', "Named pipes (FIFOs) not supported on Windows")
   def test_validate_and_load_configuration_fifo_timeout(self):
       """Test validate_and_load_configuration raises ValueError on FIFO timeout"""
       from fivetran_connector_sdk.helpers import validate_and_load_configuration
       from fivetran_connector_sdk import constants

       # Save original timeout
       original_timeout = constants.FIFO_READ_TIMEOUT_SECONDS

       try:
           # Set a very short timeout
           constants.FIFO_READ_TIMEOUT_SECONDS = 0.1

           with tempfile.TemporaryDirectory() as tmpdir:
               pipe_path = os.path.join(tmpdir, "config_pipe")
               os.mkfifo(pipe_path)

               # No writer - should timeout
               with self.assertRaises(ValueError) as cm:
                   # Need to reload the module to pick up the new constant
                   from fivetran_connector_sdk import helpers
                   import importlib
                   importlib.reload(helpers)
                   helpers.validate_and_load_configuration(tmpdir, "config_pipe")
               self.assertIn("Timed out", str(cm.exception))
       finally:
           # Restore original timeout
           constants.FIFO_READ_TIMEOUT_SECONDS = original_timeout

   @patch('builtins.input', return_value='y')
   def test_resolve_confirmation_accepts_y(self, mock_input):
       from fivetran_connector_sdk.helpers import resolve_confirmation
       result = resolve_confirmation("Continue? ", False, PromptMode.INTERACTIVE)
       self.assertTrue(result)

   @patch('builtins.input', return_value='n')
   def test_resolve_confirmation_accepts_n(self, mock_input):
       from fivetran_connector_sdk.helpers import resolve_confirmation
       result = resolve_confirmation("Continue? ", True, PromptMode.INTERACTIVE)
       self.assertFalse(result)

   @patch('builtins.input', return_value='')
   def test_resolve_confirmation_empty_returns_default(self, mock_input):
       from fivetran_connector_sdk.helpers import resolve_confirmation
       result = resolve_confirmation("Continue? ", True, PromptMode.INTERACTIVE)
       self.assertTrue(result)
       result = resolve_confirmation("Continue? ", False, PromptMode.INTERACTIVE)
       self.assertFalse(result)

   @patch('builtins.input', return_value='invalid')
   def test_resolve_confirmation_invalid_returns_default(self, mock_input):
       from fivetran_connector_sdk.helpers import resolve_confirmation
       result = resolve_confirmation("Continue? ", True, PromptMode.INTERACTIVE)
       self.assertTrue(result)
       result = resolve_confirmation("Continue? ", False, PromptMode.INTERACTIVE)
       self.assertFalse(result)


class TestValidateTableName(TestCase):

    def test_raises_for_empty_string(self):
        with self.assertRaises(ValueError):
            _validate_table_name("")

    def test_raises_for_whitespace_string(self):
        with self.assertRaises(ValueError):
            _validate_table_name("   ")

    def test_raises_type_error_for_non_string(self):
        with self.assertRaises(TypeError):
            _validate_table_name(123)

    def test_valid_table_name(self):
        _validate_table_name("orders")

    def test_valid_table_name_with_numeric_characters(self):
        _validate_table_name("table123")


class TestResolveExistingProjectPath(TestCase):

    def test_raises_for_nonexistent_path(self):
        with self.assertRaises(ValueError) as cm:
            _resolve_existing_project_path("/nonexistent/path/that/should/never/exist")
        self.assertIn("does not exist or is not a directory", str(cm.exception))

    def test_raises_for_empty_string(self):
        with self.assertRaises(ValueError) as cm:
            _resolve_existing_project_path("")
        self.assertIn("cannot be empty or contain only whitespace", str(cm.exception))

    def test_raises_for_file_instead_of_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "not_a_dir.txt")
            with open(file_path, "w") as f:
                f.write("test")
            with self.assertRaises(ValueError) as cm:
                _resolve_existing_project_path(file_path)
            self.assertIn("does not exist or is not a directory", str(cm.exception))

    def test_returns_resolved_absolute_path_for_valid_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = _resolve_existing_project_path(tmpdir)
            self.assertEqual(resolved, str(os.path.realpath(tmpdir)))
            self.assertTrue(os.path.isabs(resolved))

    def test_resolves_relative_path_to_absolute(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                resolved = _resolve_existing_project_path(".")
                self.assertEqual(resolved, str(os.path.realpath(tmpdir)))
            finally:
                os.chdir(original_cwd)

    def test_collapses_traversal_segments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "nested")
            os.makedirs(nested)
            traversal_path = os.path.join(nested, "..")
            resolved = _resolve_existing_project_path(traversal_path)
            self.assertEqual(resolved, str(os.path.realpath(tmpdir)))

    def test_resolves_symlink_to_real_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = os.path.join(tmpdir, "real")
            os.makedirs(real_dir)
            symlink_path = os.path.join(tmpdir, "link")
            os.symlink(real_dir, symlink_path)
            resolved = _resolve_existing_project_path(symlink_path)
            self.assertEqual(resolved, str(os.path.realpath(real_dir)))


if __name__ == '__main__':
   unittest.main()
