import unittest
from unittest.mock import patch


class TestMemoryMonitor(unittest.TestCase):
    """Tests for DebugMemoryTracker and SyncMemoryTracker."""

    def setUp(self):
        from fivetran_connector_sdk import constants

        self._saved_debugging = constants.DEBUGGING
        self._saved_executed_via_cli = constants.EXECUTED_VIA_CLI
        constants.DEBUGGING = False
        constants.EXECUTED_VIA_CLI = False

    def tearDown(self):
        from fivetran_connector_sdk import constants

        constants.DEBUGGING = self._saved_debugging
        constants.EXECUTED_VIA_CLI = self._saved_executed_via_cli

    @patch("builtins.print")
    def test_debug_tracker_creates_daemon_thread(self, mock_print):
        from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker

        tracker = DebugMemoryTracker()
        tracker.start()

        self.assertTrue(tracker.monitor_thread.daemon, "debug tracker thread must be daemon")
        tracker.active = False  # Stop the thread

    @patch.dict("os.environ", {"CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC": "true"})
    @patch("builtins.print")
    def test_sync_tracker_creates_non_daemon_thread(self, mock_print):
        from fivetran_connector_sdk.memory_tracker import SyncMemoryTracker

        tracker = SyncMemoryTracker()
        tracker.start()

        self.assertFalse(tracker.monitor_thread.daemon, "sync tracker thread must not be daemon")
        tracker.stop()

    @patch("fivetran_connector_sdk.memory_tracker.atexit.register")
    @patch("builtins.print")
    def test_debug_tracker_registers_atexit_handler(self, mock_print, mock_atexit_register):
        from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker

        tracker = DebugMemoryTracker()
        tracker.start()

        mock_atexit_register.assert_called_once()
        tracker.active = False

    @patch.dict("os.environ", {"CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC": "true"})
    @patch("fivetran_connector_sdk.memory_tracker.atexit.register")
    @patch("builtins.print")
    def test_sync_tracker_does_not_register_atexit(self, mock_print, mock_atexit_register):
        from fivetran_connector_sdk.memory_tracker import SyncMemoryTracker

        tracker = SyncMemoryTracker()
        tracker.start()

        mock_atexit_register.assert_not_called()
        tracker.stop()

    @patch("fivetran_connector_sdk.memory_tracker.time.sleep", side_effect=InterruptedError)
    @patch("fivetran_connector_sdk.memory_tracker.os._exit")
    @patch("fivetran_connector_sdk.memory_tracker.get_debug_memory_bytes")
    @patch("builtins.print")
    def test_debug_tracker_exits_when_limit_exceeded(
        self, mock_print, mock_get_mem, mock_exit, mock_sleep
    ):
        from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker
        from fivetran_connector_sdk import constants

        # Return memory above limit
        mock_get_mem.return_value = constants.MEMORY_LIMIT_BYTES + 1

        tracker = DebugMemoryTracker()
        tracker.baseline_bytes = 1000  # Set baseline manually
        tracker.active = True  # Set active manually

        with self.assertRaises(InterruptedError):
            tracker._monitor_loop()

        mock_exit.assert_called_once_with(1)

    @patch("fivetran_connector_sdk.memory_tracker.time.sleep", side_effect=InterruptedError)
    @patch("fivetran_connector_sdk.memory_tracker.os._exit")
    @patch("fivetran_connector_sdk.memory_tracker.get_debug_memory_bytes")
    @patch("builtins.print")
    def test_debug_tracker_does_not_exit_within_limit(
        self, mock_print, mock_get_mem, mock_exit, mock_sleep
    ):
        from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker
        from fivetran_connector_sdk import constants

        # Return memory below limit
        mock_get_mem.return_value = constants.MEMORY_LIMIT_BYTES - 1

        tracker = DebugMemoryTracker()
        tracker.baseline_bytes = 1000  # Set baseline manually
        tracker.active = True  # Set active manually

        with self.assertRaises(InterruptedError):
            tracker._monitor_loop()

        mock_exit.assert_not_called()

    @patch("fivetran_connector_sdk.memory_tracker.get_debug_memory_bytes", return_value=-1)
    @patch("builtins.print")
    def test_debug_tracker_handles_read_failure(self, mock_print, mock_get_mem):
        from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker

        tracker = DebugMemoryTracker()
        tracker.start()

        # Should not start monitoring if memory reading fails
        self.assertIsNone(tracker.monitor_thread)

    @patch.dict("os.environ", {"CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC": "true"})
    @patch("builtins.print")
    def test_tracker_calculates_peak_and_average(self, mock_print):
        from fivetran_connector_sdk.memory_tracker import SyncMemoryTracker

        tracker = SyncMemoryTracker()
        tracker.baseline_bytes = 1000
        tracker.peak_delta_bytes = 5000
        tracker.total_delta_bytes = 12000
        tracker.sample_count = 4

        tracker._log_results()

        # Should log peak and average
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("average", printed)
        self.assertIn("peak", printed)

    @patch.dict("os.environ", {"CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC": "false"})
    @patch("builtins.print")
    def test_sync_tracker_disabled_when_ff_false(self, mock_print):
        from fivetran_connector_sdk.memory_tracker import SyncMemoryTracker

        tracker = SyncMemoryTracker()
        tracker.start()

        # Should not create monitor thread when FF is disabled
        self.assertIsNone(tracker.monitor_thread)
        self.assertFalse(tracker.active)

        # stop() should be safe to call
        tracker.stop()

    @patch.dict("os.environ", {})  # FF not set (defaults to false)
    @patch("builtins.print")
    def test_sync_tracker_disabled_when_ff_not_set(self, mock_print):
        from fivetran_connector_sdk.memory_tracker import SyncMemoryTracker

        tracker = SyncMemoryTracker()
        tracker.start()

        # Should not create monitor thread when FF is not set
        self.assertIsNone(tracker.monitor_thread)
        self.assertFalse(tracker.active)

        # stop() should be safe to call
        tracker.stop()

    @patch.dict("os.environ", {"CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC": "true"})
    @patch(
        "fivetran_connector_sdk.memory_tracker._get_sync_memory_bytes",
        side_effect=Exception("Test failure"),
    )
    @patch("builtins.print")
    def test_sync_tracker_fails_open_on_startup_error(self, mock_print, mock_get_mem):
        from fivetran_connector_sdk.memory_tracker import SyncMemoryTracker

        tracker = SyncMemoryTracker()
        # Should not raise exception, should fail silently
        tracker.start()

        # Should not create monitor thread when startup fails
        self.assertIsNone(tracker.monitor_thread)
        self.assertFalse(tracker.active)

        # stop() should be safe to call
        tracker.stop()

    @patch(
        "fivetran_connector_sdk.memory_tracker.threading.Thread",
        side_effect=RuntimeError("can't start new thread"),
    )
    @patch("fivetran_connector_sdk.memory_tracker.get_debug_memory_bytes", return_value=1000)
    @patch("builtins.print")
    def test_debug_tracker_fails_open_on_thread_start_error(
        self, mock_print, mock_get_mem, mock_thread
    ):
        from fivetran_connector_sdk.memory_tracker import DebugMemoryTracker

        tracker = DebugMemoryTracker()
        # Should not raise exception, should fail silently and continue without enforcement
        tracker.start()

        self.assertIsNone(tracker.monitor_thread)
        self.assertFalse(tracker.active)


if __name__ == "__main__":
    unittest.main()
