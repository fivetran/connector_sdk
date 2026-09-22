import linecache
import platform
import reprlib
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

from fivetran_connector_sdk.constants import MEMORY_LIMIT_BYTES, REDACTED_VALUE
from fivetran_connector_sdk.memory_tracker import get_debug_memory_bytes

_SOURCE_CONTEXT_RADIUS = 2
_MAX_SOURCE_LINE_LENGTH = 240
_MAX_LOCAL_VARIABLES = 20
_MAX_REPR_LENGTH = 500
_MAX_CONTAINER_ITEMS = 5
_MAX_CONFIGURATION_KEYS = 20
_MIN_SECRET_LENGTH = 4
_LIBRARY_DIRECTORY_NAMES = frozenset(("site-packages", "dist-packages"))
_NOT_AVAILABLE = "not available"
_DIRECT_CAUSE_MESSAGE = "The above exception was the direct cause of the following exception:"
_CONTEXT_MESSAGE = "During handling of the above exception, another exception occurred:"


def build_debug_crash_report(
    exception,
    project_path,
    configuration=None,
    handler=None,
    sdk_version=None,
    state=None,
    memory_tracker=None,
):
    """Builds a local debug crash report from customer-owned traceback frames.

    The report is intended for local `debug()` failures, so it includes only
    frames owned by the connector project.
    """
    secret_values = _secret_values(configuration)
    renderer = _CrashReportRepr(secret_values)

    lines = [
        "=" * 64,
        "Crash Report",
        "=" * 64,
    ]
    lines.extend(_format_metadata(project_path, handler, sdk_version))
    lines.extend(_format_connector_inputs(state, renderer))
    lines.extend(_format_resource_snapshot(_collect_resource_snapshot(memory_tracker)))
    lines.extend(["", "Error:"])

    exception_chain = _exception_chain(exception)
    for index, (current_exception, relationship_to_inner) in enumerate(exception_chain):
        if index > 0:
            lines.extend(
                [
                    "",
                    relationship_to_inner,
                    "",
                ]
            )
        lines.extend(_format_exception(current_exception, project_path, renderer))

    lines.append("=" * 64)

    report = "\n".join(lines)
    for secret in secret_values:
        report = report.replace(secret, REDACTED_VALUE)
    return report


def _format_metadata(project_path, handler, sdk_version):
    """Formats environment metadata that helps reproduce a local debug failure."""
    return [
        "",
        "Crash metadata:",
        f"  Timestamp: {_format_timestamp()}",
        f"  Handler: {_metadata_value(handler)}",
        f"  Project path: {_metadata_value(str(Path(project_path).resolve()) if project_path else None)}",
        f"  Fivetran Connector SDK version: {_metadata_value(sdk_version)}",
        f"  Python version: {platform.python_version()}",
        f"  Platform: {_platform_summary()}",
    ]


def _format_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _metadata_value(value):
    if value is None or value == "":
        return "unknown"
    return str(value)


def _platform_summary():
    values = [platform.system(), platform.release()]
    machine = platform.machine()
    summary = " ".join(value for value in values if value)
    if machine:
        summary = f"{summary} ({machine})" if summary else machine
    return summary or "unknown"


def _format_connector_inputs(state, renderer):
    state_repr = _NOT_AVAILABLE if state is None else renderer.repr(state)
    return [
        "",
        "Connector inputs:",
        f"  State: {state_repr}",
    ]


def _collect_resource_snapshot(memory_tracker=None):
    """Collects best-effort process memory values for the report preamble."""
    current_rss_bytes = None
    peak_rss_bytes = None
    average_rss_bytes = None

    try:
        rss_bytes = get_debug_memory_bytes()
        current_rss_bytes = rss_bytes if rss_bytes != -1 else None

        if (
            memory_tracker is not None
            and current_rss_bytes is not None
            and memory_tracker.baseline_bytes is not None
            and memory_tracker.baseline_bytes >= 0
        ):
            memory_tracker.record_sample(rss_bytes)
            current_rss_bytes = max(0, current_rss_bytes - memory_tracker.baseline_bytes)

        if memory_tracker is not None and memory_tracker.sample_count > 0:
            peak_rss_bytes = memory_tracker.peak_delta_bytes
            average_rss_bytes = memory_tracker.total_delta_bytes / memory_tracker.sample_count
    except Exception:
        return {}

    if peak_rss_bytes is None:
        peak_rss_bytes = current_rss_bytes

    return {
        "current_rss_bytes": current_rss_bytes,
        "peak_rss_bytes": peak_rss_bytes,
        "average_rss_bytes": average_rss_bytes,
        "memory_limit_bytes": MEMORY_LIMIT_BYTES,
    }


