import importlib.util
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from fivetran_connector_sdk.crash_report import _collect_resource_snapshot, build_debug_crash_report
from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker


def _tracker(baseline_bytes, peak_delta_bytes=0, total_delta_bytes=0, sample_count=0):
    tracker = DebugMemoryTracker()
    tracker.baseline_bytes = baseline_bytes
    tracker.peak_delta_bytes = peak_delta_bytes
    tracker.total_delta_bytes = total_delta_bytes
    tracker.sample_count = sample_count
    return tracker


class TestCrashReport(unittest.TestCase):

    def test_build_debug_crash_report_includes_only_project_frames(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "import json\n"
                    "\n"
                    "def update(configuration, state):\n"
                    "    parse_payload(configuration['payload'])\n"
                    "\n"
                    "def parse_payload(payload):\n"
                    "    return json.loads(payload)\n"
                )

            module = _load_module(connector_path)
            configuration = {"payload": "not-json", "token": "state-secret"}

            memory_tracker = _tracker(
                baseline_bytes=0, peak_delta_bytes=5 * 1024 * 1024, total_delta_bytes=5 * 1024 * 1024, sample_count=1
            )

            try:
                module.update(configuration, {})
            except Exception as exception:
                with patch(
                    "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
                    return_value=1 * 1024 * 1024,
                ):
                    report = build_debug_crash_report(
                        exception,
                        project_path,
                        configuration=configuration,
                        handler="update()",
                        sdk_version="test-sdk-version",
                        state={"cursor": "2024-01-01", "access_token": "state-secret"},
                        memory_tracker=memory_tracker,
                    )
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("Crash Report", report)
            self.assertIn("Crash metadata:", report)
            self.assertIn("Timestamp:", report)
            self.assertIn("Handler: update()", report)
            self.assertIn(f"Project path: {os.path.realpath(project_path)}", report)
            self.assertIn("Fivetran Connector SDK version: test-sdk-version", report)
            self.assertIn("Python version:", report)
            self.assertIn("Platform:", report)
            self.assertIn("Connector inputs:", report)
            self.assertNotIn("Configuration:", report)
            self.assertIn("State: {'cursor': '2024-01-01', 'access_token': '****'}", report)
            self.assertIn("Resource snapshot:", report)
            self.assertIn("Current memory usage: 1.00 MB", report)
            self.assertIn("Peak memory usage: 5.00 MB", report)
            self.assertIn("Average memory usage: 3.00 MB", report)
            self.assertIn("Debug memory limit: 4096.00 MB", report)
            self.assertLess(report.index("Connector inputs:"), report.index("Resource snapshot:"))
            self.assertLess(report.index("Resource snapshot:"), report.index("Error:"))
            self.assertLess(report.index("Error:"), report.index("JSONDecodeError"))
            self.assertIn("JSONDecodeError", report)
            self.assertIn(f'File "{connector_path}", line 4, in update', report)
            self.assertIn(f'File "{connector_path}", line 7, in parse_payload', report)
            self.assertIn("parse_payload(configuration['payload'])", report)
            self.assertIn("return json.loads(payload)", report)
            self.assertIn("configuration = keys['payload', 'token']", report)
            self.assertIn("payload = '****'", report)
            self.assertNotIn("secret-token", report)
            self.assertNotIn("api.example.com", report)
            self.assertNotIn("state-secret", report)
            self.assertNotIn("not-json", report)
            self.assertNotIn("json/decoder.py", report)
            self.assertNotIn("site-packages", report)

    def test_build_debug_crash_report_includes_bounded_locals(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "class BrokenRepr:\n"
                    "    def __repr__(self):\n"
                    "        raise RuntimeError('repr failed')\n"
                    "\n"
                    "def update(configuration, state):\n"
                    "    visible = 'shown'\n"
                    "    large_text = 'x' * 600\n"
                    "    numbers = list(range(10))\n"
                    "    broken = BrokenRepr()\n"
                    "    raise RuntimeError('boom')\n"
                )

            module = _load_module(connector_path)
            configuration = {"api_key": "secret-token", "host": "api.example.com"}

            try:
                module.update(configuration, {"cursor": 1})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path, configuration=configuration)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("  Locals:", report)
            self.assertIn("configuration = keys['api_key', 'host']", report)
            self.assertIn("state = {'cursor': 1}", report)
            self.assertIn("visible = 'shown'", report)
            self.assertIn("large_text = '", report)
            self.assertIn("...", report)
            self.assertNotIn("x" * 600, report)
            self.assertIn("numbers = [0, 1, 2, 3, 4, ...]", report)
            self.assertIn("broken = <unrepresentable BrokenRepr>", report)
            self.assertNotIn("secret-token", report)
            self.assertNotIn("api.example.com", report)

    def test_build_debug_crash_report_handles_broken_exception_str(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "class BrokenStr(Exception):\n"
                    "    def __str__(self):\n"
                    "        raise RuntimeError('str failed')\n"
                    "\n"
                    "def update(configuration, state):\n"
                    "    raise BrokenStr()\n"
                )

            module = _load_module(connector_path)

            try:
                module.update({}, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("BrokenStr: <exception str() failed>", report)
            self.assertIn(f'File "{connector_path}", line 6, in update', report)

    def test_build_debug_crash_report_formats_mapping_items_without_indexing(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "class MappingWithBrokenGetitem(dict):\n"
                    "    def __getitem__(self, key):\n"
                    "        raise RuntimeError('getitem failed')\n"
                    "\n"
                    "def update(configuration, state):\n"
                    "    details = MappingWithBrokenGetitem({\n"
                    "        'visible': 'shown',\n"
                    "        'api_key': 'secret-token',\n"
                    "        'numbers': list(range(10)),\n"
                    "        'headers': {'Authorization': 'Bearer secret-token'},\n"
                    "        'nested': {'password': 'nested-secret'},\n"
                    "        'extra': 'omitted',\n"
                    "    })\n"
                    "    raise RuntimeError('boom')\n"
                )

            module = _load_module(connector_path)
            configuration = {"api_key": "secret-token", "cert": "nested-secret"}

            try:
                module.update(configuration, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path, configuration=configuration)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("details = {", report)
            self.assertIn("'visible': 'shown'", report)
            self.assertIn("'api_key': '****'", report)
            self.assertIn("'numbers': [0, 1, 2, 3, 4, ...]", report)
            self.assertIn("'headers': {'Authorization': '****'}", report)
            self.assertIn("'nested': {'password': '****'}", report)
            self.assertIn("...", report)
            self.assertNotIn("secret-token", report)
            self.assertNotIn("nested-secret", report)
            self.assertNotIn("getitem failed", report)

    def test_build_debug_crash_report_redacts_secret_locals_dict_keys_and_token_values(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def update(configuration, state):\n"
                    "    api_key = configuration['api_key']\n"
                    "    clientSecret = configuration['client_secret']\n"
                    "    plain_value = 'Bearer ' + configuration['api_key']\n"
                    "    basic_value = 'Basic ' + configuration['basic_token']\n"
                    "    certificate = configuration['private_key_text']\n"
                    "    jwt_value = configuration['jwt']\n"
                    "    headers = {'Authorization': 'Bearer ' + api_key, 'Accept': 'application/json'}\n"
                    "    payload = {'client_secret': clientSecret, 'cursor': state['cursor']}\n"
                    "    value = configuration['api_key']\n"
                    "    raise RuntimeError('boom')\n"
                )

            module = _load_module(connector_path)
            configuration = {
                "api_key": "secret-token",
                "client_secret": "client-secret-value",
                "basic_token": "abcdefghijklmnop",
                "private_key_text": "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
                "jwt": "eyJabcdefgh.ijklmnopqr.stuvwxyz12",
            }

            try:
                module.update(configuration, {"cursor": "cursor-value"})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path, configuration=configuration)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("api_key = '****'", report)
            self.assertIn("clientSecret = '****'", report)
            self.assertIn("plain_value = '****'", report)
            self.assertIn("basic_value = '****'", report)
            self.assertIn("certificate = '****'", report)
            self.assertIn("jwt_value = '****'", report)
            self.assertIn("headers = {'Authorization': '****', 'Accept': 'application/json'}", report)
            self.assertIn("payload = {'client_secret': '****', 'cursor': 'cursor-value'}", report)
            # A local variable name the redaction heuristics do not recognize still gets
            # redacted, because the exact configuration value is scrubbed report-wide.
            self.assertIn("value = '****'", report)
            self.assertNotIn("secret-token", report)
            self.assertNotIn("client-secret-value", report)
            self.assertNotIn("Basic abcdefghijklmnop", report)
            self.assertNotIn("BEGIN PRIVATE KEY", report)
            self.assertNotIn("eyJabcdefgh.ijklmnopqr.stuvwxyz12", report)

    def test_build_debug_crash_report_redacts_secret_longer_than_repr_bound_before_truncation(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def update(configuration, state):\n"
                    "    value = configuration['api_key']\n"
                    "    raise RuntimeError('boom')\n"
                )

            module = _load_module(connector_path)
            secret = "s3cr3t-" + ("x" * 600)
            configuration = {"api_key": secret}

            try:
                module.update(configuration, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path, configuration=configuration)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("value = '****'", report)
            self.assertNotIn(secret[:100], report)
            self.assertNotIn(secret[-100:], report)

    def test_build_debug_crash_report_includes_direct_exception_cause(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def load_record():\n"
                    "    raw = 'not-json'\n"
                    "    raise ValueError('invalid payload')\n"
                    "\n"
                    "def update(configuration, state):\n"
                    "    try:\n"
                    "        load_record()\n"
                    "    except ValueError as exc:\n"
                    "        raise RuntimeError('failed to load records') from exc\n"
                )

            module = _load_module(connector_path)

            try:
                module.update({}, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path)
            else:
                self.fail("Expected connector update to fail")

            self.assertLess(report.index("ValueError: invalid payload"), report.index("RuntimeError: failed to load records"))
            self.assertIn("The above exception was the direct cause of the following exception:", report)
            self.assertIn(f'File "{connector_path}", line 3, in load_record', report)
            self.assertIn(f'File "{connector_path}", line 7, in update', report)

    def test_build_debug_crash_report_includes_implicit_exception_context(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def parse_payload():\n"
                    "    raise ValueError('bad source payload')\n"
                    "\n"
                    "def update(configuration, state):\n"
                    "    try:\n"
                    "        parse_payload()\n"
                    "    except ValueError:\n"
                    "        raise RuntimeError('wrapped without cause')\n"
                )

            module = _load_module(connector_path)

            try:
                module.update({}, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path)
            else:
                self.fail("Expected connector update to fail")

            self.assertLess(report.index("ValueError: bad source payload"), report.index("RuntimeError: wrapped without cause"))
            self.assertIn("During handling of the above exception, another exception occurred:", report)
            self.assertIn(f'File "{connector_path}", line 2, in parse_payload', report)
            self.assertIn(f'File "{connector_path}", line 6, in update', report)

    def test_build_debug_crash_report_includes_no_customer_frames_message(self):
        with tempfile.TemporaryDirectory() as project_path:
            try:
                raise RuntimeError("boom outside project")
            except Exception as exception:
                report = build_debug_crash_report(
                    exception,
                    project_path,
                    handler="update()",
                )

        self.assertIn("Crash metadata:", report)
        self.assertIn("Handler: update()", report)
        self.assertIn("Connector inputs:", report)
        self.assertIn("Resource snapshot:", report)
        self.assertIn("RuntimeError: boom outside project", report)
        self.assertIn("No customer stack frames found.", report)

    def test_build_debug_crash_report_formats_simple_locals(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def update(configuration, state):\n"
                    "    text = 'shown'\n"
                    "    number = 42\n"
                    "    enabled = True\n"
                    "    empty = None\n"
                    "    values = [1, 2]\n"
                    "    coordinates = (3, 4)\n"
                    "    unique_values = {5}\n"
                    "    details = {'status': 'ok'}\n"
                    "    raise RuntimeError('boom')\n"
                )

            module = _load_module(connector_path)

            try:
                module.update({}, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("text = 'shown'", report)
            self.assertIn("number = 42", report)
            self.assertIn("enabled = True", report)
            self.assertIn("empty = None", report)
            self.assertIn("values = [1, 2]", report)
            self.assertIn("coordinates = (3, 4)", report)
            self.assertIn("unique_values = {5}", report)
            self.assertIn("details = {'status': 'ok'}", report)

    def test_build_debug_crash_report_omits_configuration_local_when_not_a_mapping(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def update(configuration, state):\n"
                    "    raise RuntimeError('boom')\n"
                )

            module = _load_module(connector_path)

            try:
                module.update(None, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("configuration = <NoneType omitted>", report)

    def test_build_debug_crash_report_enforces_source_and_locals_bounds(self):
        with tempfile.TemporaryDirectory() as project_path:
            connector_path = os.path.join(project_path, "connector.py")
            local_assignments = "".join(f"    local_{index:02d} = {index}\n" for index in range(21))
            long_comment = "x" * 300
            with open(connector_path, "w", encoding="utf-8") as connector_file:
                connector_file.write(
                    "def update(configuration, state):\n"
                    "    fail_with_many_locals()\n"
                    "\n"
                    "def fail_with_many_locals():\n"
                    f"{local_assignments}"
                    f"    raise RuntimeError('boom')  # {long_comment}\n"
                )

            module = _load_module(connector_path)

            try:
                module.update({}, {})
            except Exception as exception:
                report = build_debug_crash_report(exception, project_path)
            else:
                self.fail("Expected connector update to fail")

            self.assertIn("raise RuntimeError('boom')  # ", report)
            self.assertIn("... <truncated>", report)
            self.assertIn("local_00 = 0", report)
            self.assertIn("local_19 = 19", report)
            # local_20's source line still appears in the ±2 source-context window;
            # what must be bounded is the rendered Locals: list, not the source text.
            rendered_locals = report.rsplit("  Locals:", 1)[-1]
            self.assertNotIn("local_20 = 20", rendered_locals)
            self.assertIn("... 1 more local variable(s) omitted", report)

    def test_collect_resource_snapshot_folds_crash_time_reading_into_tracker_peak_and_average(self):
        # Tracker's own samples say peak/average growth was only 0.5 MB (e.g. sampler ticked
        # once before a fast late-breaking allocation). The live read at crash time (2 MB above
        # baseline) is bigger than that stale peak, and must be folded into the tracker's own
        # peak/average bookkeeping rather than just overriding "peak" with "current".
        memory_tracker = _tracker(
            baseline_bytes=1 * 1024 * 1024,
            peak_delta_bytes=int(0.5 * 1024 * 1024),
            total_delta_bytes=int(0.5 * 1024 * 1024),
            sample_count=1,
        )

        with patch(
            "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
            return_value=3 * 1024 * 1024,  # 2 MB above baseline
        ):
            snapshot = _collect_resource_snapshot(memory_tracker)

        self.assertEqual(snapshot["current_rss_bytes"], 2 * 1024 * 1024)
        self.assertEqual(snapshot["peak_rss_bytes"], 2 * 1024 * 1024)
        # average now includes the crash-time sample: (0.5 MB + 2 MB) / 2 samples = 1.25 MB
        self.assertAlmostEqual(snapshot["average_rss_bytes"], 1.25 * 1024 * 1024)

    def test_collect_resource_snapshot_falls_back_to_current_when_tracker_has_no_samples(self):
        # Live reading is at (or below) baseline, so the crash-time sample itself doesn't
        # register as growth (matches DebugMemoryTracker.record_sample's `delta_bytes > 0` gate).
        memory_tracker = _tracker(baseline_bytes=1 * 1024 * 1024)

        with patch(
            "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
            return_value=1 * 1024 * 1024,
        ):
            snapshot = _collect_resource_snapshot(memory_tracker)

        self.assertEqual(snapshot["current_rss_bytes"], 0)
        self.assertEqual(snapshot["peak_rss_bytes"], 0)
        self.assertIsNone(snapshot["average_rss_bytes"])

    def test_collect_resource_snapshot_clamps_negative_delta_instead_of_reporting_unavailable(self):
        # Live RSS dipped below baseline (e.g. GC freed memory since the tracker started).
        memory_tracker = _tracker(baseline_bytes=5 * 1024 * 1024, peak_delta_bytes=1024, total_delta_bytes=1024, sample_count=1)

        with patch(
            "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
            return_value=1 * 1024 * 1024,  # 4 MB below baseline
        ):
            snapshot = _collect_resource_snapshot(memory_tracker)

        self.assertEqual(snapshot["current_rss_bytes"], 0)
        self.assertIsNotNone(snapshot["peak_rss_bytes"])

    def test_collect_resource_snapshot_ignores_invalid_baseline(self):
        # baseline_bytes == -1 means DebugMemoryTracker.start() failed its initial read;
        # subtracting it would corrupt the delta instead of just leaving current unavailable.
        memory_tracker = _tracker(baseline_bytes=-1)

        with patch(
            "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
            return_value=5 * 1024 * 1024,
        ):
            snapshot = _collect_resource_snapshot(memory_tracker)

        self.assertEqual(snapshot["current_rss_bytes"], 5 * 1024 * 1024)

    def test_collect_resource_snapshot_returns_none_current_when_rss_unavailable(self):
        with patch(
            "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
            return_value=-1,
        ):
            snapshot = _collect_resource_snapshot(None)

        self.assertIsNone(snapshot["current_rss_bytes"])
        self.assertIsNone(snapshot["peak_rss_bytes"])

    def test_build_debug_crash_report_uses_memory_tracker_for_resource_snapshot(self):
        memory_tracker = _tracker(
            baseline_bytes=1 * 1024 * 1024,
            peak_delta_bytes=9 * 1024 * 1024,
            total_delta_bytes=15 * 1024 * 1024,
            sample_count=5,
        )

        with patch(
            "fivetran_connector_sdk.crash_report.get_debug_memory_bytes",
            return_value=1024 * 1024,
        ):
            report = build_debug_crash_report(
                RuntimeError("boom"),
                os.getcwd(),
                handler="update()",
                memory_tracker=memory_tracker,
            )

        self.assertIn("Current memory usage: 0.00 MB", report)
        self.assertIn("Peak memory usage: 9.00 MB", report)
        self.assertIn("Average memory usage: 3.00 MB", report)


def _load_module(connector_path):
    module_name = "crash_report_test_connector"
    spec = importlib.util.spec_from_file_location(module_name, connector_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
