import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from fivetran_connector_sdk.constants import VALID_COMMANDS
from fivetran_connector_sdk.plugin import PLUGIN, ConnectorSdkPlugin


class TestConnectorSdkPlugin(unittest.TestCase):

    def test_get_commands_matches_valid_commands(self):
        commands = PLUGIN.get_commands()
        self.assertEqual(set(commands.keys()), set(VALID_COMMANDS))

    def test_get_commands_have_non_empty_descriptions(self):
        commands = PLUGIN.get_commands()
        for name, description in commands.items():
            self.assertTrue(description, f"{name} has empty help text")

    def test_dispatch_calls_cli_main(self):
        plugin = ConnectorSdkPlugin()
        with patch("fivetran_connector_sdk.plugin._cli_main", return_value=0) as mock_main:
            result = plugin.dispatch(["version"])
        mock_main.assert_called_once_with(["version"])
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
