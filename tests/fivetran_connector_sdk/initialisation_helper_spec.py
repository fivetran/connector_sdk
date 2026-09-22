import sys
import os
import unittest
from unittest import TestCase
from unittest.mock import patch, MagicMock, mock_open

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from fivetran_connector_sdk.constants import AGENT_PLUGINS, SUPPORTED_AGENT_DISPLAY_NAMES, TOOLS_GITHUB_REPO, \
    TOOLS_GITHUB_REPO_URL, AI_TOOLS_INSTALLATION_DOCS_URL
from fivetran_connector_sdk.logger import Logging
from fivetran_connector_sdk.helpers import PromptMode


class TestInitialisationHelper(TestCase):
    """Test suite for initialisation_helper.py module (unit and integration tests)."""

    def setUp(self):
        """Set up test fixtures."""
        import tempfile
        # For unit tests (with mocks)
        self.test_project_dir = "/test/project/path"
        self.test_template = "examples/test_connector"

        # For integration tests (real filesystem operations)
        self.temp_dir = tempfile.mkdtemp()
        self.test_project_name = "test_connector_project"
        self.test_project_path = os.path.join(self.temp_dir, self.test_project_name)

    def tearDown(self):
        """Clean up after tests."""
        import shutil
        # Clean up temporary directories created by integration tests
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    # ============================================================================
    # Tests for init() function
    # ============================================================================

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_blank_project_runs_setup(self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test setup runs automatically when the target folder is empty."""
        from fivetran_connector_sdk.initialisation_helper import init

        init(self.test_project_path, self.test_template, PromptMode.INTERACTIVE)

        mock_input.assert_not_called()
        mock_setup_connector.assert_called_once_with(self.test_project_path, self.test_template)
        mock_setup_ai_agent.assert_called_once_with()
        mock_log.assert_called_with("Time to make a great connector; Happy coding")
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_blank_project_non_interactive_runs_setup_and_skips_ai(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test --non-interactive initializes a blank folder and skips AI setup."""
        from fivetran_connector_sdk.initialisation_helper import init

        init(self.test_project_path, self.test_template, PromptMode.DEFAULT_ANSWER)

        mock_input.assert_not_called()
        mock_setup_connector.assert_called_once_with(self.test_project_path, self.test_template)
        mock_setup_ai_agent.assert_not_called()
        mock_log.assert_any_call("skipping AI agent setup; --non-interactive is set", log_icon=Logging.LogIcon.STEP)
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_blank_project_yes_flag_runs_setup_and_skips_ai(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test --yes initializes a blank folder and skips AI setup."""
        from fivetran_connector_sdk.initialisation_helper import init

        init(self.test_project_path, self.test_template, PromptMode.YES)

        mock_input.assert_not_called()
        mock_setup_connector.assert_called_once_with(self.test_project_path, self.test_template)
        mock_setup_ai_agent.assert_not_called()
        mock_log.assert_any_call("skipping AI agent setup; --yes is set", log_icon=Logging.LogIcon.STEP)
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_project_with_virtual_environment_runs_setup_without_overwrite_prompt(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test a virtual environment with any directory name does not mark the project as existing."""
        from fivetran_connector_sdk.initialisation_helper import init
        virtual_environment_dir = os.path.join(self.test_project_path, "custom-python-environment")
        os.makedirs(virtual_environment_dir)
        with open(os.path.join(virtual_environment_dir, "pyvenv.cfg"), "w") as f:
            f.write("home = /usr/local/bin")

        init(self.test_project_path, self.test_template, PromptMode.INTERACTIVE)

        mock_input.assert_not_called()
        mock_setup_connector.assert_called_once_with(self.test_project_path, self.test_template)
        mock_setup_ai_agent.assert_called_once_with()
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input', return_value='')
    @patch('sys.exit')
    def test_init_existing_project_default_answer_skips_setup(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test existing project prompts once and defaults to no overwrite."""
        from fivetran_connector_sdk.initialisation_helper import init
        os.makedirs(self.test_project_path, exist_ok=True)
        with open(os.path.join(self.test_project_path, "notes.txt"), "w") as f:
            f.write("existing")

        init(self.test_project_path, self.test_template, PromptMode.INTERACTIVE)

        mock_input.assert_called_once_with("Overwrite existing project? (y/N): ")
        mock_setup_connector.assert_not_called()
        mock_setup_ai_agent.assert_called_once_with()
        mock_log.assert_any_call("skipping project setup; existing files were not overwritten",
                                 log_icon=Logging.LogIcon.STEP)
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_existing_project_non_interactive_skips_setup_and_ai(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test --non-interactive answers no for existing project overwrite."""
        from fivetran_connector_sdk.initialisation_helper import init
        os.makedirs(self.test_project_path, exist_ok=True)
        with open(os.path.join(self.test_project_path, "notes.txt"), "w") as f:
            f.write("existing")

        init(self.test_project_path, self.test_template, PromptMode.DEFAULT_ANSWER)

        mock_input.assert_not_called()
        mock_setup_connector.assert_not_called()
        mock_setup_ai_agent.assert_not_called()
        mock_log.assert_any_call("skipping project setup; existing files were not overwritten",
                                 log_icon=Logging.LogIcon.STEP)
        mock_log.assert_any_call("skipping AI agent setup; --non-interactive is set", log_icon=Logging.LogIcon.STEP)
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_existing_project_force_overwrites_and_skips_ai(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test --force answers yes for existing project overwrite and skips AI setup."""
        from fivetran_connector_sdk.initialisation_helper import init
        os.makedirs(self.test_project_path, exist_ok=True)
        with open(os.path.join(self.test_project_path, "notes.txt"), "w") as f:
            f.write("existing")

        init(self.test_project_path, self.test_template, PromptMode.FORCE)

        mock_input.assert_not_called()
        mock_setup_connector.assert_called_once_with(self.test_project_path, self.test_template)
        mock_setup_ai_agent.assert_not_called()
        mock_log.assert_any_call("skipping AI agent setup; --force is set", log_icon=Logging.LogIcon.STEP)
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input')
    @patch('sys.exit')
    def test_init_existing_project_yes_flag_overwrites_and_skips_ai(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test --yes overwrites existing project and skips AI setup."""
        from fivetran_connector_sdk.initialisation_helper import init
        os.makedirs(self.test_project_path, exist_ok=True)
        with open(os.path.join(self.test_project_path, "notes.txt"), "w") as f:
            f.write("existing")

        init(self.test_project_path, self.test_template, PromptMode.YES)

        mock_input.assert_not_called()
        mock_setup_connector.assert_called_once_with(self.test_project_path, self.test_template)
        mock_setup_ai_agent.assert_not_called()
        mock_log.assert_any_call("skipping AI agent setup; --yes is set", log_icon=Logging.LogIcon.STEP)
        mock_exit.assert_called_once_with(0)

    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('sys.exit')
    def test_init_failure_during_setup(self, mock_exit, mock_log, mock_setup_connector):
        """Test initialization failure with proper error handling."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.logger import Logging

        error_message = "Failed to create directory"
        mock_setup_connector.side_effect = Exception(error_message)

        init(self.test_project_dir, self.test_template, PromptMode.INTERACTIVE)

        # Verify error was logged with SEVERE level and FAILURE icon
        mock_log.assert_called_with(f"failed to initialize project error: {error_message}", level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        mock_exit.assert_called_once_with(1)

    # ============================================================================
    # Tests for setup_connector() function
    # ============================================================================

    @patch('fivetran_connector_sdk.initialisation_helper.download_git_directory')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('os.makedirs')
    def test_setup_connector_creates_directory(self, mock_makedirs, mock_log, mock_download):
        """Test setup_connector creates project directory and downloads files."""
        from fivetran_connector_sdk.initialisation_helper import setup_connector
        from fivetran_connector_sdk.logger import Logging

        setup_connector(self.test_project_dir, self.test_template)

        mock_makedirs.assert_called_once_with(self.test_project_dir, exist_ok=True)
        mock_download.assert_called_once_with(self.test_template, self.test_project_dir)
        mock_log.assert_called_once_with(f"new project created at: {self.test_project_dir}", log_icon=Logging.LogIcon.SUCCESS)

    @patch('fivetran_connector_sdk.initialisation_helper.download_git_directory')
    @patch('os.makedirs')
    def test_setup_connector_with_existing_directory(self, mock_makedirs, mock_download):
        """Test setup_connector with existing directory (exist_ok=True)."""
        from fivetran_connector_sdk.initialisation_helper import setup_connector

        setup_connector(self.test_project_dir, self.test_template)

        # Verify exist_ok=True allows overwriting
        mock_makedirs.assert_called_once_with(self.test_project_dir, exist_ok=True)

    @patch('shutil.which', return_value='/usr/local/bin/claude')
    def test_detect_installed_agents_returns_all_when_all_on_path(self, mock_which):
        """Test detect_installed_agents returns all agents when all CLIs are found."""
        from fivetran_connector_sdk.initialisation_helper import detect_installed_agents

        result = detect_installed_agents()

        self.assertIn('claude', result)
        self.assertEqual(result['claude'], AGENT_PLUGINS['claude']['display_name'])
        self.assertIn('codex', result)
        self.assertIn('gemini', result)

    def test_agent_guidance_constants_are_derived_from_agent_plugin_config(self):
        """Test agent guidance constants follow the plugin and repo constants."""
        self.assertEqual(
            SUPPORTED_AGENT_DISPLAY_NAMES,
            ", ".join(config["display_name"] for config in AGENT_PLUGINS.values())
        )
        self.assertEqual(TOOLS_GITHUB_REPO_URL, f"https://github.com/{TOOLS_GITHUB_REPO}")
        self.assertIn(
            TOOLS_GITHUB_REPO_URL,
            AGENT_PLUGINS['gemini']['install_commands'][0]
        )
        self.assertIn("update_commands", AGENT_PLUGINS['claude'])
        self.assertIn("update_commands", AGENT_PLUGINS['codex'])
        self.assertIn("update_commands", AGENT_PLUGINS['copilot'])

    @patch('shutil.which', return_value=None)
    def test_detect_installed_agents_returns_empty_when_none_on_path(self, mock_which):
        """Test detect_installed_agents returns empty dict when no CLIs are found."""
        from fivetran_connector_sdk.initialisation_helper import detect_installed_agents

        result = detect_installed_agents()

        self.assertEqual(result, {})

    def test_detect_installed_agents_returns_only_installed(self):
        """Test detect_installed_agents returns only the agents found on PATH."""
        from fivetran_connector_sdk.initialisation_helper import detect_installed_agents

        def which_side_effect(cmd):
            return '/usr/local/bin/claude' if cmd == AGENT_PLUGINS['claude']['cli_command'] else None

        with patch('shutil.which', side_effect=which_side_effect):
            result = detect_installed_agents()

        self.assertIn('claude', result)
        self.assertNotIn('codex', result)
        self.assertNotIn('gemini', result)

    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_install_agent_plugin_runs_all_commands_for_claude(self, mock_log, mock_run):
        """Test install_agent_plugin runs both install commands for Claude Code."""
        from fivetran_connector_sdk.initialisation_helper import install_agent_plugin

        mock_run.return_value = MagicMock(returncode=0)
        result = install_agent_plugin('claude')

        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(
            mock_run.call_args_list[0][0][0],
            AGENT_PLUGINS['claude']['install_commands'][0]
        )
        self.assertEqual(
            mock_run.call_args_list[1][0][0],
            AGENT_PLUGINS['claude']['install_commands'][1]
        )
        update_command = " ".join(AGENT_PLUGINS['claude']['update_commands'][0])
        self.assertTrue(any(update_command in str(c) for c in mock_log.call_args_list))
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_install_agent_plugin_logs_update_command_for_codex(self, mock_log, mock_run):
        """Test install_agent_plugin logs the manual update command for Codex CLI."""
        from fivetran_connector_sdk.initialisation_helper import install_agent_plugin

        mock_run.return_value = MagicMock(returncode=0)
        result = install_agent_plugin('codex')

        update_command = " ".join(AGENT_PLUGINS['codex']['update_commands'][0])
        self.assertTrue(any(update_command in str(c) for c in mock_log.call_args_list))
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_install_agent_plugin_logs_update_command_for_copilot(self, mock_log, mock_run):
        """Test install_agent_plugin logs the manual update command for GitHub Copilot CLI."""
        from fivetran_connector_sdk.initialisation_helper import install_agent_plugin

        mock_run.return_value = MagicMock(returncode=0)
        result = install_agent_plugin('copilot')

        update_command = " ".join(AGENT_PLUGINS['copilot']['update_commands'][0])
        self.assertTrue(any(update_command in str(c) for c in mock_log.call_args_list))
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_install_agent_plugin_runs_single_command_for_gemini(self, mock_log, mock_run):
        """Test install_agent_plugin runs one install command for Gemini CLI."""
        from fivetran_connector_sdk.initialisation_helper import install_agent_plugin

        mock_run.return_value = MagicMock(returncode=0)
        result = install_agent_plugin('gemini')

        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(
            mock_run.call_args_list[0][0][0],
            AGENT_PLUGINS['gemini']['install_commands'][0]
        )
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_install_agent_plugin_stops_on_failed_command(self, mock_log, mock_run):
        """Test install_agent_plugin stops and logs a warning when a command fails."""
        from fivetran_connector_sdk.initialisation_helper import install_agent_plugin

        mock_run.return_value = MagicMock(returncode=1)
        install_agent_plugin('claude')

        self.assertEqual(mock_run.call_count, 1)
        warning_calls = [c for c in mock_log.call_args_list if 'failed' in str(c)]
        self.assertTrue(len(warning_calls) > 0)

    @patch('subprocess.run', side_effect=OSError("No such file or directory"))
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_install_agent_plugin_handles_os_error(self, mock_log, mock_run):
        """Test install_agent_plugin catches OSError and logs manual-install guidance."""
        from fivetran_connector_sdk.initialisation_helper import install_agent_plugin

        install_agent_plugin('claude')

        self.assertEqual(mock_run.call_count, 1)
        warning_calls = [c for c in mock_log.call_args_list if 'failed' in str(c)]
        self.assertTrue(len(warning_calls) > 0)
        guidance_calls = [c for c in mock_log.call_args_list if 'install the plugin later' in str(c)]
        self.assertTrue(len(guidance_calls) > 0)
        self.assertTrue(any(AI_TOOLS_INSTALLATION_DOCS_URL in str(c) for c in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={
               'claude': AGENT_PLUGINS['claude']['display_name'],
               'gemini': AGENT_PLUGINS['gemini']['display_name'],
           })
    @patch('builtins.input', return_value='1')
    def test_setup_ai_agent_installs_first_agent_when_user_picks_1(self, mock_input, mock_detect, mock_install):
        """Test setup_ai_agent installs the first detected agent when user picks 1."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        setup_ai_agent()

        mock_install.assert_called_once_with('claude')

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.is_agent_plugin_install_supported',
           return_value=True)
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={
               'claude': AGENT_PLUGINS['claude']['display_name'],
               'codex': AGENT_PLUGINS['codex']['display_name'],
           })
    @patch('builtins.input', return_value='2')
    def test_setup_ai_agent_installs_second_agent_when_user_picks_2(
            self, mock_input, mock_detect, mock_agent_supported, mock_install):
        """Test setup_ai_agent installs the second detected agent when user picks 2."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        setup_ai_agent()

        mock_agent_supported.assert_called_once_with('codex')
        mock_install.assert_called_once_with('codex')

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={'codex': AGENT_PLUGINS['codex']['display_name']})
    @patch('builtins.input', return_value='1')
    def test_setup_ai_agent_skips_codex_install_when_codex_version_is_too_old(
            self, mock_input, mock_detect, mock_run, mock_log, mock_install):
        """Test setup_ai_agent skips Codex plugin install when Codex CLI is below 0.131.0."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        mock_run.return_value = MagicMock(returncode=0, stdout='codex-cli 0.130.9')

        setup_ai_agent()

        mock_run.assert_called_once_with(["codex", "--version"], capture_output=True, text=True, timeout=30)
        mock_install.assert_not_called()
        all_log_messages = ' '.join(str(c) for c in mock_log.call_args_list)
        min_version = ".".join(str(p) for p in AGENT_PLUGINS['codex']['min_supported_version'])
        self.assertIn('0.130.9', all_log_messages)
        self.assertIn(min_version, all_log_messages)
        self.assertIn('update Codex CLI', all_log_messages)
        self.assertIn(AI_TOOLS_INSTALLATION_DOCS_URL, all_log_messages)

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={'claude': AGENT_PLUGINS['claude']['display_name']})
    @patch('builtins.input', return_value='2')
    def test_setup_ai_agent_skips_when_user_picks_skip_option(self, mock_input, mock_detect, mock_log, mock_install):
        """Test setup_ai_agent skips when user selects the skip option number."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        setup_ai_agent()

        mock_install.assert_not_called()
        self.assertTrue(any('skipping' in str(c) for c in mock_log.call_args_list))
        mock_log.assert_any_call(
            "To install the plugin later, follow the AI tools guide:",
            log_icon=Logging.LogIcon.STEP,
        )
        mock_log.assert_any_call(AI_TOOLS_INSTALLATION_DOCS_URL, indent=True)

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={'claude': AGENT_PLUGINS['claude']['display_name']})
    @patch('builtins.input', return_value='invalid')
    def test_setup_ai_agent_skips_on_invalid_input(self, mock_input, mock_detect, mock_log, mock_install):
        """Test setup_ai_agent skips when user enters non-numeric input."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        setup_ai_agent()

        mock_install.assert_not_called()
        self.assertTrue(any('skipping' in str(c) for c in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={'claude': AGENT_PLUGINS['claude']['display_name']})
    @patch('builtins.input', return_value='99')
    def test_setup_ai_agent_skips_on_out_of_range_number(self, mock_input, mock_detect, mock_log, mock_install):
        """Test setup_ai_agent skips when user enters a number out of range."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        setup_ai_agent()

        mock_install.assert_not_called()
        self.assertTrue(any('skipping' in str(c) for c in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={})
    def test_setup_ai_agent_logs_message_and_skips_when_no_agents_detected(self, mock_detect, mock_log, mock_install):
        """Test setup_ai_agent logs an informative message when no agents are on PATH."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        setup_ai_agent()

        mock_install.assert_not_called()
        all_log_messages = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('no supported coding agents', all_log_messages)
        self.assertIn(SUPPORTED_AGENT_DISPLAY_NAMES, all_log_messages)
        self.assertIn(AI_TOOLS_INSTALLATION_DOCS_URL, all_log_messages)

    @patch('fivetran_connector_sdk.initialisation_helper.install_agent_plugin')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={})
    def test_setup_ai_agent_logs_constant_derived_guidance(self, mock_detect, mock_log, mock_install):
        """Test setup_ai_agent derives no-agent guidance from agent and repo constants."""
        from fivetran_connector_sdk.initialisation_helper import setup_ai_agent

        with patch('fivetran_connector_sdk.initialisation_helper.SUPPORTED_AGENT_DISPLAY_NAMES',
                   'Test Agent'):
            with patch('fivetran_connector_sdk.initialisation_helper.AI_TOOLS_INSTALLATION_DOCS_URL',
                       'https://example.com/ai-tools'):
                setup_ai_agent()

        mock_install.assert_not_called()
        all_log_messages = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('Test Agent', all_log_messages)
        self.assertIn('https://example.com/ai-tools', all_log_messages)
        self.assertNotIn(AGENT_PLUGINS['claude']['display_name'], all_log_messages)

    # ============================================================================
    # Tests for validate_example_directory() function
    # ============================================================================

    def test_validate_example_directory_single_connector_file(self):
        """Test validation succeeds with exactly one connector.py file."""
        from fivetran_connector_sdk.initialisation_helper import validate_example_directory

        files_to_download = [
            {'local_path': 'connector.py'},
            {'local_path': 'config.json'},
            {'local_path': 'helpers.py'}
        ]

        # Should not raise
        validate_example_directory(files_to_download)

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_validate_example_directory_no_connector_file(self, mock_log):
        """Test validation fails when no connector.py file is found."""
        from fivetran_connector_sdk.initialisation_helper import validate_example_directory
        from fivetran_connector_sdk.logger import Logging

        files_to_download = [
            {'local_path': 'config.json'},
            {'local_path': 'helpers.py'}
        ]

        with self.assertRaises(ValueError) as context:
            validate_example_directory(files_to_download)

        self.assertIn("Invalid directory passed", str(context.exception))
        mock_log.assert_called_once_with(
            "selected directory is not a valid example; missing connector.py",
            Logging.Level.SEVERE
        )

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    def test_validate_example_directory_multiple_connector_files(self, mock_log):
        """Test validation fails when multiple connector.py files are found."""
        from fivetran_connector_sdk.initialisation_helper import validate_example_directory
        from fivetran_connector_sdk.logger import Logging

        files_to_download = [
            {'local_path': 'connector.py', 'github_path': 'github/connector.py'},
            {'local_path': 'connector.py', 'github_path': 'github_traffic/connector.py'},
            {'local_path': 'config.json', 'github_path': 'github/config.json'}
        ]

        with self.assertRaises(ValueError) as context:
            validate_example_directory(files_to_download, 'git')

        self.assertIn("re-run with an exact connector name", str(context.exception))
        self.assertTrue(any("available connectors" in str(c) for c in mock_log.call_args_list))
        self.assertTrue(any("github" in str(c) for c in mock_log.call_args_list))

    def test_validate_example_directory_nested_connector_file(self):
        """Test validation with connector.py in nested path."""
        from fivetran_connector_sdk.initialisation_helper import validate_example_directory

        files_to_download = [
            {'local_path': 'src/connector.py'},
            {'local_path': 'config.json'}
        ]

        # Should not raise
        validate_example_directory(files_to_download)

    # ============================================================================
    # Tests for download_git_directory() function
    # ============================================================================

    @patch('fivetran_connector_sdk.initialisation_helper.download_file_from_github')
    @patch('fivetran_connector_sdk.initialisation_helper.validate_example_directory')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_download_git_directory_success(self, mock_get, mock_log, mock_validate, mock_download_files):
        """Test successful download of git directory."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        # Mock GitHub API response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'examples/test_connector/connector.py', 'size': 1024},
                {'type': 'blob', 'path': 'examples/test_connector/config.json', 'size': 256},
                {'type': 'blob', 'path': 'examples/other/file.py', 'size': 512},
                {'type': 'tree', 'path': 'examples/test_connector/subdir'}
            ]
        }
        mock_get.return_value = mock_response

        download_git_directory('examples/test_connector', self.test_project_dir)

        # Verify API was called
        mock_get.assert_called_once()
        self.assertIn('github.com', mock_get.call_args[0][0])

        # Verify validation was called
        mock_validate.assert_called_once()

        # Verify files were downloaded (only matching path_prefix, excluding trees)
        mock_download_files.assert_called_once()
        files_arg = mock_download_files.call_args[0][0]
        self.assertEqual(len(files_arg), 2)  # Only 2 files match path_prefix and are blobs

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_download_git_directory_api_error(self, mock_get, mock_log):
        """Test download_git_directory handles API errors gracefully."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory
        from fivetran_connector_sdk.logger import Logging

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_get.return_value = mock_response

        download_git_directory('examples/test_connector', self.test_project_dir)

        # Verify error was logged
        self.assertTrue(any("failed to download files" in str(call) for call in mock_log.call_args_list))
        self.assertTrue(any("manual download" in str(call) for call in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_download_git_directory_missing_tree_key(self, mock_get, mock_log):
        """Test download_git_directory handles missing 'tree' key in response."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory
        from fivetran_connector_sdk.logger import Logging

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}  # Missing 'tree' key
        mock_get.return_value = mock_response

        download_git_directory('examples/test_connector', self.test_project_dir)

        mock_log.assert_called_with(
            "failed to fetch repository from GitHub",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE
        )

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_download_git_directory_no_files_found(self, mock_get, mock_log):
        """Test download_git_directory when no files match the path prefix."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory
        from fivetran_connector_sdk.logger import Logging

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'other/file.py', 'size': 512}
            ]
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('examples/test_connector', self.test_project_dir)

        self.assertTrue(any("no connector found matching" in str(call) for call in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.download_file_from_github')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_download_git_directory_excludes_readme_for_template(self, mock_get, mock_log, mock_download_files):
        """Test that README files are excluded for template connectors."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': f'{TEMPLATE_CONNECTOR_PATH}/connector.py', 'size': 1024},
                {'type': 'blob', 'path': f'{TEMPLATE_CONNECTOR_PATH}/README.md', 'size': 256},
                {'type': 'blob', 'path': f'{TEMPLATE_CONNECTOR_PATH}/readme.txt', 'size': 128}
            ]
        }
        mock_get.return_value = mock_response

        download_git_directory(TEMPLATE_CONNECTOR_PATH, self.test_project_dir)

        # Verify only connector.py was included (README files excluded)
        files_arg = mock_download_files.call_args[0][0]
        self.assertEqual(len(files_arg), 1)
        self.assertEqual(files_arg[0]['local_path'], 'connector.py')

    @patch('requests.get')
    def test_download_git_directory_timeout(self, mock_get):
        """Test download_git_directory with timeout parameter."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'tree': []}
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('examples/test_connector', self.test_project_dir)

        # Verify timeout was passed
        self.assertEqual(mock_get.call_args[1]['timeout'], 10)

    # ============================================================================
    # Tests for _resolve_repo_and_path() function
    # ============================================================================

    def test_resolve_repo_and_path_connectors_prefix(self):
        """Test connectors/ prefix routes to community_connectors repo and strips prefix."""
        from fivetran_connector_sdk.initialisation_helper import _resolve_repo_and_path
        from fivetran_connector_sdk.constants import CONNECTORS_GITHUB_REPO

        repo, path = _resolve_repo_and_path('connectors/stripe')

        self.assertEqual(repo, CONNECTORS_GITHUB_REPO)
        self.assertEqual(path, 'stripe')

    def test_resolve_repo_and_path_examples_prefix(self):
        """Test examples/ prefix routes to connector_sdk repo and keeps full path."""
        from fivetran_connector_sdk.initialisation_helper import _resolve_repo_and_path
        from fivetran_connector_sdk.constants import EXAMPLES_GITHUB_REPO

        repo, path = _resolve_repo_and_path('examples/quickstart/hello')

        self.assertEqual(repo, EXAMPLES_GITHUB_REPO)
        self.assertEqual(path, 'examples/quickstart/hello')

    def test_resolve_repo_and_path_default_routes_to_community_connectors(self):
        """Test bare connector name routes to community_connectors repo."""
        from fivetran_connector_sdk.initialisation_helper import _resolve_repo_and_path
        from fivetran_connector_sdk.constants import CONNECTORS_GITHUB_REPO

        repo, path = _resolve_repo_and_path('github')

        self.assertEqual(repo, CONNECTORS_GITHUB_REPO)
        self.assertEqual(path, 'github')

    # ============================================================================
    # Tests for exact match vs prefix match behavior
    # ============================================================================

    @patch('fivetran_connector_sdk.initialisation_helper.download_file_from_github')
    @patch('fivetran_connector_sdk.initialisation_helper.validate_example_directory')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_exact_match_does_not_include_prefix_collision(self, mock_get, mock_log, mock_validate, mock_download):
        """Test github does not match github_traffic files."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'github/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'github/requirements.txt', 'size': 128},
                {'type': 'blob', 'path': 'github_traffic/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        download_git_directory('github', self.test_project_dir)

        files_arg = mock_download.call_args[0][0]
        self.assertEqual(len(files_arg), 2)
        self.assertTrue(all('github_traffic' not in f['github_path'] for f in files_arg))

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_prefix_match_lists_valid_connectors_and_exits(self, mock_get, mock_log):
        """Test partial prefix lists matching connectors (by connector.py) and exits."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'github/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'github_traffic/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'other/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('git', self.test_project_dir)

        all_logs = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('github', all_logs)
        self.assertIn('github_traffic', all_logs)
        self.assertNotIn('other', all_logs)

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_prefix_match_skips_intermediate_directories(self, mock_get, mock_log):
        """Test that intermediate grouping dirs without connector.py are not listed."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'examples/quickstart/hello/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'examples/quickstart/hello_world/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('examples/quickstart', self.test_project_dir)

        all_logs = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('examples/quickstart/hello', all_logs)
        self.assertIn('examples/quickstart/hello_world', all_logs)

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_nested_example_prefix_match_lists_connectors_across_grouping_directories(self, mock_get, mock_log):
        """Test an example name prefix matches below intermediate grouping directories."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'examples/quickstart/hello/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'examples/advanced/hello_world/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'examples/quickstart/goodbye/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'other/quickstart/hello_other/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('examples/hello', self.test_project_dir)

        all_logs = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('did you mean any of the following', all_logs)
        self.assertIn('examples/quickstart/hello', all_logs)
        self.assertIn('examples/advanced/hello_world', all_logs)
        self.assertNotIn('examples/quickstart/goodbye', all_logs)
        self.assertNotIn('other/quickstart/hello_other', all_logs)

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_connectors_prefix_match_remains_scoped_to_root_directories(self, mock_get, mock_log):
        """Test connectors/ keeps its existing root-level prefix matching behavior."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'github/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'group/gitlab/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('connectors/git', self.test_project_dir)

        all_logs = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('github', all_logs)
        self.assertNotIn('group/gitlab', all_logs)

    @patch('fivetran_connector_sdk.initialisation_helper.download_file_from_github')
    @patch('fivetran_connector_sdk.initialisation_helper.validate_example_directory')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_trailing_slash_stripped_before_match(self, mock_get, mock_log, mock_validate, mock_download):
        """Test github/ (trailing slash) correctly matches github connector."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'github/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'github_traffic/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        download_git_directory('github/', self.test_project_dir)

        files_arg = mock_download.call_args[0][0]
        self.assertEqual(len(files_arg), 1)
        self.assertEqual(files_arg[0]['github_path'], 'github/connector.py')

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('requests.get')
    def test_parent_directory_lists_all_connectors_and_exits(self, mock_get, mock_log):
        """Test examples/ lists all connectors underneath and exits."""
        from fivetran_connector_sdk.initialisation_helper import download_git_directory

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'tree': [
                {'type': 'blob', 'path': 'examples/quickstart/hello/connector.py', 'size': 512},
                {'type': 'blob', 'path': 'examples/quickstart/hello/config.json', 'size': 128},
                {'type': 'blob', 'path': 'examples/quickstart/hello_world/connector.py', 'size': 512},
            ]
        }
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit):
            download_git_directory('examples/', self.test_project_dir)

        all_logs = ' '.join(str(c) for c in mock_log.call_args_list)
        self.assertIn('examples/quickstart/hello', all_logs)
        self.assertIn('examples/quickstart/hello_world', all_logs)
        self.assertIn('available connectors', all_logs)

    # ============================================================================
    # Tests for download_file_from_github() function
    # ============================================================================

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_success(self, mock_get, mock_makedirs, mock_exists, mock_file_open, mock_log):
        """Test successful file download from GitHub."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"file content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/connector.py',
                'local_path': 'connector.py',
                'size': 100
            }
        ]

        download_file_from_github(files_to_download, self.test_project_dir)

        # Verify file was opened and written
        mock_file_open.assert_called_once()
        mock_file_open().write.assert_called_once_with(b"file content")

        # Verify success was logged with SUCCESS icon
        self.assertTrue(any("downloaded" in str(call) for call in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=True)
    @patch('requests.get')
    def test_download_file_from_github_overwrite_existing(self, mock_get, mock_exists, mock_file_open, mock_log):
        """Test file download overwrites existing file when project-level overwrite is set."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"new content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/connector.py',
                'local_path': 'connector.py',
                'size': 100
            }
        ]

        download_file_from_github(files_to_download, self.test_project_dir)

        # Verify file was written
        mock_file_open().write.assert_called_once_with(b"new content")


    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_create_nested_directories(self, mock_get, mock_makedirs, mock_exists, mock_log):
        """Test file download creates nested directories."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/sub/dir/file.py',
                'local_path': 'sub/dir/file.py',
                'size': 100
            }
        ]

        with patch('builtins.open', mock_open()):
            download_file_from_github(files_to_download, self.test_project_dir, False)

        # Verify nested directories were created
        mock_makedirs.assert_called_once()
        self.assertIn('sub/dir', mock_makedirs.call_args[0][0])

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_handles_download_error(self, mock_get, mock_makedirs, mock_exists, mock_log):
        """Test file download handles HTTP errors gracefully."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github
        from fivetran_connector_sdk.logger import Logging

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/missing.py',
                'local_path': 'missing.py',
                'size': 100
            }
        ]

        download_file_from_github(files_to_download, self.test_project_dir, False)

        # Verify error was logged with FAILURE icon
        self.assertTrue(any("failed to download" in str(call) for call in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.open', side_effect=IOError("Permission denied"))
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_handles_write_error(self, mock_get, mock_makedirs, mock_exists, mock_file_open, mock_log):
        """Test file download handles file write errors gracefully."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github
        from fivetran_connector_sdk.logger import Logging

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/file.py',
                'local_path': 'file.py',
                'size': 100
            }
        ]

        download_file_from_github(files_to_download, self.test_project_dir, False)

        # Verify error was logged with FAILURE icon
        self.assertTrue(any("failed to download" in str(call) for call in mock_log.call_args_list))

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=False)
    @patch('os.path.dirname', return_value='')
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_file_in_root(self, mock_get, mock_makedirs, mock_dirname, mock_exists, mock_file_open, mock_log):
        """Test file download when file is in project root (no subdirectory)."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/file.py',
                'local_path': 'file.py',
                'size': 100
            }
        ]

        download_file_from_github(files_to_download, self.test_project_dir, False)

        # Verify makedirs was not called for empty directory
        # (directory creation is skipped when target_dir is empty)
        mock_file_open.assert_called_once()

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_multiple_files(self, mock_get, mock_makedirs, mock_exists, mock_file_open, mock_log):
        """Test downloading multiple files in one call."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"content"
        mock_get.return_value = mock_response

        files_to_download = [
            {'github_path': 'examples/test/file1.py', 'local_path': 'file1.py', 'size': 100},
            {'github_path': 'examples/test/file2.py', 'local_path': 'file2.py', 'size': 200},
            {'github_path': 'examples/test/file3.py', 'local_path': 'file3.py', 'size': 300}
        ]

        download_file_from_github(files_to_download, self.test_project_dir, False)

        # Verify all files were downloaded
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_file_open.call_count, 3)

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_constructs_correct_url(self, mock_get, mock_makedirs, mock_exists, mock_file_open, mock_log):
        """Test that raw GitHub URL is constructed correctly."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github
        from fivetran_connector_sdk.constants import EXAMPLES_GITHUB_REPO, GITHUB_BRANCH

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test_connector/connector.py',
                'local_path': 'connector.py',
                'size': 100
            }
        ]

        download_file_from_github(files_to_download, self.test_project_dir)

        # Verify correct URL was used
        expected_url = f"https://raw.githubusercontent.com/{EXAMPLES_GITHUB_REPO}/{GITHUB_BRANCH}/examples/test_connector/connector.py"
        mock_get.assert_called_once_with(expected_url, timeout=10)

    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('requests.get')
    def test_download_file_from_github_request_timeout(self, mock_get, mock_makedirs, mock_exists, mock_log):
        """Test file download with timeout parameter."""
        from fivetran_connector_sdk.initialisation_helper import download_file_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"content"
        mock_get.return_value = mock_response

        files_to_download = [
            {
                'github_path': 'examples/test/file.py',
                'local_path': 'file.py',
                'size': 100
            }
        ]

        with patch('builtins.open', mock_open()):
            download_file_from_github(files_to_download, self.test_project_dir, False)

        # Verify timeout was passed
        self.assertEqual(mock_get.call_args[1]['timeout'], 10)

    # ============================================================================
    # Integration Tests - These actually run init() and verify directory creation
    # ============================================================================

    @patch('builtins.input')
    def test_init_creates_project_with_template_connector(self, mock_input):
        """Integration test: init creates actual project directory with template connector files."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        # Mock user input: skip AI agent setup
        mock_input.side_effect = ['4']

        # Run init in interactive mode
        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.INTERACTIVE)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        # Verify project directory was created
        self.assertTrue(os.path.exists(self.test_project_path),
                       f"Project directory should exist at {self.test_project_path}")

        # Verify connector.py exists (required file from template)
        connector_file = os.path.join(self.test_project_path, "connector.py")
        self.assertTrue(os.path.exists(connector_file),
                       f"connector.py should exist at {connector_file}")

        # Verify the connector.py file has content
        with open(connector_file, 'r') as f:
            content = f.read()
            self.assertGreater(len(content), 0, "connector.py should not be empty")
            self.assertIn("def update", content, "connector.py should contain an update function")

        # Verify other expected files
        self.assertTrue(os.path.exists(os.path.join(self.test_project_path, "configuration.json")))
        self.assertTrue(os.path.exists(os.path.join(self.test_project_path, "requirements.txt")))

    @patch('builtins.input')
    def test_init_with_non_interactive_skips_existing(self, mock_input):
        """Integration test: non-interactive init skips existing project files."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        # Create project directory with a dummy file
        os.makedirs(self.test_project_path, exist_ok=True)
        dummy_file = os.path.join(self.test_project_path, "connector.py")
        with open(dummy_file, 'w') as f:
            f.write("# This is a dummy file that should not be overwritten")

        # Run init in non-interactive mode
        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.DEFAULT_ANSWER)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        mock_input.assert_not_called()

        # Verify the file was not overwritten
        with open(dummy_file, 'r') as f:
            content = f.read()
            self.assertIn("This is a dummy file", content,
                          "File should be preserved when non-interactive chooses no overwrite")

    @patch('builtins.input')
    def test_init_yes_overwrites_existing_files(self, mock_input):
        """Integration test: init with PromptMode.YES always overwrites existing files."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        mock_input.return_value = '4'

        os.makedirs(self.test_project_path, exist_ok=True)
        dummy_file = os.path.join(self.test_project_path, "connector.py")
        with open(dummy_file, 'w') as f:
            f.write("# dummy file that should be overwritten")

        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.YES)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        with open(dummy_file, 'r') as f:
            content = f.read()
            self.assertNotIn("dummy file", content)
            self.assertIn("def update", content)

    @patch('builtins.input')
    def test_init_non_interactive_keeps_existing_files(self, mock_input):
        """Integration test: init with PromptMode.DEFAULT_ANSWER keeps existing files (default N)."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        mock_input.return_value = '4'

        os.makedirs(self.test_project_path, exist_ok=True)
        dummy_file = os.path.join(self.test_project_path, "connector.py")
        original_content = "# original file that should NOT be overwritten"
        with open(dummy_file, 'w') as f:
            f.write(original_content)

        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.DEFAULT_ANSWER)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        with open(dummy_file, 'r') as f:
            content = f.read()
            self.assertEqual(content, original_content, "File should NOT be overwritten with DEFAULT_ANSWER mode")

    @patch('subprocess.run')
    @patch('fivetran_connector_sdk.initialisation_helper.detect_installed_agents',
           return_value={'claude': AGENT_PLUGINS['claude']['display_name']})
    @patch('builtins.input')
    def test_init_with_claude_runs_plugin_install_commands(self, mock_input, mock_detect, mock_run):
        """Integration test: selecting Claude runs the native plugin install commands."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        mock_input.side_effect = ['1']
        mock_run.return_value = MagicMock(returncode=0)

        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.INTERACTIVE)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        self.assertTrue(os.path.exists(self.test_project_path))
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(
            mock_run.call_args_list[0][0][0],
            AGENT_PLUGINS['claude']['install_commands'][0]
        )
        self.assertEqual(
            mock_run.call_args_list[1][0][0],
            AGENT_PLUGINS['claude']['install_commands'][1]
        )

    @patch('builtins.input')
    def test_init_preserves_directory_structure(self, mock_input):
        """Integration test: init preserves the directory structure from the template."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        # Mock user input: skip AI agent
        mock_input.side_effect = ['4']

        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.INTERACTIVE)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        # Verify key files exist
        expected_files = [
            "connector.py",
            "configuration.json",
            "requirements.txt"
        ]

        for file_name in expected_files:
            file_path = os.path.join(self.test_project_path, file_name)
            self.assertTrue(os.path.exists(file_path),
                          f"Expected file {file_name} should exist in project")

    @patch('builtins.input')
    def test_init_excludes_readme_from_template(self, mock_input):
        """Integration test: README files are excluded when downloading template."""
        from fivetran_connector_sdk.initialisation_helper import init
        from fivetran_connector_sdk.constants import TEMPLATE_CONNECTOR_PATH

        # Mock user input: skip AI agent
        mock_input.side_effect = ['4']

        try:
            init(self.test_project_path, TEMPLATE_CONNECTOR_PATH, PromptMode.INTERACTIVE)
        except SystemExit as e:
            self.assertEqual(e.code, 0)

        # Verify README files are not present
        readme_variations = ["README.md", "readme.md", "README.txt", "readme.txt"]
        for readme_file in readme_variations:
            readme_path = os.path.join(self.test_project_path, readme_file)
            self.assertFalse(os.path.exists(readme_path),
                           f"{readme_file} should be excluded from template")

    @patch('fivetran_connector_sdk.initialisation_helper.setup_ai_agent')
    @patch('fivetran_connector_sdk.initialisation_helper.setup_connector')
    @patch('fivetran_connector_sdk.initialisation_helper.print_library_log')
    @patch('builtins.input', return_value='y')
    @patch('sys.exit')
    def test_init_with_ignored_files_skips_overwrite_prompt_and_valid_files_prompts(
            self, mock_exit, mock_input, mock_log, mock_setup_connector, mock_setup_ai_agent):
        """Test that ignored files (.env, __pycache__) do not mark project as existing, but valid files (requirements.txt) do."""
        from fivetran_connector_sdk.initialisation_helper import init

        # 1. Create ignored directory and hidden file
        os.makedirs(os.path.join(self.test_project_path, "__pycache__"), exist_ok=True)
        with open(os.path.join(self.test_project_path, ".env"), "w") as f:
            f.write("SECRET=12345")

        # In interactive mode, ignored files should NOT trigger an overwrite prompt
        init(self.test_project_path, self.test_template, PromptMode.INTERACTIVE)
        mock_input.assert_not_called()
        mock_setup_connector.assert_called_with(self.test_project_path, self.test_template)

        # 2. Add a valid file (requirements.txt) to turn it into an existing project
        with open(os.path.join(self.test_project_path, "requirements.txt"), "w") as f:
            f.write("fivetran-connector-sdk")

        # Now interactive mode SHOULD trigger the overwrite prompt
        init(self.test_project_path, self.test_template, PromptMode.INTERACTIVE)
        mock_input.assert_called_once()
        mock_setup_connector.assert_called_with(self.test_project_path, self.test_template)


if __name__ == '__main__':
    unittest.main()