def _format_resource_snapshot(snapshot):
    snapshot = snapshot or {}
    return [
        "",
        "Resource snapshot:",
        f"  Current memory usage: {_format_mb(snapshot.get('current_rss_bytes'))}",
        f"  Peak memory usage: {_format_mb(snapshot.get('peak_rss_bytes'))}",
        f"  Average memory usage: {_format_mb(snapshot.get('average_rss_bytes'))}",
        f"  Debug memory limit: {_format_mb(snapshot.get('memory_limit_bytes'))}",
    ]


def _format_mb(value):
    if value is None or value < 0:
        return _NOT_AVAILABLE
    return f"{value / (1024 * 1024):.2f} MB"


def _exception_chain(exception):
    """Returns chained exceptions from root cause to outermost exception."""
    outer_to_inner = []
    current_exception = exception
    seen_exception_ids = set()

    while current_exception and id(current_exception) not in seen_exception_ids:
        seen_exception_ids.add(id(current_exception))

        if current_exception.__cause__ is not None:
            relationship_to_inner = _DIRECT_CAUSE_MESSAGE
            next_exception = current_exception.__cause__
        elif (
            current_exception.__context__ is not None
            and not current_exception.__suppress_context__
        ):
            relationship_to_inner = _CONTEXT_MESSAGE
            next_exception = current_exception.__context__
        else:
            relationship_to_inner = None
            next_exception = None

        outer_to_inner.append((current_exception, relationship_to_inner))
        current_exception = next_exception

    return list(reversed(outer_to_inner))


def _format_exception(exception, project_path, renderer):
    """Formats one exception and the connector-owned frames from its traceback."""
    customer_frames = list(_customer_frames(exception.__traceback__, project_path))

    lines = [
        _format_exception_summary(exception),
        "",
        "Customer stack trace (most recent call last):",
    ]

    if not customer_frames:
        lines.append("  No customer stack frames found.")
    else:
        for frame, line_number in customer_frames:
            lines.extend(_format_frame(frame, line_number, renderer))

    return lines


def _format_exception_summary(exception):
    """Formats exception type and message without trusting customer `__str__` code."""
    return "".join(traceback.format_exception_only(exception)).rstrip("\n")


def _customer_frames(traceback_object, project_path):
    """Yields traceback frames that belong to the connector project."""
    resolved_project_path = Path(project_path).resolve()
    for frame, line_number in traceback.walk_tb(traceback_object):
        frame_path = Path(frame.f_code.co_filename).resolve()
        if not frame_path.is_relative_to(resolved_project_path):
            continue
        if _LIBRARY_DIRECTORY_NAMES.isdisjoint(frame_path.parts):
            yield frame, line_number


def _format_frame(frame, line_number, renderer):
    filename = frame.f_code.co_filename
    lines = [
        "",
        f'File "{filename}", line {line_number}, in {frame.f_code.co_name}',
    ]
    lines.extend(_format_source_context(filename, line_number))
    lines.extend(_format_locals(frame, renderer))
    return lines


def _format_source_context(filename, line_number):
    source_lines = linecache.getlines(filename)
    if not source_lines:
        return []

    start_line = max(1, line_number - _SOURCE_CONTEXT_RADIUS)
    end_line = min(len(source_lines), line_number + _SOURCE_CONTEXT_RADIUS)
    line_number_width = len(str(end_line))

    context = []
    for current_line_number in range(start_line, end_line + 1):
        marker = "-->" if current_line_number == line_number else "   "
        source_line = _truncate_source_line(source_lines[current_line_number - 1].rstrip())
        context.append(f"  {marker} {current_line_number:{line_number_width}} | {source_line}")
    return context


