import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class TestFivetranShim(unittest.TestCase):

    def _load_shim(self):
        shim_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "fivetran_connector_sdk"
            / "fivetran_shim.py"
        )
        spec = importlib.util.spec_from_file_location("fivetran_shim_under_test", shim_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_direct_cli(self):
        cli_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "fivetran_connector_sdk"
            / "cli.py"
        )
        spec = importlib.util.spec_from_file_location("fivetran_sdk_cli_under_test", cli_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_delegates_to_unified_cli_when_available(self):
        shim = self._load_shim()
        package = types.ModuleType("fivetran_cli")
        package.__path__ = []
        cli = types.ModuleType("fivetran_cli.cli")

        def unified_main():
            return 42

        cli.main = unified_main

        with patch.dict(sys.modules, {"fivetran_cli": package, "fivetran_cli.cli": cli}):
            self.assertEqual(shim.main(), 42)

    def test_falls_back_to_sdk_cli_when_unified_cli_is_not_available(self):
        shim = self._load_shim()
        sdk_package = types.ModuleType("fivetran_connector_sdk")
        sdk_package.__path__ = []
        sdk_cli = types.ModuleType("fivetran_connector_sdk.cli")

        def sdk_main():
            return 7

        sdk_cli.main = sdk_main

        with patch.dict(
            sys.modules,
            {"fivetran_connector_sdk": sdk_package, "fivetran_connector_sdk.cli": sdk_cli},
        ):
            self.assertEqual(shim.main(), 7)

    def test_direct_cli_sets_argv_and_restores_it(self):
        direct_cli = self._load_direct_cli()
        original_argv = sys.argv
        sdk_package = types.ModuleType("fivetran_connector_sdk")

        def sdk_main():
            self.assertEqual(sys.argv, [original_argv[0], "deploy", "connector"])
            return 11

        sdk_package.main = sdk_main

        with patch.dict(sys.modules, {"fivetran_connector_sdk": sdk_package}):
            self.assertEqual(direct_cli.main(["deploy", "connector"]), 11)

        self.assertEqual(sys.argv, original_argv)


    def test_reraises_when_fivetran_cli_is_installed_but_cli_module_is_missing(self):
        shim = self._load_shim()
        package = types.ModuleType("fivetran_cli")
        package.__path__ = []  # empty path: submodule lookup will fail with name="fivetran_cli.cli"

        with patch.dict(sys.modules, {"fivetran_cli": package}):
            with self.assertRaises(ModuleNotFoundError):
                shim.main()

    def test_direct_cli_uses_sys_argv_unchanged_when_no_argv_given(self):
        direct_cli = self._load_direct_cli()
        expected_argv = list(sys.argv)
        sdk_package = types.ModuleType("fivetran_connector_sdk")

        def sdk_main():
            self.assertEqual(sys.argv, expected_argv)
            return 99

        sdk_package.main = sdk_main

        with patch.dict(sys.modules, {"fivetran_connector_sdk": sdk_package}):
            self.assertEqual(direct_cli.main(), 99)

        self.assertEqual(sys.argv, expected_argv)

    def test_direct_cli_restores_argv_after_in_place_mutation(self):
        direct_cli = self._load_direct_cli()
        expected_argv = list(sys.argv)
        sdk_package = types.ModuleType("fivetran_connector_sdk")

        def sdk_main():
            sys.argv.clear()
            return 5

        sdk_package.main = sdk_main

        with patch.dict(sys.modules, {"fivetran_connector_sdk": sdk_package}):
            direct_cli.main()  # argv=None: uses sys.argv directly

        self.assertEqual(sys.argv, expected_argv)


if __name__ == "__main__":
    unittest.main()
