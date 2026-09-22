import sys
import os
import io

from unittest.mock import patch, MagicMock, mock_open
from fivetran_connector_sdk.connector_helper import fetch_requirements_as_dict, dir_walker
from fivetran_connector_sdk.connector_helper import validate_requirements_file, REQUIREMENTS_TXT
from fivetran_connector_sdk.connector_helper import process_data_type, delete_file_if_exists
from fivetran_connector_sdk import Logging
from fivetran_connector_sdk.constants import (
    CONFIGURATION_FORM_FILENAME,
    ROOT_LOCATION,
    TESTER_LOCATION,
)
import unittest
from fivetran_connector_sdk.helpers import PromptMode

FIVETRAN_NAMING = "FIVETRAN_NAMING"


class TestConnectorHelper(unittest.TestCase):

    def test_process_tables(self):
        from fivetran_connector_sdk.connector_helper import process_tables

        response = [
            {
                "table": "my_table",
                "columns": {"col1": "STRING", "col2": "INT"},
                "primary_key": ["col1"],
            }
        ]
        table_list = {}

        process_tables(response, table_list)
        self.assertIn("my_table", table_list)
        table = table_list["my_table"]
        self.assertEqual(table.name, "my_table")
        col_names = [col.name for col in table.columns]
        self.assertIn("col1", col_names)
        self.assertIn("col2", col_names)
        col1 = next(col for col in table.columns if col.name == "col1")
        self.assertTrue(col1.primary_key)
        col2 = next(col for col in table.columns if col.name == "col2")
        self.assertFalse(col2.primary_key)

    @patch("builtins.print")
    def test_print_library_log(self, mock_print):
        from fivetran_connector_sdk.connector_helper import print_library_log

        print_library_log("test", Logging.Level.INFO)
        mock_print.assert_called()
        printed_args = mock_print.call_args[0][0]
        self.assertIn("test", printed_args)
        self.assertIn("INFO", printed_args)

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    def test_validate_requirements_file_success(
        self,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):

        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==1.0.0"},  # tmp_requirements
        ]

        # Should not raise or prompt
        validate_requirements_file("dummy_path", is_deploy=False, version="1.0.0")

        mock_copy.assert_called()
        mock_delete.assert_called()
        mock_subprocess_run.assert_called()

    @patch("fivetran_connector_sdk.connector_helper.time.sleep")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict", return_value={})
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.os.listdir", return_value=[])
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=True)
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    def test_validate_requirements_file_retries_and_fails(
        self,
        mock_subprocess_run,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_copy,
        mock_fetch,
        mock_delete,
        mock_print_log,
        mock_sleep,
    ):
        mock_subprocess_run.return_value = MagicMock(returncode=1, stderr="pipreqs error")

        validate_requirements_file("dummy_path", is_deploy=False, version="1.0.0")

        # Should log retry/failure messages
        self.assertTrue(
            any(
                "attempt" in str(call)
                for call in [args[0][0] for args in mock_print_log.call_args_list]
            )
        )
        self.assertTrue(
            any(
                "retrying after" in str(call)
                for call in [args[0][0] for args in mock_print_log.call_args_list]
            )
        )
        self.assertTrue(
            any(
                "pipreqs failed after" in str(call)
                for call in [args[0][0] for args in mock_print_log.call_args_list]
            )
        )
        self.assertTrue(
            any(
                "skipping requirements.txt validation" in str(call)
                for call in [args[0][0] for args in mock_print_log.call_args_list]
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    def test_corrupt_requirements_are_removed(
        self,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        # Simulate a corrupt requirement
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"~corrupt": "~corrupt==1.0.0", "package": "package==1.0.0"},  # tmp_requirements
        ]
        validate_requirements_file("dummy_path", is_deploy=False, version="1.0.0")
        self.assertTrue(True)
        for call in mock_fetch.call_args_list:
            requirements_dict = call[0][0]
            self.assertNotIn("~corrupt", requirements_dict)

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.input")
    def test_version_mismatch_deps_prompt_y(
        self,
        mock_input,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):

        # Setup mocks
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        # Simulate version mismatch
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==2.0.0"},  # tmp_requirements
        ]
        mock_input.return_value = "y"
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        mock_input.assert_any_call(
            "Would you like us to update requirements.txt to the current stable versions of the dependent libraries? (y/N): "
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.input")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_version_mismatch_deps_prompt_n(
        self,
        mock_log,
        mock_input,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==2.0.0"},  # tmp_requirements
        ]
        mock_input.return_value = "n"
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        mock_log.assert_any_call(
            f"Changes identified for libraries with version conflicts have been ignored. These changes have NOT been made to {REQUIREMENTS_TXT}."
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.input")
    def test_missing_deps_prompt_y(
        self,
        mock_input,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):

        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        # Simulate pipreqs returning no detected imports, so existing requirements look unused.
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==1.0.0", "missing": "missing==1.0.0"},  # tmp_requirements
        ]
        mock_input.return_value = "y"
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        print(mock_input.call_args_list)
        mock_input.assert_any_call(
            "Would you like us to update requirements.txt to add missing dependent libraries? (y/N): "
        )

    @patch("builtins.print")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.input")
    def test_empty_pipreqs_response(
        self,
        mock_input,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
        mock_print,
    ):

        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        # Simulate pipreqs returning no detected imports, so existing requirements look unused.
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {},  # tmp_requirements
        ]
        mock_input.return_value = ""
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        warning_calls = [
            call
            for call in mock_print.call_args_list
            if len(call[0]) > 0 and "package" in str(call[0][0])
        ]
        self.assertTrue(
            len(warning_calls) > 0, "Expected warning message containing 'package' to be printed"
        )
        mock_input.assert_not_called()
        mock_open_file().write.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.print")
    @patch("builtins.input")
    def test_unused_deps_logs_without_prompting_or_updating(
        self,
        mock_input,
        mock_print,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):

        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        # Simulate unused dep
        mock_fetch.side_effect = [
            {"package": "package==1.0.0", "unused": "unused==1.0.0"},  # requirements.txt
            {"package": "package==1.0.0"},  # tmp_requirements
        ]
        mock_input.return_value = ""
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        mock_input.assert_not_called()
        warning_calls = [
            call
            for call in mock_print.call_args_list
            if len(call[0]) > 0 and "unused" in str(call[0][0])
        ]
        self.assertTrue(
            len(warning_calls) > 0, "Expected warning message containing 'unused' to be printed"
        )
        mock_open_file().write.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.input")
    def test_unused_deps_does_not_prompt_or_abort(
        self,
        mock_input,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):

        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        # Simulate unused dep
        mock_fetch.side_effect = [
            {"package": "package==1.0.0", "unused": "unused==1.0.0"},  # requirements.txt
            {"package": "package==1.0.0"},  # tmp_requirements
        ]
        mock_input.return_value = "n"
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        mock_input.assert_not_called()
        mock_open_file().write.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("builtins.input")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_missing_deps_prompt_n(
        self,
        mock_log,
        mock_input,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
    ):
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==1.0.0", "missing": "missing==1.0.0"},  # tmp_requirements
        ]
        mock_input.return_value = "n"
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")
        mock_log.assert_any_call(
            f"Changes identified as missing dependencies for libraries have been ignored. These changes have NOT been made to {REQUIREMENTS_TXT}."
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("fivetran_connector_sdk.connector_helper.resolve_confirmation")
    def test_missing_deps_prompt_empty_input(
        self,
        mock_resolve_confirmation,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
        mock_log,
    ):
        """Test that empty input (pressing Enter) defaults to 'no' for missing dependencies"""
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==1.0.0", "missing": "missing==1.0.0"},  # tmp_requirements
        ]
        # Simulate user pressing Enter (empty input) which should default to False (no)
        mock_resolve_confirmation.return_value = False
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")

        # Verify resolve_confirmation was called with correct parameters
        mock_resolve_confirmation.assert_any_call(
            f"Would you like us to update {REQUIREMENTS_TXT} to add missing dependent libraries? (y/N): ",
            default=False,
            prompt_mode=PromptMode.INTERACTIVE,
        )

        # Verify the "ignored" message was logged
        mock_log.assert_any_call(
            f"Changes identified as missing dependencies for libraries have been ignored. These changes have NOT been made to {REQUIREMENTS_TXT}."
        )

        # Verify requirements.txt was not written
        mock_open_file().write.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch("fivetran_connector_sdk.connector_helper.subprocess.run")
    @patch("fivetran_connector_sdk.connector_helper.os.listdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir")
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists")
    @patch(
        "fivetran_connector_sdk.connector_helper.open",
        new_callable=mock_open,
        read_data="package==1.0.0\n",
    )
    @patch("fivetran_connector_sdk.connector_helper.resolve_confirmation")
    def test_version_mismatch_deps_prompt_empty_input(
        self,
        mock_resolve_confirmation,
        mock_open_file,
        mock_exists,
        mock_isdir,
        mock_listdir,
        mock_subprocess_run,
        mock_copy,
        mock_fetch,
        mock_delete,
        mock_log,
    ):
        """Test that empty input (pressing Enter) defaults to 'no' for version mismatch"""
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_listdir.return_value = []
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_fetch.side_effect = [
            {"package": "package==1.0.0"},  # requirements.txt
            {"package": "package==2.0.0"},  # tmp_requirements with version mismatch
        ]
        # Simulate user pressing Enter (empty input) which should default to False (no)
        mock_resolve_confirmation.return_value = False
        validate_requirements_file("dummy_path", is_deploy=True, version="1.0.0")

        # Verify resolve_confirmation was called with correct parameters
        mock_resolve_confirmation.assert_any_call(
            f"Would you like us to update {REQUIREMENTS_TXT} to the current stable versions of the dependent libraries? (y/N): ",
            default=False,
            prompt_mode=PromptMode.INTERACTIVE,
        )

        # Verify the "ignored" message was logged
        mock_log.assert_any_call(
            f"Changes identified for libraries with version conflicts have been ignored. These changes have NOT been made to {REQUIREMENTS_TXT}."
        )

        # Verify requirements.txt was not written
        mock_open_file().write.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.path.isfile", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.time.time", return_value=100000)
    def test_new_version_available(
        self,
        mock_time,
        mock_open_file,
        mock_rq_get,
        mock_isfile,
        mock_isdir,
        mock_makedirs,
        mock_log,
    ):
        # Simulate response with a newer version
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = '{"info": {"version": "2.0.0"}}'
        mock_rq_get.return_value = mock_response

        from fivetran_connector_sdk.connector_helper import check_newer_version
        from fivetran_connector_sdk.logger import Logging

        check_newer_version("1.0.0")
        mock_log.assert_any_call(
            "fivetran-connector-sdk 2.0.0 is available. (a newer release exists)",
            log_icon=Logging.LogIcon.LIGHTNING,
            level=Logging.Level.WARNING,
        )
        mock_log.assert_any_call(
            "run 'pip install --upgrade fivetran-connector-sdk' to update",
            log_icon=Logging.LogIcon.LIGHTNING,
            level=Logging.Level.WARNING,
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.path.isfile", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.time.time", return_value=100000)
    def test_no_new_version(
        self,
        mock_time,
        mock_open_file,
        mock_rq_get,
        mock_isfile,
        mock_isdir,
        mock_makedirs,
        mock_log,
    ):
        # Simulate response with the same version
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = '{"info": {"version": "1.0.0"}}'
        mock_rq_get.return_value = mock_response

        from fivetran_connector_sdk.connector_helper import check_newer_version

        check_newer_version("1.0.0")
        # Should not log a notice about a new version
        self.assertFalse(
            any(
                "new release" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.path.isfile", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.time.time", return_value=100000)
    def test_minor_version_newer_detected(
        self,
        mock_time,
        mock_open_file,
        mock_rq_get,
        mock_isfile,
        mock_isdir,
        mock_makedirs,
        mock_log,
    ):
        # 2.9.2 installed, 2.10.0 available: string comparison wrongly treats "2.10.0" < "2.9.2";
        # numeric tuple comparison correctly detects the update.
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = '{"info": {"version": "2.10.0"}}'
        mock_rq_get.return_value = mock_response

        from fivetran_connector_sdk.connector_helper import check_newer_version
        from fivetran_connector_sdk.logger import Logging

        check_newer_version("2.9.2")
        mock_log.assert_any_call(
            "fivetran-connector-sdk 2.10.0 is available. (a newer release exists)",
            log_icon=Logging.LogIcon.LIGHTNING,
            level=Logging.Level.WARNING,
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.path.isfile", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.time.time", return_value=100000)
    def test_minor_version_no_false_positive(
        self,
        mock_time,
        mock_open_file,
        mock_rq_get,
        mock_isfile,
        mock_isdir,
        mock_makedirs,
        mock_log,
    ):
        # 2.10.0 installed, 2.9.2 on PyPI: string comparison wrongly shows an update notice;
        # numeric tuple comparison correctly suppresses it.
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = '{"info": {"version": "2.9.2"}}'
        mock_rq_get.return_value = mock_response

        from fivetran_connector_sdk.connector_helper import check_newer_version

        check_newer_version("2.10.0")
        self.assertFalse(
            any(
                "is available" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=True)
    @patch("fivetran_connector_sdk.connector_helper.os.path.isfile", return_value=True)
    @patch(
        "fivetran_connector_sdk.connector_helper.open", new_callable=mock_open, read_data="99999"
    )
    @patch("fivetran_connector_sdk.connector_helper.time.time", return_value=100000)
    def test_recent_check_skips(
        self, mock_time, mock_open_file, mock_isfile, mock_isdir, mock_makedirs, mock_log
    ):
        from fivetran_connector_sdk.connector_helper import check_newer_version

        # Should return early and not log anything
        check_newer_version("1.0.0")
        mock_log.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.path.isfile", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.rq.get", side_effect=Exception("fail"))
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.time.time", return_value=100000)
    @patch("fivetran_connector_sdk.connector_helper.time.sleep")
    def test_request_fails_and_retries(
        self,
        mock_sleep,
        mock_time,
        mock_open_file,
        mock_rq_get,
        mock_isfile,
        mock_isdir,
        mock_makedirs,
        mock_log,
    ):
        from fivetran_connector_sdk.connector_helper import check_newer_version, MAX_RETRIES

        check_newer_version("1.0.0")
        # Should log a warning for each retry
        self.assertTrue(
            any(
                "unable to check for a newer version" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )
        self.assertEqual(mock_sleep.call_count, MAX_RETRIES)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_no_exit_calls(self, mock_log):
        from fivetran_connector_sdk.connector_helper import exit_check

        code = "def foo():\n    return 42\n"
        with patch("builtins.open", mock_open(read_data=code)):
            with patch("os.path.join", return_value="dummy_path/connector.py"):
                exit_check("dummy_path")
        mock_log.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_exit_call(self, mock_log):
        from fivetran_connector_sdk.connector_helper import exit_check

        code = "def foo():\n    exit()\n"
        with patch("builtins.open", mock_open(read_data=code)):
            with patch("os.path.join", return_value="dummy_path/connector.py"):
                exit_check("dummy_path")
        self.assertTrue(
            any(
                "avoid using exit()" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_os__exit_call(self, mock_log):
        from fivetran_connector_sdk.connector_helper import exit_check

        code = "def foo():\n    sys.exit(1)\n"
        with patch("builtins.open", mock_open(read_data=code)):
            with patch("os.path.join", return_value="dummy_path/connector.py"):
                exit_check("dummy_path")
        self.assertTrue(
            any(
                "avoid using sys.exit()" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_sys_exit_call(self, mock_log):
        from fivetran_connector_sdk.connector_helper import exit_check

        code = "def foo():\n    sys.exit(1)\n"
        with patch("builtins.open", mock_open(read_data=code)):
            with patch("os.path.join", return_value="dummy_path/connector.py"):
                exit_check("dummy_path")
        self.assertTrue(
            any(
                "avoid using sys.exit()" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_syntax_error(self, mock_log):
        from fivetran_connector_sdk.connector_helper import exit_check

        code = "def foo(:\n    pass\n"
        with patch("builtins.open", mock_open(read_data=code)):
            with patch("os.path.join", return_value="dummy_path/connector.py"):
                exit_check("dummy_path")
        self.assertTrue(
            any(
                "SyntaxError" in str(call)
                for call in [args[0][0] for args in mock_log.call_args_list]
            )
        )

    def test_empty_input(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        self.assertEqual(check_dict({}), {})
        self.assertEqual(check_dict(None), {})

    def test_non_dict_input(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        with self.assertRaises(ValueError):
            check_dict("not_a_dict")

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_string_only_with_non_string_value(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import check_dict

        # Should log and call sys.exit(1)
        check_dict({"a": 1, "b": "str"}, string_only=True)
        mock_log.assert_any_call(
            "invalid configuration file; all values must be strings\nreference: https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json#workingwithconfigurationjson",
            Logging.Level.SEVERE,
        )
        mock_exit.assert_called_once_with(1)

    def test_string_only_with_all_strings(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        d = {"a": "1", "b": "str"}
        self.assertEqual(check_dict(d, string_only=True), d)

    def test_string_only_false_with_mixed_types(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        d = {"a": 1, "b": "str"}
        self.assertEqual(check_dict(d, string_only=False), d)

    @patch("os.path.exists", return_value=False)
    def test_file_not_exists(self, mock_exists):
        result = fetch_requirements_as_dict("fake_path.txt")
        self.assertEqual(result, {})

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="package==1.0.0\n")
    def test_single_valid_requirement(self, mock_file, mock_exists):
        result = fetch_requirements_as_dict("requirements.txt")
        self.assertEqual(result, {"package": "package==1.0.0"})

    @patch("os.path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="pkg1==1.0.0\npkg2>=2.0.0\npkg3<=3.0.0\n",
    )
    def test_multiple_valid_requirements(self, mock_file, mock_exists):
        result = fetch_requirements_as_dict("requirements.txt")
        self.assertEqual(
            result, {"pkg1": "pkg1==1.0.0", "pkg2": "pkg2>=2.0.0", "pkg3": "pkg3<=3.0.0"}
        )

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="# comment\n\npkg==1.0.0\n")
    def test_comments_and_empty_lines(self, mock_file, mock_exists):
        result = fetch_requirements_as_dict("requirements.txt")
        self.assertEqual(result, {"pkg": "pkg==1.0.0"})

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="invalidformat\npkg==1.0.0\n")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_invalid_format(self, mock_log, mock_file, mock_exists):
        result = fetch_requirements_as_dict("requirements.txt")
        self.assertIn("pkg", result)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="my-pkg==1.2.3\n")
    def test_dash_in_package_name(self, mock_file, mock_exists):
        result = fetch_requirements_as_dict("requirements.txt")
        self.assertIn("my_pkg", result)
        self.assertEqual(result["my_pkg"], "my-pkg==1.2.3")

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="==\n")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_invalid_requirement_format(self, mock_log, mock_file, mock_exists):
        with patch(
            "fivetran_connector_sdk.connector_helper.fetch_requirements_from_file",
            return_value=["badline"],
        ):
            with patch("re.split", side_effect=ValueError("bad split")):
                result = fetch_requirements_as_dict("requirements.txt")
                mock_log.assert_called_once()
                self.assertEqual(result, {})

    def test_fetch_requirements_as_dict_file_not_exists(self):
        with patch("os.path.exists", return_value=False):
            result = fetch_requirements_as_dict("nonexistent.txt")
            assert result == {}

    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=False)
    def test_load_or_add_requirements_file_creates_file(self, mock_exists, mock_open_file):
        from fivetran_connector_sdk.connector_helper import load_or_add_requirements_file

        result = load_or_add_requirements_file("requirements.txt")
        mock_open_file.assert_called_once_with("requirements.txt", "w", encoding="utf-8")
        assert result == {}

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch(
        "fivetran_connector_sdk.connector_helper.load_or_add_requirements_file", return_value={}
    )
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=False)
    def test_validate_requirements_file_no_warning_when_no_deps(
        self, mock_exists, mock_load, mock_copy, mock_pipreqs, mock_fetch, mock_delete, mock_log
    ):
        mock_fetch.return_value = {}
        validate_requirements_file("/project", False, "1.0.0")
        warning_calls = [
            c
            for c in mock_log.call_args_list
            if c.args
            == ("`requirements.txt` file not found in your project folder", Logging.Level.WARNING)
        ]
        assert warning_calls == [], "WARNING must not fire when no deps detected"
        validation_calls = [c for c in mock_log.call_args_list if "Validation of" in str(c)]
        assert validation_calls == [], "Validation completed must not fire when no deps detected"

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch(
        "fivetran_connector_sdk.connector_helper.load_or_add_requirements_file", return_value={}
    )
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=False)
    def test_validate_requirements_file_no_validation_log_on_deploy_when_no_deps(
        self, mock_exists, mock_load, mock_copy, mock_pipreqs, mock_fetch, mock_delete, mock_log
    ):
        mock_fetch.return_value = {}
        validate_requirements_file("/project", True, "1.0.0")
        validation_calls = [c for c in mock_log.call_args_list if "Validation of" in str(c)]
        assert (
            validation_calls == []
        ), "Validation completed must not fire on deploy when no deps detected"

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch(
        "fivetran_connector_sdk.connector_helper.load_or_add_requirements_file", return_value={}
    )
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=False)
    def test_validate_requirements_file_warns_when_deps_found_and_file_absent(
        self, mock_exists, mock_load, mock_copy, mock_pipreqs, mock_fetch, mock_delete, mock_log
    ):
        mock_fetch.return_value = {"pandas": "pandas==2.0.0"}
        validate_requirements_file("/project", False, "1.0.0")
        warning_calls = [
            c
            for c in mock_log.call_args_list
            if c.args
            == ("`requirements.txt` file not found in your project folder", Logging.Level.WARNING)
        ]
        assert len(warning_calls) == 1, "WARNING must fire when file absent and deps detected"
        validation_calls = [c for c in mock_log.call_args_list if "Validation of" in str(c)]
        assert validation_calls == [], "Validation completed must not fire in non-deploy mode"

    def test_supported_types(self):
        from fivetran_connector_sdk.protos import common_pb2

        # Map of type string to expected attribute value
        type_map = {
            "BOOLEAN": 1,
            "SHORT": 2,
            "INT": 3,
            "LONG": 4,
            "FLOAT": 6,
            "DOUBLE": 7,
            "NAIVE_DATE": 8,
            "NAIVE_DATETIME": 9,
            "UTC_DATETIME": 10,
            "BINARY": 11,
            "XML": 12,
            "STRING": 13,
            "JSON": 14,
        }
        # Patch common_pb2.DataType to have these values
        with patch("fivetran_connector_sdk.connector_helper.common_pb2") as mock_pb2:
            for idx, (type_str, val) in enumerate(type_map.items(), 1):
                setattr(mock_pb2.DataType, type_str, val)
            for type_str, val in type_map.items():
                col = common_pb2.Column()
                process_data_type(col, type_str)
                self.assertEqual(col.type, val)

    def test_decimal_type_raises(self):
        from fivetran_connector_sdk.protos import common_pb2

        with patch("fivetran_connector_sdk.connector_helper.common_pb2"):
            col = common_pb2.Column()
            with self.assertRaises(ValueError) as cm:
                process_data_type(col, "DECIMAL")
            self.assertIn("DECIMAL data type missing precision and scale", str(cm.exception))

    def test_unrecognized_type_raises(self):
        from fivetran_connector_sdk.protos import common_pb2

        with patch("fivetran_connector_sdk.connector_helper.common_pb2"):
            col = common_pb2.Column()
            with self.assertRaises(ValueError) as cm:
                process_data_type(col, "FOOBAR")
            self.assertIn("Unrecognized column type encountered", str(cm.exception))

    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.connector_helper.os.remove")
    def test_file_exists(self, mock_remove, mock_exists):
        delete_file_if_exists("somefile.txt")
        mock_remove.assert_called_once_with("somefile.txt")

    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.os.remove")
    def test_file_not_exists(self, mock_remove, mock_exists):
        delete_file_if_exists("somefile.txt")
        mock_remove.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.common_pb2")
    def test_process_columns_all_types(self, mock_pb2):
        type_map = {
            "BOOLEAN": 1,
            "SHORT": 2,
            "INT": 3,
            "LONG": 4,
            "FLOAT": 6,
            "DOUBLE": 7,
            "NAIVE_DATE": 8,
            "NAIVE_DATETIME": 9,
            "UTC_DATETIME": 10,
            "BINARY": 11,
            "XML": 12,
            "STRING": 13,
            "JSON": 14,
            "DECIMAL": 15,
        }
        for k, v in type_map.items():
            setattr(mock_pb2.DataType, k, v)
        for t in type_map:
            if t == "DECIMAL":
                continue
            columns = {}
            entry = {"columns": {"col": t}}
            if t == "BOOLEAN":
                entry["primary_key"] = ["col"]
            from fivetran_connector_sdk.connector_helper import process_columns

            process_columns(columns, entry)
            self.assertIn("col", columns)
            self.assertEqual(columns["col"].type, type_map[t])
            if t == "BOOLEAN":
                self.assertTrue(columns["col"].primary_key)
        # Test DECIMAL dict
        columns = {}
        entry = {"columns": {"col": {"type": "DECIMAL", "precision": 5, "scale": 2}}}
        process_columns(columns, entry)
        self.assertEqual(columns["col"].type, type_map["DECIMAL"])
        # Check values directly instead of assert_called_with
        self.assertEqual(columns["col"].params.decimal.precision, 5)
        self.assertEqual(columns["col"].params.decimal.scale, 2)
        # Test DECIMAL string raises
        with self.assertRaises(ValueError) as excinfo:
            process_columns({}, {"columns": {"col": "DECIMAL"}})
        error_message = (
            "DECIMAL data type missing precision and scale. "
            "Use a dictionary for DECIMAL column type like: "
            """"col_name": {  # Decimal data type with precision and scale.\n"""
            """    "type": "DECIMAL",\n"""
            """    "precision": 15,\n"""
            """    "scale": 2\n"""
            """}"""
        )
        assert error_message == str(excinfo.exception)

        # Test NON-DECIMAL dict type raises
        with self.assertRaises(ValueError) as excinfo:
            entry = {"columns": {"foo": {"type": "NON-DECIMAL"}}}
            process_columns({}, entry)

        error_message = (
            f"Expecting DECIMAL data type for dictionary column entry, but got: NON-DECIMAL in entry: {entry} for column: foo. "
            "Dictionary type is only allowed for DECIMAL columns with 'precision' and 'scale' fields, as in: {'type': 'DECIMAL', 'precision': <int>, 'scale': <int>}. "
            "For all other data types, use a string as the column type."
        )
        assert error_message == str(excinfo.exception)

        # Test unsupported type (not str or dict) raises
        with self.assertRaises(ValueError) as excinfo:
            entry = {"columns": {"foo": object()}}  # Passing an unsupported type (not str or dict)
            process_columns({}, entry)
        error_message = f"Unrecognized column type for column: foo in entry: {entry}. Got: {entry['columns']['foo']}"
        assert error_message == str(excinfo.exception)

    @patch("fivetran_connector_sdk.connector_helper.common_pb2")
    def test_process_primary_keys(self, mock_pb2):
        from fivetran_connector_sdk.protos import common_pb2

        columns = {}
        entry = {"primary_key": ["id", "other"]}
        from fivetran_connector_sdk.connector_helper import process_primary_keys

        process_primary_keys(columns, entry)
        self.assertIn("id", columns)
        self.assertTrue(columns["id"].primary_key)
        self.assertIn("other", columns)
        self.assertTrue(columns["other"].primary_key)
        # Test with existing column
        col = common_pb2.Column()
        columns = {"id": col}
        process_primary_keys(columns, entry)
        self.assertTrue(columns["id"].primary_key)

    @patch("fivetran_connector_sdk.connector_helper.common_pb2")
    @patch("fivetran_connector_sdk.connector_helper.process_primary_keys")
    @patch("fivetran_connector_sdk.connector_helper.process_columns")
    def test_process_tables(self, mock_columns, mock_pkeys, mock_pb2):
        mock_pb2.Table = lambda name: MagicMock(name=name, columns=[])
        table_list = {}
        from fivetran_connector_sdk.connector_helper import process_tables

        # Test missing 'table'
        with self.assertRaises(TypeError) as cm:
            process_tables([{}], table_list)
        self.assertIn('can only concatenate str (not "dict") to str', str(cm.exception))
        # Test empty table name
        with self.assertRaises(ValueError):
            process_tables([{"table": ""}], {})
        # Test whitespace table name
        with self.assertRaises(ValueError):
            process_tables([{"table": "   "}], {})
        # Test duplicate table
        table_list = {"foo": "bar"}
        with self.assertRaises(ValueError):
            process_tables([{"table": "foo"}], table_list)
        # Test normal path
        table_list = {}
        with patch("fivetran_connector_sdk.connector_helper.TABLES", {}):
            process_tables([{"table": "t1", "primary_key": [], "columns": {}}], table_list)
            self.assertIn("t1", table_list)

    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_maybe_colorize_jar_output(self, mock_constants):
        from fivetran_connector_sdk.connector_helper import _maybe_colorize_jar_output

        mock_constants.DEBUGGING = False
        self.assertEqual(_maybe_colorize_jar_output("plain line"), "plain line")
        mock_constants.DEBUGGING = True
        self.assertIn("\033[196m", _maybe_colorize_jar_output("SEVERE error"))
        self.assertIn("\033[196m", _maybe_colorize_jar_output("Exception occurred"))
        self.assertIn("\033[130m", _maybe_colorize_jar_output("WARNING: something"))
        self.assertEqual(_maybe_colorize_jar_output("all good"), "all good")

    @patch("os.path.join", return_value="dummy_path/config.json")
    @patch("os.path.isfile", return_value=False)
    def test_config_file_not_exists(self, mock_isfile, mock_join):
        from fivetran_connector_sdk import update_base_url_if_required

        update_base_url_if_required()
        # Should do nothing, so no exception

    @patch("os.path.join", return_value="dummy_path/config.json")
    @patch("os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data='{"foo": "bar"}')
    @patch("json.load", return_value={"foo": "bar"})
    def test_config_file_no_base_url(self, mock_json, mock_open_file, mock_isfile, mock_join):
        from fivetran_connector_sdk import constants
        from fivetran_connector_sdk import update_base_url_if_required

        old_url = constants.PRODUCTION_BASE_URL
        update_base_url_if_required()
        self.assertEqual(constants.PRODUCTION_BASE_URL, old_url)

    @patch("os.path.join", return_value="dummy_path/config.json")
    @patch("os.path.isfile", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"production_base_url": "http://new.url"}',
    )
    @patch("json.load", return_value={"production_base_url": "http://new.url"})
    @patch("fivetran_connector_sdk.print_library_log")
    def test_config_file_with_base_url(
        self, mock_log, mock_json, mock_open_file, mock_isfile, mock_join
    ):
        from fivetran_connector_sdk import constants
        from fivetran_connector_sdk import update_base_url_if_required

        update_base_url_if_required()
        self.assertEqual(constants.PRODUCTION_BASE_URL, "http://new.url")

    @patch("socket.socket")
    def test_is_port_in_use_true(self, mock_socket):
        # Simulate connect_ex returning 0 (port in use)
        mock_socket.return_value.__enter__.return_value.connect_ex.return_value = 0
        from fivetran_connector_sdk.connector_helper import is_port_in_use

        self.assertTrue(is_port_in_use(50051))

    @patch("socket.socket")
    def test_is_port_in_use_false(self, mock_socket):
        # Simulate connect_ex returning non-zero (port not in use)
        mock_socket.return_value.__enter__.return_value.connect_ex.return_value = 1
        from fivetran_connector_sdk.connector_helper import is_port_in_use

        self.assertFalse(is_port_in_use(50051))

    @patch("fivetran_connector_sdk.connector_helper.is_port_in_use")
    def test_get_available_port_found(self, mock_is_port_in_use):
        # First port not in use
        mock_is_port_in_use.side_effect = [False]
        from fivetran_connector_sdk.connector_helper import get_available_port

        self.assertEqual(get_available_port(), 50049)

    @patch("fivetran_connector_sdk.connector_helper.is_port_in_use")
    def test_get_available_port_none(self, mock_is_port_in_use):
        # All ports in use
        mock_is_port_in_use.side_effect = [True] * 12
        from fivetran_connector_sdk.connector_helper import get_available_port

        self.assertIsNone(get_available_port())

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.upload_package")
    @patch("fivetran_connector_sdk.connector_helper.create_package")
    def test_package_project_success(
        self, mock_create_package, mock_upload_package, mock_delete, mock_exit
    ):
        from fivetran_connector_sdk.connector_helper import package_project

        mock_create_package.return_value = "dummy.zip"
        mock_upload_package.return_value = "pkg_123"
        configuration_form_method = MagicMock()

        result = package_project("proj", "key", configuration_form_method)

        mock_create_package.assert_called_once_with("proj", configuration_form_method)
        mock_upload_package.assert_called_once_with("dummy.zip", "key")
        mock_delete.assert_called_once_with("dummy.zip")
        mock_exit.assert_not_called()
        self.assertEqual(result, "pkg_123")

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.upload_package")
    @patch("fivetran_connector_sdk.connector_helper.create_package")
    def test_package_project_failure(
        self, mock_create_package, mock_upload_package, mock_delete, mock_exit
    ):
        from fivetran_connector_sdk.connector_helper import package_project

        mock_create_package.return_value = "dummy.zip"
        mock_upload_package.return_value = None

        package_project("proj", "key")

        mock_exit.assert_called_once_with(1)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open)
    @patch(
        "fivetran_connector_sdk.connector_helper.fetch_requirements_from_file",
        return_value=["pkg==1.0.0", "foo==2.0.0"],
    )
    def test_copy_requirements_file_to_tmp_requirements_file(
        self, mock_fetch, mock_open_file, mock_exists
    ):
        from fivetran_connector_sdk.connector_helper import (
            copy_requirements_file_to_tmp_requirements_file,
        )

        copy_requirements_file_to_tmp_requirements_file("requirements.txt", "tmp_requirements.txt")
        mock_fetch.assert_called_once_with("requirements.txt")
        mock_open_file.assert_called_once_with("tmp_requirements.txt", "w")
        handle = mock_open_file()
        handle.write.assert_called_once_with("pkg==1.0.0\nfoo==2.0.0")

    @patch("os.path.exists", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_from_file")
    @patch("builtins.open")
    def test_copy_requirements_file_to_tmp_requirements_file_file_not_exists(
        self, mock_open_file, mock_fetch, mock_exists
    ):
        from fivetran_connector_sdk.connector_helper import (
            copy_requirements_file_to_tmp_requirements_file,
        )

        copy_requirements_file_to_tmp_requirements_file("requirements.txt", "tmp_requirements.txt")
        mock_fetch.assert_not_called()
        mock_open_file.assert_not_called()

    def test_remove_unwanted_packages(self):
        from fivetran_connector_sdk.connector_helper import remove_unwanted_packages

        reqs = {
            "fivetran_connector_sdk": "fivetran_connector_sdk==1.0.0",
            "requests": "requests==2.0.0",
            "other": "other==3.0.0",
        }
        remove_unwanted_packages(reqs)
        self.assertNotIn("fivetran_connector_sdk", reqs)
        self.assertNotIn("requests", reqs)
        self.assertIn("other", reqs)

    def test_remove_unwanted_packages_no_unwanted(self):
        from fivetran_connector_sdk.connector_helper import remove_unwanted_packages

        reqs = {"foo": "foo==1.0.0"}
        remove_unwanted_packages(reqs)
        self.assertEqual(reqs, {"foo": "foo==1.0.0"})

    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_code", return_value=True)
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    def test_cleanup_uploaded_project_success(self, mock_exit, mock_cleanup):
        from fivetran_connector_sdk.connector_helper import cleanup_uploaded_project

        cleanup_uploaded_project("key", "pkg_123")
        mock_cleanup.assert_called_once_with("key", "pkg_123")
        mock_exit.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_code", return_value=False)
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    def test_cleanup_uploaded_project_failure(self, mock_exit, mock_cleanup):
        from fivetran_connector_sdk.connector_helper import cleanup_uploaded_project

        cleanup_uploaded_project("key", "pkg_123")
        mock_cleanup.assert_called_once_with("key", "pkg_123")
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.patch")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_update_connection_all_cases(self, mock_constants, mock_patch, mock_log):
        from fivetran_connector_sdk.connector_helper import (
            SETUP_TESTS_RUNNING_MESSAGE,
            update_connection,
        )

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        config = {"secrets_list": [{"key": "k", "value": "v"}], "foo": "bar"}
        resp = update_connection("cid", "cname", "gname", config, "pkg_123", "dkey", "agentid")

        self.assertEqual(resp, mock_response)
        mock_patch.assert_called_once()
        mock_log.assert_any_call(SETUP_TESTS_RUNNING_MESSAGE, log_icon=Logging.LogIcon.STEP)

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_failing_setup_tests")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_handle_failing_tests_message_and_exit(self, mock_log, mock_print_failing, mock_exit):
        from fivetran_connector_sdk.connector_helper import (
            handle_failing_tests_message_and_exit,
            Logging,
        )

        resp = MagicMock()
        resp.json.return_value = {"data": {"id": "conn-123", "setup_tests": []}}
        log_message = "Some error occurred"
        handle_failing_tests_message_and_exit(resp, log_message)

        mock_log.assert_any_call(log_message, Logging.Level.SEVERE)
        mock_print_failing.assert_called_once_with(resp)
        mock_log.assert_any_call("connection id: conn-123")
        mock_exit.assert_called_once_with(1)

    def test_are_setup_tests_failing_true(self):
        from fivetran_connector_sdk.connector_helper import are_setup_tests_failing

        response = MagicMock()
        response.json.return_value = {
            "data": {
                "setup_tests": [
                    {"status": "PASSED"},
                    {"status": "FAILED"},
                    {"status": "JOB_FAILED"},
                ]
            }
        }
        self.assertTrue(are_setup_tests_failing(response))

    def test_are_setup_tests_failing_false(self):
        from fivetran_connector_sdk.connector_helper import are_setup_tests_failing

        response = MagicMock()
        response.json.return_value = {
            "data": {
                "setup_tests": [
                    {"status": "PASSED"},
                    {"status": "PASSED"},
                ]
            }
        }
        self.assertFalse(are_setup_tests_failing(response))

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.post")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_create_connection_success(self, mock_constants, mock_post, mock_log, mock_user_agent):
        from fivetran_connector_sdk.connector_helper import (
            SETUP_TESTS_RUNNING_MESSAGE,
            create_connection,
        )

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_user_agent.return_value = "fivetran-connector-sdk/2.7.2/linux-x64"
        mock_response = MagicMock()
        mock_post.return_value = mock_response

        deploy_key = "key"
        group_id = "gid"
        config = {"foo": "bar"}
        hd_agent_id = "agent123"
        package_id = "pkg_123"

        result = create_connection(
            deploy_key, group_id, config, hd_agent_id, package_id, FIVETRAN_NAMING
        )

        mock_post.assert_called_once_with(
            "http://test/v1/connectors",
            headers={
                "Authorization": f"Basic {deploy_key}",
                "User-Agent": "fivetran-connector-sdk/2.7.2/linux-x64",
            },
            json={
                "group_id": group_id,
                "service": "connector_sdk",
                "config": config,
                "paused": True,
                "run_setup_tests": True,
                "sync_frequency": "360",
                "destination_schema_names": FIVETRAN_NAMING,
                "hybrid_deployment_agent_id": hd_agent_id,
            },
        )
        self.assertEqual(result, mock_response)
        mock_log.assert_any_call(SETUP_TESTS_RUNNING_MESSAGE, log_icon=Logging.LogIcon.STEP)

    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    def test_connection_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": {"items": [{"id": "conn-123", "service": "connector_sdk"}]}
        }
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_connection_details

        result = get_connection_details("my_conn", "my_group", "group_id", "deploy_key")
        self.assertEqual(result, ("conn-123", "connector_sdk"))

    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    def test_connection_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"items": []}}
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_connection_details

        result = get_connection_details("my_conn", "my_group", "group_id", "deploy_key")
        self.assertIsNone(result)

    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    def test_request_failed(self, mock_exit, mock_log, mock_get):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_connection_details

        get_connection_details("my_conn", "my_group", "group_id", "deploy_key")
        mock_log.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.zip_folder")
    def test_create_upload_file_returns_zip_path(self, mock_zip_folder, mock_log):
        from fivetran_connector_sdk.connector_helper import (
            create_package,
            CONFIGURATION_FORM_FILENAME,
        )
        from fivetran_connector_sdk.logger import Logging

        mock_zip_folder.return_value = "some/path/project.zip"
        result = create_package("some/path")
        mock_log.assert_any_call("packaging project for upload", log_icon=Logging.LogIcon.STEP)
        mock_zip_folder.assert_called_once_with(
            "some/path", extra_files={CONFIGURATION_FORM_FILENAME: b""}
        )
        assert result == "some/path/project.zip"

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.zip_folder")
    def test_create_package_initializes_log_level_before_packaging_logged_form(
        self, mock_zip_folder, mock_log
    ):
        from fivetran_connector_sdk.connector_helper import (
            create_package,
            CONFIGURATION_FORM_FILENAME,
        )
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.logger import Logging

        original_level = Logging.LOG_LEVEL
        Logging.LOG_LEVEL = None
        try:

            def logged_form():
                Logging.info("building configuration form for packaging")
                return ConfigurationForm()

            mock_zip_folder.return_value = "some/path/project.zip"

            result = create_package("some/path", logged_form)

            extra_files = mock_zip_folder.call_args.kwargs["extra_files"]
            self.assertIn(CONFIGURATION_FORM_FILENAME, extra_files)
            self.assertEqual(Logging.LOG_LEVEL, Logging.Level.INFO)
            self.assertEqual(result, "some/path/project.zip")
        finally:
            Logging.LOG_LEVEL = original_level

    @patch("fivetran_connector_sdk.connector_helper.os.path.join", return_value="proj/upload.zip")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    def test_zip_folder_success(self, mock_dir_walker, mock_zipfile, mock_join):
        mock_dir_walker.return_value = [
            ("proj", ["connector.py", "foo.txt"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        from fivetran_connector_sdk.connector_helper import zip_folder

        result = zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})
        self.assertEqual(result, "proj/upload.zip")
        self.assertEqual(mock_zip.write.call_count, 2)

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.path.join", return_value="proj/upload.zip")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    def test_missing_connector_file(
        self, mock_dir_walker, mock_zipfile, mock_join, mock_log, mock_exit
    ):
        mock_dir_walker.return_value = [
            ("proj", ["foo.txt"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        from fivetran_connector_sdk.connector_helper import zip_folder

        zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})
        mock_log.assert_any_call(
            "connector.py not found in the project root\nthis file is required to start a sync and must be named in lowercase",
            Logging.Level.SEVERE,
        )
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.os.path.join", return_value="proj/upload.zip")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    def test_custom_drivers_without_install_script(
        self, mock_dir_walker, mock_zipfile, mock_join, mock_log, mock_exit
    ):
        mock_dir_walker.return_value = [
            ("proj", ["connector.py"]),
            ("proj/drivers", ["driver1.jar"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        from fivetran_connector_sdk.connector_helper import zip_folder

        zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})
        mock_log.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_zip_folder_dynamic_filename_from_project_name(
        self, mock_makedirs, mock_dir_walker, mock_zipfile
    ):
        """Test zip_folder creates zip filename based on project folder name"""
        from fivetran_connector_sdk.connector_helper import zip_folder

        mock_dir_walker.return_value = [("/path/to/my_connector", ["connector.py"])]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        result = zip_folder(
            "/path/to/my_connector", extra_files={CONFIGURATION_FORM_FILENAME: b""}
        )

        # Verify filename is derived from project name, not hardcoded
        self.assertIn("my_connector.zip", result)
        self.assertIn("/path/to/my_connector/files/my_connector.zip", result)

    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_zip_folder_handles_trailing_slash(self, mock_makedirs, mock_dir_walker, mock_zipfile):
        """Test zip_folder handles paths with trailing slashes correctly"""
        from fivetran_connector_sdk.connector_helper import zip_folder

        mock_dir_walker.return_value = [("/path/to/test_project/", ["connector.py"])]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        result = zip_folder(
            "/path/to/test_project/", extra_files={CONFIGURATION_FORM_FILENAME: b""}
        )

        # Should still use "test_project.zip" despite trailing slash
        self.assertIn("test_project.zip", result)
        self.assertNotIn("/.zip", result)

    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_zip_folder_fallback_to_upload_filename(
        self, mock_makedirs, mock_dir_walker, mock_zipfile
    ):
        """Test zip_folder falls back to UPLOAD_FILENAME for root path"""
        from fivetran_connector_sdk.connector_helper import zip_folder
        from fivetran_connector_sdk.constants import UPLOAD_FILENAME

        mock_dir_walker.return_value = [("/", ["connector.py"])]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        result = zip_folder("/", extra_files={CONFIGURATION_FORM_FILENAME: b""})

        # Root path should fall back to UPLOAD_FILENAME constant
        self.assertIn(UPLOAD_FILENAME, result)
        self.assertEqual(UPLOAD_FILENAME, "code.zip")

    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_zip_folder_resolves_relative_paths(
        self, mock_makedirs, mock_dir_walker, mock_zipfile
    ):
        """Test zip_folder resolves relative paths to actual folder names"""
        from fivetran_connector_sdk.connector_helper import zip_folder
        import os

        mock_dir_walker.return_value = [(".", ["connector.py"])]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        # Current directory should resolve to actual folder name
        cwd = os.getcwd()
        expected_name = os.path.basename(cwd)

        result = zip_folder(".", extra_files={CONFIGURATION_FORM_FILENAME: b""})

        # Should use actual folder name, not "."
        self.assertIn(f"{expected_name}.zip", result)
        self.assertNotIn("..zip", result)

    @patch("fivetran_connector_sdk.connector_helper.os.path.join", return_value="proj/upload.zip")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    def test_custom_drivers_with_install_script(self, mock_dir_walker, mock_zipfile, mock_join):
        mock_dir_walker.return_value = [
            ("proj", ["connector.py"]),
            ("proj/drivers", ["driver1.jar", "installation.sh"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip
        from fivetran_connector_sdk.connector_helper import zip_folder

        result = zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})
        self.assertEqual(result, "proj/upload.zip")
        self.assertEqual(mock_zip.write.call_count, 3)

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_drivers_folder_uppercase_D_not_treated_as_drivers(
        self, mock_makedirs, mock_dir_walker, mock_zipfile, mock_log, mock_exit
    ):
        import os
        from unittest.mock import call

        from fivetran_connector_sdk.connector_helper import zip_folder
        from fivetran_connector_sdk.constants import OUTPUT_FILES_DIR
        from zipfile import ZIP_DEFLATED

        mock_dir_walker.return_value = [
            ("proj", ["connector.py"]),
            ("proj/Drivers", ["driver1.jar"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        result = zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})

        expected_upload_filepath = os.path.join("proj", OUTPUT_FILES_DIR, "proj.zip")
        self.assertEqual(result, expected_upload_filepath)
        mock_zipfile.assert_called_once_with(expected_upload_filepath, "w", ZIP_DEFLATED)
        mock_zip.write.assert_has_calls(
            [
                call(
                    os.path.join("proj", "connector.py"),
                    os.path.relpath(os.path.join("proj", "connector.py"), "proj"),
                ),
                call(
                    os.path.join("proj", "Drivers", "driver1.jar"),
                    os.path.relpath(os.path.join("proj", "Drivers", "driver1.jar"), "proj"),
                ),
            ],
            any_order=False,
        )
        self.assertEqual(mock_zip.write.call_count, 2)
        mock_exit.assert_not_called()
        mock_log.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_drivers_folder_all_caps_not_treated_as_drivers(
        self, mock_makedirs, mock_dir_walker, mock_zipfile, mock_log, mock_exit
    ):
        import os
        from unittest.mock import call

        from fivetran_connector_sdk.connector_helper import zip_folder
        from fivetran_connector_sdk.constants import OUTPUT_FILES_DIR
        from zipfile import ZIP_DEFLATED

        mock_dir_walker.return_value = [
            ("proj", ["connector.py"]),
            ("proj/DRIVERS", ["driver1.jar"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip
        result = zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})
        expected_upload_filepath = os.path.join("proj", OUTPUT_FILES_DIR, "proj.zip")
        self.assertEqual(result, expected_upload_filepath)
        mock_zipfile.assert_called_once_with(expected_upload_filepath, "w", ZIP_DEFLATED)
        mock_zip.write.assert_has_calls(
            [
                call(
                    os.path.join("proj", "connector.py"),
                    os.path.relpath(os.path.join("proj", "connector.py"), "proj"),
                ),
                call(
                    os.path.join("proj", "DRIVERS", "driver1.jar"),
                    os.path.relpath(os.path.join("proj", "DRIVERS", "driver1.jar"), "proj"),
                ),
            ],
            any_order=False,
        )
        self.assertEqual(mock_zip.write.call_count, 2)
        mock_exit.assert_not_called()
        mock_log.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.dir_walker")
    @patch("os.makedirs")
    def test_drivers_folder_lowercase_detected_as_drivers(
        self, mock_makedirs, mock_dir_walker, mock_zipfile, mock_log, mock_exit
    ):
        from fivetran_connector_sdk.connector_helper import zip_folder

        mock_dir_walker.return_value = [
            ("proj", ["connector.py"]),
            ("proj/drivers", ["driver1.jar"]),
        ]
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip
        zip_folder("proj", extra_files={CONFIGURATION_FORM_FILENAME: b""})
        mock_exit.assert_called_once_with(1)
        mock_log.assert_called_once()

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_basic(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        from fivetran_connector_sdk.connector_helper import dir_walker

        # No .gitignore patterns for basic test
        mock_load_gitignore.return_value = []

        def listdir_side_effect(path):
            if path == "top":
                return ["file1.py", "file2.txt", "requirements.txt", "subdir", "drivers"]
            elif path == "top/subdir":
                return ["file3.py"]
            elif path == "top/drivers":
                return ["driver1.jar", "installation.sh", "driver2.txt"]
            return []

        def isdir_side_effect(path):
            return path in ["top/subdir", "top/drivers"]

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("top"))

        self.assertIn(("top", ["file1.py", "file2.txt", "requirements.txt"]), result)
        self.assertIn(("top/subdir", ["file3.py"]), result)
        self.assertIn(("top/drivers", ["driver1.jar", "installation.sh", "driver2.txt"]), result)

    @patch("fivetran_connector_sdk.connector_helper.get_os_arch_suffix")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.post")
    @patch("builtins.open", new_callable=mock_open, read_data="data")
    def test_upload_success(self, mock_file, mock_post, mock_log, mock_os_arch):
        from fivetran_connector_sdk.connector_helper import upload_package
        from fivetran_connector_sdk.logger import Logging

        mock_os_arch.return_value = "test-arch"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"data": {"id": "pkg_123"}}
        mock_post.return_value = mock_response

        result = upload_package("file.zip", "key")
        self.assertEqual(result, "pkg_123")
        mock_log.assert_any_call("uploading package", log_icon=Logging.LogIcon.STEP)

    @patch("fivetran_connector_sdk.connector_helper.get_os_arch_suffix")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.post")
    @patch("builtins.open", new_callable=mock_open, read_data="data")
    def test_upload_failure(self, mock_file, mock_post, mock_log, mock_os_arch):
        from fivetran_connector_sdk.connector_helper import upload_package, Logging

        mock_os_arch.return_value = "test-arch"
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.reason = "Bad Request"
        mock_response.text = '{"message" : "File not valid"}'
        mock_post.return_value = mock_response

        result = upload_package("file.zip", "key")
        self.assertIsNone(result)
        mock_log.assert_any_call(
            "failed to upload the package error: Bad Request: File not valid",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.delete")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_cleanup_success(self, mock_constants, mock_delete, mock_log, mock_user_agent):
        from fivetran_connector_sdk.connector_helper import cleanup_uploaded_code
        from fivetran_connector_sdk.logger import Logging

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_user_agent.return_value = "fivetran-connector-sdk/2.7.2/linux-x64"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_delete.return_value = mock_response

        result = cleanup_uploaded_code("key", "pkg_123")
        mock_delete.assert_called_once_with(
            "http://test/v1/connector-sdk/packages/pkg_123",
            headers={
                "Authorization": "Basic key",
                "User-Agent": "fivetran-connector-sdk/2.7.2/linux-x64",
            },
        )
        mock_log.assert_any_call(
            "cleaning up orphaned package: pkg_123", log_icon=Logging.LogIcon.STEP
        )
        self.assertTrue(result)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.delete")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_cleanup_failure(self, mock_constants, mock_delete, mock_log):
        from fivetran_connector_sdk.connector_helper import cleanup_uploaded_code, Logging

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.reason = "Not Found"
        mock_delete.return_value = mock_response

        result = cleanup_uploaded_code("key", "pkg_123")
        mock_log.assert_any_call(
            "cleaning up orphaned package: pkg_123", log_icon=Logging.LogIcon.STEP
        )
        mock_log.assert_any_call(
            "failed to cleanup orphaned package error: Not Found",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        self.assertFalse(result)

    @patch("platform.system")
    @patch("platform.machine")
    def test_supported_os_arch(self, mock_machine, mock_system):
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        # Example: Linux x86_64
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        # Adjust expected value based on your OS_MAP and ARCH_MAP
        self.assertEqual(get_os_arch_suffix(), "linux-x64")

    @patch("platform.system")
    @patch("platform.machine")
    def test_unsupported_os(self, mock_machine, mock_system):
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        mock_system.return_value = "Solaris"
        mock_machine.return_value = "x86_64"
        with self.assertRaises(RuntimeError) as cm:
            get_os_arch_suffix()
        self.assertIn("unsupported OS", str(cm.exception))

    @patch("platform.system")
    @patch("platform.machine")
    def test_unsupported_arch(self, mock_machine, mock_system):
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        mock_system.return_value = "Linux"
        mock_machine.return_value = "armv7l"
        with self.assertRaises(RuntimeError) as cm:
            get_os_arch_suffix()
        self.assertIn("unsupported architecture", str(cm.exception))

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_single_group_no_name(self, mock_constants, mock_get, mock_exit, mock_log):
        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"items": [{"id": "gid", "name": "gname"}]}}
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_group_info

        result = get_group_info("", "key")
        self.assertEqual(result, ("gid", "gname"))

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_multiple_groups_no_name(self, mock_constants, mock_get, mock_exit, mock_log):
        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": {"items": [{"id": "gid1", "name": "g1"}, {"id": "gid2", "name": "g2"}]}
        }
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_group_info

        get_group_info("", "key")
        mock_log.assert_called()
        self.assertGreaterEqual(mock_exit.call_count, 1)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_group_found(self, mock_constants, mock_get, mock_exit, mock_log):
        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"items": [{"id": "gid", "name": "gname"}]}}
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_group_info

        result = get_group_info("gname", "key")
        self.assertEqual(result, ("gid", "gname"))

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_group_not_found(self, mock_constants, mock_get, mock_exit, mock_log):
        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"items": [{"id": "gid", "name": "gname"}]}}
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_group_info

        get_group_info("notfound", "key")
        mock_log.assert_called()
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit", side_effect=SystemExit)
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_request_failed(self, mock_constants, mock_get, mock_exit, mock_log):
        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        from fivetran_connector_sdk.connector_helper import get_group_info

        with self.assertRaises(SystemExit):
            get_group_info("gname", "key")
        mock_log.assert_called()
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    def test_no_groups_exits(self, mock_exit, mock_log):
        from fivetran_connector_sdk.connector_helper import Logging

        # Simulate empty groups
        groups = []
        # Call the code under test
        if not groups:
            from fivetran_connector_sdk.connector_helper import print_library_log

            print_library_log("No destinations defined in the account", Logging.Level.SEVERE)
            import os

            sys.exit(1)
        mock_log.assert_called_once_with(
            "No destinations defined in the account", Logging.Level.SEVERE
        )
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    def test_groups_pagination_parsing(self, mock_get):
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {
            "data": {
                "items": [{"id": "gid1", "name": "g1"}, {"id": "gid2", "name": "g2"}],
                "next_cursor": "abc123",
            }
        }
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {
            "data": {
                "items": [{"id": "gid3", "name": "g3"}, {"id": "gid4", "name": "aa"}]
                # No next_cursor, so pagination ends
            }
        }
        mock_get.side_effect = [mock_resp1, mock_resp2]

        from fivetran_connector_sdk.connector_helper import get_group_info

        result = get_group_info("aa", "key")
        assert result is not None
        self.assertEqual(result, ("gid4", "aa"))
        mock_get.assert_called()

    @patch("os.path.join", side_effect=lambda *args: "/".join(args))
    def test_java_exe_helper_windows(self, mock_join):
        from fivetran_connector_sdk.connector_helper import java_exe_helper, WIN_OS, X64

        result = java_exe_helper("C:/java", f"{WIN_OS}-{X64}")
        self.assertEqual(result, "C:/java/bin/java.exe")

    @patch("os.path.join", side_effect=lambda *args: "/".join(args))
    def test_java_exe_helper_windows_arm64(self, mock_join):
        from fivetran_connector_sdk.connector_helper import java_exe_helper, WIN_OS, ARM_64

        result = java_exe_helper("C:/java", f"{WIN_OS}-{ARM_64}")
        self.assertEqual(result, "C:/java/bin/java.exe")

    @patch("os.path.join", side_effect=lambda *args: "/".join(args))
    def test_java_exe_helper_non_windows(self, mock_join):
        from fivetran_connector_sdk.connector_helper import java_exe_helper

        result = java_exe_helper("/usr/lib/jvm", "linux-x64")
        self.assertEqual(result, "/usr/lib/jvm/bin/java")

    def test_process_stream_filters_pattern(self):
        from fivetran_connector_sdk.connector_helper import process_stream

        input_text = (
            "This is a normal line\n"
            "import com.fivetran.partner_sdk.foo.tools.testers.Bar\n"
            "Another normal line\n"
            "com.fivetran.partner_sdk.some.tools.testers.Baz should be removed\n"
            "Keep this line\n"
        )
        expected_output = ["This is a normal line\n", "Another normal line\n", "Keep this line\n"]
        stream = io.StringIO(input_text)
        result = list(process_stream(stream))
        self.assertEqual(result, expected_output)

    def test_process_stream_no_matches(self):
        from fivetran_connector_sdk.connector_helper import process_stream

        input_text = "No pattern here\n" "Still nothing\n"
        stream = io.StringIO(input_text)
        result = list(process_stream(stream))
        self.assertEqual(result, ["No pattern here\n", "Still nothing\n"])

    def test_process_stream_all_match(self):
        from fivetran_connector_sdk.connector_helper import process_stream

        input_text = (
            "com.fivetran.partner_sdk.foo.tools.testers.Bar\n"
            "com.fivetran.partner_sdk.bar.tools.testers.Baz\n"
        )
        stream = io.StringIO(input_text)
        result = list(process_stream(stream))
        self.assertEqual(result, [])

    @patch(
        "fivetran_connector_sdk.connector_helper._maybe_colorize_jar_output",
        side_effect=lambda x: x,
    )
    @patch("fivetran_connector_sdk.connector_helper.process_stream")
    @patch("fivetran_connector_sdk.connector_helper.subprocess")
    @patch("fivetran_connector_sdk.connector_helper.os.mkdir")
    @patch(
        "fivetran_connector_sdk.connector_helper.os.path.join",
        side_effect=lambda *args: "/".join(args),
    )
    def test_run_tester_success(
        self, mock_join, mock_mkdir, mock_subprocess, mock_process_stream, mock_colorize
    ):
        from fivetran_connector_sdk.connector_helper import run_tester

        mock_popen = MagicMock()
        mock_popen.stdout = MagicMock()
        mock_popen.stderr = MagicMock()
        mock_popen.wait.return_value = 0
        mock_subprocess.Popen.return_value = mock_popen
        mock_process_stream.side_effect = [
            iter(["stderr line 1", "stderr line 2"]),
            iter(["stdout line 1", "stdout line 2"]),
        ]

        # Call function and collect output
        result = list(run_tester("java", "root", "proj", 1234, "{}", {}, FIVETRAN_NAMING))
        self.assertIn("stderr line 1", result)
        self.assertIn("stdout line 2", result)
        mock_mkdir.assert_called_once()
        mock_subprocess.Popen.assert_called_once()
        mock_popen.stdout.close.assert_called_once()
        mock_popen.wait.assert_called_once()

    @patch(
        "fivetran_connector_sdk.connector_helper._maybe_colorize_jar_output",
        side_effect=lambda x: x,
    )
    @patch("fivetran_connector_sdk.connector_helper.process_stream")
    @patch("fivetran_connector_sdk.connector_helper.subprocess")
    @patch("fivetran_connector_sdk.connector_helper.os.mkdir", side_effect=FileExistsError)
    @patch(
        "fivetran_connector_sdk.connector_helper.os.path.join",
        side_effect=lambda *args: "/".join(args),
    )
    def test_run_tester_nonzero_exit(
        self, mock_join, mock_mkdir, mock_subprocess, mock_process_stream, mock_colorize
    ):
        import subprocess as real_subprocess
        from fivetran_connector_sdk.connector_helper import run_tester

        mock_popen = MagicMock()
        mock_popen.stdout = MagicMock()
        mock_popen.stderr = MagicMock()
        mock_popen.wait.return_value = 1
        mock_subprocess.Popen.return_value = mock_popen
        mock_process_stream.side_effect = [iter([]), iter([])]

        # Patch CalledProcessError to the real one
        with patch(
            "fivetran_connector_sdk.connector_helper.subprocess.CalledProcessError",
            real_subprocess.CalledProcessError,
        ):
            with self.assertRaises(real_subprocess.CalledProcessError):
                list(run_tester("java", "root", "proj", 1234, "{}", {}, FIVETRAN_NAMING))

    @patch(
        "fivetran_connector_sdk.connector_helper._maybe_colorize_jar_output",
        side_effect=lambda x: x,
    )
    @patch("fivetran_connector_sdk.connector_helper.process_stream")
    @patch("fivetran_connector_sdk.connector_helper.subprocess")
    @patch("fivetran_connector_sdk.connector_helper.os.mkdir", side_effect=FileExistsError)
    @patch(
        "fivetran_connector_sdk.connector_helper.os.path.join",
        side_effect=lambda *args: "/".join(args),
    )
    def test_run_tester_redacts_configuration_on_error(
        self, mock_join, mock_mkdir, mock_subprocess, mock_process_stream, mock_colorize
    ):
        import subprocess as real_subprocess
        from fivetran_connector_sdk.connector_helper import run_tester
        from fivetran_connector_sdk.constants import REDACTED_VALUE
        import json

        mock_popen = MagicMock()
        mock_popen.stdout = MagicMock()
        mock_popen.stderr = MagicMock()
        mock_popen.wait.return_value = 1
        mock_subprocess.Popen.return_value = mock_popen
        mock_process_stream.side_effect = [iter([]), iter([])]

        # Configuration with sensitive data
        config = {"username": "admin", "password": "secret123", "api_key": "abc123"}
        redacted_config_expected = json.dumps(
            {"username": REDACTED_VALUE, "password": REDACTED_VALUE, "api_key": REDACTED_VALUE}
        )

        # Patch CalledProcessError to the real one
        with patch(
            "fivetran_connector_sdk.connector_helper.subprocess.CalledProcessError",
            real_subprocess.CalledProcessError,
        ):
            with self.assertRaises(real_subprocess.CalledProcessError) as context:
                list(run_tester("java", "root", "proj", 1234, "{}", config, FIVETRAN_NAMING))

        # Verify the exception command contains redacted configuration, not actual values
        exception_cmd = context.exception.cmd
        cmd_str = " ".join(exception_cmd)
        self.assertIn(redacted_config_expected, cmd_str)
        self.assertNotIn("secret123", cmd_str)
        self.assertNotIn("abc123", cmd_str)

    @patch(
        "fivetran_connector_sdk.connector_helper._maybe_colorize_jar_output",
        side_effect=lambda x: x,
    )
    @patch("fivetran_connector_sdk.connector_helper.process_stream")
    @patch("fivetran_connector_sdk.connector_helper.subprocess")
    @patch("fivetran_connector_sdk.connector_helper.os.mkdir", side_effect=FileExistsError)
    @patch(
        "fivetran_connector_sdk.connector_helper.os.path.join",
        side_effect=lambda *args: "/".join(args),
    )
    def test_run_tester_redacts_configuration_with_fewer_keys(
        self, mock_join, mock_mkdir, mock_subprocess, mock_process_stream, mock_colorize
    ):
        import subprocess as real_subprocess
        from fivetran_connector_sdk.connector_helper import run_tester
        import json

        mock_popen = MagicMock()
        mock_popen.stdout = MagicMock()
        mock_popen.stderr = MagicMock()
        mock_popen.wait.return_value = 1
        mock_subprocess.Popen.return_value = mock_popen
        mock_process_stream.side_effect = [iter([]), iter([])]

        # Configuration with fewer keys (different from test_run_tester_redacts_configuration_on_error)
        config = {"username": "admin", "password": "secret123"}

        # Patch CalledProcessError to the real one
        with patch(
            "fivetran_connector_sdk.connector_helper.subprocess.CalledProcessError",
            real_subprocess.CalledProcessError,
        ):
            with self.assertRaises(real_subprocess.CalledProcessError) as context:
                # run_tester will automatically redact configuration on error
                list(run_tester("java", "root", "proj", 1234, "{}", config, FIVETRAN_NAMING))

        # Verify the exception command has redacted configuration
        exception_cmd = context.exception.cmd
        cmd_str = " ".join(exception_cmd)
        from fivetran_connector_sdk.constants import REDACTED_VALUE

        # run_tester should automatically redact the configuration
        self.assertIn(REDACTED_VALUE, cmd_str)
        # Most importantly, verify sensitive values are NOT exposed
        self.assertNotIn("secret123", cmd_str)
        self.assertNotIn("admin", cmd_str)

    def test_redact_configuration_values_simple_dict(self):
        from fivetran_connector_sdk.connector_helper import redact_configuration_values
        from fivetran_connector_sdk.constants import REDACTED_VALUE

        # Configuration values are always strings (enforced by check_dict with string_only=True)
        config = {"username": "admin", "password": "secret123", "api_key": "abc123"}
        redacted = redact_configuration_values(config)

        self.assertEqual(
            redacted,
            {"username": REDACTED_VALUE, "password": REDACTED_VALUE, "api_key": REDACTED_VALUE},
        )
        # Ensure original is not modified
        self.assertEqual(config["password"], "secret123")

    def test_redact_configuration_values_empty_dict(self):
        from fivetran_connector_sdk.connector_helper import redact_configuration_values

        config = {}
        redacted = redact_configuration_values(config)

        self.assertEqual(redacted, {})

    def test_redact_configuration_values_none(self):
        from fivetran_connector_sdk.connector_helper import redact_configuration_values

        config = None
        redacted = redact_configuration_values(config)

        self.assertIsNone(redacted)

    # Tests for .gitignore functionality
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="*.log\n__pycache__/\n")
    def test_load_gitignore_file_exists(self, mock_file, mock_exists):
        from fivetran_connector_sdk.connector_helper import load_gitignore
        import pathspec

        mock_exists.return_value = True

        patterns = load_gitignore("/test/path")

        mock_exists.assert_called_once_with("/test/path/.gitignore")
        mock_file.assert_called_once_with("/test/path/.gitignore", "r", encoding="utf-8")
        # Verify the patterns can be compiled and used
        self.assertEqual(patterns, ["*.log", "__pycache__/"])
        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        self.assertTrue(spec.match_file("test.log"))
        self.assertFalse(spec.match_file("test.py"))

    @patch("os.path.exists", return_value=False)
    def test_load_gitignore_file_not_exists(self, mock_exists):
        from fivetran_connector_sdk.connector_helper import load_gitignore
        import pathspec

        patterns = load_gitignore("/test/path")

        mock_exists.assert_called_once_with("/test/path/.gitignore")
        # Should return empty list
        self.assertEqual(patterns, [])
        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        self.assertFalse(spec.match_file("test.log"))
        self.assertFalse(spec.match_file("test.py"))

    @patch("os.path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="# Comment\n\n__pycache__/\n  \n*.pyc\n# Another comment\nbuild/\n\n",
    )
    def test_load_gitignore_filters_comments_and_empty_lines(self, mock_file, mock_exists):
        """Test that load_gitignore filters out comments and empty lines."""
        from fivetran_connector_sdk.connector_helper import load_gitignore
        import pathspec

        patterns = load_gitignore("/test/path")

        # Should only contain non-comment, non-empty patterns
        self.assertEqual(len(patterns), 3, "Should have exactly 3 patterns after filtering")
        self.assertIn("__pycache__/", patterns)
        self.assertIn("*.pyc", patterns)
        self.assertIn("build/", patterns)

        # Verify comments and empty lines were filtered out
        for pattern in patterns:
            self.assertFalse(pattern.startswith("#"), "No pattern should start with #")
            self.assertTrue(pattern.strip(), "No pattern should be empty or whitespace-only")

        # Verify the patterns work correctly
        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        self.assertTrue(spec.match_file("__pycache__/test.pyc"))
        self.assertTrue(spec.match_file("test.pyc"))
        self.assertTrue(spec.match_file("build/output"))

    def test_get_default_ignore_patterns(self):
        from fivetran_connector_sdk.connector_helper import get_default_ignore_patterns
        import pathspec

        patterns = get_default_ignore_patterns()
        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

        # Test default patterns
        self.assertTrue(spec.match_file("__pycache__/"))
        self.assertTrue(spec.match_file(".git/"))
        self.assertTrue(spec.match_file(".venv/"))
        self.assertTrue(spec.match_file("lib/"))
        self.assertTrue(spec.match_file("files/"))
        # Regular files should not match
        self.assertFalse(spec.match_file("test.py"))
        self.assertFalse(spec.match_file("connector.py"))

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_gitignore_preserves_drivers_behavior(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        from fivetran_connector_sdk.connector_helper import dir_walker

        # .gitignore ignores *.jar files
        mock_load_gitignore.return_value = ["*.jar"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["test.py", "drivers"]
            elif path == "proj/drivers":
                return ["driver1.jar", "driver2.so", "installation.sh"]
            return []

        def isdir_side_effect(path):
            return path == "proj/drivers"

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # In drivers folder, ALL file types are checked (not just .py), but .gitignore still applies
        drivers_result = next((r for r in result if r[0] == "proj/drivers"), None)
        self.assertIsNotNone(drivers_result)
        _, drivers_files = drivers_result
        # driver1.jar should be EXCLUDED by .gitignore (*.jar pattern)
        self.assertNotIn("driver1.jar", drivers_files)
        # Other files not matching .gitignore should be included
        self.assertIn("driver2.so", drivers_files)
        self.assertIn("installation.sh", drivers_files)

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_no_gitignore_backwards_compatible(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        from fivetran_connector_sdk.connector_helper import dir_walker

        # No .gitignore file - return empty list
        mock_load_gitignore.return_value = []

        def listdir_side_effect(path):
            if path == "proj":
                return ["test.py", "test.txt", "requirements.txt", ".git", "__pycache__"]
            return []

        def isdir_side_effect(path):
            return path in ["proj/.git", "proj/__pycache__"]

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should exclude .git and __pycache__ (default exclusions)
        # Should include all file types unless excluded by patterns
        root_result = result[0]
        _, files = root_result
        self.assertIn("test.py", files)
        self.assertIn("requirements.txt", files)
        self.assertIn("test.txt", files)  # All file types are now included
        # .git and __pycache__ should be excluded by defaults
        self.assertEqual(len(result), 1)  # No subdirectories walked

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_includes_gitignore_despite_dot_pattern(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that .gitignore files are included in the output despite the .* default exclusion pattern."""
        from fivetran_connector_sdk.connector_helper import dir_walker

        mock_load_gitignore.return_value = []

        def listdir_side_effect(path):
            if path == "proj":
                return ["connector.py", ".gitignore", ".env", "src"]
            elif path == "proj/src":
                return ["helper.py", ".gitignore"]
            return []

        def isdir_side_effect(path):
            return path in ["proj/src"]

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Root directory
        root_files = result[0][1]
        self.assertIn(
            ".gitignore", root_files, ".gitignore should be included via ALWAYS_INCLUDED_FILES"
        )
        self.assertIn("connector.py", root_files)
        self.assertNotIn(".env", root_files, ".env should be excluded by .* default pattern")

        # Subdirectory
        src_result = next((r for r in result if r[0] == "proj/src"), None)
        self.assertIsNotNone(src_result)
        src_files = src_result[1]
        self.assertIn(
            ".gitignore",
            src_files,
            ".gitignore in subdirectory should also be included via ALWAYS_INCLUDED_FILES",
        )
        self.assertIn("helper.py", src_files)

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_excludes_virtual_environments(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        from fivetran_connector_sdk.connector_helper import dir_walker

        # No .gitignore file - return empty list
        mock_load_gitignore.return_value = []

        def listdir_side_effect(path):
            if path == "proj":
                return ["test.py", "venv", "env", "mydir"]
            elif path == "proj/venv":
                return ["pyvenv.cfg", "lib"]  # Virtual env indicator
            elif path == "proj/env":
                return ["pyvenv.cfg", "Scripts"]  # Virtual env indicator
            elif path == "proj/mydir":
                return ["data.py"]  # Regular directory
            return []

        def isdir_side_effect(path):
            return path in ["proj/venv", "proj/env", "proj/mydir"]

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should have root and mydir only (venv and env excluded)
        self.assertEqual(len(result), 2)

        # Check root has test.py
        root_result = result[0]
        self.assertEqual(root_result[0], "proj")
        _, root_files = root_result
        self.assertIn("test.py", root_files)

        # Check mydir was walked (not excluded)
        mydir_result = next((r for r in result if r[0] == "proj/mydir"), None)
        self.assertIsNotNone(mydir_result)
        _, mydir_files = mydir_result
        self.assertIn("data.py", mydir_files)

        # venv and env should NOT be in results
        venv_result = next((r for r in result if r[0] == "proj/venv"), None)
        self.assertIsNone(venv_result)
        env_result = next((r for r in result if r[0] == "proj/env"), None)
        self.assertIsNone(env_result)

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_directory_negation_patterns(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that .gitignore with 'foo/' and '!foo/bar.py' correctly packages bar.py.

        This tests the core gitignore-style negation behavior: directories matching ignore
        patterns are still descended into when negation patterns exist, allowing specific
        files to be re-included.
        """
        from fivetran_connector_sdk.connector_helper import dir_walker

        # .gitignore contains 'foo/' (ignore directory) and '!foo/bar.py' (re-include specific file)
        mock_load_gitignore.return_value = ["foo/", "!foo/bar.py"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["test.py", "foo"]
            elif path == "proj/foo":
                return ["bar.py", "baz.py", "qux.txt"]
            return []

        def isdir_side_effect(path):
            return path == "proj/foo"

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should have root and foo directory (descended to check for negations)
        self.assertEqual(len(result), 2)

        # Check root has test.py
        root_result = result[0]
        self.assertEqual(root_result[0], "proj")
        _, root_files = root_result
        self.assertIn("test.py", root_files)

        # Check foo was walked and bar.py is included (negation worked!)
        foo_result = next((r for r in result if r[0] == "proj/foo"), None)
        self.assertIsNotNone(
            foo_result, "Directory 'foo/' should be descended into when negation patterns exist"
        )
        _, foo_files = foo_result
        self.assertIn(
            "bar.py", foo_files, "bar.py should be included due to negation pattern '!foo/bar.py'"
        )
        self.assertNotIn("baz.py", foo_files, "baz.py should be excluded by 'foo/' pattern")
        self.assertNotIn("qux.txt", foo_files, "qux.txt should be excluded by 'foo/' pattern")

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_gitignore_negation_does_not_override_venv_exclusion(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that .gitignore negation patterns cannot override virtual environment exclusion.

        Virtual environments should ALWAYS be excluded, even if .gitignore tries to include them.
        This ensures backwards compatibility with the original _should_descend_into_dir() logic.
        """
        from fivetran_connector_sdk.connector_helper import dir_walker

        # .gitignore tries to negate the 'lib/' exclusion with '!lib/'
        # But lib/ with pyvenv.cfg should still be excluded as a virtual environment
        mock_load_gitignore.return_value = ["!lib/"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["test.py", "lib", "mydir"]
            elif path == "proj/lib":
                return ["pyvenv.cfg", "site-packages"]  # Virtual env indicator
            elif path == "proj/mydir":
                return ["data.py"]
            return []

        def isdir_side_effect(path):
            return path in ["proj/lib", "proj/mydir"]

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should have root and mydir only (lib excluded as virtual environment)
        self.assertEqual(len(result), 2)

        # Check root has test.py
        root_result = result[0]
        self.assertEqual(root_result[0], "proj")
        _, root_files = root_result
        self.assertIn("test.py", root_files)

        # Check mydir was walked (not excluded)
        mydir_result = next((r for r in result if r[0] == "proj/mydir"), None)
        self.assertIsNotNone(mydir_result)
        _, mydir_files = mydir_result
        self.assertIn("data.py", mydir_files)

        # lib should NOT be in results even though .gitignore has '!lib/'
        lib_result = next((r for r in result if r[0] == "proj/lib"), None)
        self.assertIsNone(
            lib_result,
            "Virtual environment 'lib/' should be excluded even with .gitignore negation pattern '!lib/'",
        )

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}\\{b}")  # Windows-style join
    @patch(
        "os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}\\", "")
    )  # Windows-style relpath
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_windows_path_separators(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that .gitignore patterns work correctly with Windows-style backslash paths.

        This ensures cross-platform compatibility by verifying that paths with backslashes
        are correctly matched against forward-slash patterns in .gitignore files.
        """
        from fivetran_connector_sdk.connector_helper import dir_walker

        # .gitignore uses forward slashes (POSIX-style) even on Windows
        mock_load_gitignore.return_value = ["build/", "test.txt"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["src", "build", "test.txt", "main.py"]
            elif path == "proj\\src":
                return ["app.py"]
            elif path == "proj\\build":
                return ["output.exe"]
            return []

        def isdir_side_effect(path):
            return path in ["proj\\src", "proj\\build"]

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should have proj and proj\src (build excluded by pattern 'build/')
        self.assertEqual(len(result), 2)

        # Check root has main.py but not test.txt (excluded by pattern 'test.txt')
        root_result = result[0]
        self.assertEqual(root_result[0], "proj")
        _, root_files = root_result
        self.assertIn("main.py", root_files)
        self.assertNotIn(
            "test.txt", root_files, "test.txt should be excluded by .gitignore pattern"
        )

        # Check src was walked (not excluded)
        src_result = next((r for r in result if r[0] == "proj\\src"), None)
        self.assertIsNotNone(src_result, "src/ directory should be walked")
        _, src_files = src_result
        self.assertIn("app.py", src_files)

        # Check build was NOT walked (excluded by pattern 'build/')
        build_result = next((r for r in result if r[0] == "proj\\build"), None)
        self.assertIsNone(
            build_result,
            "build/ should be excluded by .gitignore pattern even with Windows backslash paths",
        )

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.listdir")
    @patch("os.path.isdir")
    def test_dir_walker_hierarchical_gitignore_anchored_patterns(
        self, mock_isdir, mock_listdir, mock_open_file, mock_exists
    ):
        """Test that anchored patterns in nested .gitignore files are interpreted relative to their directory."""
        # Directory structure:
        # proj/
        #   .gitignore (contains: /root_secret.py)
        #   root_secret.py   <- Should be excluded by /root_secret.py
        #   ok_file.py       <- Should be included
        #   src/
        #     .gitignore (contains: /secret.py)
        #     secret.py      <- Should be excluded by /secret.py in src/.gitignore
        #     app.py         <- Should be included
        #     nested/
        #       secret.py    <- Should be included (anchored pattern only matches src/secret.py)
        #       data.py      <- Should be included

        def exists_side_effect(path):
            return path in ["proj/.gitignore", "proj/src/.gitignore"]

        def open_side_effect(path, *args, **kwargs):
            if path == "proj/.gitignore":
                return mock_open(read_data="/root_secret.py\n").return_value
            elif path == "proj/src/.gitignore":
                return mock_open(read_data="/secret.py\n").return_value
            raise FileNotFoundError(f"Unexpected file: {path}")

        def listdir_side_effect(path):
            if path == "proj":
                return ["root_secret.py", "ok_file.py", "src"]
            elif path == "proj/src":
                return ["secret.py", "app.py", "nested"]
            elif path == "proj/src/nested":
                return ["secret.py", "data.py"]
            return []

        def isdir_side_effect(path):
            return path in ["proj/src", "proj/src/nested"]

        mock_exists.side_effect = exists_side_effect
        mock_open_file.side_effect = open_side_effect
        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should walk: proj, proj/src, proj/src/nested
        self.assertEqual(len(result), 3)

        # Check root: should have ok_file.py but NOT root_secret.py
        root_result = result[0]
        self.assertEqual(root_result[0], "proj")
        _, root_files = root_result
        self.assertIn("ok_file.py", root_files)
        self.assertNotIn(
            "root_secret.py",
            root_files,
            "/root_secret.py should exclude root_secret.py at project root",
        )

        # Check src: should have app.py but NOT secret.py
        src_result = next((r for r in result if r[0] == "proj/src"), None)
        self.assertIsNotNone(src_result)
        _, src_files = src_result
        self.assertIn("app.py", src_files)
        self.assertNotIn(
            "secret.py", src_files, "/secret.py in src/.gitignore should exclude src/secret.py"
        )

        # Check nested: SHOULD have secret.py (anchored pattern /secret.py only matches src/secret.py)
        nested_result = next((r for r in result if r[0] == "proj/src/nested"), None)
        self.assertIsNotNone(nested_result)
        _, nested_files = nested_result
        self.assertIn(
            "secret.py",
            nested_files,
            "Anchored pattern /secret.py should not exclude src/nested/secret.py",
        )
        self.assertIn("data.py", nested_files)

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.listdir")
    @patch("os.path.isdir")
    def test_dir_walker_hierarchical_gitignore_unanchored_patterns(
        self, mock_isdir, mock_listdir, mock_open_file, mock_exists
    ):
        """Test that unanchored patterns in nested .gitignore files match recursively under their directory."""
        # Directory structure:
        # proj/
        #   temp.py          <- Should be included (no .gitignore at root)
        #   src/
        #     .gitignore (contains: *.pyc)
        #     debug.pyc      <- Should be excluded by *.pyc
        #     app.py         <- Should be included
        #     sub/
        #       trace.pyc    <- Should be excluded by *.pyc (unanchored = recursive)
        #       data.py      <- Should be included

        def exists_side_effect(path):
            return path == "proj/src/.gitignore"

        def open_side_effect(path, *args, **kwargs):
            if path == "proj/src/.gitignore":
                return mock_open(read_data="*.pyc\n").return_value
            raise FileNotFoundError(f"Unexpected file: {path}")

        def listdir_side_effect(path):
            if path == "proj":
                return ["temp.py", "src"]
            elif path == "proj/src":
                return ["debug.pyc", "app.py", "sub"]
            elif path == "proj/src/sub":
                return ["trace.pyc", "data.py"]
            return []

        def isdir_side_effect(path):
            return path in ["proj/src", "proj/src/sub"]

        mock_exists.side_effect = exists_side_effect
        mock_open_file.side_effect = open_side_effect
        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should walk: proj, proj/src, proj/src/sub
        self.assertEqual(len(result), 3)

        # Check root: should have temp.py (no .gitignore at root)
        root_result = result[0]
        self.assertEqual(root_result[0], "proj")
        _, root_files = root_result
        self.assertIn(
            "temp.py", root_files, "temp.py at root should be included (no pattern matches it)"
        )

        # Check src: should have app.py but NOT debug.pyc
        src_result = next((r for r in result if r[0] == "proj/src"), None)
        self.assertIsNotNone(src_result)
        _, src_files = src_result
        self.assertIn("app.py", src_files)
        self.assertNotIn("debug.pyc", src_files, "*.pyc should exclude debug.pyc in src/")

        # Check sub: should have data.py but NOT trace.pyc (unanchored pattern matches recursively)
        sub_result = next((r for r in result if r[0] == "proj/src/sub"), None)
        self.assertIsNotNone(sub_result)
        _, sub_files = sub_result
        self.assertIn("data.py", sub_files)
        self.assertNotIn(
            "trace.pyc", sub_files, "Unanchored pattern *.pyc should match recursively in src/sub/"
        )

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.listdir")
    @patch("os.path.isdir")
    def test_dir_walker_hierarchical_gitignore_negation_with_anchoring(
        self, mock_isdir, mock_listdir, mock_open_file, mock_exists
    ):
        """Test that negation patterns with anchoring work correctly in hierarchical .gitignore files."""
        # Directory structure:
        # proj/
        #   src/
        #     .gitignore (contains: /*.py\n!/important.py)
        #     debug.py        <- Should be excluded by /*.py
        #     important.py    <- Should be re-included by !/important.py
        #     app.py          <- Should be excluded by /*.py
        #     sub/
        #       trace.py      <- Should be included (anchored pattern /*.py only matches src/*.py)
        #       data.py       <- Should be included

        def exists_side_effect(path):
            return path == "proj/src/.gitignore"

        def open_side_effect(path, *args, **kwargs):
            if path == "proj/src/.gitignore":
                return mock_open(read_data="/*.py\n!/important.py\n").return_value
            raise FileNotFoundError(f"Unexpected file: {path}")

        def listdir_side_effect(path):
            if path == "proj":
                return ["src"]
            elif path == "proj/src":
                return ["debug.py", "important.py", "app.py", "sub"]
            elif path == "proj/src/sub":
                return ["trace.py", "data.py"]
            return []

        def isdir_side_effect(path):
            return path in ["proj/src", "proj/src/sub"]

        mock_exists.side_effect = exists_side_effect
        mock_open_file.side_effect = open_side_effect
        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Should walk: proj, proj/src, proj/src/sub
        self.assertEqual(len(result), 3)

        # Check src: should have important.py (re-included), but NOT debug.py or app.py
        src_result = next((r for r in result if r[0] == "proj/src"), None)
        self.assertIsNotNone(src_result)
        _, src_files = src_result
        self.assertIn("important.py", src_files, "!/important.py should re-include important.py")
        self.assertNotIn("debug.py", src_files, "/*.py should exclude debug.py")
        self.assertNotIn("app.py", src_files, "/*.py should exclude app.py")

        # Check sub: should have trace.py and data.py (anchored pattern /*.py doesn't match subdirectories)
        sub_result = next((r for r in result if r[0] == "proj/src/sub"), None)
        self.assertIsNotNone(src_result)
        _, sub_files = sub_result
        self.assertIn(
            "trace.py",
            sub_files,
            "Anchored pattern /*.py should not exclude trace.py in subdirectory",
        )
        self.assertIn("data.py", sub_files)

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_drivers_folder_with_negation_patterns(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that drivers/ folder respects .gitignore negation patterns.

        drivers/ folder should include ALL file types by default, but .gitignore patterns
        (including negations) should still be respected.
        """
        from fivetran_connector_sdk.connector_helper import dir_walker

        # .gitignore: exclude all .jar files, but re-include important.jar
        mock_load_gitignore.return_value = ["*.jar", "!important.jar"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["connector.py", "drivers"]
            elif path == "proj/drivers":
                return ["driver1.jar", "driver2.jar", "important.jar", "config.xml", "lib.so"]
            return []

        def isdir_side_effect(path):
            return path == "proj/drivers"

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        result = list(dir_walker("proj"))

        # Check root
        root_result = next((r for r in result if r[0] == "proj"), None)
        self.assertIsNotNone(root_result)
        _, root_files = root_result
        self.assertIn("connector.py", root_files)

        # Check drivers/ folder
        drivers_result = next((r for r in result if r[0] == "proj/drivers"), None)
        self.assertIsNotNone(drivers_result, "drivers/ directory should be walked")
        _, drivers_files = drivers_result

        # Verify exclusions and negations work
        self.assertNotIn(
            "driver1.jar", drivers_files, "driver1.jar should be excluded by *.jar pattern"
        )
        self.assertNotIn(
            "driver2.jar", drivers_files, "driver2.jar should be excluded by *.jar pattern"
        )
        self.assertIn(
            "important.jar",
            drivers_files,
            "important.jar should be re-included by !important.jar negation",
        )
        self.assertIn("config.xml", drivers_files, "config.xml should be included (not a .jar)")
        self.assertIn("lib.so", drivers_files, "lib.so should be included (not a .jar)")

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_dir_walker_invalid_pattern_exits_with_error(
        self, mock_log, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that dir_walker exits with error message when .gitignore contains invalid pattern."""
        from fivetran_connector_sdk.connector_helper import dir_walker
        from fivetran_connector_sdk.logger import Logging

        # Return an invalid pattern (trailing escape without character)
        mock_load_gitignore.return_value = ["test\\"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["connector.py"]
            return []

        def isdir_side_effect(path):
            return False

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        # Should exit with SystemExit
        with self.assertRaises(SystemExit) as cm:
            list(dir_walker("proj"))

        # Verify exit code is 1
        self.assertEqual(cm.exception.code, 1)

        # Verify error message was logged
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        error_message = call_args[0][0]
        log_level = call_args.kwargs["level"]

        self.assertIn("failed to parse .gitignore", error_message)
        self.assertEqual(log_level, Logging.Level.SEVERE)

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("os.path.join", side_effect=lambda a, b: f"{a}/{b}")
    @patch("os.path.relpath", side_effect=lambda p, s: p.replace(f"{s}/", ""))
    @patch("fivetran_connector_sdk.connector_helper.load_gitignore")
    def test_dir_walker_valid_patterns_do_not_raise_error(
        self, mock_load_gitignore, mock_relpath, mock_join, mock_isdir, mock_listdir
    ):
        """Test that valid patterns in .gitignore work without errors."""
        from fivetran_connector_sdk.connector_helper import dir_walker

        # Return valid patterns
        mock_load_gitignore.return_value = ["*.log", "!important.log", "__pycache__/", ".git/"]

        def listdir_side_effect(path):
            if path == "proj":
                return ["connector.py", "test.log", "important.log"]
            return []

        def isdir_side_effect(path):
            return False

        mock_listdir.side_effect = listdir_side_effect
        mock_isdir.side_effect = isdir_side_effect

        # Should not raise an exception
        result = list(dir_walker("proj"))

        # Verify we got results
        self.assertEqual(len(result), 1)
        root_path, files = result[0]
        self.assertEqual(root_path, "proj")
        self.assertIn("connector.py", files)

    def test_get_destination_group_from_args(self):
        from fivetran_connector_sdk.connector_helper import get_destination_group

        args = MagicMock()
        args.destination = "existing_group"
        result = get_destination_group(args)
        self.assertEqual(result, "existing_group")

    def test_get_destination_group_from_env_var(self):
        from fivetran_connector_sdk.connector_helper import get_destination_group

        args = MagicMock()
        args.destination = None
        with patch.dict(os.environ, {"FIVETRAN_DESTINATION_NAME": "env_group"}):
            result = get_destination_group(args)
        self.assertEqual(result, "env_group")

    def test_get_destination_group_returns_none_when_missing(self):
        from fivetran_connector_sdk.connector_helper import get_destination_group

        args = MagicMock()
        args.destination = None
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIVETRAN_DESTINATION_NAME", None)
            result = get_destination_group(args)
        self.assertIsNone(result)

    def test_get_connection_name_from_args(self):
        from fivetran_connector_sdk.connector_helper import get_connection_name

        args = MagicMock()
        args.connection = "existing_connection"
        result = get_connection_name(args)
        self.assertEqual(result, "existing_connection")

    def test_get_connection_name_from_env_var(self):
        from fivetran_connector_sdk.connector_helper import get_connection_name

        args = MagicMock()
        args.connection = None
        with patch.dict(os.environ, {"FIVETRAN_CONNECTION_NAME": "env_connection"}):
            result = get_connection_name(args)
        self.assertEqual(result, "env_connection")

    def test_get_connection_name_returns_none_when_missing(self):
        from fivetran_connector_sdk.connector_helper import get_connection_name

        args = MagicMock()
        args.connection = None
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIVETRAN_CONNECTION_NAME", None)
            result = get_connection_name(args)
        self.assertIsNone(result)

    def test_get_api_key_from_args(self):
        from fivetran_connector_sdk.connector_helper import get_api_key

        args = MagicMock()
        args.api_key = "existing_key"
        result = get_api_key(args)
        self.assertEqual(result, "existing_key")

    def test_get_api_key_from_env_var(self):
        from fivetran_connector_sdk.connector_helper import get_api_key

        args = MagicMock()
        args.api_key = None
        with patch.dict(os.environ, {"FIVETRAN_API_KEY": "env_api_key"}):
            result = get_api_key(args)
        self.assertEqual(result, "env_api_key")

    def test_get_api_key_returns_none_when_missing(self):
        from fivetran_connector_sdk.connector_helper import get_api_key

        args = MagicMock()
        args.api_key = None
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIVETRAN_API_KEY", None)
            result = get_api_key(args)
        self.assertIsNone(result)

    def test_get_python_version_default(self):
        """Test get_python_version returns None when not set"""
        from fivetran_connector_sdk.connector_helper import get_python_version

        args = MagicMock()
        args.python_version = None

        result = get_python_version(args, PromptMode.INTERACTIVE)

        # Should return None when no version is set
        self.assertIsNone(result)

    def test_get_python_version_from_args(self):
        """Test get_python_version from args"""
        from fivetran_connector_sdk.connector_helper import get_python_version

        args = MagicMock()
        args.python_version = "3.11"

        result = get_python_version(args, PromptMode.INTERACTIVE)

        self.assertEqual(result, "3.11")

    def test_get_hd_agent_id(self):
        """Test get_hd_agent_id returns value from args"""
        from fivetran_connector_sdk.connector_helper import get_hd_agent_id

        args = MagicMock()
        args.hybrid_deployment_agent_id = "agent_123"

        result = get_hd_agent_id(args, PromptMode.INTERACTIVE)

        self.assertEqual(result, "agent_123")

    def test_get_hd_agent_id_none(self):
        """Test get_hd_agent_id returns None when not set"""
        from fivetran_connector_sdk.connector_helper import get_hd_agent_id

        args = MagicMock()
        args.hybrid_deployment_agent_id = None

        result = get_hd_agent_id(args, PromptMode.INTERACTIVE)

        self.assertIsNone(result)

    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_state")
    def test_get_state(self, mock_load):
        """Test get_state"""
        from fivetran_connector_sdk.connector_helper import get_state

        mock_load.return_value = {"cursor": "2024-01-01"}
        args = MagicMock()
        args.state = "state.json"

        result = get_state(args)

        self.assertEqual(result, {"cursor": "2024-01-01"})

    def test_config_root_dir_helper(self):
        """Test config_root_dir_helper returns path"""
        from fivetran_connector_sdk.connector_helper import config_root_dir_helper

        result = config_root_dir_helper()

        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith(ROOT_LOCATION))

    def test_tester_root_dir_helper(self):
        """Test tester_root_dir_helper returns path"""
        from fivetran_connector_sdk.connector_helper import tester_root_dir_helper

        result = tester_root_dir_helper()

        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith(os.path.join(ROOT_LOCATION, TESTER_LOCATION)))

    def test_is_connection_name_valid_true(self):
        """Test is_connection_name_valid with valid name"""
        from fivetran_connector_sdk.connector_helper import is_connection_name_valid

        self.assertTrue(is_connection_name_valid("valid_name_123"))
        self.assertTrue(is_connection_name_valid("test"))

    def test_is_connection_name_valid_false_spaces(self):
        """Test is_connection_name_valid with spaces"""
        from fivetran_connector_sdk.connector_helper import is_connection_name_valid

        self.assertFalse(is_connection_name_valid("invalid name"))

    def test_is_connection_name_valid_false_special_chars(self):
        """Test is_connection_name_valid with special characters"""
        from fivetran_connector_sdk.connector_helper import is_connection_name_valid

        self.assertFalse(is_connection_name_valid("invalid@name"))
        self.assertFalse(is_connection_name_valid("invalid!"))

    def test_is_connection_name_valid_false_uppercase(self):
        """Test is_connection_name_valid with uppercase"""
        from fivetran_connector_sdk.connector_helper import is_connection_name_valid

        self.assertFalse(is_connection_name_valid("InvalidName"))

    @patch("fivetran_connector_sdk.connector_helper.is_port_in_use")
    def test_get_available_port(self, mock_is_in_use):
        """Test get_available_port finds free port"""
        from fivetran_connector_sdk.connector_helper import get_available_port

        mock_is_in_use.side_effect = [True, True, False]

        result = get_available_port()

        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 50050)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch(
        "fivetran_connector_sdk.connector_helper.config_root_dir_helper", return_value="/test/root"
    )
    @patch("os.path.isfile")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"production_base_url": "http://new.url"}',
    )
    def test_update_base_url_if_required_with_config(
        self, mock_file, mock_isfile, mock_root, mock_log
    ):
        """Test update_base_url_if_required when config file exists with production_base_url"""
        from fivetran_connector_sdk.connector_helper import update_base_url_if_required
        from fivetran_connector_sdk import constants

        mock_isfile.return_value = True
        original_url = constants.PRODUCTION_BASE_URL
        expected_config_path = os.path.join("/test/root", "_config.json")

        try:
            update_base_url_if_required()

            # Verify the URL was updated
            self.assertEqual(constants.PRODUCTION_BASE_URL, "http://new.url")

            # Verify log message was printed
            mock_log.assert_called_with(
                "using custom production url: http://new.url", log_icon=Logging.LogIcon.INFO
            )

            # Verify file was checked and opened at the config root (not the tester root)
            mock_isfile.assert_called_once_with(expected_config_path)
            mock_file.assert_called_once_with(expected_config_path, "r", encoding="utf-8")
        finally:
            # Restore original URL
            constants.PRODUCTION_BASE_URL = original_url

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch(
        "fivetran_connector_sdk.connector_helper.config_root_dir_helper", return_value="/test/root"
    )
    @patch("os.path.isfile", return_value=False)
    def test_update_base_url_if_required_no_config(self, mock_isfile, mock_root, mock_log):
        """Test update_base_url_if_required when config file doesn't exist"""
        from fivetran_connector_sdk.connector_helper import update_base_url_if_required
        from fivetran_connector_sdk import constants

        original_url = constants.PRODUCTION_BASE_URL
        expected_config_path = os.path.join("/test/root", "_config.json")

        try:
            update_base_url_if_required()

            # Verify the URL was not changed
            self.assertEqual(constants.PRODUCTION_BASE_URL, original_url)

            # Verify log was not called
            mock_log.assert_not_called()

            # Verify the config root (not the tester root) was checked
            mock_isfile.assert_called_once_with(expected_config_path)
        finally:
            # Restore original URL
            constants.PRODUCTION_BASE_URL = original_url

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch(
        "fivetran_connector_sdk.connector_helper.config_root_dir_helper", return_value="/test/root"
    )
    @patch("os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data='{"other_key": "value"}')
    def test_update_base_url_if_required_no_base_url_key(
        self, mock_file, mock_isfile, mock_root, mock_log
    ):
        """Test update_base_url_if_required when config file exists but has no production_base_url key"""
        from fivetran_connector_sdk.connector_helper import update_base_url_if_required
        from fivetran_connector_sdk import constants

        original_url = constants.PRODUCTION_BASE_URL
        expected_config_path = os.path.join("/test/root", "_config.json")

        try:
            update_base_url_if_required()

            # Verify the URL was not changed
            self.assertEqual(constants.PRODUCTION_BASE_URL, original_url)

            # Verify log was not called
            mock_log.assert_not_called()

            # Verify the config root (not the tester root) was used
            mock_file.assert_called_once_with(expected_config_path, "r", encoding="utf-8")
        finally:
            # Restore original URL
            constants.PRODUCTION_BASE_URL = original_url

    def test_fetch_requirements_from_file_additional(self):
        """Test fetch_requirements_from_file"""
        from fivetran_connector_sdk.connector_helper import fetch_requirements_from_file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("requests==2.28.0\n")
            f.write("# comment\n")
            f.write("\n")
            f.write("pandas>=1.0.0\n")
            f.flush()
            temp_path = f.name

        try:
            result = fetch_requirements_from_file(temp_path)

            # Function returns all lines including comments and empty lines
            self.assertEqual(len(result), 4)
            self.assertIn("requests==2.28.0", result)
            self.assertIn("# comment", result)
            self.assertIn("", result)
            self.assertIn("pandas>=1.0.0", result)
        finally:
            os.unlink(temp_path)

    def test_fetch_requirements_as_dict_additional(self):
        """Test fetch_requirements_as_dict"""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("requests==2.28.0\n")
            f.write("pandas>=1.0.0\n")
            f.flush()
            temp_path = f.name

        try:
            result = fetch_requirements_as_dict(temp_path)

            self.assertIn("requests", result)
            self.assertEqual(result["requests"], "requests==2.28.0")
            self.assertIn("pandas", result)
            self.assertEqual(result["pandas"], "pandas>=1.0.0")
        finally:
            os.unlink(temp_path)

    @patch("builtins.print")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_log_unused_deps_yes(self, mock_log, mock_print):
        """Test log_unused_deps logs correctly"""
        from fivetran_connector_sdk.connector_helper import log_unused_deps

        unused_deps = ["unused_package"]

        log_unused_deps(unused_deps, is_deploy=True)

        # Should log the warning message with deps included
        mock_log.assert_called_once_with(
            "The following dependencies are not needed, they are already installed or not in use. "
            "Remove them from requirements.txt:\nunused_package",
            Logging.Level.WARNING,
        )

    @patch("builtins.print")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_log_unused_deps_no(self, mock_log, mock_print):
        """Test log_unused_deps in debug mode"""
        from fivetran_connector_sdk.connector_helper import log_unused_deps

        unused_deps = ["unused_package"]

        log_unused_deps(unused_deps, is_deploy=False)

        # Should log with INFO level in debug mode, with deps included
        mock_log.assert_called_once_with(
            "The following dependencies are not needed, they are already installed or not in use. "
            "Remove them from requirements.txt:\nunused_package",
            Logging.Level.INFO,
        )

    @patch("builtins.print")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_handle_missing_deps_yes(self, mock_log, mock_print):
        """Test handle_missing_deps logs correctly"""
        from fivetran_connector_sdk.connector_helper import handle_missing_deps

        missing_deps = {"missing_package": "missing_package==1.0.0"}

        handle_missing_deps(missing_deps, is_deploy=True)

        # Should log the message with deps included
        self.assertTrue(mock_log.called)
        # Should reference the current project-dependencies docs URL
        logged_message = mock_log.call_args[0][0]
        self.assertIn(
            "https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/project-dependencies",
            logged_message,
        )
        self.assertIn("missing_package==1.0.0", logged_message)

    @patch("builtins.print")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_handle_missing_deps_no(self, mock_log, mock_print):
        """Test handle_missing_deps in debug mode"""
        from fivetran_connector_sdk.connector_helper import handle_missing_deps

        missing_deps = {"missing_package": "missing_package==1.0.0"}

        handle_missing_deps(missing_deps, is_deploy=False)

        # Should log with INFO level in debug mode
        self.assertTrue(mock_log.called)
        # Should reference the current project-dependencies docs URL
        logged_message = mock_log.call_args[0][0]
        self.assertIn(
            "https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/project-dependencies",
            logged_message,
        )

    def test_copy_requirements_file_to_tmp(self):
        """Test copy_requirements_file_to_tmp_requirements_file"""
        from fivetran_connector_sdk.connector_helper import (
            copy_requirements_file_to_tmp_requirements_file,
        )
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as src:
            src.write("requests==2.28.0\n")
            src.flush()
            src_path = src.name

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as dst:
            dst_path = dst.name

        try:
            copy_requirements_file_to_tmp_requirements_file(src_path, dst_path)

            with open(dst_path, "r") as f:
                content = f.read()
                self.assertIn("requests==2.28.0", content)
        finally:
            os.unlink(src_path)
            os.unlink(dst_path)

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.upload_package")
    @patch("fivetran_connector_sdk.connector_helper.create_package")
    def test_package_project_exception_during_upload(
        self, mock_create_package, mock_upload_package, mock_delete
    ):
        """Test package_project ensures cleanup when upload_package raises exception"""
        from fivetran_connector_sdk.connector_helper import package_project

        mock_create_package.return_value = "test.zip"
        mock_upload_package.side_effect = RuntimeError("Network error during upload")

        # Should raise the exception but still cleanup
        with self.assertRaises(RuntimeError) as context:
            package_project("proj", "key")

        self.assertIn("Network error", str(context.exception))
        # Verify cleanup happened despite exception
        mock_delete.assert_called_once_with("test.zip")

    @patch("fivetran_connector_sdk.connector_helper.upload_package")
    @patch("fivetran_connector_sdk.connector_helper.create_package")
    def test_package_project_removes_empty_files_dir(
        self, mock_create_package, mock_upload_package
    ):
        """package_project should clean up an empty files/ dir left behind after deploy."""
        from fivetran_connector_sdk.connector_helper import package_project, OUTPUT_FILES_DIR
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            files_dir = os.path.join(tmpdir, OUTPUT_FILES_DIR)
            os.makedirs(files_dir, exist_ok=True)
            zip_path = os.path.join(files_dir, "pkg.zip")
            open(zip_path, "w").close()

            mock_create_package.return_value = zip_path
            mock_upload_package.return_value = "pkg-id-123"

            with patch("fivetran_connector_sdk.connector_helper.print_library_log"):
                result = package_project(tmpdir, "key")

            self.assertEqual(result, "pkg-id-123")
            # zip is gone (delete_file_if_exists ran) and the empty dir is removed too
            self.assertFalse(os.path.exists(zip_path))
            self.assertFalse(os.path.isdir(files_dir))

    @patch("fivetran_connector_sdk.connector_helper.upload_package")
    @patch("fivetran_connector_sdk.connector_helper.create_package")
    def test_package_project_preserves_non_empty_files_dir(
        self, mock_create_package, mock_upload_package
    ):
        """package_project must not delete files/ if the user has content in it."""
        from fivetran_connector_sdk.connector_helper import package_project, OUTPUT_FILES_DIR
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            files_dir = os.path.join(tmpdir, OUTPUT_FILES_DIR)
            os.makedirs(files_dir, exist_ok=True)
            user_file = os.path.join(files_dir, "state.json")
            with open(user_file, "w") as f:
                f.write("{}")
            zip_path = os.path.join(files_dir, "pkg.zip")
            open(zip_path, "w").close()

            mock_create_package.return_value = zip_path
            mock_upload_package.return_value = "pkg-id-123"

            with patch("fivetran_connector_sdk.connector_helper.print_library_log"):
                package_project(tmpdir, "key")

            # zip is gone but the user's file and the dir remain
            self.assertFalse(os.path.exists(zip_path))
            self.assertTrue(os.path.isdir(files_dir))
            self.assertTrue(os.path.exists(user_file))

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_code")
    def test_cleanup_uploaded_project_additional(self, mock_cleanup, mock_exit):
        """Test cleanup_uploaded_project with package ID"""
        from fivetran_connector_sdk.connector_helper import cleanup_uploaded_project

        mock_cleanup.return_value = True

        cleanup_uploaded_project("test_key", "pkg_456")

        mock_cleanup.assert_called_once_with("test_key", "pkg_456")
        mock_exit.assert_not_called()

    @patch("requests.patch")
    def test_update_connection_additional(self, mock_patch):
        """Test update_connection returns response object"""
        from fivetran_connector_sdk.connector_helper import update_connection

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_patch.return_value = mock_response

        # Config with secrets_list (should be removed)
        config = {"schema": "test", "secrets_list": ""}

        resp = update_connection("conn_id", "name", "group", config, "pkg_123", "key", None)

        self.assertEqual(resp, mock_response)
        mock_patch.assert_called_once()

    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_project")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.are_setup_tests_failing", return_value=False)
    def test_handle_connection_response_new_connection_success(
        self, mock_failing, mock_log, mock_cleanup
    ):
        """Test handle_connection_response for successful new connection"""
        from fivetran_connector_sdk.connector_helper import handle_connection_response
        from http import HTTPStatus

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = HTTPStatus.CREATED
        mock_response.json.return_value = {
            "data": {
                "id": "new_conn_id",
                "config": {"python_version": "3.9"},
                "destination_schema_names": FIVETRAN_NAMING,
            }
        }

        handle_connection_response(
            mock_response,
            "pkg_123",
            "deploy_key",
            HTTPStatus.CREATED.value,
            is_new_connection=True,
        )

        mock_log.assert_any_call("connection created", log_icon=Logging.LogIcon.SUCCESS)
        mock_log.assert_any_call("connection id: new_conn_id", indent=True)
        mock_log.assert_any_call(
            f"naming strategy: {FIVETRAN_NAMING}", level=Logging.Level.INFO, indent=True
        )
        mock_log.assert_any_call("visit the Fivetran dashboard to start the initial sync:")
        mock_cleanup.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_project")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.are_setup_tests_failing", return_value=False)
    def test_handle_connection_response_existing_connection_success(
        self, mock_failing, mock_log, mock_cleanup
    ):
        """Test handle_connection_response for successful existing connection update"""
        from fivetran_connector_sdk.connector_helper import handle_connection_response
        from http import HTTPStatus

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = HTTPStatus.OK
        mock_response.json.return_value = {
            "data": {
                "config": {"python_version": "3.10"},
                "destination_schema_names": FIVETRAN_NAMING,
            }
        }

        handle_connection_response(
            mock_response,
            "pkg_456",
            "deploy_key",
            HTTPStatus.OK.value,
            is_new_connection=False,
            connection_id="existing_conn_id",
        )

        mock_log.assert_any_call("connection updated", log_icon=Logging.LogIcon.SUCCESS)
        mock_log.assert_any_call("connection id: existing_conn_id", indent=True)
        mock_log.assert_any_call(
            f"naming strategy: {FIVETRAN_NAMING}", level=Logging.Level.INFO, indent=True
        )
        mock_log.assert_any_call("visit the Fivetran dashboard to manage the connection:")
        mock_cleanup.assert_not_called()

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_project")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_handle_connection_response_create_failure(self, mock_log, mock_cleanup, mock_exit):
        """Test handle_connection_response when connection creation fails"""
        from fivetran_connector_sdk.connector_helper import handle_connection_response
        from http import HTTPStatus

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid config"}

        handle_connection_response(
            mock_response,
            "pkg_789",
            "deploy_key",
            HTTPStatus.CREATED.value,
            is_new_connection=True,
        )

        mock_log.assert_any_call(
            "failed to create connection error: Invalid config",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        mock_cleanup.assert_called_once_with("deploy_key", "pkg_789")
        mock_exit.assert_called_once_with(1)

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.cleanup_uploaded_project")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_handle_connection_response_update_failure(self, mock_log, mock_cleanup, mock_exit):
        """Test handle_connection_response when connection update fails"""
        from fivetran_connector_sdk.connector_helper import handle_connection_response
        from http import HTTPStatus

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Connection not found"}

        handle_connection_response(
            mock_response,
            "pkg_999",
            "deploy_key",
            HTTPStatus.OK.value,
            is_new_connection=False,
            connection_id="conn_id",
        )

        mock_log.assert_any_call(
            "failed to update connection error: Connection not found",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        mock_cleanup.assert_called_once_with("deploy_key", "pkg_999")
        mock_exit.assert_called_once_with(1)

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.handle_failing_tests_message_and_exit")
    @patch("fivetran_connector_sdk.connector_helper.are_setup_tests_failing", return_value=True)
    def test_handle_connection_response_setup_tests_fail(
        self, mock_failing, mock_handle_fail, mock_exit
    ):
        """Test handle_connection_response when setup tests fail (no cleanup)"""
        from fivetran_connector_sdk.connector_helper import handle_connection_response
        from http import HTTPStatus

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = HTTPStatus.CREATED
        mock_response.json.return_value = {"data": {"id": "new_id"}}

        handle_connection_response(
            mock_response,
            "pkg_111",
            "deploy_key",
            HTTPStatus.CREATED.value,
            is_new_connection=True,
        )

        mock_handle_fail.assert_called_once_with(
            mock_response, "connection created but setup tests failed"
        )
        # Note: handle_failing_tests_message_and_exit calls sys.exit, but we don't cleanup package

    @patch("requests.post")
    def test_create_connection_additional(self, mock_post):
        """Test create_connection"""
        from fivetran_connector_sdk.connector_helper import create_connection

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        config = {"schema": "test"}

        create_connection("key", "group_id", config, None, "pkg_123", FIVETRAN_NAMING)

        mock_post.assert_called_once()

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_print_failing_setup_tests(self, mock_log):
        """Test print_failing_setup_tests"""
        from fivetran_connector_sdk.connector_helper import print_failing_setup_tests

        response = MagicMock()
        response.json.return_value = {
            "data": {
                "setup_tests": [
                    {"title": "Test1", "status": "FAILED", "message": "Error1"},
                    {"title": "Test2", "status": "PASSED"},
                ]
            }
        }

        print_failing_setup_tests(response)

        # Should log failing tests
        self.assertTrue(mock_log.called)

    @patch("requests.get")
    def test_get_connection_details_additional(self, mock_get):
        """Test get_connection_details"""
        from fivetran_connector_sdk.connector_helper import get_connection_details

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "data": {
                "items": [{"schema": "test_conn", "id": "conn_123", "service": "connector_sdk"}]
            }
        }
        mock_get.return_value = mock_response

        result = get_connection_details("test_conn", "group", "group_id", "key")

        self.assertEqual(result, ("conn_123", "connector_sdk"))

    @patch("requests.get")
    def test_get_group_info_additional(self, mock_get):
        """Test get_group_info"""
        from fivetran_connector_sdk.connector_helper import get_group_info

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "data": {"items": [{"name": "test_group", "id": "group_123"}]}
        }
        mock_get.return_value = mock_response

        result = get_group_info("test_group", "key")

        self.assertEqual(result, ("group_123", "test_group"))

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_get_os_arch_suffix_mac_arm(self, mock_machine, mock_system):
        """Test get_os_arch_suffix for Mac ARM"""
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        result = get_os_arch_suffix()

        self.assertEqual(result, "mac-arm64")

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="x86_64")
    def test_get_os_arch_suffix_mac_x64(self, mock_machine, mock_system):
        """Test get_os_arch_suffix for Mac x64"""
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        result = get_os_arch_suffix()

        self.assertEqual(result, "mac-x64")

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_get_os_arch_suffix_linux(self, mock_machine, mock_system):
        """Test get_os_arch_suffix for Linux"""
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        result = get_os_arch_suffix()

        self.assertEqual(result, "linux-x64")

    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="AMD64")
    def test_get_os_arch_suffix_windows(self, mock_machine, mock_system):
        """Test get_os_arch_suffix for Windows"""
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        result = get_os_arch_suffix()

        self.assertEqual(result, "windows-x64")

    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="ARM64")
    def test_get_os_arch_suffix_windows_arm64(self, mock_machine, mock_system):
        """Test get_os_arch_suffix for Windows ARM64"""
        from fivetran_connector_sdk.connector_helper import get_os_arch_suffix

        result = get_os_arch_suffix()

        self.assertEqual(result, "windows-arm64")

    @patch("os.path.exists", return_value=True)
    @patch("os.remove")
    def test_delete_file_if_exists_additional(self, mock_remove, mock_exists):
        """Test delete_file_if_exists when file exists"""
        delete_file_if_exists("/test/file.txt")

        mock_remove.assert_called_once_with("/test/file.txt")

    @patch("os.path.exists", return_value=False)
    def test_delete_file_if_exists_no_file(self, mock_exists):
        """Test delete_file_if_exists when file doesn't exist"""
        # Should not raise error
        delete_file_if_exists("/test/nonexistent.txt")

    def test_remove_dir_if_empty_removes_empty_dir(self):
        """remove_dir_if_empty deletes a real empty directory."""
        from fivetran_connector_sdk.connector_helper import remove_dir_if_empty
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "empty")
            os.mkdir(target)
            remove_dir_if_empty(target)
            self.assertFalse(os.path.exists(target))

    def test_remove_dir_if_empty_preserves_non_empty_dir(self):
        """remove_dir_if_empty leaves a directory with content untouched."""
        from fivetran_connector_sdk.connector_helper import remove_dir_if_empty
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "with_content")
            os.mkdir(target)
            inner = os.path.join(target, "x.txt")
            open(inner, "w").close()
            remove_dir_if_empty(target)
            self.assertTrue(os.path.isdir(target))
            self.assertTrue(os.path.exists(inner))

    def test_remove_dir_if_empty_does_nothing_when_dir_missing(self):
        """remove_dir_if_empty does nothing (and does not raise) when dir is missing."""
        from fivetran_connector_sdk.connector_helper import remove_dir_if_empty

        # Should not raise
        remove_dir_if_empty("/path/that/does/not/exist/here")

    @patch("fivetran_connector_sdk.connector_helper.os.rmdir", side_effect=OSError("boom"))
    @patch("fivetran_connector_sdk.connector_helper.os.listdir", return_value=[])
    @patch("fivetran_connector_sdk.connector_helper.os.path.isdir", return_value=True)
    def test_remove_dir_if_empty_swallows_oserror(self, _isdir, _listdir, _rmdir):
        """remove_dir_if_empty must not propagate OSError from rmdir (race / permission)."""
        from fivetran_connector_sdk.connector_helper import remove_dir_if_empty

        # Should not raise even though rmdir blows up
        remove_dir_if_empty("/whatever")

    def test_java_exe_helper_not_windows(self):
        """Test java_exe_helper on non-Windows"""
        from fivetran_connector_sdk.connector_helper import java_exe_helper

        result = java_exe_helper("/path/to/java", "linux_x64")

        # Function appends /bin/java to the location
        self.assertEqual(result, "/path/to/java/bin/java")

    # Tests for get_configuration
    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_configuration")
    def test_get_configuration_uses_cli_flag(self, mock_validate):
        """CLI --configuration flag takes highest precedence"""
        from fivetran_connector_sdk.connector_helper import get_configuration

        args = MagicMock()
        args.configuration = "my_config.json"
        args.project_path = "/test/path"
        mock_validate.return_value = {"key": "value"}

        config, config_path = get_configuration(args)

        self.assertEqual(config, {"key": "value"})
        self.assertEqual(config_path, "my_config.json")
        mock_validate.assert_called_once_with("/test/path", "my_config.json")

    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_configuration")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_get_configuration_uses_env_var(self, mock_log, mock_validate):
        """FIVETRAN_CONFIGURATION env var used when no CLI flag"""
        from fivetran_connector_sdk.connector_helper import get_configuration
        import os

        args = MagicMock()
        args.configuration = None
        args.project_path = "/test/path"
        mock_validate.return_value = {"env_key": "env_value"}

        with patch.dict(os.environ, {"FIVETRAN_CONFIGURATION": "env_config.json"}):
            config, config_path = get_configuration(args)

        self.assertEqual(config, {"env_key": "env_value"})
        self.assertEqual(config_path, "env_config.json")
        info_calls = [c for c in mock_log.call_args_list if "FIVETRAN_CONFIGURATION" in str(c)]
        self.assertGreater(len(info_calls), 0)

    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_configuration")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("os.path.exists", return_value=True)
    def test_get_configuration_uses_configuration_json(self, mock_exists, mock_log, mock_validate):
        """configuration.json in project folder used when no flag or env var"""
        from fivetran_connector_sdk.connector_helper import get_configuration
        import os

        args = MagicMock()
        args.configuration = None
        args.project_path = "/test/path"
        mock_validate.return_value = {"file_key": "file_value"}

        with patch.dict(os.environ, {}, clear=False):
            # Ensure FIVETRAN_CONFIGURATION is not set
            os.environ.pop("FIVETRAN_CONFIGURATION", None)
            config, config_path = get_configuration(args)

        self.assertEqual(config, {"file_key": "file_value"})
        self.assertEqual(config_path, "configuration.json")
        info_calls = [
            c
            for c in mock_log.call_args_list
            if "reading configuration from configuration.json found in project folder" in str(c)
        ]
        self.assertGreater(len(info_calls), 0)

    @patch("os.path.exists", return_value=False)
    def test_get_configuration_returns_none_when_none_provided(self, mock_exists):
        """Returns (None, None) when no flag, env var, or configuration.json found"""
        from fivetran_connector_sdk.connector_helper import get_configuration
        import os

        args = MagicMock()
        args.configuration = None
        args.project_path = "/test/path"

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIVETRAN_CONFIGURATION", None)
            config, config_path = get_configuration(args)

        self.assertIsNone(config)
        self.assertIsNone(config_path)

    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_configuration")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_get_configuration_cli_flag_overrides_env_var(self, mock_log, mock_validate):
        """CLI flag takes precedence over FIVETRAN_CONFIGURATION env var"""
        from fivetran_connector_sdk.connector_helper import get_configuration
        import os

        args = MagicMock()
        args.configuration = "flag_config.json"
        args.project_path = "/test/path"
        mock_validate.return_value = {"key": "value"}

        with patch.dict(os.environ, {"FIVETRAN_CONFIGURATION": "env_config.json"}):
            config, config_path = get_configuration(args)

        self.assertEqual(config_path, "flag_config.json")
        mock_validate.assert_called_once_with("/test/path", "flag_config.json")
        env_calls = [c for c in mock_log.call_args_list if "FIVETRAN_CONFIGURATION" in str(c)]
        self.assertEqual(len(env_calls), 0)

    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_configuration")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("os.path.exists", return_value=True)
    def test_get_configuration_cli_flag_overrides_configuration_json(
        self, mock_exists, mock_log, mock_validate
    ):
        """CLI flag takes precedence over configuration.json in project folder"""
        from fivetran_connector_sdk.connector_helper import get_configuration
        import os

        args = MagicMock()
        args.configuration = "flag_config.json"
        args.project_path = "/test/path"
        mock_validate.return_value = {"key": "value"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIVETRAN_CONFIGURATION", None)
            config, config_path = get_configuration(args)

        self.assertEqual(config_path, "flag_config.json")
        mock_validate.assert_called_once_with("/test/path", "flag_config.json")
        file_calls = [c for c in mock_log.call_args_list if "configuration.json found" in str(c)]
        self.assertEqual(len(file_calls), 0)

    @patch("fivetran_connector_sdk.connector_helper.validate_and_load_configuration")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("os.path.exists", return_value=True)
    def test_get_configuration_env_var_overrides_configuration_json(
        self, mock_exists, mock_log, mock_validate
    ):
        """FIVETRAN_CONFIGURATION env var takes precedence over configuration.json in project folder"""
        from fivetran_connector_sdk.connector_helper import get_configuration
        import os

        args = MagicMock()
        args.configuration = None
        args.project_path = "/test/path"
        mock_validate.return_value = {"key": "value"}

        with patch.dict(os.environ, {"FIVETRAN_CONFIGURATION": "env_config.json"}):
            config, config_path = get_configuration(args)

        self.assertEqual(config_path, "env_config.json")
        mock_validate.assert_called_once_with("/test/path", "env_config.json")
        file_calls = [c for c in mock_log.call_args_list if "configuration.json found" in str(c)]
        self.assertEqual(len(file_calls), 0)

    @patch(
        "fivetran_connector_sdk.connector_helper.validate_and_load_configuration",
        side_effect=ValueError("Configuration path is incorrect"),
    )
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_get_configuration_exits_on_invalid_file_path(self, mock_log, mock_validate):
        """Exits with error when config file path does not exist"""
        from fivetran_connector_sdk.connector_helper import get_configuration

        args = MagicMock()
        args.configuration = "missing_config.json"
        args.project_path = "/test/path"

        with self.assertRaises(SystemExit):
            get_configuration(args)

        error_calls = [
            c for c in mock_log.call_args_list if "invalid configuration error" in str(c)
        ]
        self.assertGreater(len(error_calls), 0)

    @patch(
        "fivetran_connector_sdk.connector_helper.validate_and_load_configuration",
        side_effect=ValueError("Configuration must be provided as a JSON file"),
    )
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_get_configuration_exits_on_invalid_json(self, mock_log, mock_validate):
        """Exits with error when config file contains invalid JSON"""
        from fivetran_connector_sdk.connector_helper import get_configuration

        args = MagicMock()
        args.configuration = "bad_config.json"
        args.project_path = "/test/path"

        with self.assertRaises(SystemExit):
            get_configuration(args)

        error_calls = [
            c for c in mock_log.call_args_list if "invalid configuration error" in str(c)
        ]
        self.assertGreater(len(error_calls), 0)


class TestNamingStrategy(unittest.TestCase):
    """Tests for naming strategy validation and retrieval functions."""

    def test_validate_naming_fivetran_lowercase(self):
        """Test validate_naming with lowercase 'fivetran'."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming("fivetran")
        self.assertEqual(result, "FIVETRAN")

    def test_validate_naming_fivetran_uppercase(self):
        """Test validate_naming with uppercase 'FIVETRAN'."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming("FIVETRAN")
        self.assertEqual(result, "FIVETRAN")

    def test_validate_naming_fivetran_mixedcase(self):
        """Test validate_naming with mixed case 'FiveTran'."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming("FiveTran")
        self.assertEqual(result, "FIVETRAN")

    def test_validate_naming_source_lowercase(self):
        """Test validate_naming with lowercase 'source'."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming("source")
        self.assertEqual(result, "SOURCE")

    def test_validate_naming_source_uppercase(self):
        """Test validate_naming with uppercase 'SOURCE'."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming("SOURCE")
        self.assertEqual(result, "SOURCE")

    def test_validate_naming_none(self):
        """Test validate_naming with None returns None."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming(None)
        self.assertIsNone(result)

    def test_validate_naming_empty_string(self):
        """Test validate_naming with empty string returns None."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        result = validate_naming("")
        self.assertIsNone(result)

    def test_validate_naming_strips_whitespace(self):
        """Test validate_naming strips surrounding whitespace before matching."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        self.assertEqual(validate_naming(" SOURCE "), "SOURCE")
        self.assertEqual(validate_naming(" fivetran "), "FIVETRAN")

    @patch("builtins.print")
    def test_validate_naming_invalid_value_exits(self, mock_print):
        """Test validate_naming with invalid value calls sys.exit."""
        from fivetran_connector_sdk.connector_helper import validate_naming

        with self.assertRaises(SystemExit) as cm:
            validate_naming("INVALID")
        self.assertEqual(cm.exception.code, 1)

    def test_get_naming_from_args_fivetran(self):
        """Test get_naming returns formatted FIVETRAN_NAMING from args."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming="FIVETRAN")
        result = get_naming(args)
        self.assertEqual(result, FIVETRAN_NAMING)

    def test_get_naming_from_args_source(self):
        """Test get_naming returns formatted SOURCE_NAMING from args."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming="SOURCE")
        result = get_naming(args)
        self.assertEqual(result, "SOURCE_NAMING")

    def test_get_naming_from_args_lowercase(self):
        """Test get_naming handles lowercase input from args."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming="source")
        result = get_naming(args)
        self.assertEqual(result, "SOURCE_NAMING")

    @patch.dict(os.environ, {FIVETRAN_NAMING: "SOURCE"})
    def test_get_naming_from_env_source(self):
        """Test get_naming reads from FIVETRAN_NAMING environment variable."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming=None)
        result = get_naming(args)
        self.assertEqual(result, "SOURCE_NAMING")

    @patch.dict(os.environ, {FIVETRAN_NAMING: "FIVETRAN"})
    def test_get_naming_from_env_fivetran(self):
        """Test get_naming reads FIVETRAN from environment."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming=None)
        result = get_naming(args)
        self.assertEqual(result, FIVETRAN_NAMING)

    @patch.dict(os.environ, {FIVETRAN_NAMING: " SOURCE "})
    def test_get_naming_from_env_with_whitespace(self):
        """Test get_naming strips whitespace from FIVETRAN_NAMING environment variable."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming=None)
        result = get_naming(args)
        self.assertEqual(result, "SOURCE_NAMING")

    @patch.dict(os.environ, {}, clear=True)
    def test_get_naming_returns_none_when_not_set(self):
        """Test get_naming returns None when no value provided via CLI or environment."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace(naming=None)
        result = get_naming(args)
        self.assertIsNone(result)

    def test_get_naming_args_without_naming_attribute(self):
        """Test get_naming handles args without naming attribute."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        args = Namespace()  # No naming attribute
        result = get_naming(args)
        self.assertIsNone(result)

    def test_get_naming_args_takes_precedence_over_env(self):
        """Test get_naming prefers args over environment variable."""
        from fivetran_connector_sdk.connector_helper import get_naming
        from argparse import Namespace

        with patch.dict(os.environ, {FIVETRAN_NAMING: "FIVETRAN"}):
            args = Namespace(naming="SOURCE")
            result = get_naming(args)
            self.assertEqual(result, "SOURCE_NAMING")


class TestGenerateConfigurationFormBytes(unittest.TestCase):

    def test_returns_empty_file_sentinel_when_no_configuration_form_method(self):
        from fivetran_connector_sdk.connector_helper import (
            _generate_configuration_form_bytes,
            CONFIGURATION_FORM_FILENAME,
        )

        self.assertEqual(
            _generate_configuration_form_bytes(None), {CONFIGURATION_FORM_FILENAME: b""}
        )

    def test_returns_serialized_proto_bytes_when_form_defined(self):
        from fivetran_connector_sdk.connector_helper import (
            _generate_configuration_form_bytes,
            CONFIGURATION_FORM_FILENAME,
        )
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        form = ConfigurationForm()

        result = _generate_configuration_form_bytes(lambda: form)

        self.assertIn(CONFIGURATION_FORM_FILENAME, result)
        self.assertIsInstance(result[CONFIGURATION_FORM_FILENAME], bytes)
        self.assertGreater(len(result), 0)

    def test_initializes_log_level_before_packaging_logged_form(self):
        from fivetran_connector_sdk.connector_helper import (
            _generate_configuration_form_bytes,
            CONFIGURATION_FORM_FILENAME,
        )
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.logger import Logging

        original_level = Logging.LOG_LEVEL
        Logging.LOG_LEVEL = None
        try:

            def logged_form():
                Logging.info("building configuration form for packaging")
                return ConfigurationForm()

            result = _generate_configuration_form_bytes(logged_form)

            self.assertIn(CONFIGURATION_FORM_FILENAME, result)
            self.assertEqual(Logging.LOG_LEVEL, Logging.Level.INFO)
        finally:
            Logging.LOG_LEVEL = original_level

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_exits_with_severe_log_on_exception(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import _generate_configuration_form_bytes
        from fivetran_connector_sdk.logger import Logging

        def failing_form():
            raise Exception("import error")

        _generate_configuration_form_bytes(failing_form)

        mock_log.assert_called_once_with(
            "failed to package configuration form response: import error", Logging.Level.SEVERE
        )
        mock_exit.assert_called_once_with(1)


@unittest.skipIf(sys.version_info < (3, 11), "tomllib not available (Python < 3.11)")
class TestPyprojectTomlValidation(unittest.TestCase):
    """Tests for pyproject.toml validation using tomllib + pipreqs."""

    SKIP_MSG = "tomllib not available (Python < 3.11)"

    def test_parse_pyproject_dependencies(self):
        """Parse [project.dependencies] with various version specifiers."""
        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        from fivetran_connector_sdk.connector_helper import parse_pyproject_dependencies
        import tempfile

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
            f.write(
                b"[project]\ndependencies = [\n"
                b'  "pytz==2023.3",\n'
                b'  "pandas>=2.0",\n'
                b'  "numpy>1.20,<2.0",\n'
                b'  "charset-normalizer>=3.0",\n'
                b"]\n"
            )
            tmp = f.name
        try:
            result = parse_pyproject_dependencies(tmp)
            self.assertEqual(result["pytz"], "pytz==2023.3")
            self.assertEqual(result["pandas"], "pandas>=2.0")
            self.assertEqual(result["numpy"], "numpy>1.20,<2.0")
            self.assertEqual(result["charset_normalizer"], "charset-normalizer>=3.0")
        finally:
            os.unlink(tmp)

    def test_parse_pyproject_dependencies_empty(self):
        """No [project] section → empty dict."""
        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        from fivetran_connector_sdk.connector_helper import parse_pyproject_dependencies
        import tempfile

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
            f.write(b'[build-system]\nrequires = ["setuptools"]\n')
            tmp = f.name
        try:
            result = parse_pyproject_dependencies(tmp)
            self.assertEqual(result, {})
        finally:
            os.unlink(tmp)

    def test_parse_pyproject_dependencies_normalizes_names(self):
        """Hyphens in package names converted to underscores in keys."""
        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        from fivetran_connector_sdk.connector_helper import parse_pyproject_dependencies
        import tempfile

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
            f.write(b'[project]\ndependencies = ["my-cool-package>=1.0"]\n')
            tmp = f.name
        try:
            result = parse_pyproject_dependencies(tmp)
            self.assertIn("my_cool_package", result)
            self.assertEqual(result["my_cool_package"], "my-cool-package>=1.0")
        finally:
            os.unlink(tmp)

    def test_parse_pyproject_dependencies_pep508_edge_cases(self):
        """Marker-only, URL refs, spaces around operators all produce correct keys."""
        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        from fivetran_connector_sdk.connector_helper import parse_pyproject_dependencies
        import tempfile

        toml_content = (
            b"[project]\ndependencies = [\n"
            b'  "importlib-metadata; python_version < \\"3.10\\"",\n'
            b'  "pkg @ https://example.com/pkg.tar.gz",\n'
            b'  "requests >= 2.28.0",\n'
            b'  "six",\n'
            b"]\n"
        )
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            tmp = f.name
        try:
            result = parse_pyproject_dependencies(tmp)
            # marker-only dep: key must be the package name only, not "importlib-metadata; python_version ..."
            self.assertIn("importlib_metadata", result)
            self.assertNotIn("importlib_metadata; python_version", str(result.keys()))
            # URL reference: key must be the package name only
            self.assertIn("pkg", result)
            # space before operator
            self.assertIn("requests", result)
            # no version specifier at all
            self.assertIn("six", result)
        finally:
            os.unlink(tmp)

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_parse_pyproject_dependencies_malformed_exits(self, mock_log):
        """Malformed pyproject.toml → SEVERE log + sys.exit(1)."""
        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        from fivetran_connector_sdk.connector_helper import parse_pyproject_dependencies
        import tempfile

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
            f.write(b"this is not valid toml ][[[")
            tmp = f.name
        try:
            with self.assertRaises(SystemExit) as cm:
                parse_pyproject_dependencies(tmp)
            self.assertEqual(cm.exception.code, 1)
            log_calls = [str(c) for c in mock_log.call_args_list]
            self.assertTrue(any("failed to parse" in c and "SEVERE" in c for c in log_calls))
        finally:
            os.unlink(tmp)

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch(
        "fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries",
        side_effect=RuntimeError("pipreqs failed"),
    )
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_tmp_file_deleted_on_exception(
        self, mock_open_file, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """Temp file is deleted even when pipreqs raises an exception (try/finally)."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        with self.assertRaises(RuntimeError):
            validate_pyproject_file("/dummy", is_deploy=False)
        mock_delete.assert_called()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_no_violations(
        self, mock_open_file, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """Clean project → no prompts, completes successfully."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3"}
        with patch("builtins.input") as mock_input:
            validate_pyproject_file("/dummy", is_deploy=True)
            mock_input.assert_not_called()
        mock_pipreqs.assert_called()
        mock_delete.assert_called()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_debug_reports_missing(
        self, mock_open_file, mock_log, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """Debug: pipreqs finds import not in toml → reported as missing at INFO, no prompt."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3", "colorama": "colorama==0.4.6"}
        with patch("builtins.input") as mock_input:
            validate_pyproject_file("/dummy", is_deploy=False)
            mock_input.assert_not_called()
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any("Include the following" in str(c) and "INFO" in str(c) for c in log_calls)
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_debug_reports_unused(
        self, mock_open_file, mock_log, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """Debug: dep in toml not imported → reported as unused at INFO, no prompt."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3", "six": "six==1.16.0"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3"}
        with patch("builtins.input") as mock_input:
            validate_pyproject_file("/dummy", is_deploy=False)
            mock_input.assert_not_called()
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any(
                "Remove them from pyproject.toml" in str(c) and "INFO" in str(c) for c in log_calls
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_debug_reports_version_mismatch(
        self, mock_open_file, mock_log, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """Debug: declared version != pipreqs version → reported at INFO, no prompt."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2026.1"}
        with patch("builtins.input") as mock_input:
            validate_pyproject_file("/dummy", is_deploy=False)
            mock_input.assert_not_called()
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any(
                "recommend" in str(c) and "stable version" in str(c) and "INFO" in str(c)
                for c in log_calls
            )
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="")
    def test_validate_pyproject_deploy_default_continues_on_missing(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + missing deps + Enter (default Y) → prompt fires once, validation continues."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3", "colorama": "colorama==0.4.6"}
        validate_pyproject_file("/dummy", is_deploy=True)
        mock_input.assert_called_once()
        self.assertIn("(Y/n)", mock_input.call_args[0][0])
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any("Include the following" in str(c) and "SEVERE" in str(c) for c in log_calls)
        )
        self.assertTrue(
            any("Validation of" in str(c) and "completed" in str(c) for c in log_calls)
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="")
    def test_validate_pyproject_deploy_logs_unused_without_prompt(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + unused deps → log warning, no prompt, validation continues."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3", "six": "six==1.16.0"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3"}
        validate_pyproject_file("/dummy", is_deploy=True)
        mock_input.assert_not_called()
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any(
                "Remove them from pyproject.toml" in str(c) and "WARNING" in str(c)
                for c in log_calls
            )
        )
        self.assertTrue(
            any("Validation of" in str(c) and "completed" in str(c) for c in log_calls)
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="")
    def test_validate_pyproject_deploy_default_continues_on_version_mismatch(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + version mismatch + Enter (default Y) → prompt fires, validation continues."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2026.1"}
        validate_pyproject_file("/dummy", is_deploy=True)
        mock_input.assert_called_once()
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any(
                "recommend" in str(c) and "stable version" in str(c) and "WARNING" in str(c)
                for c in log_calls
            )
        )
        self.assertTrue(
            any("Validation of" in str(c) and "completed" in str(c) for c in log_calls)
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="n")
    def test_validate_pyproject_deploy_aborts_on_n_missing(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + missing deps + 'n' → sys.exit(1)."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3", "colorama": "colorama==0.4.6"}
        with self.assertRaises(SystemExit) as cm:
            validate_pyproject_file("/dummy", is_deploy=True)
        self.assertEqual(cm.exception.code, 1)
        mock_input.assert_called_once()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="n")
    def test_validate_pyproject_deploy_does_not_prompt_or_abort_on_unused(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + unused deps → no prompt or abort, even if input would be 'n'."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3", "six": "six==1.16.0"}
        mock_fetch.return_value = {"pytz": "pytz==2023.3"}
        validate_pyproject_file("/dummy", is_deploy=True)
        mock_input.assert_not_called()
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any("Validation of" in str(c) and "completed" in str(c) for c in log_calls)
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="n")
    def test_validate_pyproject_deploy_aborts_on_n_version_mismatch(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + version mismatch + 'n' → sys.exit(1)."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3"}
        mock_fetch.return_value = {"pytz": "pytz==2026.1"}
        with self.assertRaises(SystemExit) as cm:
            validate_pyproject_file("/dummy", is_deploy=True)
        self.assertEqual(cm.exception.code, 1)
        mock_input.assert_called_once()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="")
    def test_validate_pyproject_deploy_two_prompts_when_all_issues(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + version mismatch + missing + unused → prompts only for version mismatch and missing."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3", "six": "six==1.16.0"}
        mock_fetch.return_value = {"pytz": "pytz==2026.1", "colorama": "colorama==0.4.6"}
        validate_pyproject_file("/dummy", is_deploy=True)
        self.assertEqual(mock_input.call_count, 2)
        self.assertFalse(any("not used" in str(call) for call in mock_input.call_args_list))
        log_calls = mock_log.call_args_list
        self.assertTrue(
            any("Validation of" in str(c) and "completed" in str(c) for c in log_calls)
        )

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    @patch("builtins.input", return_value="n")
    def test_validate_pyproject_deploy_aborts_on_first_decline(
        self,
        mock_input,
        mock_open_file,
        mock_log,
        mock_parse,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Deploy + multiple issues + first prompt 'n' → aborts before subsequent prompts."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3", "six": "six==1.16.0"}
        mock_fetch.return_value = {"pytz": "pytz==2026.1", "colorama": "colorama==0.4.6"}
        with self.assertRaises(SystemExit) as cm:
            validate_pyproject_file("/dummy", is_deploy=True)
        self.assertEqual(cm.exception.code, 1)
        # First prompt is version mismatch → 'n' aborts before later validations
        self.assertEqual(mock_input.call_count, 1)

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_debug_no_prompt(
        self, mock_open_file, mock_log, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """Debug mode → warnings only, no prompts even with all three issue types."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {"pytz": "pytz==2023.3", "six": "six==1.16.0"}
        mock_fetch.return_value = {"pytz": "pytz==2026.1", "colorama": "colorama==0.4.6"}
        with patch("builtins.input") as mock_input:
            validate_pyproject_file("/dummy", is_deploy=False)
            mock_input.assert_not_called()

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch("fivetran_connector_sdk.connector_helper.parse_pyproject_dependencies")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.open", new_callable=mock_open)
    def test_validate_pyproject_filters_platform_packages(
        self, mock_open_file, mock_log, mock_parse, mock_pipreqs, mock_fetch, mock_delete
    ):
        """fivetran_connector_sdk and requests not reported as unused."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file

        if sys.version_info < (3, 11):
            self.skipTest(self.SKIP_MSG)
        mock_parse.return_value = {
            "pytz": "pytz==2023.3",
            "fivetran_connector_sdk": "fivetran-connector-sdk>=1.0",
            "requests": "requests>=2.28",
        }
        mock_fetch.return_value = {"pytz": "pytz==2023.3"}
        with patch("builtins.input") as mock_input:
            validate_pyproject_file("/dummy", is_deploy=True)
            mock_input.assert_not_called()
        log_calls = mock_log.call_args_list
        self.assertFalse(any("Remove them from" in str(c) for c in log_calls))

    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_validate_pyproject_skips_on_old_python(self, mock_log):
        """Python < 3.11 → validation skipped with log message."""
        from fivetran_connector_sdk.connector_helper import validate_pyproject_file
        from fivetran_connector_sdk.constants import PYPROJECT_SKIP_VALIDATION_MESSAGE

        with patch("fivetran_connector_sdk.connector_helper.sys") as mock_sys:
            mock_sys.version_info = (3, 10, 0)
            validate_pyproject_file("/dummy", is_deploy=False)
        log_messages = [str(call) for call in mock_log.call_args_list]
        self.assertTrue(any(PYPROJECT_SKIP_VALIDATION_MESSAGE in msg for msg in log_messages))


class TestValidationWithPromptMode(unittest.TestCase):
    """Tests for validation functions with prompt_mode parameter."""

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch(
        "fivetran_connector_sdk.connector_helper.load_or_add_requirements_file",
        return_value={"package": "package==1.0.0"},
    )
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.connector_helper.resolve_confirmation", return_value=True)
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_validate_requirements_with_yes_mode_auto_answers(
        self,
        mock_open_file,
        mock_resolve,
        mock_exists,
        mock_load,
        mock_copy,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Test validation with PromptMode.YES auto-answers prompts"""
        mock_fetch.return_value = {"newpkg": "newpkg==2.0.0"}

        validate_requirements_file("/project", True, "1.0.0", PromptMode.YES)

        # resolve_confirmation should be called with YES mode
        self.assertTrue(mock_resolve.called)
        call_args = mock_resolve.call_args
        self.assertEqual(call_args[1]["prompt_mode"], PromptMode.YES)

    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("fivetran_connector_sdk.connector_helper.fetch_requirements_as_dict")
    @patch("fivetran_connector_sdk.connector_helper.run_pipreqs_with_retries")
    @patch(
        "fivetran_connector_sdk.connector_helper.copy_requirements_file_to_tmp_requirements_file"
    )
    @patch(
        "fivetran_connector_sdk.connector_helper.load_or_add_requirements_file",
        return_value={"package": "package==1.0.0"},
    )
    @patch("fivetran_connector_sdk.connector_helper.os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.connector_helper.resolve_confirmation", return_value=False)
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_validate_requirements_with_default_mode_uses_default(
        self,
        mock_open_file,
        mock_resolve,
        mock_exists,
        mock_load,
        mock_copy,
        mock_pipreqs,
        mock_fetch,
        mock_delete,
    ):
        """Test validation with PromptMode.DEFAULT_ANSWER uses default answers"""
        mock_fetch.return_value = {"newpkg": "newpkg==2.0.0"}

        validate_requirements_file("/project", True, "1.0.0", PromptMode.DEFAULT_ANSWER)

        # resolve_confirmation should be called with DEFAULT_ANSWER mode
        self.assertTrue(mock_resolve.called)
        call_args = mock_resolve.call_args
        self.assertEqual(call_args[1]["prompt_mode"], PromptMode.DEFAULT_ANSWER)


class TestGetProxyHelpers(unittest.TestCase):

    def _make_args(self, **kwargs):
        args = MagicMock()
        for key, value in kwargs.items():
            setattr(args, key, value)
        return args

    def test_get_proxy_id_from_args(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_id

        args = self._make_args(proxy_id="my-proxy-123")
        self.assertEqual(get_proxy_id(args), "my-proxy-123")

    def test_get_proxy_id_none(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_id

        args = self._make_args(proxy_id=None)
        self.assertIsNone(get_proxy_id(args))

    def test_get_proxy_id_missing_attr(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_id

        args = MagicMock(spec=[])  # no attributes
        self.assertIsNone(get_proxy_id(args))

    def test_get_proxy_host_config_key_from_args(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_host_config_key

        args = self._make_args(proxy_host_config_key="host")
        self.assertEqual(get_proxy_host_config_key(args), "host")

    def test_get_proxy_host_config_key_none(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_host_config_key

        args = self._make_args(proxy_host_config_key=None)
        self.assertIsNone(get_proxy_host_config_key(args))

    def test_get_proxy_host_config_key_missing_attr(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_host_config_key

        args = MagicMock(spec=[])
        self.assertIsNone(get_proxy_host_config_key(args))

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_get_proxy_id_empty_string_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import get_proxy_id

        args = self._make_args(proxy_id="")
        get_proxy_id(args)
        mock_exit.assert_called_once_with(1)
        self.assertIn("--proxy-id was provided with an empty value", str(mock_log.call_args))

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_get_proxy_id_whitespace_only_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import get_proxy_id

        args = self._make_args(proxy_id="   ")
        get_proxy_id(args)
        mock_exit.assert_called_once_with(1)

    def test_get_proxy_id_strips_whitespace(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_id

        args = self._make_args(proxy_id="  my-proxy-123  ")
        self.assertEqual(get_proxy_id(args), "my-proxy-123")

    def test_get_proxy_host_config_key_empty_string_returns_none(self):
        from fivetran_connector_sdk.connector_helper import get_proxy_host_config_key

        args = self._make_args(proxy_host_config_key="")
        self.assertIsNone(get_proxy_host_config_key(args))


class TestValidateProxyConfiguration(unittest.TestCase):

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_proxy_host_config_key_without_proxy_id_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        validate_proxy_configuration({}, proxy_id=None, proxy_host_config_key="host")
        mock_exit.assert_called_once_with(1)
        self.assertIn("--proxy-host-config-key", str(mock_log.call_args))

    def test_no_proxy_id_returns_none(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        result = validate_proxy_configuration(
            {"host": "db:5432"}, proxy_id=None, proxy_host_config_key=None
        )
        self.assertIsNone(result)

    def test_proxy_id_with_explicit_key(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"db_host": "mydb.example.com:5432"}
        result = validate_proxy_configuration(
            config, proxy_id="p-123", proxy_host_config_key="db_host"
        )
        self.assertEqual(result, "db_host")

    def test_proxy_id_with_explicit_key_strips_whitespace(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"db_host": "mydb.example.com:5432"}
        result = validate_proxy_configuration(
            config, proxy_id="p-123", proxy_host_config_key="  db_host  "
        )
        self.assertEqual(result, "db_host")

    def test_proxy_id_with_host_key_fallback(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"host": "mydb.example.com:5432"}
        result = validate_proxy_configuration(config, proxy_id="p-123", proxy_host_config_key=None)
        self.assertEqual(result, "host")

    def test_proxy_id_with_hosts_key_fallback(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"hosts": ["h1:5432", "h2:5433"]}
        result = validate_proxy_configuration(config, proxy_id="p-123", proxy_host_config_key=None)
        self.assertEqual(result, "hosts")

    def test_proxy_id_host_takes_priority_over_hosts(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"host": "primary:5432", "hosts": ["h1:5432", "h2:5433"]}
        result = validate_proxy_configuration(config, proxy_id="p-123", proxy_host_config_key=None)
        self.assertEqual(result, "host")

    def test_explicit_key_takes_priority_over_default_host(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"host": "default.host:5432", "custom_key": "custom.host:5433"}
        result = validate_proxy_configuration(
            config, proxy_id="p-123", proxy_host_config_key="custom_key"
        )
        self.assertEqual(result, "custom_key")

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_proxy_id_with_explicit_key_not_in_config_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        validate_proxy_configuration({}, proxy_id="p-123", proxy_host_config_key="missing_key")
        mock_exit.assert_called_once_with(1)
        self.assertIn("does not exist", str(mock_log.call_args))

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_proxy_id_no_host_or_hosts_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        validate_proxy_configuration(
            {"other_key": "value:1234"}, proxy_id="p-123", proxy_host_config_key=None
        )
        mock_exit.assert_called_once_with(1)
        self.assertIn("Unable to determine", str(mock_log.call_args))

    def test_null_value_for_host_key_returns_host(self):
        """Value emptiness is not validated; presence of key is sufficient."""
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        result = validate_proxy_configuration(
            {"host": None}, proxy_id="p-123", proxy_host_config_key=None
        )
        self.assertEqual(result, "host")

    def test_empty_list_for_hosts_key_returns_hosts(self):
        """Value emptiness is not validated; presence of key is sufficient."""
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        result = validate_proxy_configuration(
            {"hosts": []}, proxy_id="p-123", proxy_host_config_key=None
        )
        self.assertEqual(result, "hosts")

    def test_explicit_key_with_empty_value_returns_key(self):
        """Explicit --proxy-host-config-key does not validate value emptiness."""
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        result = validate_proxy_configuration(
            {"db_host": ""}, proxy_id="p-123", proxy_host_config_key="db_host"
        )
        self.assertEqual(result, "db_host")

    def test_key_matching_is_case_sensitive(self):
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        config = {"HOST": "db.example.com:5432"}
        with (
            patch("fivetran_connector_sdk.connector_helper.sys.exit") as mock_exit,
            patch("fivetran_connector_sdk.connector_helper.print_library_log"),
        ):
            validate_proxy_configuration(config, proxy_id="p-123", proxy_host_config_key=None)
            mock_exit.assert_called_once_with(1)

    def test_auto_detect_host_wins_over_hosts_when_both_present(self):
        """First key present ('host' iterated before 'hosts') is returned."""
        from fivetran_connector_sdk.connector_helper import validate_proxy_configuration

        result = validate_proxy_configuration(
            {"host": "h1:5432", "hosts": ["h2:5433"]}, proxy_id="p-123", proxy_host_config_key=None
        )
        self.assertEqual(result, "host")


class TestCheckDictExemptKeys(unittest.TestCase):
    """Tests for check_dict() exempt_keys behavior used by proxy support."""

    def test_exempt_key_with_list_value_passes(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        result = check_dict({"host": ["h1:5432", "h2:5433"], "user": "admin"}, True, {"host"})
        self.assertEqual(result, {"host": ["h1:5432", "h2:5433"], "user": "admin"})

    def test_exempt_key_with_string_value_passes(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        result = check_dict({"host": "db.example.com:5432"}, True, {"host"})
        self.assertEqual(result, {"host": "db.example.com:5432"})

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_exempt_key_with_int_value_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import check_dict

        check_dict({"host": 123}, True, {"host"})
        mock_exit.assert_called_once_with(1)
        self.assertIn("must be a string or a list of strings", str(mock_log.call_args))

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_exempt_key_with_dict_value_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import check_dict

        check_dict({"host": {"nested": "value"}}, True, {"host"})
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_exempt_key_with_bool_value_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import check_dict

        check_dict({"host": True}, True, {"host"})
        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_list_value_without_exempt_keys_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import check_dict

        check_dict({"host": ["h1", "h2"]}, True)
        mock_exit.assert_called_once_with(1)
        self.assertIn("all values must be strings", str(mock_log.call_args))

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    def test_non_exempt_key_with_non_string_still_exits(self, mock_log, mock_exit):
        from fivetran_connector_sdk.connector_helper import check_dict

        check_dict({"host": ["h1:5432"], "port": 5432}, True, {"host"})
        mock_exit.assert_called_once_with(1)
        self.assertIn("all values must be strings", str(mock_log.call_args))

    def test_string_only_false_allows_any_type(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        result = check_dict({"port": 5432, "flag": True, "hosts": ["h1", "h2"]}, False)
        self.assertEqual(result["port"], 5432)

    def test_exempt_keys_none_treated_as_empty_set(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        result = check_dict({"user": "admin"}, True, None)
        self.assertEqual(result, {"user": "admin"})

    def test_empty_dict_returns_empty(self):
        from fivetran_connector_sdk.connector_helper import check_dict

        self.assertEqual(check_dict({}, True, {"host"}), {})


class TestUpdateConnectionWithProxy(unittest.TestCase):

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.patch")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_update_connection_with_proxy_id(self, mock_constants, mock_patch, mock_log, mock_ua):
        from fivetran_connector_sdk.connector_helper import update_connection

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_patch.return_value = MagicMock()

        config = {"schema": "s", "secrets_list": []}
        update_connection(
            "cid", "cname", "gname", config, "pkg", "dkey", None, proxy_agent_id="proxy-123"
        )

        _, kwargs = mock_patch.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["proxy_agent_id"], "proxy-123")
        self.assertEqual(payload["networking_method"], "ProxyAgent")

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.patch")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_update_connection_clears_proxy_when_none(
        self, mock_constants, mock_patch, mock_log, mock_ua
    ):
        from fivetran_connector_sdk.connector_helper import update_connection

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_patch.return_value = MagicMock()

        config = {"schema": "s", "secrets_list": []}
        update_connection(
            "cid", "cname", "gname", config, "pkg", "dkey", None, proxy_agent_id=None
        )

        _, kwargs = mock_patch.call_args
        payload = kwargs["json"]
        self.assertIn("proxy_agent_id", payload)
        self.assertIsNone(payload["proxy_agent_id"])
        self.assertIn("networking_method", payload)
        self.assertEqual(payload["networking_method"], "Directly")

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.patch")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_update_connection_switches_from_proxy_to_directly(
        self, mock_constants, mock_patch, mock_log, mock_ua
    ):
        """When proxy_agent_id is None, networking_method must be 'Directly' (not null).
        The API treats null as 'unchanged', so 'Directly' is required to switch a
        connection back from ProxyAgent to direct networking.
        """
        from fivetran_connector_sdk.connector_helper import update_connection

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_patch.return_value = MagicMock()

        config = {"schema": "s", "secrets_list": []}
        update_connection(
            "cid", "cname", "gname", config, "pkg", "dkey", None, proxy_agent_id=None
        )

        _, kwargs = mock_patch.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["networking_method"], "Directly")
        self.assertIsNone(payload["proxy_agent_id"])
        self.assertNotEqual(payload["networking_method"], None)

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.patch")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_update_connection_clears_proxy_host_config_key_when_switching_to_directly(
        self, mock_constants, mock_patch, mock_log, mock_ua
    ):
        """When switching from proxy to direct, proxy_host_config_key in config must
        be set to null so the server clears any previously stored value.
        """
        from fivetran_connector_sdk.connector_helper import update_connection

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_patch.return_value = MagicMock()

        config = {"schema": "s", "secrets_list": []}
        update_connection(
            "cid", "cname", "gname", config, "pkg", "dkey", None, proxy_agent_id=None
        )

        _, kwargs = mock_patch.call_args
        payload = kwargs["json"]
        self.assertIn("proxy_host_config_key", payload["config"])
        self.assertIsNone(payload["config"]["proxy_host_config_key"])

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.patch")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_update_connection_preserves_proxy_host_config_key_when_proxy_active(
        self, mock_constants, mock_patch, mock_log, mock_ua
    ):
        """When proxy remains active, proxy_host_config_key already set in config must be preserved."""
        from fivetran_connector_sdk.connector_helper import update_connection

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_patch.return_value = MagicMock()

        config = {
            "schema": "s",
            "secrets_list": [{"key": "host", "value": "h1:5432"}],
            "proxy_host_config_key": "host",
        }
        update_connection(
            "cid", "cname", "gname", config, "pkg", "dkey", None, proxy_agent_id="proxy-123"
        )

        _, kwargs = mock_patch.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["config"]["proxy_host_config_key"], "host")


class TestCreateConnectionWithProxy(unittest.TestCase):

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.post")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_create_connection_with_proxy_id(self, mock_constants, mock_post, mock_log, mock_ua):
        from fivetran_connector_sdk.connector_helper import (
            create_connection,
            FIVETRAN_NAMING_VALUE,
            UNDERSCORE_NAMING,
        )

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_post.return_value = MagicMock()

        config = {"schema": "s"}
        create_connection("dkey", "gid", config, None, "pkg", None, proxy_agent_id="proxy-456")

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["proxy_agent_id"], "proxy-456")
        self.assertEqual(payload["networking_method"], "ProxyAgent")

    @patch("fivetran_connector_sdk.connector_helper.get_user_agent", return_value="ua")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.connector_helper.rq.post")
    @patch("fivetran_connector_sdk.connector_helper.constants")
    def test_create_connection_without_proxy_id(
        self, mock_constants, mock_post, mock_log, mock_ua
    ):
        from fivetran_connector_sdk.connector_helper import create_connection

        mock_constants.PRODUCTION_BASE_URL = "http://test"
        mock_post.return_value = MagicMock()

        config = {"schema": "s"}
        create_connection("dkey", "gid", config, None, "pkg", None)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertNotIn("proxy_agent_id", payload)
        self.assertNotIn("networking_method", payload)


if __name__ == "__main__":
    unittest.main()