def _truncate_source_line(source_line):
    if len(source_line) <= _MAX_SOURCE_LINE_LENGTH:
        return source_line
    return source_line[:_MAX_SOURCE_LINE_LENGTH] + "... <truncated>"


def _format_locals(frame, renderer):
    local_variables = [
        (name, value) for name, value in frame.f_locals.items() if not name.startswith("__")
    ]
    if not local_variables:
        return []

    lines = [
        "",
        "  Locals:",
    ]

    for name, value in local_variables[:_MAX_LOCAL_VARIABLES]:
        lines.append(f"    {name} = {_local_repr(name, value, renderer)}")

    omitted_count = len(local_variables) - _MAX_LOCAL_VARIABLES
    if omitted_count > 0:
        lines.append(f"    ... {omitted_count} more local variable(s) omitted")

    return lines


def _local_repr(name, value, renderer):
    """Formats a local variable while preserving configured redaction behavior."""
    if name == "configuration":
        return _configuration_keys_repr(value)
    return renderer.repr(value)


def _configuration_keys_repr(configuration):
    """Renders configuration key names only; values never reach the report."""
    if not isinstance(configuration, Mapping):
        return f"<{type(configuration).__name__} omitted>"

    key_count = len(configuration)
    keys = ", ".join(repr(key) for key in islice(configuration.keys(), _MAX_CONFIGURATION_KEYS))
    if key_count > _MAX_CONFIGURATION_KEYS:
        keys += ", ..."
    return f"keys[{keys}]"


class _CrashReportRepr(reprlib.Repr):
    """Bounded, redacting repr for crash report values.

    Size bounds and recursion limits come from `reprlib.Repr`. Only the mapping,
    string and instance cases are overridden, to redact secrets and to avoid
    calling customer `__getitem__`.
    """

    def __init__(self, secret_values):
        # reprlib.Repr.__init__ assigns every bound as an instance attribute, so
        # class-level overrides would be discarded by a plain super().__init__().
        super().__init__()
        self.maxlevel = 4
        self.maxdict = self.maxlist = self.maxtuple = self.maxset = self.maxfrozenset = (
            self.maxdeque
        ) = _MAX_CONTAINER_ITEMS
        self.maxstring = self.maxother = _MAX_REPR_LENGTH
        self.secret_values = secret_values

    def repr1(self, value, level):
        # reprlib dispatches on the exact type name, so Mapping subclasses would
        # bypass redaction. Route every mapping through repr_mapping.
        if isinstance(value, Mapping):
            return self.repr_mapping(value, level)
        return super().repr1(value, level)

    def repr_mapping(self, value, level):
        if not value:
            return "{}"
        if level <= 0:
            return "{...}"
        items = []
        # Iterating items() avoids customer __getitem__, which reprlib.repr_dict calls.
        for key, item in islice(value.items(), self.maxdict):
            items.append(f"{self.repr1(key, level - 1)}: {self.repr1(item, level - 1)}")
        if len(value) > self.maxdict:
            items.append("...")
        return "{" + ", ".join(items) + "}"

    def repr_str(self, value, level):
        # Redact before reprlib truncates, so a secret longer than maxstring
        # cannot survive as two visible halves.
        if self._contains_secret(value):
            return repr(REDACTED_VALUE)
        return super().repr_str(value, level)

    def repr_instance(self, value, level):
        try:
            rendered = repr(value)
        except Exception:
            return f"<unrepresentable {type(value).__name__}>"
        if self._contains_secret(rendered):
            return repr(REDACTED_VALUE)
        # Delegate bounding to reprlib's own middle-elision truncation.
        return super().repr_instance(value, level)

    def _contains_secret(self, text):
        return any(secret in text for secret in self.secret_values)


def _secret_values(configuration):
    """Returns configuration values in both raw and repr-escaped form.

    `repr()` escapes newlines, tabs and quotes, so the raw value alone would not
    match the rendered text of a multi-line secret such as a PEM private key.
    """
    secrets = set()
    for value in (configuration or {}).values():
        text = str(value)
        if len(text) < _MIN_SECRET_LENGTH:
            continue
        secrets.update((text, repr(text)[1:-1]))
    return secrets
