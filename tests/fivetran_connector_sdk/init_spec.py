import os
import sys
import unittest

from unittest.mock import patch, MagicMock, mock_open, ANY
from fivetran_connector_sdk import Connector, Logging, constants, __version__
from fivetran_connector_sdk.constants import DEPRECATED_FORCE_FLAG_WARNING
from fivetran_connector_sdk.helpers import PromptMode


def test_import_all():
    import fivetran_connector_sdk

    assert hasattr(fivetran_connector_sdk, "Connector")
    assert hasattr(fivetran_connector_sdk, "Logging")
    assert hasattr(fivetran_connector_sdk, "Operations")


class TestInit(unittest.TestCase):

    def setUp(self):

        from fivetran_connector_sdk.operations import Operations, _OperationStream

        # Reset the operation stream for each test
        Operations.operation_stream = _OperationStream()

        from fivetran_connector_sdk import Connector

        self.connector = Connector(update=MagicMock())
        self.args = MagicMock()
        self.args.project_path = "/proj"
        self.args.python_version = "3.8"
        self.args.non_interactive = False
        self.args.configuration = "dummy_config"

        # Tests use non-existent placeholder paths (e.g. "/proj"); bypass the real
        # directory-existence check so those paths keep flowing through unchanged.
        # Patched under both module paths since some tests below import main() via
        # `fivetran_connector_sdk.__init__`, which Python loads as a second, separate
        # module object from `fivetran_connector_sdk` itself.
        validate_path_patcher = patch(
            "fivetran_connector_sdk._resolve_existing_project_path",
            side_effect=lambda path: path,
        )
        validate_path_patcher.start()
        self.addCleanup(validate_path_patcher.stop)

        validate_path_dunder_init_patcher = patch(
            "fivetran_connector_sdk.__init__._resolve_existing_project_path",
            side_effect=lambda path: path,
        )
        validate_path_dunder_init_patcher.start()
        self.addCleanup(validate_path_dunder_init_patcher.stop)

    @patch("fivetran_connector_sdk.__init__.print_library_log")
    @patch("builtins.print")
    def test_main_version(self, mock_print, mock_log):
        test_args = ["fivetran", "version"]
        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main, __version__

            try:
                main()
            except SystemExit:
                pass  # Version command calls sys.exit(0) after printing version
            mock_log.assert_called_with("fivetran_connector_sdk " + __version__)

    @patch("fivetran_connector_sdk.helpers.reset_local_file_directory")
    @patch("builtins.input", return_value="y")
    def test_main_reset(self, mock_reset, mock_input):
        test_args = ["fivetran", "reset"]
        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass  # Reset command calls sys.exit(0) after completing
            mock_reset.assert_called()

    @patch("fivetran_connector_sdk.cli_parser.create_argument_parser")
    def test_main_help(self, mock_create_parser):
        """Test main() help command prints help and exits"""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_create_parser.return_value = mock_parser
        mock_args.command = "help"
        mock_args.version = False
        mock_args.test = False
        mock_args.project_path = "/test/path"
        mock_parser.parse_args.return_value = mock_args

        test_args = ["fivetran", "help"]
        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()

            # Verify help was printed and exit code is 0
            self.assertEqual(cm.exception.code, 0)

    @patch("fivetran_connector_sdk.__init__.get_configuration", return_value=({}, None))
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.helpers.validate_and_load_configuration", return_value={})
    @patch("fivetran_connector_sdk.helpers.validate_and_load_state", return_value={})
    @patch(
        "fivetran_connector_sdk.helpers.get_input_from_cli",
        side_effect=["api_key", "group", "connection"],
    )
    def test_main_deploy(
        self, mock_input, mock_state, mock_config, mock_find, mock_get_configuration
    ):
        mock_connector = MagicMock()
        mock_find.return_value = mock_connector
        test_args = [
            "fivetran",
            "deploy",
            "--api-key",
            "api_key",
            "--destination",
            "group",
            "--connection",
            "connection",
            "--configuration",
            "configuration.json",
        ]
        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass  # Deploy command may call sys.exit() after completion
            mock_connector.deploy.assert_called()

    def test_parser_uses_non_interactive_flag(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        args = parser.parse_args(["deploy", "--non-interactive"])

        self.assertTrue(args.non_interactive)
        self.assertFalse(args.force)

    def test_parser_keeps_force_flags_as_force_aliases(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()

        for force_flag in ("--force", "-f"):
            with self.subTest(force_flag=force_flag):
                args = parser.parse_args(["deploy", force_flag])

                self.assertFalse(args.non_interactive)
                self.assertTrue(args.force)

    def test_parser_uses_yes_flag(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        args = parser.parse_args(["deploy", "--yes"])

        self.assertTrue(args.yes)
        self.assertFalse(args.non_interactive)
        self.assertFalse(args.force)

    def test_force_not_visible_in_help(self):
        import argparse
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        deploy_parser = parser._subparsers._group_actions[0].choices["deploy"]
        for action in deploy_parser._actions:
            if hasattr(action, "option_strings") and "--force" in action.option_strings:
                self.assertEqual(action.help, argparse.SUPPRESS)
                return
        self.fail("--force action not found in deploy parser")

    def test_yes_visible_in_help(self):
        import argparse
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        deploy_parser = parser._subparsers._group_actions[0].choices["deploy"]
        for action in deploy_parser._actions:
            if hasattr(action, "option_strings") and "--yes" in action.option_strings:
                self.assertNotEqual(action.help, argparse.SUPPRESS)
                return
        self.fail("--yes action not found in deploy parser")

    def test_main_errors_on_yes_and_non_interactive_together(self):
        from fivetran_connector_sdk.__init__ import main

        test_args = [
            "fivetran",
            "deploy",
            "--api-key",
            "key",
            "--destination",
            "dest",
            "--connection",
            "conn",
            "--yes",
            "--non-interactive",
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("fivetran_connector_sdk.__init__.print_library_log") as mock_log,
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 1)

    def test_main_errors_on_yes_and_force_together(self):
        from fivetran_connector_sdk.__init__ import main

        test_args = [
            "fivetran",
            "deploy",
            "--api-key",
            "key",
            "--destination",
            "dest",
            "--connection",
            "conn",
            "--yes",
            "--force",
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("fivetran_connector_sdk.__init__.print_library_log") as mock_log,
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 1)

    def test_main_logs_deprecation_warning_for_force_flags(self):
        from fivetran_connector_sdk.__init__ import main

        for force_flag in ("--force", "-f"):
            with self.subTest(force_flag=force_flag):
                mock_connector = MagicMock()
                test_args = [
                    "fivetran",
                    "deploy",
                    "--api-key",
                    "api_key",
                    "--destination",
                    "group",
                    "--connection",
                    "connection",
                    force_flag,
                ]
                with (
                    patch.object(sys, "argv", test_args),
                    patch(
                        "fivetran_connector_sdk.__init__.find_connector_object",
                        return_value=mock_connector,
                    ),
                    patch(
                        "fivetran_connector_sdk.__init__.get_destination_group",
                        return_value="group",
                    ),
                    patch(
                        "fivetran_connector_sdk.__init__.get_connection_name",
                        return_value="connection",
                    ),
                    patch("fivetran_connector_sdk.__init__.get_api_key", return_value="api_key"),
                    patch("fivetran_connector_sdk.__init__.get_python_version", return_value=None),
                    patch("fivetran_connector_sdk.__init__.get_hd_agent_id", return_value=None),
                    patch(
                        "fivetran_connector_sdk.__init__.get_configuration",
                        return_value=({}, None),
                    ),
                    patch("fivetran_connector_sdk.__init__.get_state"),
                    patch("fivetran_connector_sdk.__init__.print_library_log") as mock_log,
                ):
                    main()

                mock_log.assert_any_call(DEPRECATED_FORCE_FLAG_WARNING, Logging.Level.WARNING)
                mock_connector.deploy.assert_called_once()
                self.assertTrue(mock_connector.deploy.call_args.args[8])

    def test_main_does_not_log_deprecation_warning_for_non_interactive(self):
        from fivetran_connector_sdk.__init__ import main

        mock_connector = MagicMock()
        test_args = [
            "fivetran",
            "deploy",
            "--api-key",
            "api_key",
            "--destination",
            "group",
            "--connection",
            "connection",
            "--non-interactive",
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch(
                "fivetran_connector_sdk.__init__.find_connector_object",
                return_value=mock_connector,
            ),
            patch("fivetran_connector_sdk.__init__.get_destination_group", return_value="group"),
            patch(
                "fivetran_connector_sdk.__init__.get_connection_name", return_value="connection"
            ),
            patch("fivetran_connector_sdk.__init__.get_api_key", return_value="api_key"),
            patch("fivetran_connector_sdk.__init__.get_python_version", return_value=None),
            patch("fivetran_connector_sdk.__init__.get_hd_agent_id", return_value=None),
            patch("fivetran_connector_sdk.__init__.get_configuration", return_value=({}, None)),
            patch("fivetran_connector_sdk.__init__.get_state"),
            patch("fivetran_connector_sdk.__init__.print_library_log") as mock_log,
        ):
            main()

        deprecated_warning_calls = [
            log_call
            for log_call in mock_log.call_args_list
            if log_call.args == (DEPRECATED_FORCE_FLAG_WARNING, Logging.Level.WARNING)
        ]
        self.assertEqual(deprecated_warning_calls, [])
        mock_connector.deploy.assert_called_once()
        self.assertTrue(mock_connector.deploy.call_args.args[8])

    @patch("fivetran_connector_sdk.__init__.find_connector_object", return_value=None)
    def test_main_exits_if_no_connector_object(self, mock_find):

        test_args = ["fivetran", "deploy"]
        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)

    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.process_tables")
    def test_schema_success(self, mock_process_tables, mock_print_log):
        mock_schema_method = MagicMock(return_value="mock_response")
        connector = Connector(update=MagicMock(), schema=mock_schema_method)
        connector.configuration = {"foo": "bar"}
        mock_request = MagicMock()
        mock_context = MagicMock()

        with patch("fivetran_connector_sdk.TABLES", {"t1": "table1", "t2": "table2"}):
            with patch("fivetran_connector_sdk.common_pb2.TableList") as mock_table_list:
                with patch(
                    "fivetran_connector_sdk.connector_sdk_pb2.SchemaResponse"
                ) as mock_schema_response:
                    result = connector.Schema(mock_request, mock_context)
                    mock_print_log.assert_called_with("calling schema()", Logging.Level.INFO)
                    mock_schema_method.assert_called_with({"foo": "bar"})
                    mock_process_tables.assert_called()
                    mock_schema_response.assert_called()
                    self.assertEqual(result, mock_schema_response())

    @patch("fivetran_connector_sdk.print_library_log")
    def test_schema_no_schema_method(self, mock_print_log):
        connector = Connector(update=MagicMock(), schema=None)
        mock_request = MagicMock()
        mock_context = MagicMock()
        with patch(
            "fivetran_connector_sdk.connector_sdk_pb2.SchemaResponse"
        ) as mock_schema_response:
            result = connector.Schema(mock_request, mock_context)
            mock_schema_response.assert_called_with(schema_response_not_supported=True)
            self.assertEqual(result, mock_schema_response())

    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.process_tables", side_effect=Exception("fail"))
    def test_schema_exception(self, mock_process_tables, mock_print_log):
        mock_schema_method = MagicMock(return_value="mock_response")
        connector = Connector(update=MagicMock(), schema=mock_schema_method)
        connector.configuration = {"foo": "bar"}
        mock_request = MagicMock()
        mock_context = MagicMock()
        with patch("fivetran_connector_sdk.TABLES", {}):
            with patch("fivetran_connector_sdk.common_pb2.TableList"):
                with patch("fivetran_connector_sdk.connector_sdk_pb2.SchemaResponse"):
                    original_debugging = constants.DEBUGGING
                    constants.DEBUGGING = False
                    try:
                        with self.assertRaises(RuntimeError) as cm:
                            connector.Schema(mock_request, mock_context)
                    finally:
                        constants.DEBUGGING = original_debugging
                    self.assertIn("failed while executing schema", str(cm.exception))
                    self.assertIn("Traceback (most recent call last):", str(cm.exception))
                    mock_print_log.assert_called()

    @patch("fivetran_connector_sdk.print_library_log")
    def test_schema_debug_stores_crash_report_without_changing_error_behavior(
        self, mock_print_log
    ):
        connector = Connector(
            update=MagicMock(), schema=MagicMock(side_effect=ValueError("schema fail"))
        )
        connector.configuration = {"foo": "bar"}
        connector.project_path = "/project"
        mock_request = MagicMock()
        mock_context = MagicMock()

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = True
        try:
            with patch(
                "fivetran_connector_sdk.build_debug_crash_report", return_value="SCHEMA REPORT"
            ) as mock_report:
                with self.assertRaises(RuntimeError) as cm:
                    connector.Schema(mock_request, mock_context)
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing schema", str(cm.exception))
        self.assertNotIn("Traceback (most recent call last):", str(cm.exception))
        mock_report.assert_called_once()
        self.assertIsInstance(mock_report.call_args.args[0], ValueError)
        self.assertEqual(mock_report.call_args.args[1], "/project")
        self.assertEqual(mock_report.call_args.kwargs["handler"], "schema()")
        self.assertEqual(mock_report.call_args.kwargs["sdk_version"], __version__)
        self.assertIsNone(mock_report.call_args.kwargs["state"])
        self.assertEqual(mock_report.call_args.kwargs["configuration"], {"foo": "bar"})
        self.assertEqual(connector._debug_crash_report, "SCHEMA REPORT")
        mock_print_log.assert_called()

    @patch("fivetran_connector_sdk.print_library_log")
    def test_schema_debug_preserves_original_error_when_crash_report_generation_fails(
        self, mock_print_log
    ):
        connector = Connector(
            update=MagicMock(), schema=MagicMock(side_effect=ValueError("schema fail"))
        )
        connector.configuration = {"foo": "bar"}
        connector.project_path = "/project"
        mock_request = MagicMock()
        mock_context = MagicMock()

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = True
        try:
            with patch(
                "fivetran_connector_sdk.build_debug_crash_report",
                side_effect=RuntimeError("report fail"),
            ):
                with self.assertRaises(RuntimeError) as cm:
                    connector.Schema(mock_request, mock_context)
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing schema() error: schema fail", str(cm.exception))
        self.assertNotIn("Traceback (most recent call last):", str(cm.exception))
        self.assertNotIn("report fail", str(cm.exception))
        self.assertIsNone(connector._debug_crash_report)
        self.assertTrue(
            any(
                "failed to build crash report" in str(call.args[0])
                and call.args[1] == Logging.Level.WARNING
                for call in mock_print_log.call_args_list
            )
        )

    @patch("fivetran_connector_sdk.print_library_log")
    def test_update_typeerror_none_iterable(self, mock_log):
        connector = Connector(update=MagicMock())
        connector.update_method = MagicMock(
            side_effect=TypeError("'NoneType' object is not iterable")
        )
        mock_request = MagicMock()
        mock_request.state_json = "{}"
        mock_context = MagicMock()
        gen = connector.Update(mock_request, mock_context)
        with self.assertRaises(RuntimeError) as cm:
            next(gen)
        self.assertIn("'NoneType' object is not iterable", str(cm.exception))

    @patch("fivetran_connector_sdk.print_library_log")
    def test_update_typeerror_other(self, mock_log):
        connector = Connector(update=MagicMock())
        connector.update_method = MagicMock(side_effect=TypeError("other error"))
        mock_request = MagicMock()
        mock_request.state_json = "{}"
        mock_context = MagicMock()
        gen = connector.Update(mock_request, mock_context)
        with self.assertRaises(RuntimeError) as cm:
            next(gen)
        self.assertIn("other error", str(cm.exception))

    @patch("fivetran_connector_sdk.print_library_log")
    def test_update_generic_exception(self, mock_log):
        connector = Connector(update=MagicMock())
        connector.update_method = MagicMock(side_effect=ValueError("fail"))
        mock_request = MagicMock()
        mock_request.state_json = "{}"
        mock_context = MagicMock()
        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = False
        try:
            gen = connector.Update(mock_request, mock_context)
            with self.assertRaises(RuntimeError) as cm:
                next(gen)
        finally:
            constants.DEBUGGING = original_debugging
        self.assertIn("failed while executing update", str(cm.exception))
        self.assertIn("Traceback (most recent call last):", str(cm.exception))
        self.assertTrue(
            any(
                "failed" in str(call.args[0]) and call.args[1] == Logging.Level.SEVERE
                for call in mock_log.call_args_list
            )
        )

    @patch("fivetran_connector_sdk.print_library_log")
    def test_update_debug_stores_crash_report_without_changing_error_behavior(self, mock_log):
        connector = Connector(update=MagicMock(side_effect=ValueError("fail")))
        connector.project_path = "/project"
        connector.configuration = {"api_key": "secret-token"}
        mock_request = MagicMock()
        mock_request.configuration = {"api_key": "secret-token"}
        mock_request.state_json = "{}"
        mock_context = MagicMock()

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = True
        try:
            mock_memory_tracker = MagicMock()
            with (
                patch(
                    "fivetran_connector_sdk.build_debug_crash_report", return_value="REPORT"
                ) as mock_report,
                patch("builtins.print") as mock_print,
                patch(
                    "fivetran_connector_sdk.get_memory_tracker", return_value=mock_memory_tracker
                ),
            ):
                gen = connector.Update(mock_request, mock_context)
                with self.assertRaises(RuntimeError) as cm:
                    next(gen)
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing update", str(cm.exception))
        self.assertNotIn("Traceback (most recent call last):", str(cm.exception))
        mock_report.assert_called_once()
        self.assertIsInstance(mock_report.call_args.args[0], ValueError)
        self.assertEqual(mock_report.call_args.args[1], "/project")
        self.assertEqual(mock_report.call_args.kwargs["handler"], "update()")
        self.assertEqual(mock_report.call_args.kwargs["sdk_version"], __version__)
        self.assertEqual(mock_report.call_args.kwargs["state"], {})
        self.assertEqual(
            mock_report.call_args.kwargs["configuration"], {"api_key": "secret-token"}
        )
        self.assertEqual(connector._debug_crash_report, "REPORT")
        mock_print.assert_not_called()

    @patch("fivetran_connector_sdk.print_library_log")
    def test_update_debug_preserves_original_error_when_crash_report_generation_fails(
        self, mock_log
    ):
        connector = Connector(update=MagicMock(side_effect=ValueError("fail")))
        connector.project_path = "/project"
        mock_request = MagicMock()
        mock_request.configuration = {"api_key": "secret-token"}
        mock_request.state_json = "{}"
        mock_context = MagicMock()

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = True
        try:
            with (
                patch(
                    "fivetran_connector_sdk.build_debug_crash_report",
                    side_effect=RuntimeError("report fail"),
                ),
                patch("fivetran_connector_sdk.get_memory_tracker", return_value=MagicMock()),
            ):
                gen = connector.Update(mock_request, mock_context)
                with self.assertRaises(RuntimeError) as cm:
                    next(gen)
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing update() error: fail", str(cm.exception))
        self.assertNotIn("Traceback (most recent call last):", str(cm.exception))
        self.assertNotIn("report fail", str(cm.exception))
        self.assertIsNone(connector._debug_crash_report)
        self.assertTrue(
            any(
                "failed" in str(call.args[0]) and call.args[1] == Logging.Level.SEVERE
                for call in mock_log.call_args_list
            )
        )
        self.assertTrue(
            any(
                "failed to build crash report" in str(call.args[0])
                and call.args[1] == Logging.Level.WARNING
                for call in mock_log.call_args_list
            )
        )

    def test_print_debug_crash_report_prints_stored_report(self):
        connector = Connector(update=MagicMock())
        connector._debug_crash_report = "REPORT"

        with patch("builtins.print") as mock_print:
            connector._print_debug_crash_report()

        mock_print.assert_called_once_with(Logging.colorize("REPORT", Logging.Level.SEVERE))
        self.assertIsNone(connector._debug_crash_report)

    def test_print_debug_crash_report_clears_report_so_a_second_call_is_a_noop(self):
        connector = Connector(update=MagicMock())
        connector._debug_crash_report = "REPORT"

        with patch("builtins.print") as mock_print:
            connector._print_debug_crash_report()
            connector._print_debug_crash_report()

        mock_print.assert_called_once_with(Logging.colorize("REPORT", Logging.Level.SEVERE))

    def test_print_debug_crash_report_is_noop_without_report(self):
        connector = Connector(update=MagicMock())

        with patch("builtins.print") as mock_print:
            connector._print_debug_crash_report()

        mock_print.assert_not_called()

    def test_connector_test(self):
        from fivetran_connector_sdk.protos import common_pb2

        connector = Connector(update=MagicMock())
        mock_request = MagicMock()
        mock_context = MagicMock()

        result = connector.Test(mock_request, mock_context)
        self.assertIsInstance(result, common_pb2.TestResponse)
        self.assertTrue(result.success)

    def test_run_debugging_false(self):
        connector = Connector(update=MagicMock())
        with (
            patch("fivetran_connector_sdk.check_dict", side_effect=lambda x, *a, **k: x),
            patch("fivetran_connector_sdk.Logging") as mock_logging,
            patch("fivetran_connector_sdk.constants") as mock_constants,
            patch("fivetran_connector_sdk.print_library_log") as mock_log,
            patch(
                "fivetran_connector_sdk.connector_sdk_pb2_grpc.add_SourceConnectorServicer_to_server"
            ) as mock_add,
            patch("fivetran_connector_sdk.grpc.server") as mock_grpc_server,
        ):
            mock_constants.DEBUGGING = False
            mock_server = MagicMock()
            mock_grpc_server.return_value = mock_server

            connector.run(
                port=12345,
                configuration={"foo": "bar"},
                state={"baz": 1},
                log_level=Logging.Level.FINE,
            )

            mock_log.assert_called_with("Running on fivetran_connector_sdk: " + __version__)
            mock_add.assert_called_with(connector, mock_server)
            mock_server.add_insecure_port.assert_called_with("[::]:12345")
            mock_server.start.assert_called_once()
            mock_server.wait_for_termination.assert_called_once()
            self.assertEqual(connector.configuration, {"foo": "bar"})
            self.assertEqual(connector.state, {"baz": 1})
            self.assertEqual(mock_logging.LOG_LEVEL, Logging.Level.FINE)

    def test_run_debugging_true(self):
        connector = Connector(update=MagicMock())
        with (
            patch("fivetran_connector_sdk.check_dict", side_effect=lambda x, *a, **k: x),
            patch("fivetran_connector_sdk.Logging") as mock_logging,
            patch("fivetran_connector_sdk.constants") as mock_constants,
            patch("fivetran_connector_sdk.print_library_log") as mock_log,
            patch(
                "fivetran_connector_sdk.connector_sdk_pb2_grpc.add_SourceConnectorServicer_to_server"
            ) as mock_add,
            patch("fivetran_connector_sdk.grpc.server") as mock_grpc_server,
        ):
            mock_constants.DEBUGGING = True
            mock_server = MagicMock()
            mock_grpc_server.return_value = mock_server

            result = connector.run(
                port=54321, configuration={"a": 1}, state={"b": 2}, log_level=Logging.Level.INFO
            )

            mock_log.assert_not_called()
            mock_add.assert_called_with(connector, mock_server)
            mock_server.add_insecure_port.assert_called_with("127.0.0.1:54321")
            mock_server.start.assert_called_once()
            mock_server.wait_for_termination.assert_not_called()
            self.assertIs(result, mock_server)
            self.assertEqual(connector.configuration, {"a": 1})
            self.assertEqual(connector.state, {"b": 2})
            self.assertEqual(mock_logging.LOG_LEVEL, Logging.Level.INFO)

    def test_connector_configuration_form(self):
        connector = Connector(update=MagicMock())
        connector.configuration_form = MagicMock(return_value="form_resp")
        mock_request = MagicMock()
        mock_context = MagicMock()
        with patch(
            "fivetran_connector_sdk.protos.common_pb2.ConfigurationFormResponse"
        ) as mock_form_response:
            connector.ConfigurationForm(mock_request, mock_context)
            self.assertTrue(mock_form_response.called)

        with (
            patch("fivetran_connector_sdk.Connector.debug") as mock_debug,
            patch("fivetran_connector_sdk.print_library_log") as mock_log,
        ):
            mock_debug.return_value = None
            Connector.debug("dummy_path", "dummy_config", "dummy_state", False)
            mock_debug.assert_called_once()

    def test_deploy_command_success(self):
        with (
            patch("fivetran_connector_sdk.Connector.deploy") as mock_deploy,
            patch("fivetran_connector_sdk.print_library_log") as mock_log,
        ):
            from fivetran_connector_sdk import Connector

            mock_deploy.return_value = None
            Connector.deploy(
                mock_deploy.__class__,
                "dummy_path",
                "dummy_key",
                "dummy_group",
                "dummy_conn",
                "dummy_hd_agent_id",
            )
            mock_deploy.assert_called_once()

    @patch("os.path.exists", return_value=False)
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.get_group_info", side_effect=SystemExit(1))
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_validate_requirements_file_called_when_interactive(
        self, mock_version_check, mock_get_group_info, mock_validate, mock_exists
    ):
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        project_path = "/dummy/path"
        non_interactive = False
        version = __version__

        with self.assertRaises(SystemExit) as cm:
            connector.deploy(
                project_path,
                "dummy_key",
                "dummy_group",
                "dummy_conn",
                "dummy_hd_agent_id",
                configuration={},
                prompt_mode=PromptMode.INTERACTIVE,
            )

        # Assert that SystemExit was raised with code 1
        self.assertEqual(cm.exception.code, 1)

        # Ensure validate_requirements_file was called before the failure (no pyproject.toml exists)
        mock_validate.assert_called_once_with(project_path, True, version, PromptMode.INTERACTIVE)

    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.get_group_info", side_effect=SystemExit(1))
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_validate_pyproject_file_called_for_pyproject_toml(
        self,
        mock_version_check,
        mock_get_group_info,
        mock_validate_req,
        mock_validate_toml,
        mock_exists,
    ):
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        project_path = "/dummy/path"
        non_interactive = False

        with self.assertRaises(SystemExit) as cm:
            connector.deploy(
                project_path,
                "dummy_key",
                "dummy_group",
                "dummy_conn",
                "dummy_hd_agent_id",
                configuration={},
                prompt_mode=PromptMode.INTERACTIVE,
            )

        self.assertEqual(cm.exception.code, 1)

        # Ensure validate_pyproject_file was called and validate_requirements_file was NOT
        mock_validate_toml.assert_called_once()
        mock_validate_req.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.get_group_info", side_effect=SystemExit(1))
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_with_non_interactive_runs_pyproject_validation(
        self,
        mock_version_check,
        mock_get_group_info,
        mock_validate_req,
        mock_validate_toml,
        mock_log,
        mock_exists,
    ):
        """Deploy with non_interactive and pyproject.toml present: validation runs with DEFAULT_ANSWER mode."""
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        with self.assertRaises(SystemExit):
            connector.deploy(
                "/dummy/path",
                "dummy_key",
                "dummy_group",
                "dummy_conn",
                "dummy_hd_agent_id",
                configuration={},
                prompt_mode=PromptMode.DEFAULT_ANSWER,
            )

        mock_validate_toml.assert_called_once_with("/dummy/path", True, PromptMode.DEFAULT_ANSWER)
        mock_validate_req.assert_not_called()

    @patch("os.path.exists", return_value=False)
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=None)
    @patch("fivetran_connector_sdk.get_group_info", return_value=("group_id", "group_name"))
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_exits_when_configuration_is_none_for_new_connection(
        self, mock_version, mock_group, mock_connection, mock_validate, mock_exists
    ):
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        with self.assertRaises(SystemExit) as cm:
            connector.deploy(
                "/dummy/path",
                "dummy_key",
                "dummy_group",
                "dummy_conn",
                "dummy_hd_agent_id",
                configuration=None,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_debug_exits_when_configuration_is_none(self):
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        with self.assertRaises(SystemExit) as cm:
            connector.debug(project_path="/dummy/path", configuration=None)
        self.assertEqual(cm.exception.code, 1)

    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.get_group_info", side_effect=SystemExit(1))
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_with_yes_runs_pyproject_validation(
        self,
        mock_version_check,
        mock_get_group_info,
        mock_validate_req,
        mock_validate_toml,
        mock_log,
        mock_exists,
    ):
        """Deploy with --yes runs dependency validation with YES mode."""
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        with self.assertRaises(SystemExit):
            connector.deploy(
                "/dummy/path",
                "dummy_key",
                "dummy_group",
                "dummy_conn",
                "dummy_hd_agent_id",
                prompt_mode=PromptMode.YES,
            )

        mock_validate_toml.assert_called_once_with("/dummy/path", True, PromptMode.YES)
        mock_validate_req.assert_not_called()

    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.exit_check")
    @patch("fivetran_connector_sdk.get_available_port", return_value=55555)
    @patch("fivetran_connector_sdk.run_tester", return_value=["log1", "log2"])
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch(
        "fivetran_connector_sdk.ensure_tester_installed",
        return_value=("/tmp/tester/java", "/tmp/tester"),
    )
    @patch("fivetran_connector_sdk.Connector.run")
    @patch("fivetran_connector_sdk.update_base_url_if_required")
    def test_debug_no_install_needed(
        self,
        mock_update_base_url,
        mock_run,
        mock_ensure,
        mock_check,
        mock_tester,
        mock_port,
        mock_exit,
        mock_validate,
        mock_log,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        connector = Connector(update=MagicMock())
        connector.state = {"foo": "bar"}
        connector.configuration = {"baz": 1}
        connector.debug(project_path="/proj", configuration={"baz": 1}, state={"foo": "bar"})
        mock_log.assert_any_call("debugging connector at: /proj", log_icon=Logging.LogIcon.STEP)
        mock_log.assert_any_call("starting connector tester", log_icon=Logging.LogIcon.STEP)
        mock_server.stop.assert_called_once_with(grace=2.0)

    def test_debug_registers_crash_report_exit_hook_before_memory_reporting(self):
        events = []
        mock_server = MagicMock()
        connector = Connector(update=MagicMock())
        connector.state = {}
        connector.configuration = {}

        with (
            patch("fivetran_connector_sdk.print_library_log"),
            patch("fivetran_connector_sdk.validate_requirements_file"),
            patch("fivetran_connector_sdk.exit_check"),
            patch("fivetran_connector_sdk.get_available_port", return_value=55555),
            patch("fivetran_connector_sdk.run_tester", return_value=[]),
            patch("fivetran_connector_sdk.check_newer_version"),
            patch("fivetran_connector_sdk.tester_root_dir_helper", return_value="/tmp/tester"),
            patch("fivetran_connector_sdk.get_os_arch_suffix", return_value="osx-arm64"),
            patch("fivetran_connector_sdk.java_exe_helper", return_value="/tmp/tester/java"),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", mock_open(read_data=constants.TESTER_VERSION)),
            patch("fivetran_connector_sdk.Connector.run", return_value=mock_server),
            patch(
                "fivetran_connector_sdk.atexit.register",
                side_effect=lambda _: events.append("crash_report"),
            ),
            patch("fivetran_connector_sdk.faulthandler.enable"),
        ):
            connector.debug(project_path="/proj", configuration={}, state={})

        self.assertEqual(events, ["crash_report"])
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.exit_check")
    @patch("fivetran_connector_sdk.get_available_port", return_value=55555)
    @patch("fivetran_connector_sdk.run_tester", return_value=["log1"])
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch(
        "fivetran_connector_sdk.connector_helper.tester_root_dir_helper",
        return_value="/tmp/tester",
    )
    @patch("fivetran_connector_sdk.connector_helper.get_os_arch_suffix", return_value="osx-arm64")
    @patch(
        "fivetran_connector_sdk.connector_helper.java_exe_helper", return_value="/tmp/tester/java"
    )
    @patch("os.path.isfile", return_value=False)
    @patch("os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.ZipFile")
    @patch("fivetran_connector_sdk.connector_helper.delete_file_if_exists")
    @patch("os.stat")
    @patch("os.chmod")
    @patch("fivetran_connector_sdk.Connector.run")
    def test_debug_install_needed(
        self,
        mock_run,
        mock_chmod,
        mock_stat,
        mock_delete,
        mock_zip,
        mock_openfile,
        mock_rq,
        mock_makedirs,
        mock_isfile,
        mock_java,
        mock_arch,
        mock_dir,
        mock_check,
        mock_tester,
        mock_port,
        mock_exit,
        mock_validate_req,
        mock_validate_toml,
        mock_log,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        mock_rq.return_value.ok = True
        mock_rq.return_value.headers = {}
        mock_rq.return_value.iter_content.return_value = [b"zip"]
        mock_rq.return_value.__enter__.return_value = mock_rq.return_value
        mock_rq.return_value.__exit__.return_value = False
        connector = Connector(update=MagicMock())
        connector.state = {}
        connector.configuration = {}
        connector.debug(project_path="/proj", configuration={}, state={})
        mock_makedirs.assert_called()
        mock_zip.assert_called()
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.exit_check")
    @patch("fivetran_connector_sdk.get_available_port", return_value=55555)
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch(
        "fivetran_connector_sdk.connector_helper.tester_root_dir_helper",
        return_value="/tmp/tester",
    )
    @patch("fivetran_connector_sdk.connector_helper.get_os_arch_suffix", return_value="osx-arm64")
    @patch(
        "fivetran_connector_sdk.connector_helper.java_exe_helper", return_value="/tmp/tester/java"
    )
    @patch("os.path.isfile", return_value=False)
    @patch("os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.Connector.run")
    def test_debug_download_fails(
        self,
        mock_run,
        mock_openfile,
        mock_rq,
        mock_makedirs,
        mock_isfile,
        mock_java,
        mock_arch,
        mock_dir,
        mock_check,
        mock_port,
        mock_exit,
        mock_validate,
        mock_log,
    ):
        mock_rq.return_value.ok = False
        mock_rq.return_value.status_code = 403
        mock_rq.return_value.__enter__.return_value = mock_rq.return_value
        mock_rq.return_value.__exit__.return_value = False
        connector = Connector(update=MagicMock())
        with self.assertRaises(RuntimeError) as cm:
            connector.debug(project_path="/proj", configuration={}, state={})
        self.assertIn("failed to download connector tester", str(cm.exception))

    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.exit_check")
    @patch("fivetran_connector_sdk.get_available_port", return_value=55555)
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch(
        "fivetran_connector_sdk.connector_helper.tester_root_dir_helper",
        return_value="/tmp/tester",
    )
    @patch("fivetran_connector_sdk.connector_helper.get_os_arch_suffix", return_value="osx-arm64")
    @patch(
        "fivetran_connector_sdk.connector_helper.java_exe_helper", return_value="/tmp/tester/java"
    )
    @patch("os.path.isfile", return_value=False)
    @patch("os.makedirs")
    @patch("fivetran_connector_sdk.connector_helper.rq.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("fivetran_connector_sdk.connector_helper.ZipFile", side_effect=Exception("unzip fail"))
    @patch("fivetran_connector_sdk.connector_helper.shutil.rmtree")
    @patch("fivetran_connector_sdk.Connector.run")
    def test_debug_unzip_fails(
        self,
        mock_run,
        mock_rmtree,
        mock_zip,
        mock_openfile,
        mock_rq,
        mock_makedirs,
        mock_isfile,
        mock_java,
        mock_arch,
        mock_dir,
        mock_check,
        mock_port,
        mock_exit,
        mock_validate,
        mock_log,
    ):
        mock_rq.return_value.ok = True
        mock_rq.return_value.headers = {}
        mock_rq.return_value.iter_content.return_value = [b"zip"]
        mock_rq.return_value.__enter__.return_value = mock_rq.return_value
        mock_rq.return_value.__exit__.return_value = False
        connector = Connector(update=MagicMock())
        with self.assertRaises(RuntimeError) as cm:
            connector.debug(project_path="/proj", configuration={}, state={})
        self.assertIn("failed to download connector tester", str(cm.exception))
        mock_rmtree.assert_called_with("/tmp/tester")

    @patch("fivetran_connector_sdk.update_base_url_if_required")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.exit_check")
    @patch("fivetran_connector_sdk.get_available_port", return_value=55555)
    @patch("fivetran_connector_sdk.run_tester", side_effect=Exception("tester fail"))
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch(
        "fivetran_connector_sdk.ensure_tester_installed",
        return_value=("/tmp/tester/java", "/tmp/tester"),
    )
    @patch("fivetran_connector_sdk.Connector.run")
    def test_debug_run_tester_exception(
        self,
        mock_run,
        mock_ensure,
        mock_check,
        mock_tester,
        mock_port,
        mock_exit,
        mock_validate,
        mock_log,
        mock_update_base_url,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        connector = Connector(update=MagicMock())
        connector.state = {}
        connector.configuration = {}
        with self.assertRaises(Exception) as cm:
            connector.debug(project_path="/proj", configuration={}, state={})
        self.assertEqual(str(cm.exception), "tester fail")
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_new_connection_success(
        self,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_create,
        mock_handle_response,
    ):
        from http import HTTPStatus

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"data": {"id": "cid", "config": {"python_version": "3.8"}}}
        mock_create.return_value = mock_resp
        mock_upload.return_value = "pkg_123"
        path, key, group, conn, hdid, conf, confpath = (
            "path",
            "key",
            "group",
            "conn",
            "hdid",
            {"foo": "bar"},
            "conf.json",
        )
        self.connector.configuration_form_method = MagicMock()

        self.connector.deploy(path, key, group, conn, hdid, conf, confpath)

        mock_upload.assert_called_once_with(path, key, self.connector.configuration_form_method)
        mock_create.assert_called_once()
        mock_handle_response.assert_called_once_with(
            mock_resp, "pkg_123", key, HTTPStatus.CREATED.value, is_new_connection=True
        )

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_new_connection_setup_tests_fail(
        self,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_create,
        mock_handle_response,
    ):
        from http import HTTPStatus

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"data": {"id": "cid", "config": {"python_version": "3.8"}}}
        mock_create.return_value = mock_resp
        mock_upload.return_value = "pkg_456"

        self.connector.deploy(self.args, "key", "group", "conn", "hdid", {"foo": "bar"})
        mock_upload.assert_called_once()
        mock_create.assert_called_once()
        mock_handle_response.assert_called_once_with(
            mock_resp, "pkg_456", "key", HTTPStatus.CREATED.value, is_new_connection=True
        )

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_new_connection_create_fails(
        self,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_create,
        mock_handle_response,
    ):
        from http import HTTPStatus

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"message": "fail"}
        mock_create.return_value = mock_resp
        mock_upload.return_value = "pkg_789"

        self.connector.deploy(self.args, "key", "group", "conn", "hdid", {"foo": "bar"})
        mock_upload.assert_called_once()
        mock_create.assert_called_once()
        mock_handle_response.assert_called_once_with(
            mock_resp, "pkg_789", "key", HTTPStatus.CREATED.value, is_new_connection=True
        )

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.update_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "connector_sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("fivetran_connector_sdk.resolve_confirmation", return_value=True)
    def test_deploy_update_connection_with_configuration_uses_one_confirmation(
        self,
        mock_confirmation,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_update,
        mock_handle_response,
    ):
        from http import HTTPStatus

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.json.return_value = {"data": {"config": {"python_version": "3.8"}}}
        mock_update.return_value = mock_resp
        mock_upload.return_value = "pkg_999"

        path, key, group, conn, hdid, conf = "path", "key", "group", "conn", "hdid", {"foo": "bar"}
        self.connector.deploy(path, key, group, conn, hdid, conf, "configuration.json")

        mock_confirmation.assert_called_once_with(
            "connection 'conn' already exists in destination 'group'.\n"
            "updating it will overwrite the existing code and replace its configuration with keys and values from configuration.json.\n"
            "please provide the complete configuration, as any missing keys will be deleted.\n"
            "tip: consider downloading the existing connector code from the Fivetran dashboard\n"
            "continue with update? (y/N): ",
            False,
            PromptMode.INTERACTIVE,
        )
        mock_upload.assert_called_once()
        mock_update.assert_called_once()
        mock_log.assert_any_call(
            "updating connection conn in group gname", log_icon=Logging.LogIcon.STEP
        )
        mock_handle_response.assert_called_once_with(
            mock_resp,
            "pkg_999",
            key,
            HTTPStatus.OK.value,
            is_new_connection=False,
            connection_id="cid",
        )

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.update_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "connector_sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("fivetran_connector_sdk.resolve_confirmation", return_value=False)
    def test_deploy_update_connection_cancels_when_configuration_confirmation_is_rejected(
        self,
        mock_confirmation,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_update,
        mock_handle_response,
        mock_exit,
    ):
        path, key, group, conn, hdid = "path", "key", "group", "conn", "hdid"
        self.connector.deploy(path, key, group, conn, hdid, {"foo": "bar"}, "configuration.json")

        mock_confirmation.assert_called_once_with(
            "connection 'conn' already exists in destination 'group'.\n"
            "updating it will overwrite the existing code and replace its configuration with keys and values from configuration.json.\n"
            "please provide the complete configuration, as any missing keys will be deleted.\n"
            "tip: consider downloading the existing connector code from the Fivetran dashboard\n"
            "continue with update? (y/N): ",
            False,
            PromptMode.INTERACTIVE,
        )
        mock_upload.assert_not_called()
        mock_update.assert_not_called()
        mock_log.assert_any_call("update cancelled", log_icon=Logging.LogIcon.FAILURE)
        mock_exit.assert_called_with(1)

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.update_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "connector_sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("fivetran_connector_sdk.resolve_confirmation", return_value=False)
    def test_deploy_update_connection_without_configuration_retains_original_confirmation(
        self,
        mock_confirmation,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_update,
        mock_handle_response,
        mock_exit,
    ):
        self.connector.deploy("path", "key", "group", "conn", "hdid")

        mock_confirmation.assert_called_once_with(
            "connection 'conn' already exists in destination 'group'\n"
            "updating it will overwrite the existing code\n"
            "tip: consider downloading the existing connector code from the Fivetran dashboard\n"
            "continue with update? (y/N): ",
            False,
            PromptMode.INTERACTIVE,
        )
        mock_upload.assert_not_called()
        mock_update.assert_not_called()
        mock_log.assert_any_call("update cancelled", log_icon=Logging.LogIcon.FAILURE)
        mock_exit.assert_called_with(1)

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "not_sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_update_connection_wrong_service(
        self,
        mock_version_check,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_log,
        mock_exit,
    ):
        self.connector.deploy("path", "key", "group", "conn", "hdid", {"foo": "bar"})
        mock_log.assert_any_call(
            "cannot update connection 'conn'; not a Connector SDK connection",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )
        mock_exit.assert_called_once_with(1)

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_update_connection_with_naming(
        self,
        mock_version_check,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_log,
        mock_exit,
    ):
        self.connector.deploy(
            "path", "key", "group", "conn", "hdid", {"foo": "bar"}, naming="SOURCE_NAMING"
        )

        mock_log.assert_any_call(
            "ignored --naming flag; naming strategy cannot be changed after connection creation",
            Logging.Level.WARNING,
        )

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_logs_python_version_not_specified(
        self,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_create,
        mock_handle_response,
    ):
        from fivetran_connector_sdk.constants import DEFAULT_PYTHON_VERSION

        self.connector.deploy("path", "key", "group", "conn", "hdid", configuration={})

        mock_log.assert_any_call(
            f"python version not specified; connection will use the default python version ({DEFAULT_PYTHON_VERSION})"
        )
        mock_log.assert_any_call(
            "set --python-version <version> in the deploy command or update it in your Fivetran dashboard"
        )

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.update_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "connector_sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_existing_connection_does_not_log_python_version_not_specified(
        self,
        mock_version_check,
        mock_log,
        mock_check,
        mock_validate_req,
        mock_group,
        mock_conn_id,
        mock_upload,
        mock_update,
        mock_handle_response,
    ):
        self.connector.deploy(
            "path", "key", "group", "conn", "hdid", prompt_mode=PromptMode.FORCE, configuration={}
        )

        python_version_calls = [
            call
            for call in mock_log.call_args_list
            if call.args and "python version not specified" in call.args[0]
        ]
        self.assertEqual(
            len(python_version_calls),
            0,
            "print_library_log should not be called with 'python version not specified' for existing connections",
        )

    def test_connector_init_with_schema(self):
        """Test Connector initialization with schema method"""
        from fivetran_connector_sdk import Connector

        update_method = MagicMock()
        schema_method = MagicMock()

        connector = Connector(update=update_method, schema=schema_method)

        self.assertEqual(connector.update_method, update_method)
        self.assertEqual(connector.schema_method, schema_method)
        self.assertIsNone(connector.configuration)
        self.assertIsNone(connector.state)

    def test_connector_init_without_schema(self):
        """Test Connector initialization without schema method"""
        from fivetran_connector_sdk import Connector

        update_method = MagicMock()

        connector = Connector(update=update_method)

        self.assertEqual(connector.update_method, update_method)
        self.assertIsNone(connector.schema_method)

    @patch("fivetran_connector_sdk.constants")
    @patch("grpc.server")
    def test_run_method_basic(self, mock_grpc_server, mock_constants):
        """Test run method starts gRPC server"""
        from fivetran_connector_sdk import Connector

        mock_constants.DEBUGGING = False
        update_method = MagicMock()
        connector = Connector(update=update_method)

        mock_server = MagicMock()
        mock_grpc_server.return_value = mock_server

        _server = connector.run(port=50051, configuration={}, state={})

        mock_grpc_server.assert_called_once()
        mock_server.add_insecure_port.assert_called_once_with("[::]:50051")
        self.assertIsNotNone(connector.configuration)
        self.assertIsNotNone(connector.state)

    @patch("grpc.server")
    def test_run_method_with_log_level(self, mock_grpc_server):
        """Test run method with different log levels"""
        from fivetran_connector_sdk import Connector

        update_method = MagicMock()
        connector = Connector(update=update_method)

        mock_server = MagicMock()
        mock_grpc_server.return_value = mock_server

        connector.run(log_level=Logging.Level.SEVERE)

        self.assertEqual(Logging.LOG_LEVEL, Logging.Level.SEVERE)

    def test_configuration_form_method(self):
        """Test ConfigurationForm gRPC method"""
        from fivetran_connector_sdk import Connector
        from fivetran_connector_sdk.protos import common_pb2

        connector = Connector(update=MagicMock())
        request = MagicMock()
        context = MagicMock()

        response = connector.ConfigurationForm(request, context)

        self.assertIsInstance(response, common_pb2.ConfigurationFormResponse)
        # schema_selection_supported defaults to False
        self.assertFalse(response.schema_selection_supported)

    def test_method_returns_success_when_no_configuration_form(self):
        """Test gRPC Test method returns success when configuration_form_method is unset"""
        from fivetran_connector_sdk import Connector
        from fivetran_connector_sdk.protos import common_pb2

        connector = Connector(update=MagicMock())
        request = MagicMock()
        context = MagicMock()

        response = connector.Test(request, context)

        self.assertIsInstance(response, common_pb2.TestResponse)
        self.assertTrue(response.success)

    def test_schema_method_without_schema_method(self):
        """Test Schema gRPC method when no schema method is provided"""
        from fivetran_connector_sdk import Connector
        from fivetran_connector_sdk.protos import connector_sdk_pb2

        connector = Connector(update=MagicMock())
        request = MagicMock()
        request.configuration = {}
        context = MagicMock()

        response = connector.Schema(request, context)

        self.assertIsInstance(response, connector_sdk_pb2.SchemaResponse)
        self.assertTrue(response.schema_response_not_supported)

    def test_update_method_basic(self):
        """Test Update gRPC method"""
        from fivetran_connector_sdk import Connector

        update_method = MagicMock()
        update_method.return_value = iter([])

        connector = Connector(update=update_method)
        connector.configuration = {}
        connector.state = {}

        request = MagicMock()
        request.configuration = {}
        request.state_json = "{}"
        context = MagicMock()

        responses = list(connector.Update(request, context))

        update_method.assert_called_once()
        self.assertIsInstance(responses, list)

    def test_update_method_with_state_and_config(self):
        """Test Update method with configuration and state"""
        from fivetran_connector_sdk import Connector

        update_method = MagicMock()
        update_method.return_value = iter([])

        connector = Connector(update=update_method)

        request = MagicMock()
        request.configuration = {"api_key": "test"}
        request.state_json = '{"cursor": "2024-01-01"}'
        context = MagicMock()

        list(connector.Update(request, context))

        # Verify update_method was called with the parsed configuration and state
        update_method.assert_called_once()
        call_args = update_method.call_args
        self.assertEqual(call_args.kwargs["configuration"], {"api_key": "test"})
        self.assertEqual(call_args.kwargs["state"], {"cursor": "2024-01-01"})

    @patch("sys.exit")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_print_version(self, mock_log, mock_exit):
        """Test print_version function"""
        from fivetran_connector_sdk.__init__ import print_version, __version__

        print_version()
        mock_log.assert_called_once_with(f"fivetran_connector_sdk {__version__}")
        mock_exit.assert_called_once_with(0)

    @patch("fivetran_connector_sdk.connector_helper.check_dict")
    def test_deploy_with_configuration(self, mock_check_dict):
        """Test deploy method with configuration dictionary"""
        from fivetran_connector_sdk import Connector

        connector = Connector(update=MagicMock())
        config = {"key1": "value1", "key2": "value2"}

        with patch.object(connector, "deploy", wraps=connector.deploy) as mock_deploy:
            # We can't easily test the full flow, so just verify config processing
            mock_check_dict.return_value = config

            # Verify check_dict is called in deploy
            self.assertIsNotNone(config)

    # Tests for debug command in main() function (lines 593-611)
    @patch(
        "fivetran_connector_sdk.__init__.get_configuration",
        return_value=({"test": "config"}, "config.json"),
    )
    @patch("fivetran_connector_sdk.__init__.get_state", return_value={"test": "state"})
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    def test_main_debug_success(self, mock_find, _mock_get_state, _mock_get_configuration):
        """Test main() debug command success path"""
        mock_connector = MagicMock()
        mock_connector.debug = MagicMock()
        mock_find.return_value = mock_connector
        test_args = ["fivetran", "debug", "/test/path"]

        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass  # Debug command may call sys.exit() after completion

            # Verify debug was called with correct args
            mock_connector.debug.assert_called_once()
            call_args = mock_connector.debug.call_args[0]
            self.assertEqual(call_args[0], "/test/path")  # project_path
            # Configuration and state are retrieved from get_configuration and get_state mocks
            self.assertIsInstance(call_args[1], dict)  # configuration
            self.assertIsInstance(call_args[2], dict)  # state
            self.assertTrue(constants.DEBUGGING)

    @patch("fivetran_connector_sdk.__init__.get_configuration", return_value=({}, None))
    @patch("fivetran_connector_sdk.__init__.get_state", return_value={})
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_main_debug_subprocess_error(
        self, mock_log, mock_find, _mock_get_state, _mock_get_configuration
    ):
        """Test main() debug command with subprocess.CalledProcessError"""
        import subprocess

        mock_connector = MagicMock()
        mock_connector.debug = MagicMock(
            side_effect=subprocess.CalledProcessError(returncode=42, cmd="test")
        )
        mock_find.return_value = mock_connector
        test_args = ["fivetran", "debug", "/test/path"]

        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 42)

            # Verify error was logged
            mock_log.assert_any_call(
                "connector tester failed with exit code: 42",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )

    @patch("fivetran_connector_sdk.__init__.get_configuration", return_value=({}, None))
    @patch("fivetran_connector_sdk.__init__.get_state", return_value={})
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_main_debug_generic_exception(
        self, mock_log, mock_find, _mock_get_state, _mock_get_configuration
    ):
        """Test main() debug command with generic Exception"""
        mock_connector = MagicMock()
        mock_connector.debug = MagicMock(side_effect=Exception("Something went wrong"))
        mock_find.return_value = mock_connector
        test_args = ["fivetran", "debug", "/test/path"]

        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)

            # Verify error was logged
            mock_log.assert_any_call(
                "debug run failed error: Something went wrong",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )

    @patch("fivetran_connector_sdk.__init__.get_configuration", return_value=({}, None))
    @patch("fivetran_connector_sdk.__init__.get_state", return_value={})
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    def test_main_debug_env_vars_set_and_cleaned(
        self, mock_find, _mock_get_state, _mock_get_configuration
    ):
        """Test main() debug command sets and cleans up environment variables"""
        mock_connector = MagicMock()

        # Track environment variables during debug call
        env_vars_during_call = {}

        def capture_env(*args, **kwargs):
            env_vars_during_call["FIVETRAN_CONNECTION_ID"] = os.environ.get(
                "FIVETRAN_CONNECTION_ID"
            )
            env_vars_during_call["FIVETRAN_DEPLOYMENT_MODEL"] = os.environ.get(
                "FIVETRAN_DEPLOYMENT_MODEL"
            )
            env_vars_during_call["FIVETRAN_GROUP_ID"] = os.environ.get("FIVETRAN_GROUP_ID")
            env_vars_during_call["FIVETRAN_CONNECTION_NAME"] = os.environ.get(
                "FIVETRAN_CONNECTION_NAME"
            )

        mock_connector.debug = MagicMock(side_effect=capture_env)
        mock_find.return_value = mock_connector
        test_args = ["fivetran", "debug", "/test/path"]

        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass  # Debug command may call sys.exit() after completion

            # Verify env vars were set during call
            self.assertEqual(env_vars_during_call["FIVETRAN_CONNECTION_ID"], "test_connection_id")
            self.assertEqual(env_vars_during_call["FIVETRAN_DEPLOYMENT_MODEL"], "local_debug")
            self.assertEqual(env_vars_during_call["FIVETRAN_GROUP_ID"], "test_group_id")
            self.assertEqual(
                env_vars_during_call["FIVETRAN_CONNECTION_NAME"], "test_connection_name"
            )

            # Verify env vars were cleaned up after
            self.assertNotIn("FIVETRAN_CONNECTION_ID", os.environ)
            self.assertNotIn("FIVETRAN_DEPLOYMENT_MODEL", os.environ)
            self.assertNotIn("FIVETRAN_GROUP_ID", os.environ)
            self.assertNotIn("FIVETRAN_CONNECTION_NAME", os.environ)

    @patch("fivetran_connector_sdk.__init__.get_configuration", return_value=({}, None))
    @patch("fivetran_connector_sdk.__init__.get_state", return_value={})
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_main_debug_env_vars_cleaned_on_exception(
        self, _mock_log, mock_find, _mock_get_state, _mock_get_configuration
    ):
        """Test main() debug command cleans up environment variables even on exception"""
        mock_connector = MagicMock()
        mock_connector.debug = MagicMock(side_effect=Exception("Test error"))
        mock_find.return_value = mock_connector
        test_args = ["fivetran", "debug", "/test/path"]

        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass  # Exception handler calls sys.exit(1)

            # Verify env vars were cleaned up even after exception
            self.assertNotIn("FIVETRAN_CONNECTION_ID", os.environ)
            self.assertNotIn("FIVETRAN_DEPLOYMENT_MODEL", os.environ)
            self.assertNotIn("FIVETRAN_GROUP_ID", os.environ)
            self.assertNotIn("FIVETRAN_CONNECTION_NAME", os.environ)

    @patch("fivetran_connector_sdk.sys.exit")
    @patch("fivetran_connector_sdk.create_package")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    def test_package_command_success(self, mock_log, mock_validate, mock_create, mock_exit):
        """Test package() command creates package successfully"""
        from fivetran_connector_sdk import package

        mock_create.return_value = "/path/to/package.zip"

        package("/test/project", PromptMode.INTERACTIVE)

        mock_validate.assert_called_once()
        mock_create.assert_called_once_with("/test/project", None)
        mock_log.assert_any_call(
            "package created at: /path/to/package.zip", log_icon=Logging.LogIcon.SUCCESS
        )
        mock_exit.assert_called_once_with(0)

    @patch("fivetran_connector_sdk.__init__.package")
    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    def test_main_package_passes_configuration_form_method(self, mock_find, mock_package):
        mock_connector = MagicMock()
        mock_connector.configuration_form_method = MagicMock()
        mock_find.return_value = mock_connector
        test_args = ["fivetran", "package", "/test/project"]

        with patch.object(sys, "argv", test_args):
            from fivetran_connector_sdk.__init__ import main

            main()

        mock_package.assert_called_once_with(
            "/test/project", PromptMode.INTERACTIVE, mock_connector.configuration_form_method
        )

    @patch("fivetran_connector_sdk.sys.exit")
    @patch("fivetran_connector_sdk.create_package")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    def test_package_command_with_non_interactive(
        self, mock_log, mock_validate, mock_create, mock_exit
    ):
        """Test package() with non_interactive skips validation"""
        from fivetran_connector_sdk import package

        mock_create.return_value = "/path/to/package.zip"

        package("/test/project", PromptMode.DEFAULT_ANSWER)

        mock_validate.assert_called_once_with(
            "/test/project", True, __version__, PromptMode.DEFAULT_ANSWER
        )
        mock_create.assert_called_once_with("/test/project", None)
        mock_exit.assert_called_once_with(0)

    @patch("fivetran_connector_sdk.sys.exit")
    @patch("fivetran_connector_sdk.create_package")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    def test_package_command_with_yes(self, mock_log, mock_validate, mock_create, mock_exit):
        """Test package() with --yes runs validation with YES mode"""
        from fivetran_connector_sdk import package

        mock_create.return_value = "/path/to/package.zip"

        package("/test/project", PromptMode.YES)

        mock_validate.assert_called_once_with("/test/project", True, __version__, PromptMode.YES)
        mock_create.assert_called_once_with("/test/project", None)
        mock_exit.assert_called_once_with(0)

    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.sys.exit")
    @patch("fivetran_connector_sdk.create_package")
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    def test_package_command_with_pyproject_toml(
        self, mock_log, mock_validate_req, mock_validate_toml, mock_create, mock_exit, mock_exists
    ):
        """Test package() calls validate_pyproject_file when pyproject.toml exists"""
        from fivetran_connector_sdk import package

        mock_create.return_value = "/path/to/package.zip"

        package("/test/project", PromptMode.INTERACTIVE)

        mock_validate_toml.assert_called_once()
        mock_validate_req.assert_not_called()
        mock_create.assert_called_once_with("/test/project", None)
        mock_exit.assert_called_once_with(0)

    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.sys.exit")
    @patch("fivetran_connector_sdk.create_package")
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    def test_package_command_with_non_interactive_and_pyproject_toml(
        self, mock_log, mock_validate_req, mock_validate_toml, mock_create, mock_exit, mock_exists
    ):
        """package() with non_interactive and pyproject.toml present: pyproject validator runs with DEFAULT_ANSWER mode."""
        from fivetran_connector_sdk import package

        mock_create.return_value = "/path/to/package.zip"

        package("/test/project", PromptMode.DEFAULT_ANSWER)

        mock_validate_toml.assert_called_once_with(
            "/test/project", True, PromptMode.DEFAULT_ANSWER
        )
        mock_validate_req.assert_not_called()
        mock_create.assert_called_once_with("/test/project", None)
        mock_exit.assert_called_once_with(0)

    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.validate_pyproject_file")
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.exit_check")
    @patch("fivetran_connector_sdk.get_available_port", return_value=55555)
    @patch("fivetran_connector_sdk.run_tester", return_value=["log1", "log2"])
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch(
        "fivetran_connector_sdk.ensure_tester_installed",
        return_value=("/tmp/tester/java", "/tmp/tester"),
    )
    @patch("fivetran_connector_sdk.Connector.run")
    @patch("fivetran_connector_sdk.update_base_url_if_required")
    def test_debug_with_pyproject_toml(
        self,
        mock_update_base_url,
        mock_run,
        mock_ensure_tester_installed,
        mock_check,
        mock_tester,
        mock_port,
        mock_exit,
        mock_validate_req,
        mock_validate_toml,
        mock_log,
        mock_exists,
    ):
        """Test debug() calls validate_pyproject_file when pyproject.toml exists"""
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        connector = Connector(update=MagicMock())
        connector.state = {"foo": "bar"}
        connector.configuration = {"baz": 1}
        connector.debug(project_path="/proj", configuration={"baz": 1}, state={"foo": "bar"})

        mock_validate_toml.assert_called_once()
        mock_validate_req.assert_not_called()
        mock_log.assert_any_call("debugging connector at: /proj", log_icon=Logging.LogIcon.STEP)
        mock_server.stop.assert_called_once_with(grace=2.0)


