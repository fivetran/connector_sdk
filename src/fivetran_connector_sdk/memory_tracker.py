import os
import sys
import time
import atexit
import threading
import subprocess

from fivetran_connector_sdk import constants
from fivetran_connector_sdk.constants import CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC
from fivetran_connector_sdk.logger import Logging
from fivetran_connector_sdk.helpers import print_library_log


def get_debug_memory_bytes() -> int:
    """Get current process RSS for local debug monitoring.

    Used by DebugMemoryTracker to enforce local memory limits during development.
    Returns process RSS only, no cgroups (debug runs outside containers).
    Only tracks the current Python process and its threads, not child processes.

    Returns:
        int: RSS in bytes, or -1 if unavailable.
    """
    try:
        if sys.platform == "linux":
            # /proc/self/status provides accurate current RSS in KB
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024  # KB to bytes
        elif sys.platform == "darwin":
            # ru_maxrss on macOS returns peak RSS, not current — use ps instead
            result = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                capture_output=True,
                text=True,
            )
            rss_kb = result.stdout.strip()
            if rss_kb:
                return int(rss_kb) * 1024
        elif sys.platform == "win32":
            import ctypes
            import ctypes.wintypes
            
            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.wintypes.DWORD),
                    ("PageFaultCount", ctypes.wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            
            pmc = ProcessMemoryCounters()
            pmc.cb = ctypes.sizeof(pmc)
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                ctypes.wintypes.DWORD,
            ]
            result = psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb
            )
            if result:
                return pmc.WorkingSetSize
    except Exception:
        pass
    
    return -1


def _get_sync_memory_bytes() -> int:
    """Get current memory for production sync tracking.

    Used by SyncMemoryTracker to measure connector memory during syncs.
    Tries cgroups first (accurate in production containers), falls back to RSS.

    Returns:
        int: Active memory in bytes, or -1 if unavailable.
    """
    # Try cgroups first (production containers)
    try:
        # Try cgroups v2 first
        total_path = '/sys/fs/cgroup/memory.current'
        stat_path = '/sys/fs/cgroup/memory.stat'

        # Fallback to cgroups v1
        if not os.path.exists(total_path):
            total_path = '/sys/fs/cgroup/memory/memory.usage_in_bytes'
            stat_path = '/sys/fs/cgroup/memory/memory.stat'

        with open(total_path, 'r') as f:
            total_bytes = int(f.read().strip())

        inactive_file_bytes = 0
        with open(stat_path, 'r') as f:
            for line in f:
                if line.startswith('inactive_file '):
                    inactive_file_bytes = int(line.split()[1])
                    break

        return total_bytes - inactive_file_bytes
    except Exception:
        pass  # cgroups not available, try RSS

    # Fallback to process RSS (local dev)
    return get_debug_memory_bytes()  # Returns -1 if unavailable


def _log_memory_constraint_warning(memory_limit_bytes: int) -> None:
    print_library_log(
        f"could not enforce memory constraint of {memory_limit_bytes // (1024 ** 3)} GB; "
        "debug will continue without memory constraint",
        Logging.Level.WARNING
    )


class _MemoryTrackerBase:
    """Shared baseline/peak/average accounting for memory trackers."""

    def __init__(self, sample_interval: float):
        self.sample_interval = sample_interval
        self.baseline_bytes = 0
        self.peak_delta_bytes = 0
        self.total_delta_bytes = 0
        self.sample_count = 0
        self.active = False
        self.monitor_thread = None

    def record_sample(self, current_bytes: int) -> None:
        delta_bytes = current_bytes - self.baseline_bytes
        if delta_bytes > self.peak_delta_bytes:
            self.peak_delta_bytes = delta_bytes
        if delta_bytes > 0:
            self.total_delta_bytes += delta_bytes
            self.sample_count += 1

    def _log_results(self) -> None:
        """Log peak and average memory usage."""
        try:
            if self.sample_count == 0:
                return  # No samples collected
            peak_mb = self.peak_delta_bytes / 1024 / 1024
            average_mb = self.total_delta_bytes / self.sample_count / 1024 / 1024
            print_library_log(
                f"connector process memory usage: average {average_mb:.2f} MB, peak {peak_mb:.2f} MB",
                Logging.Level.INFO,
            )
        except Exception:
            pass  # Fail silently if logging fails


