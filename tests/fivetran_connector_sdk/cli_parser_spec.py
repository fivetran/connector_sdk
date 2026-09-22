import sys
import unittest

from unittest.mock import patch
from contextlib import redirect_stderr
import io


class TestCliParser(unittest.TestCase):

    def test_create_argument_parser(self):
        """Test create_argument_parser creates parser with all commands"""
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        self.assertIsNotNone(parser)
        # Test that parser has expected subparsers
        with patch('sys.argv', ['fivetran', '--help']):
            try:
                parser.parse_args()
            except SystemExit:
                pass  # Expected for --help

    def _get_command_help_text(self, command):
        """Capture the help text emitted by `fivetran <command> -h`."""
        import io
        import contextlib
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args([command, "-h"])
            self.assertEqual(cm.exception.code, 0)
        return buf.getvalue()

    def test_deploy_help_is_context_sensitive(self):
        """`fivetran deploy -h` should advertise only deploy-relevant flags."""
        out = self._get_command_help_text("deploy")
        for expected in ("--api-key", "--destination", "--connection",
                         "--configuration", "--python-version",
                         "--hybrid-deployment-agent-id", "--non-interactive"):
            self.assertIn(expected, out, f"deploy help missing {expected}")
        # Flags belonging to other commands must not appear.
        self.assertNotIn("--template", out)
        # --state is deprecated on deploy - must remain hidden in help.
        self.assertNotIn("--state", out)

    def test_debug_help_is_context_sensitive(self):
        """`fivetran debug -h` should show only configuration and state."""
        out = self._get_command_help_text("debug")
        self.assertIn("--configuration", out)
        self.assertIn("--state", out)
        for unexpected in ("--api-key", "--destination", "--connection",
                           "--python-version", "--template",
                           "--hybrid-deployment-agent-id"):
            self.assertNotIn(unexpected, out,
                             f"debug help unexpectedly contains {unexpected}")

    def test_deploy_configuration_help_mentions_redeploy_behavior(self):
        """`fivetran deploy -h` should explain that existing configuration is preserved on redeploy."""
        out = " ".join(self._get_command_help_text("deploy").split())
        self.assertIn("On redeploy", out)
        self.assertIn("existing configuration is preserved if none is provided", out)

    def test_debug_configuration_help_is_unchanged(self):
        """`fivetran debug -h` should keep the plain --configuration description."""
        out = " ".join(self._get_command_help_text("debug").split())
        self.assertIn("Path to configuration JSON file", out)
        self.assertNotIn("On redeploy", out)

    def test_init_help_is_context_sensitive(self):
        out = self._get_command_help_text("init")
        self.assertIn("--template", out)
        self.assertIn("--non-interactive", out)
        for unexpected in ("--api-key", "--destination", "--connection",
                           "--configuration", "--state", "--python-version"):
            self.assertNotIn(unexpected, out,
                             f"init help unexpectedly contains {unexpected}")

    def test_package_help_is_context_sensitive(self):
        out = self._get_command_help_text("package")
        self.assertIn("--non-interactive", out)
        for unexpected in ("--api-key", "--destination", "--connection",
                           "--configuration", "--state", "--template",
                           "--python-version"):
            self.assertNotIn(unexpected, out,
                             f"package help unexpectedly contains {unexpected}")

    def test_reset_help_is_context_sensitive(self):
        out = self._get_command_help_text("reset")
        self.assertIn("--non-interactive", out)
        for unexpected in ("--api-key", "--destination", "--connection",
                           "--configuration", "--state", "--template",
                           "--python-version"):
            self.assertNotIn(unexpected, out,
                             f"reset help unexpectedly contains {unexpected}")

    def test_configuration_help_is_context_sensitive(self):
        out = self._get_command_help_text("configuration")
        self.assertIn("--test", out)
        self.assertIn("--disable-encryption", out)
        for unexpected in ("--api-key", "--destination", "--connection",
                           "--configuration", "--state", "--template",
                           "--python-version", "--hybrid-deployment-agent-id",
                           "--non-interactive"):
            self.assertNotIn(unexpected, out,
                             f"configuration help unexpectedly contains {unexpected}")

    def test_top_level_help_lists_subcommands(self):
        """`fivetran -h` must still list the public top-level commands."""
        import io
        import contextlib
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit):
                parser.parse_args(["-h"])
        out = buf.getvalue()
        for cmd in ("version", "init", "debug", "deploy", "package", "reset", "help"):
            self.assertIn(cmd, out, f"top-level help missing command '{cmd}'")

    def test_top_level_help_hides_configuration_command(self):
        """`configuration` is a hidden command and must not appear in `fivetran -h`."""
        import io
        import contextlib
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit):
                parser.parse_args(["-h"])
        out = buf.getvalue()
        self.assertNotIn("configuration", out)

    def test_configuration_command_still_works_when_hidden(self):
        """Hiding `configuration` from top-level help must not stop it from running."""
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        args = parser.parse_args(["configuration"])
        self.assertEqual(args.command, "configuration")

    def test_typo_command_routes_to_suggester(self):
        """`fivetran depoly` must still hit suggest_correct_command."""
        from fivetran_connector_sdk.cli_parser import intercept_unknown_command
        with patch("sys.argv", ["fivetran", "depoly"]):
            with patch("fivetran_connector_sdk.cli_parser.suggest_correct_command",
                       return_value=True) as mock_suggest:
                with self.assertRaises(SystemExit) as cm:
                    intercept_unknown_command()
                self.assertEqual(cm.exception.code, 1)
                mock_suggest.assert_called_once_with("depoly")

    def test_invalid_command_exits(self):
        """When suggester declines, a clean error is logged and exit code is 1."""
        from fivetran_connector_sdk.cli_parser import intercept_unknown_command
        with patch("sys.argv", ["fivetran", "totally-bogus-token"]):
            with patch("fivetran_connector_sdk.cli_parser.suggest_correct_command",
                       return_value=False):
                with patch("fivetran_connector_sdk.cli_parser.print_library_log") as mock_log:
                    with self.assertRaises(SystemExit) as cm:
                        intercept_unknown_command()
                    self.assertEqual(cm.exception.code, 1)
                    mock_log.assert_called_once()
                    self.assertIn("invalid command", mock_log.call_args[0][0])

    def test_uppercase_command_is_normalised(self):
        """`fivetran DEPLOY ...` must still parse (case-insensitive command)."""
        from fivetran_connector_sdk.cli_parser import (
            intercept_unknown_command, create_argument_parser,
        )
        argv = ["fivetran", "DEPLOY", "--api-key", "K",
                "--destination", "G", "--connection", "C"]
        with patch.object(sys, "argv", list(argv)):
            intercept_unknown_command()
            #  intercept_unknown_command rewrites sys.argv[1] in place.
            self.assertEqual(sys.argv[1], "deploy")
            args = create_argument_parser().parse_args(sys.argv[1:])
            self.assertEqual(args.command, "deploy")
            self.assertEqual(args.api_key, "K")

    def test_intercept_passes_through_known_command(self):
        """A valid command is left alone by the intercept."""
        from fivetran_connector_sdk.cli_parser import  intercept_unknown_command
        with patch.object(sys, "argv", ["fivetran", "deploy", "--api-key", "K"]):
            intercept_unknown_command()  # must not raise or sys.exit
            self.assertEqual(sys.argv[1], "deploy")
            
    def test_debug_proxy_id_without_value_reports_unsupported(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["debug", "--proxy-id"])

        self.assertEqual(cm.exception.code, 2)
        self.assertIn("Proxy Agent routing is not supported with `fivetran debug`.", buf.getvalue())
        self.assertIn("`--proxy-id` is only supported with `fivetran deploy`.", buf.getvalue())

    def test_debug_proxy_id_with_value_reports_unsupported(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["debug", "--proxy-id", "proxy-123"])

        self.assertEqual(cm.exception.code, 2)
        self.assertIn("Proxy Agent routing is not supported with `fivetran debug`.", buf.getvalue())
        self.assertIn("Please run `fivetran debug` from a machine that can reach the source directly.", buf.getvalue())

    def test_debug_proxy_host_config_key_reports_unsupported(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["debug", "--proxy-host-config-key", "host"])

        self.assertEqual(cm.exception.code, 2)
        self.assertIn("Proxy Agent routing is not supported with `fivetran debug`.", buf.getvalue())
        self.assertIn("`--proxy-host-config-key` is only supported with `fivetran deploy`.", buf.getvalue())

    def test_deploy_proxy_arguments_are_accepted(self):
        from fivetran_connector_sdk.cli_parser import create_argument_parser

        parser = create_argument_parser()
        args = parser.parse_args([
            "deploy",
            "--api-key", "key",
            "--destination", "group",
            "--connection", "conn",
            "--proxy-id", "proxy-123",
            "--proxy-host-config-key", "host",
        ])

        self.assertEqual(args.command, "deploy")
        self.assertEqual(args.proxy_id, "proxy-123")
        self.assertEqual(args.proxy_host_config_key, "host")

    def test_configuration_disable_encryption_flag_parses(self):
        """`fivetran configuration --disable-encryption` must parse the flag."""
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        args = parser.parse_args(["configuration", "--disable-encryption"])
        self.assertTrue(args.disable_encryption)

    def test_configuration_disable_encryption_flag_defaults_to_false(self):
        """`fivetran configuration` without --disable-encryption must default to False."""
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        args = parser.parse_args(["configuration"])
        self.assertFalse(args.disable_encryption)

    def test_configuration_with_test_and_disable_encryption(self):
        """`fivetran configuration --test --disable-encryption` must parse both flags."""
        from fivetran_connector_sdk.cli_parser import create_argument_parser
        parser = create_argument_parser()
        args = parser.parse_args(["configuration", "--test", "--disable-encryption"])
        self.assertTrue(args.test)
        self.assertTrue(args.disable_encryption)


if __name__ == "__main__":
    unittest.main()