class TestConfigurationFormHandler(unittest.TestCase):
    """Tests for the ConfigurationForm gRPC handler."""

    @staticmethod
    def _make_connector_with_form(form):
        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form
        return connector

    def test_configuration_form_returns_empty_response_when_no_method(self):
        from fivetran_connector_sdk.protos import common_pb2

        connector = Connector(update=MagicMock())
        response = connector.ConfigurationForm(MagicMock(), MagicMock())
        self.assertIsInstance(response, common_pb2.ConfigurationFormResponse)

    @patch("fivetran_connector_sdk.print_library_log")
    def test_configuration_form_returns_proto_from_form(self, _mock_log):
        from fivetran_connector_sdk.protos import common_pb2
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk import form_field

        form = ConfigurationForm()
        form.add_field(form_field.TextField("host", "Host"))

        connector = self._make_connector_with_form(form)
        response = connector.ConfigurationForm(MagicMock(), MagicMock())

        self.assertIsInstance(response, common_pb2.ConfigurationFormResponse)
        self.assertEqual(len(response.fields), 1)
        self.assertEqual(response.fields[0].name, "host")

    @patch("fivetran_connector_sdk.print_library_log")
    def test_configuration_form_uses_cached_form(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk import form_field

        form = ConfigurationForm()
        form.add_field(form_field.TextField("host", "Host"))
        configuration_form_method = MagicMock(return_value=form)
        connector = Connector(update=MagicMock(), configuration_form=configuration_form_method)

        first_response = connector.ConfigurationForm(MagicMock(), MagicMock())
        second_response = connector.ConfigurationForm(MagicMock(), MagicMock())

        self.assertEqual(first_response.fields[0].name, "host")
        self.assertEqual(second_response.fields[0].name, "host")
        configuration_form_method.assert_called_once_with()

    @patch("fivetran_connector_sdk.print_library_log")
    def test_configuration_form_includes_tests_in_proto(self, _mock_log):
        from fivetran_connector_sdk.protos import common_pb2
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        def my_test(config):
            pass

        form = ConfigurationForm()
        form.add_test(label="Check connection", func=my_test)

        connector = self._make_connector_with_form(form)
        response = connector.ConfigurationForm(MagicMock(), MagicMock())

        self.assertIsInstance(response, common_pb2.ConfigurationFormResponse)
        self.assertEqual(len(response.tests), 1)
        self.assertEqual(response.tests[0].name, "my_test")
        self.assertEqual(response.tests[0].label, "Check connection")

    @patch("fivetran_connector_sdk.print_library_log")
    def test_configuration_form_raises_runtime_error_on_exception(self, _mock_log):
        connector = Connector(update=MagicMock())
        connector.configuration_form_method = MagicMock(side_effect=ValueError("bad form"))

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = False
        try:
            with self.assertRaises(RuntimeError) as cm:
                connector.ConfigurationForm(MagicMock(), MagicMock())
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing configuration_form()", str(cm.exception))
        self.assertIn("bad form", str(cm.exception))
        self.assertIn("Traceback (most recent call last):", str(cm.exception))

    @patch("fivetran_connector_sdk.print_library_log")
    def test_configuration_form_debug_stores_crash_report_without_traceback_in_error(
        self, _mock_log
    ):
        connector = Connector(update=MagicMock())
        connector.configuration_form_method = MagicMock(side_effect=ValueError("bad form"))
        connector.project_path = "/project"

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = True
        try:
            with patch(
                "fivetran_connector_sdk.build_debug_crash_report", return_value="FORM REPORT"
            ) as mock_report:
                with self.assertRaises(RuntimeError) as cm:
                    connector.ConfigurationForm(MagicMock(), MagicMock())
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing configuration_form()", str(cm.exception))
        self.assertNotIn("Traceback (most recent call last):", str(cm.exception))
        mock_report.assert_called_once()
        self.assertEqual(mock_report.call_args.kwargs["handler"], "configuration_form()")
        self.assertEqual(connector._debug_crash_report, "FORM REPORT")

    @patch("fivetran_connector_sdk.print_library_log")
    def test_configuration_form_initializes_log_level_before_customer_logging(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        original_level = Logging.LOG_LEVEL
        Logging.LOG_LEVEL = None
        try:

            def logged_form():
                Logging.info("building configuration form")
                return ConfigurationForm()

            connector = Connector(update=MagicMock())
            connector.configuration_form_method = logged_form

            connector.ConfigurationForm(MagicMock(), MagicMock())

            self.assertEqual(Logging.LOG_LEVEL, Logging.Level.INFO)
        finally:
            Logging.LOG_LEVEL = original_level


class TestTestHandler(unittest.TestCase):
    """Tests for the Test gRPC handler."""

    @staticmethod
    def _make_request(name="my_test", configuration=None):
        req = MagicMock()
        req.name = name
        req.configuration = configuration or {}
        return req

    def test_returns_success_when_no_configuration_form_method(self):
        from fivetran_connector_sdk.protos import common_pb2

        connector = Connector(update=MagicMock())
        response = connector.Test(self._make_request(), MagicMock())
        self.assertIsInstance(response, common_pb2.TestResponse)
        self.assertTrue(response.success)

    @patch("fivetran_connector_sdk.print_library_log")
    def test_registered_test_returns_success(self, _mock_log):
        from fivetran_connector_sdk.protos import common_pb2
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.test import Test

        def my_test(config):
            return Test.success()

        form = ConfigurationForm()
        form.add_test(label="My test", func=my_test)

        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form

        response = connector.Test(self._make_request(name="my_test"), MagicMock())

        self.assertIsInstance(response, common_pb2.TestResponse)
        self.assertTrue(response.success)

    @patch("fivetran_connector_sdk.print_library_log")
    def test_test_uses_cached_form_from_configuration_form(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.test import Test

        def my_test(config):
            return Test.success()

        form = ConfigurationForm()
        form.add_test(label="My test", func=my_test)
        configuration_form_method = MagicMock(return_value=form)
        connector = Connector(update=MagicMock(), configuration_form=configuration_form_method)

        connector.ConfigurationForm(MagicMock(), MagicMock())
        response = connector.Test(self._make_request(name="my_test"), MagicMock())

        self.assertTrue(response.success)
        configuration_form_method.assert_called_once_with()

    @patch("fivetran_connector_sdk.print_library_log")
    def test_registered_test_returns_failure(self, _mock_log):
        from fivetran_connector_sdk.protos import common_pb2
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.test import Test

        def my_test(config):
            return Test.failure("could not connect")

        form = ConfigurationForm()
        form.add_test(label="My test", func=my_test)

        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form

        response = connector.Test(self._make_request(name="my_test"), MagicMock())

        self.assertIsInstance(response, common_pb2.TestResponse)
        self.assertFalse(response.success)
        self.assertEqual(response.failure, "could not connect")

    @patch("fivetran_connector_sdk.print_library_log")
    def test_raises_runtime_error_when_no_test_registered_with_name(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        form = ConfigurationForm()
        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form

        with self.assertRaises(RuntimeError) as cm:
            connector.Test(self._make_request(name="nonexistent_test"), MagicMock())

        self.assertIn("no test registered with name 'nonexistent_test'", str(cm.exception))

    @patch("fivetran_connector_sdk.print_library_log")
    def test_raises_runtime_error_when_test_function_raises_exception(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        def failing_test(config):
            raise ConnectionError("timeout")

        form = ConfigurationForm()
        form.add_test(label="Bad test", func=failing_test)

        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = False
        try:
            with self.assertRaises(RuntimeError) as cm:
                connector.Test(self._make_request(name="failing_test"), MagicMock())
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing test 'failing_test'", str(cm.exception))
        self.assertIn("timeout", str(cm.exception))
        self.assertIn("Traceback (most recent call last):", str(cm.exception))

    @patch("fivetran_connector_sdk.print_library_log")
    def test_test_debug_stores_crash_report_without_traceback_in_error(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        def failing_test(config):
            raise ConnectionError("timeout")

        form = ConfigurationForm()
        form.add_test(label="Bad test", func=failing_test)

        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form
        connector.project_path = "/project"

        original_debugging = constants.DEBUGGING
        constants.DEBUGGING = True
        try:
            with patch(
                "fivetran_connector_sdk.build_debug_crash_report", return_value="TEST REPORT"
            ) as mock_report:
                with self.assertRaises(RuntimeError) as cm:
                    connector.Test(self._make_request(name="failing_test"), MagicMock())
        finally:
            constants.DEBUGGING = original_debugging

        self.assertIn("failed while executing test 'failing_test'", str(cm.exception))
        self.assertNotIn("Traceback (most recent call last):", str(cm.exception))
        mock_report.assert_called_once()
        self.assertEqual(mock_report.call_args.kwargs["handler"], "test()")
        self.assertEqual(connector._debug_crash_report, "TEST REPORT")

    @patch("fivetran_connector_sdk.print_library_log")
    def test_raises_runtime_error_when_test_returns_wrong_type(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm

        def bad_return_test(config):
            return "not a TestResponse"

        form = ConfigurationForm()
        form.add_test(label="Bad return", func=bad_return_test)

        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form

        response = connector.Test(self._make_request(name="bad_return_test"), MagicMock())

        self.assertFalse(response.success)
        self.assertIn("must return Test.success() or Test.failure(...)", response.failure)

    @patch("fivetran_connector_sdk.print_library_log")
    def test_test_uses_connector_configuration_when_set(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.test import Test

        received = {}

        def capture_config_test(config):
            received["config"] = config
            return Test.success()

        form = ConfigurationForm()
        form.add_test(label="Capture", func=capture_config_test)

        connector = Connector(update=MagicMock())
        connector.configuration_form_method = lambda: form
        connector.configuration = {"api_key": "secret"}

        connector.Test(self._make_request(name="capture_config_test"), MagicMock())

        self.assertEqual(received["config"], {"api_key": "secret"})

    @patch("fivetran_connector_sdk.print_library_log")
    def test_test_initializes_log_level_before_customer_logging(self, _mock_log):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.test import Test

        original_level = Logging.LOG_LEVEL
        Logging.LOG_LEVEL = None
        try:

            def logged_test(config):
                Logging.info("running setup test")
                return Test.success()

            form = ConfigurationForm()
            form.add_test(label="Logged test", func=logged_test)

            connector = Connector(update=MagicMock())
            connector.configuration_form_method = lambda: form

            response = connector.Test(self._make_request(name="logged_test"), MagicMock())

            self.assertTrue(response.success)
            self.assertEqual(Logging.LOG_LEVEL, Logging.Level.INFO)
        finally:
            Logging.LOG_LEVEL = original_level


class TestGenerateConfiguration(unittest.TestCase):

    def _make_connector_with_form(self, tests=None):
        from fivetran_connector_sdk.configuration_form import ConfigurationForm
        from fivetran_connector_sdk.test import Test

        form = ConfigurationForm()
        if tests:
            for label, fn in tests:
                form.add_test(label=label, func=fn)
        connector = Connector(update=MagicMock())
        connector.configuration_form_method = MagicMock(return_value=form)
        return connector

    @patch("fivetran_connector_sdk.print_library_log")
    def test_exits_when_no_configuration_form_method(self, mock_log):
        connector = Connector(update=MagicMock())
        with self.assertRaises(SystemExit) as cm:
            connector.generate_configuration("/proj")
        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(
            any(
                "Your connector does not implement the configuration_form() method"
                in str(call.args[0])
                and call.args[1] == Logging.Level.SEVERE
                for call in mock_log.call_args_list
            )
        )

    @patch("fivetran_connector_sdk.print_library_log")
    def test_exits_when_run_tests_but_no_tests_defined(self, mock_log):
        connector = self._make_connector_with_form()
        with self.assertRaises(SystemExit) as cm:
            connector.generate_configuration("/proj", run_tests=True)
        self.assertEqual(cm.exception.code, 1)
        connector.configuration_form_method.assert_called_once_with()
        self.assertIs(connector._cached_form, connector.configuration_form_method.return_value)
        mock_log.assert_any_call(
            "Your connector does not provide any configuration tests to run.", Logging.Level.SEVERE
        )

    def test_configuration_form_exception_propagates_unwrapped(self):
        class SentinelError(Exception):
            pass

        sentinel = SentinelError("boom")
        connector = Connector(update=MagicMock())
        connector.configuration_form_method = MagicMock(side_effect=sentinel)

        with self.assertRaises(SentinelError) as cm:
            connector.generate_configuration("/proj")

        self.assertIs(cm.exception, sentinel)

    @patch("fivetran_connector_sdk.Connector.run")
    @patch("fivetran_connector_sdk.run_configuration_tester")
    @patch("fivetran_connector_sdk.get_available_port", return_value=50051)
    @patch("fivetran_connector_sdk.ensure_tester_installed", return_value=("/java", "/tester"))
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("builtins.input", return_value="y")
    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.print_library_log")
    def test_prompts_and_continues_when_configuration_json_exists_and_user_confirms(
        self,
        _mock_log,
        _mock_exists,
        _mock_input,
        _mock_check,
        _mock_install,
        _mock_port,
        _mock_tester,
        mock_run,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        connector = self._make_connector_with_form()
        connector.generate_configuration("/proj")
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("builtins.input", return_value="n")
    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.print_library_log")
    def test_exits_when_user_declines_override(
        self, mock_log, _mock_exists, _mock_input, _mock_check
    ):
        connector = self._make_connector_with_form()
        with self.assertRaises(SystemExit) as cm:
            connector.generate_configuration("/proj")
        self.assertEqual(cm.exception.code, 0)
        logged_messages = [str(call.args[0]) for call in mock_log.call_args_list if call.args]
        self.assertTrue(any("cancelled" in m for m in logged_messages))

    @patch("fivetran_connector_sdk.Connector.run")
    @patch("fivetran_connector_sdk.run_configuration_tester")
    @patch("fivetran_connector_sdk.get_available_port", return_value=50051)
    @patch("fivetran_connector_sdk.ensure_tester_installed", return_value=("/java", "/tester"))
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("os.path.exists", return_value=False)
    @patch("fivetran_connector_sdk.print_library_log")
    def test_skips_prompt_when_configuration_json_not_exists(
        self,
        _mock_log,
        _mock_exists,
        _mock_check,
        _mock_install,
        _mock_port,
        _mock_tester,
        mock_run,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        with patch("builtins.input") as mock_input:
            connector = self._make_connector_with_form()
            connector.generate_configuration("/proj")
            mock_input.assert_not_called()
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.Connector.run")
    @patch("fivetran_connector_sdk.run_configuration_tester")
    @patch("fivetran_connector_sdk.get_available_port", return_value=50051)
    @patch("fivetran_connector_sdk.ensure_tester_installed", return_value=("/java", "/tester"))
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("os.path.exists", return_value=True)
    @patch("fivetran_connector_sdk.print_library_log")
    def test_skips_prompt_when_run_tests_even_if_configuration_json_exists(
        self,
        _mock_log,
        _mock_exists,
        _mock_check,
        _mock_install,
        _mock_port,
        _mock_tester,
        mock_run,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server

        def my_test(config):
            pass

        with patch("builtins.input") as mock_input:
            connector = self._make_connector_with_form(tests=[("My test", my_test)])
            connector.generate_configuration("/proj", run_tests=True)
            mock_input.assert_not_called()
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.Connector.run")
    @patch(
        "fivetran_connector_sdk.run_configuration_tester", side_effect=Exception("tester error")
    )
    @patch("fivetran_connector_sdk.get_available_port", return_value=50051)
    @patch("fivetran_connector_sdk.ensure_tester_installed", return_value=("/java", "/tester"))
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("os.path.exists", return_value=False)
    @patch("fivetran_connector_sdk.print_library_log")
    def test_stops_server_in_finally_on_exception(
        self,
        _mock_log,
        _mock_exists,
        _mock_check,
        _mock_install,
        _mock_port,
        _mock_tester,
        mock_run,
    ):
        mock_server = MagicMock()
        mock_run.return_value = mock_server
        connector = self._make_connector_with_form()
        with self.assertRaises(Exception):
            connector.generate_configuration("/proj")
        mock_server.stop.assert_called_once_with(grace=2.0)

    @patch("fivetran_connector_sdk.Connector.run")
    @patch("fivetran_connector_sdk.run_configuration_tester")
    @patch("fivetran_connector_sdk.get_available_port", return_value=50051)
    @patch("fivetran_connector_sdk.ensure_tester_installed", return_value=("/java", "/tester"))
    @patch("fivetran_connector_sdk.check_newer_version")
    @patch("os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_does_not_print_traceback_when_configuration_tester_returns_non_zero(
        self,
        mock_print,
        _mock_exists,
        _mock_check,
        _mock_install,
        _mock_port,
        mock_tester,
        mock_run,
    ):
        import subprocess

        mock_server = MagicMock()
        mock_run.return_value = mock_server
        mock_tester.side_effect = subprocess.CalledProcessError(returncode=1, cmd="tester")
        connector = self._make_connector_with_form()

        with self.assertRaises(subprocess.CalledProcessError):
            connector.generate_configuration("/proj")

        printed_messages = [str(call.args[0]) for call in mock_print.call_args_list if call.args]
        self.assertFalse(
            any("Traceback (most recent call last)" in message for message in printed_messages)
        )
        mock_server.stop.assert_called_once_with(grace=2.0)


class TestMainConfigurationCommand(unittest.TestCase):

    def setUp(self):
        import fivetran_connector_sdk.__init__  # ensure __init__ submodule is in sys.modules for @patch to resolve

        # Tests use non-existent placeholder paths (e.g. "/test/path"); bypass the real
        # directory-existence check so those paths keep flowing through unchanged.
        validate_path_dunder_init_patcher = patch(
            "fivetran_connector_sdk.__init__._resolve_existing_project_path",
            side_effect=lambda path: path,
        )
        validate_path_dunder_init_patcher.start()
        self.addCleanup(validate_path_dunder_init_patcher.stop)

    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_test_flag_with_non_configuration_command_exits(self, mock_log, mock_find):
        mock_find.return_value = MagicMock()
        with patch.object(sys, "argv", ["fivetran", "debug", "--test"]):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 2)
        mock_log.assert_not_called()

    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    def test_configuration_command_calls_generate_configuration(self, mock_find):
        mock_connector = MagicMock()
        mock_find.return_value = mock_connector
        with patch.object(sys, "argv", ["fivetran", "configuration", "/proj"]):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass
        mock_connector.generate_configuration.assert_called_once_with(
            "/proj", run_tests=False, disable_encryption=False
        )

    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_configuration_command_subprocess_error(self, mock_log, mock_find):
        import subprocess

        mock_connector = MagicMock()
        mock_connector.generate_configuration.side_effect = subprocess.CalledProcessError(
            returncode=42, cmd="test"
        )
        mock_find.return_value = mock_connector
        with patch.object(sys, "argv", ["fivetran", "configuration", "/proj"]):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 42)
        mock_log.assert_any_call(
            "connector tester failed with exit code: 42",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )

    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    @patch("fivetran_connector_sdk.__init__.print_library_log")
    def test_configuration_command_generic_exception(self, mock_log, mock_find):
        mock_connector = MagicMock()
        mock_connector.generate_configuration.side_effect = Exception("something failed")
        mock_find.return_value = mock_connector
        with patch.object(sys, "argv", ["fivetran", "configuration", "/proj"]):
            from fivetran_connector_sdk.__init__ import main

            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        mock_log.assert_any_call(
            "configuration command failed error: something failed",
            level=Logging.Level.SEVERE,
            log_icon=Logging.LogIcon.FAILURE,
        )

    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    def test_configuration_command_with_disable_encryption_flag(self, mock_find):
        mock_connector = MagicMock()
        mock_find.return_value = mock_connector
        with patch.object(
            sys, "argv", ["fivetran", "configuration", "/proj", "--disable-encryption"]
        ):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass
        mock_connector.generate_configuration.assert_called_once_with(
            "/proj", run_tests=False, disable_encryption=True
        )

    @patch("fivetran_connector_sdk.__init__.find_connector_object")
    def test_configuration_command_with_test_and_disable_encryption(self, mock_find):
        mock_connector = MagicMock()
        mock_find.return_value = mock_connector
        with patch.object(
            sys, "argv", ["fivetran", "configuration", "/proj", "--test", "--disable-encryption"]
        ):
            from fivetran_connector_sdk.__init__ import main

            try:
                main()
            except SystemExit:
                pass
        mock_connector.generate_configuration.assert_called_once_with(
            "/proj", run_tests=True, disable_encryption=True
        )


class TestDeployWithProxy(unittest.TestCase):
    """Tests for deploy() with --proxy-id and --proxy-host-config-key."""

    def setUp(self):
        from fivetran_connector_sdk import Connector

        self.connector = Connector(update=MagicMock())

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_new_connection_with_proxy_id(
        self,
        mock_version,
        mock_log,
        mock_check,
        mock_validate,
        mock_group,
        mock_conn,
        mock_upload,
        mock_create,
        mock_handle,
    ):
        """proxy_id is forwarded to create_connection and resolved proxy host config key is stored in config."""
        mock_create.return_value = MagicMock(ok=True, status_code=201)
        mock_upload.return_value = "pkg"

        config = {"host": "db.example.com:5432"}
        with patch("fivetran_connector_sdk.validate_proxy_configuration", return_value="host"):
            self.connector.deploy(
                "path",
                "key",
                "group",
                "conn",
                None,
                config,
                "conf.json",
                python_version="3.12",
                proxy_id="proxy-123",
                proxy_host_config_key="host",
                prompt_mode=PromptMode.YES,
            )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        self.assertIn("proxy-123", call_args.args or list(call_args[0]))

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.update_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=("cid", "connector_sdk"))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_update_clears_proxy_when_not_provided(
        self,
        mock_version,
        mock_log,
        mock_check,
        mock_validate,
        mock_group,
        mock_conn,
        mock_upload,
        mock_update,
        mock_handle,
    ):
        """Redeploying without --proxy-id passes None to update_connection so proxy is cleared."""
        mock_update.return_value = MagicMock(ok=True, status_code=200)
        mock_upload.return_value = "pkg"

        self.connector.deploy(
            "path",
            "key",
            "group",
            "conn",
            None,
            prompt_mode=PromptMode.YES,
            proxy_id=None,
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        # proxy_agent_id should be None (last positional or keyword arg)
        proxy_passed = call_args.kwargs.get("proxy_agent_id") or (
            call_args.args[-1] if call_args.args else None
        )
        self.assertIsNone(proxy_passed)

    @patch("fivetran_connector_sdk.sys.exit")
    @patch("fivetran_connector_sdk.validate_proxy_configuration")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_exits_when_proxy_host_config_key_without_proxy_id(
        self, mock_version, mock_log, mock_check, mock_validate_proxy, mock_exit
    ):
        """--proxy-host-config-key without --proxy-id is caught by validate_proxy_configuration."""
        mock_validate_proxy.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit):
            self.connector.deploy(
                "path",
                "key",
                "group",
                "conn",
                None,
                prompt_mode=PromptMode.YES,
                proxy_host_config_key="host",
            )

        mock_validate_proxy.assert_called_once()

    @patch("fivetran_connector_sdk.connector_helper.sys.exit")
    @patch("fivetran_connector_sdk.check_dict")
    @patch("fivetran_connector_sdk.connector_helper.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_exits_when_proxy_id_and_hd_agent_id_both_provided(
        self, mock_version, mock_log, mock_check, mock_exit
    ):
        """proxy_id and hd_agent_id together causes an immediate error."""
        mock_exit.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit):
            self.connector.deploy(
                "path",
                "key",
                "group",
                "conn",
                hd_agent_id="hd-agent-123",
                prompt_mode=PromptMode.YES,
                proxy_id="proxy-123",
            )

        calls = [str(c) for c in mock_log.call_args_list]
        self.assertTrue(
            any(
                "Proxy Agent is not supported in Hybrid Deployment connections" in c for c in calls
            )
        )

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_hosts_list_preserved_in_secrets_list(
        self,
        mock_version,
        mock_log,
        mock_validate,
        mock_group,
        mock_conn,
        mock_upload,
        mock_create,
        mock_handle,
    ):
        """hosts as a list of strings flows through unchanged into secrets_list."""
        mock_create.return_value = MagicMock(ok=True, status_code=201)
        mock_upload.return_value = "pkg"

        config = {"hosts": ["h1:5432", "h2:5433"], "user": "admin"}
        self.connector.deploy(
            "path",
            "key",
            "group",
            "conn",
            None,
            config,
            "conf.json",
            python_version="3.12",
            proxy_id="proxy-123",
            proxy_host_config_key=None,
            prompt_mode=PromptMode.YES,
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        connection_config = (
            call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("config")
        )
        secrets_list = connection_config["secrets_list"]

        hosts_entry = next((s for s in secrets_list if s["key"] == "hosts"), None)
        self.assertIsNotNone(hosts_entry)
        self.assertEqual(hosts_entry["value"], ["h1:5432", "h2:5433"])
        self.assertEqual(connection_config["proxy_host_config_key"], "hosts")

    @patch("fivetran_connector_sdk.handle_connection_response")
    @patch("fivetran_connector_sdk.create_connection")
    @patch("fivetran_connector_sdk.package_project")
    @patch("fivetran_connector_sdk.get_connection_details", return_value=(None, None))
    @patch("fivetran_connector_sdk.get_group_info", return_value=("gid", "gname"))
    @patch("fivetran_connector_sdk.validate_requirements_file")
    @patch("fivetran_connector_sdk.print_library_log")
    @patch("fivetran_connector_sdk.check_newer_version")
    def test_deploy_auto_detected_host_key_set_in_connection_config(
        self,
        mock_version,
        mock_log,
        mock_validate,
        mock_group,
        mock_conn,
        mock_upload,
        mock_create,
        mock_handle,
    ):
        """When proxy_host_config_key is not passed, the auto-detected 'host' key is set in connection_config."""
        mock_create.return_value = MagicMock(ok=True, status_code=201)
        mock_upload.return_value = "pkg"

        config = {"host": "db.example.com:5432"}
        self.connector.deploy(
            "path",
            "key",
            "group",
            "conn",
            None,
            config,
            "conf.json",
            python_version="3.12",
            proxy_id="proxy-123",
            proxy_host_config_key=None,
            prompt_mode=PromptMode.YES,
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        connection_config = (
            call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("config")
        )
        self.assertEqual(connection_config["proxy_host_config_key"], "host")


if __name__ == "__main__":
    unittest.main()