class DebugMemoryTracker(_MemoryTrackerBase):
    """Enforces a memory limit during local `fivetran debug` runs.

    Runs for the entire debug session (including any Update() calls) as a
    daemon thread, using RSS-only reads (no cgroups needed for local dev).
    Kills the process if the limit is exceeded, and logs peak + average
    usage via an atexit hook when the session ends.
    """

    def __init__(self, sample_interval=1.0):
        super().__init__(sample_interval)
        self.memory_limit_bytes = constants.MEMORY_LIMIT_BYTES
        self.atexit_registered = False

    def start(self):
        """Measure baseline and start background monitoring."""
        self.baseline_bytes = get_debug_memory_bytes()
        if self.baseline_bytes == -1:
            _log_memory_constraint_warning(self.memory_limit_bytes)
            return  # Don't start monitoring if we can't read memory

        print_library_log(
            f"enforcing a {self.memory_limit_bytes // (1024 ** 3)} GB memory limit for local testing. "
            "Connectors may be subject to memory limits in production as well",
            Logging.Level.INFO
        )

        try:
            self.active = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
        except Exception:
            _log_memory_constraint_warning(self.memory_limit_bytes)
            self.active = False
            self.monitor_thread = None
            return

        if not self.atexit_registered:
            try:
                atexit.register(self._log_results)
                self.atexit_registered = True
            except Exception:
                print_library_log(
                    "peak memory reporting could not be registered; memory limit is still enforced",
                    Logging.Level.WARNING
                )

    def _monitor_loop(self):
        """Background thread that samples memory at the configured interval."""
        logged_read_failure = False

        while self.active:
            try:
                current_bytes = get_debug_memory_bytes()
                if current_bytes == -1:
                    if not logged_read_failure:
                        _log_memory_constraint_warning(self.memory_limit_bytes)
                        logged_read_failure = True
                    time.sleep(self.sample_interval)
                    continue

                self.record_sample(current_bytes)

                if current_bytes > self.memory_limit_bytes:
                    used_gb = current_bytes / (1024 ** 3)
                    limit_gb = self.memory_limit_bytes / (1024 ** 3)
                    print_library_log(
                        f"memory usage of connector code exceeded the allowed limit "
                        f"(used: {used_gb:.2f} GB, limit: {limit_gb:.2f} GB)",
                        Logging.Level.SEVERE
                    )
                    print_library_log(
                        "refer to https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/connector-memory-management "
                        "for analysing and fixing memory usage",
                        Logging.Level.SEVERE
                    )
                    sys.stdout.flush()
                    sys.stderr.flush()
                    os._exit(1)

            except Exception:
                if not logged_read_failure:
                    _log_memory_constraint_warning(self.memory_limit_bytes)
                    logged_read_failure = True

            time.sleep(self.sample_interval)

    def stop(self, timeout=3.0):
        """Stop monitoring (no-op for debug mode).
        
        Debug mode logs at exit via atexit hook, not here.
        The daemon thread will exit when the main thread exits.
        """
        pass


class SyncMemoryTracker(_MemoryTrackerBase):
    """Monitors connector memory usage during a production sync's Update() call.

    Uses cgroups (with RSS fallback) for accuracy, runs only while update()
    executes, and does not enforce any limit. Logs peak + average usage
    once stop() is called.
    """

    def __init__(self, sample_interval=1.0):
        super().__init__(sample_interval)

    def start(self):
        """Measure baseline and start background monitoring."""
        if os.environ.get(CONNECTOR_SDK_MEMORY_TRACKING_IN_SYNC, "false") != "true":
            self.active = False
            self.monitor_thread = None
            return

        try:
            self.baseline_bytes = _get_sync_memory_bytes()
            # -1 means memory reading is unavailable, don't start tracking
            if self.baseline_bytes == -1:
                print_library_log(
                    "Memory reading unavailable. Continuing without tracking.",
                    Logging.Level.WARNING,
                    dev_log=True
                )
                self.active = False
                self.monitor_thread = None
                return
            
            self.active = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=False)
            self.monitor_thread.start()
        except Exception as exception:
            print_library_log(
                f"Failed to start memory tracking: {exception}. Continuing without tracking.",
                Logging.Level.WARNING,
                dev_log=True
            )
            self.active = False
            self.monitor_thread = None

    def stop(self, timeout=3.0):
        """Stop monitoring and log results."""
        self.active = False

        if self.monitor_thread is None:
            return

        self.monitor_thread.join(timeout=timeout)
        self._log_results()

    def _monitor_loop(self):
        """Background thread that samples memory at the configured interval."""
        while self.active:
            try:
                current_bytes = _get_sync_memory_bytes()
                if current_bytes != -1:
                    self.record_sample(current_bytes)
            except Exception:
                pass  # Fail silently

            time.sleep(self.sample_interval)


def get_memory_tracker():
    if constants.DEBUGGING:
        return DebugMemoryTracker()
    else:
        return SyncMemoryTracker()
