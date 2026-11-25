"""Reads row changes for one table shard from PlanetScale's VStream gRPC API, used by connector.py.

A shard is read in bounded passes. Each pass opens a VStream at the saved TableCursor, emits row changes and moves
the cursor forward from VGTID and LASTPK events. Before every pass the reader asks VStream for the shard's current
position, and stops once the cursor has caught up with it, so a sync ends instead of streaming forever. Timeouts,
expired binlogs and schema changes are handled the same way as in PlanetScale's own Fivetran connector.
"""

# For the basic authentication header
import base64

# For measuring checkpoint intervals and backing off between passes
import time

# For grouping the result of a pass and of a table read
from dataclasses import dataclass
from typing import Callable, Optional

# For calling PlanetScale's VStream API
import grpc

# For converting row values to their destination types
import value_converter

# For the VStream request, response and cursor messages
from vitess_messages import (
    VEVENT_TYPE,
    VSTREAM_METHOD,
    Filter,
    Rule,
    ShardGtid,
    TableCursor,
    TableLastPK,
    VGtid,
    VStreamFlags,
    VStreamRequest,
    VStreamResponse,
)

__TLS_PORT = 443
__POSITION_DEADLINE_SECONDS = 45
__CELLS = "planetscale_operator_default"
__CURSOR_CHECKPOINT_ROWS = 1000
__CURSOR_CHECKPOINT_INTERVAL_SECONDS = 10 * 60
__INITIAL_READ_SECONDS = 60
__MAX_READ_SECONDS = 60 * 60
__READ_DURATION_MULTIPLIER = 2.8
__INITIAL_BACKOFF_SECONDS = 10
__MAX_BACKOFF_SECONDS = 5 * 60
__MAX_CONSECUTIVE_NO_PROGRESS_TIMEOUTS = 5
__BINLOG_EXPIRATION_MESSAGE = "Cannot replicate because the source purged required binary logs"
__CURRENT_POSITION = "current"
__NULL_LENGTH = -1

# The outcomes of one pass.
STOP_POSITION_REACHED = "STOP_POSITION_REACHED"
COPY_COMPLETED = "COPY_COMPLETED"
STREAM_ENDED = "STREAM_ENDED"
ERROR = "ERROR"

# Row change operations.
INSERT = "INSERT"
UPDATE = "UPDATE"
DELETE = "DELETE"


class VStreamError(Exception):
    """A gRPC failure, or a stream the reader cannot process, carrying a gRPC status code name."""

    def __init__(self, code: str, description: str):
        """
        Create the error; the message reads "<CODE>: <description>" like a gRPC status.
        Args:
            code: the gRPC status code name, e.g. "DEADLINE_EXCEEDED".
            description: the status description.
        """
        super().__init__(f"{code}: {description}")
        self.code = code
        self.description = description


class TableReadError(Exception):
    """A failure that ends a table read, with the gRPC error that caused it when there is one."""


@dataclass
class PassResult:
    """The cursor after one pass, why the pass stopped, and its error when it failed."""

    cursor: object
    outcome: str
    error: Optional[Exception] = None


@dataclass
class ReadResult:
    """The latest cursor that made progress, a binlog-expiry note to store with it, and any error."""

    cursor: Optional[object]
    binlog_expiration_error: Optional[str] = None
    error: Optional[Exception] = None


@dataclass
class Listener:
    """Where a table read reports progress: log lines, a dashboard warning, and expired binlogs."""

    info: Callable[[str], None]
    warning: Callable[[str], None]
    warning_alert: Callable[[str], None]
    record_binlog_expiration: Callable[[str, str, str], None]


@dataclass
class ReadState:
    """The mutable progress of one table read across passes."""

    current: object
    read_seconds: float
    backoff_seconds: float
    last_cursor: Optional[object] = None
    binlog_reset_cursor: Optional[object] = None
    binlog_expiration_error: Optional[str] = None
    consecutive_timeouts: int = 0


def open_channel(host: str):
    """
    Open a TLS gRPC channel to the PlanetScale host. Responses are not size-limited, because one row with a large
    BLOB or TEXT value arrives as one message.
    Args:
        host: the database host name.
    Returns:
        The grpc.Channel.
    """
    return grpc.secure_channel(
        f"{host}:{__TLS_PORT}",
        grpc.ssl_channel_credentials(),
        options=[("grpc.max_receive_message_length", -1)],
    )


@dataclass
class VStreamClient:
    """One short-lived channel and the credentials used for a single VStream call."""

    channel: object
    username: str
    password: str
    position_deadline_seconds: float

    def close(self):
        """Close the channel."""
        self.channel.close()


def open_client(host: str, username: str, password: str):
    """
    Create a client with its own channel; the caller closes it when its call is done.
    Args:
        host: the database host name.
        username: the PlanetScale database username.
        password: the PlanetScale database password.
    Returns:
        The VStreamClient.
    """
    return VStreamClient(open_channel(host), username, password, __POSITION_DEADLINE_SECONDS)


def quote_identifier(identifier: str):
    """
    Quote a MySQL identifier with backticks.
    Args:
        identifier: the table name.
    Returns:
        The quoted identifier.
    """
    return "`" + identifier.replace("`", "``") + "`"


def build_request(keyspace, shard, table_name, cursor, tablet_type):
    """
    Build the VStream request that starts at a table cursor and streams only one table.
    Args:
        keyspace: the keyspace, used when the cursor has none.
        shard: the shard, used when the cursor has none.
        table_name: the table to stream.
        cursor: the TableCursor to start at; a last known primary key resumes an initial copy.
        tablet_type: the topodata.TabletType number.
    Returns:
        The VStreamRequest.
    """
    shard_gtid = ShardGtid(
        keyspace=cursor.keyspace or keyspace,
        shard=cursor.shard or shard,
        gtid=cursor.position,
    )
    if cursor.HasField("last_known_pk"):
        shard_gtid.table_p_ks.append(
            TableLastPK(table_name=table_name, lastpk=cursor.last_known_pk)
        )
    rule = Rule(match=table_name, filter="SELECT * FROM " + quote_identifier(table_name))
    return VStreamRequest(
        tablet_type=tablet_type,
        vgtid=VGtid(shard_gtids=[shard_gtid]),
        filter=Filter(rules=[rule]),
        flags=VStreamFlags(minimize_skew=True, cells=__CELLS),
    )


def open_vstream(client, keyspace, shard, table_name, cursor, tablet_type, read_seconds):
    """
    Start a VStream and yield its responses. gRPC failures are raised as VStreamError.
    Args:
        client: the VStreamClient.
        keyspace: the keyspace.
        shard: the shard.
        table_name: the table to stream.
        cursor: the TableCursor to start at.
        tablet_type: the topodata.TabletType number.
        read_seconds: the deadline of the call.
    Returns:
        A generator of VStreamResponse messages.
    """
    token = base64.b64encode(f"{client.username}:{client.password}".encode("utf-8")).decode(
        "ascii"
    )
    call = client.channel.unary_stream(
        VSTREAM_METHOD,
        request_serializer=VStreamRequest.SerializeToString,
        response_deserializer=VStreamResponse.FromString,
    )
    request = build_request(keyspace, shard, table_name, cursor, tablet_type)
    try:
        yield from call(
            request, timeout=read_seconds, metadata=[("authorization", "Basic " + token)]
        )
    except grpc.RpcError as error:
        raise VStreamError(error.code().name, error.details() or "") from error


def get_latest_position(client, keyspace, shard, table_name, tablet_type):
    """
    Read a shard's current position by starting a VStream at "current" and taking the first position it reports
    for that shard.
    Args:
        client: the VStreamClient.
        keyspace: the keyspace.
        shard: the shard.
        table_name: any table of the keyspace, used for the stream filter.
        tablet_type: the topodata.TabletType number.
    Returns:
        The position.
    """
    cursor = TableCursor(keyspace=keyspace, shard=shard, position=__CURRENT_POSITION)
    responses = open_vstream(
        client, keyspace, shard, table_name, cursor, tablet_type, client.position_deadline_seconds
    )
    try:
        for response in responses:
            for event in response.events:
                if event.type != VEVENT_TYPE["VGTID"]:
                    continue
                for shard_gtid in event.vgtid.shard_gtids:
                    if shard_gtid.keyspace == keyspace and shard_gtid.shard == shard:
                        if shard_gtid.gtid:
                            return shard_gtid.gtid
    finally:
        responses.close()
    raise ValueError(f"VStream completed without a position for shard {shard}")


def normalize_table_name(table_name: str):
    """
    Drop the keyspace prefix VStream puts on table names, e.g. "commerce.orders" to "orders".
    Args:
        table_name: the name from an event.
    Returns:
        The bare table name.
    """
    return table_name.rpartition(".")[2]


def normalize_cursor_identity(cursor, keyspace: str, shard: str):
    """
    Fill in a cursor's keyspace and shard when they are empty, as they are for a table read for the first time.
    Args:
        cursor: the TableCursor.
        keyspace: the keyspace.
        shard: the shard.
    Returns:
        A new TableCursor.
    """
    normalized = TableCursor()
    normalized.CopyFrom(cursor)
    normalized.keyspace = cursor.keyspace or keyspace
    normalized.shard = cursor.shard or shard
    return normalized


def validate_last_known_pk(last_known_pk, table_name: str):
    """
    Reject a copy cursor whose last known primary key has no field metadata, because it could not be resumed.
    Args:
        last_known_pk: the query.QueryResult, or None.
        table_name: the table, for the error message.
    """
    if last_known_pk is not None and not last_known_pk.fields:
        raise VStreamError(
            "INTERNAL",
            f"VStream copy cursor for table {table_name} is missing LastKnownPk field metadata",
        )


def cursor_from_vgtid(cursor, vgtid, table_name: str):
    """
    Move the cursor to the position a VGTID event reports for its shard, taking the table's last known primary key
    from the event when the initial copy is still running.
    Args:
        cursor: the current TableCursor.
        vgtid: the binlogdata.VGtid.
        table_name: the table being read.
    Returns:
        The new TableCursor.
    """
    for shard_gtid in vgtid.shard_gtids:
        if shard_gtid.keyspace != cursor.keyspace or shard_gtid.shard != cursor.shard:
            continue
        updated = TableCursor()
        updated.CopyFrom(cursor)
        if shard_gtid.gtid:
            updated.position = shard_gtid.gtid
        last_known_pk = None
        for table_pk in shard_gtid.table_p_ks:
            if normalize_table_name(table_pk.table_name) == table_name:
                last_known_pk = table_pk.lastpk
                break
        if last_known_pk is None:
            updated.ClearField("last_known_pk")
        else:
            updated.last_known_pk.CopyFrom(last_known_pk)
        validate_last_known_pk(last_known_pk, table_name)
        return updated
    return cursor


def cursor_from_last_pk(cursor, event, table_name: str):
    """
    Apply a LASTPK event: record copy progress, or clear it when the copy of the table has completed.
    Args:
        cursor: the current TableCursor.
        event: the binlogdata.LastPKEvent.
        table_name: the table being read.
    Returns:
        The new TableCursor.
    """
    if not event.HasField("table_last_p_k"):
        return cursor
    if normalize_table_name(event.table_last_p_k.table_name) != table_name:
        return cursor
    updated = TableCursor()
    updated.CopyFrom(cursor)
    if event.completed:
        updated.ClearField("last_known_pk")
        return updated
    validate_last_known_pk(event.table_last_p_k.lastpk, table_name)
    updated.last_known_pk.CopyFrom(event.table_last_p_k.lastpk)
    return updated


def has_progress(cursor):
    """
    Tell whether a cursor records any position or copy progress.
    Args:
        cursor: the TableCursor, or None.
    Returns:
        True when it does.
    """
    return cursor is not None and (bool(cursor.position) or cursor.HasField("last_known_pk"))


def made_progress(before, after):
    """
    Tell whether a pass moved the cursor.
    Args:
        before: the cursor at the start of the pass, or None.
        after: the cursor at the end of the pass, or None.
    Returns:
        True when the position or the copy progress changed.
    """
    if after is None:
        return False
    if before is None:
        return has_progress(after)
    if before.position != after.position:
        return True
    if before.HasField("last_known_pk") != after.HasField("last_known_pk"):
        return True
    return before.HasField("last_known_pk") and before.last_known_pk != after.last_known_pk


def should_checkpoint(cursor, records_since_checkpoint: int, last_checkpoint: float, now: float):
    """
    Tell whether to save copy progress: every 1000 rows or every ten minutes while the initial copy runs.
    Args:
        cursor: the current TableCursor.
        records_since_checkpoint: rows emitted since the last saved cursor.
        last_checkpoint: when the cursor was last saved, in seconds.
        now: the current time, in seconds.
    Returns:
        True when the cursor should be saved.
    """
    if not cursor.HasField("last_known_pk") or records_since_checkpoint == 0:
        return False
    is_interval_elapsed = now - last_checkpoint >= __CURSOR_CHECKPOINT_INTERVAL_SECONDS
    return records_since_checkpoint >= __CURSOR_CHECKPOINT_ROWS or is_interval_elapsed


def convert_row(fields: list, row, column_types: dict):
    """
    Split a VStream row into its column values and convert each one. A length of -1 is SQL NULL.
    Args:
        fields: the query.Field list from the table's FIELD event.
        row: the query.Row.
        column_types: column name to Fivetran type, from schema discovery.
    Returns:
        A dictionary of column name to converted value.
    """
    if len(row.lengths) != len(fields):
        raise ValueError("VStream row field count does not match field metadata")
    values = row.values
    offset = 0
    converted = {}
    for field_, length in zip(fields, row.lengths):
        raw_value = None
        if length >= 0:
            if length > len(values) - offset:
                raise ValueError("VStream row value is shorter than its field lengths")
            raw_value = values[offset : offset + length]
            offset += length
        elif length != __NULL_LENGTH:
            raise ValueError("VStream row contains an invalid null field length")
        data_type = column_types.get(field_.name)
        if raw_value is not None and data_type is None:
            raise ValueError(f"Missing column type for {field_.name}")
        converted[field_.name] = value_converter.convert(
            field_, raw_value, data_type or value_converter.STRING
        )
    return converted


def emit_row_changes(row_event, fields, column_types, on_row):
    """
    Convert and emit the row changes of one ROW event.
    Args:
        row_event: the binlogdata.RowEvent.
        fields: the table's query.Field list.
        column_types: column name to Fivetran type.
        on_row: called with (operation, before, after) for each change.
    Returns:
        The number of changes emitted.
    """
    count = 0
    for change in row_event.row_changes:
        has_before, has_after = change.HasField("before"), change.HasField("after")
        if not has_before and not has_after:
            continue
        operation = UPDATE if has_before and has_after else (INSERT if has_after else DELETE)
        try:
            before = convert_row(fields, change.before, column_types) if has_before else {}
            after = convert_row(fields, change.after, column_types) if has_after else {}
            on_row(operation, before, after)
        except Exception as error:
            # Any failure in conversion or in the row handler ends the pass without moving the cursor.
            description = (
                "unable to serialize update" if operation == UPDATE else "unable to serialize row"
            )
            raise VStreamError("INTERNAL", description) from error
        count += 1
    return count


def notify_cursor(on_cursor, cursor):
    """
    Hand a cursor to the caller to save.
    Args:
        on_cursor: called with the TableCursor.
        cursor: the TableCursor.
    """
    try:
        on_cursor(cursor)
    except Exception as error:
        raise VStreamError("INTERNAL", "unable to serialize cursor") from error


def apply_event(event, table_name, fields_by_table, cursor, column_types, on_row):
    """
    Apply one VStream event to the pass.
    Args:
        event: the binlogdata.VEvent.
        table_name: the table being read.
        fields_by_table: field metadata from FIELD events, keyed by full and bare table name.
        cursor: the current TableCursor.
        column_types: column name to Fivetran type.
        on_row: the row handler.
    Returns:
        A tuple of (new cursor, rows emitted, whether the copy completed).
    """
    if event.type == VEVENT_TYPE["FIELD"] and event.HasField("field_event"):
        fields = list(event.field_event.fields)
        fields_by_table[event.field_event.table_name] = fields
        fields_by_table[normalize_table_name(event.field_event.table_name)] = fields
    elif event.type == VEVENT_TYPE["ROW"]:
        row_event = event.row_event
        if normalize_table_name(row_event.table_name) != table_name:
            return cursor, 0, False
        fields = fields_by_table.get(row_event.table_name) or fields_by_table.get(
            normalize_table_name(row_event.table_name)
        )
        if not fields:
            raise VStreamError(
                "INTERNAL", f"missing VStream fields for table {row_event.table_name}"
            )
        return cursor, emit_row_changes(row_event, fields, column_types, on_row), False
    elif event.type == VEVENT_TYPE["VGTID"]:
        return cursor_from_vgtid(cursor, event.vgtid, table_name), 0, False
    elif event.type == VEVENT_TYPE["LASTPK"]:
        return cursor_from_last_pk(cursor, event.last_p_k_event, table_name), 0, False
    elif event.type == VEVENT_TYPE["COPY_COMPLETED"]:
        return cursor, 0, True
    return cursor, 0, False


def run_pass(
    client_factory,
    clock,
    keyspace,
    shard,
    table_name,
    start_cursor,
    stop_position,
    tablet_type,
    read_seconds,
    column_types,
    on_row,
    on_cursor,
):
    """
    Run one bounded VStream pass for a table shard.
    The pass ends when the initial copy completes, when the stream moves past the stop position, when the stream
    ends, or on an error. Row changes go to on_row; cursor progress goes to on_cursor.
    Args:
        client_factory: returns a new VStreamClient.
        clock: returns the current time in seconds.
        keyspace: the keyspace.
        shard: the shard.
        table_name: the table.
        start_cursor: the TableCursor to start at.
        stop_position: the shard position this pass should catch up with.
        tablet_type: the topodata.TabletType number.
        read_seconds: the deadline of the pass.
        column_types: column name to Fivetran type.
        on_row: called with (operation, before, after).
        on_cursor: called with a TableCursor to save.
    Returns:
        The PassResult. On a row or event error the cursor is the one the pass started at, so nothing is skipped.
    """
    pass_start = normalize_cursor_identity(start_cursor, keyspace, shard)
    cursor = pass_start
    client = client_factory()
    try:
        responses = open_vstream(
            client, keyspace, shard, table_name, cursor, tablet_type, read_seconds
        )
        fields_by_table = {}
        records_since_checkpoint, last_checkpoint = 0, clock()
        watch_for_newer_position = False
        for response in responses:
            copy_completed = False
            for event in response.events:
                try:
                    cursor, rows, completed = apply_event(
                        event, table_name, fields_by_table, cursor, column_types, on_row
                    )
                except VStreamError as error:
                    # Rows emitted in this pass will be read again, so the pass's start cursor is kept.
                    return PassResult(pass_start, ERROR, error)
                records_since_checkpoint += rows
                copy_completed = copy_completed or completed
            watch_for_newer_position = watch_for_newer_position or cursor.position == stop_position
            if should_checkpoint(cursor, records_since_checkpoint, last_checkpoint, clock()):
                try:
                    notify_cursor(on_cursor, cursor)
                except VStreamError as error:
                    return PassResult(cursor, ERROR, error)
                records_since_checkpoint, last_checkpoint = 0, clock()
            if copy_completed:
                return finish_pass(on_cursor, cursor, COPY_COMPLETED)
            is_copying = cursor.HasField("last_known_pk")
            is_past_stop = cursor.position != stop_position
            if watch_for_newer_position and not is_copying and is_past_stop:
                return finish_pass(on_cursor, cursor, STOP_POSITION_REACHED)
        return PassResult(cursor, STREAM_ENDED)
    except VStreamError as error:
        return PassResult(cursor, ERROR, error)
    finally:
        client.close()


def finish_pass(on_cursor, cursor, outcome: str):
    """
    Save the final cursor of a pass.
    Args:
        on_cursor: called with the TableCursor.
        cursor: the TableCursor.
        outcome: the outcome to report when saving succeeds.
    Returns:
        The PassResult.
    """
    try:
        notify_cursor(on_cursor, cursor)
    except VStreamError as error:
        return PassResult(cursor, ERROR, error)
    return PassResult(cursor, outcome)


def next_read_seconds(current: float):
    """
    Lengthen the read window after a timeout, up to one hour.
    Args:
        current: the current window, in seconds.
    Returns:
        The next window.
    """
    return min(current * __READ_DURATION_MULTIPLIER, __MAX_READ_SECONDS)


def next_backoff_seconds(current: float):
    """
    Double the backoff after a timeout without progress, up to five minutes.
    Args:
        current: the current backoff, in seconds.
    Returns:
        The next backoff.
    """
    return min(current * 2, __MAX_BACKOFF_SECONDS)


def is_binlog_expiration(error: Exception):
    """
    Tell whether VStream failed because the binlogs at the cursor's position have been purged.
    Args:
        error: the failure.
    Returns:
        True when the cursor must be reset to a new initial copy.
    """
    return __BINLOG_EXPIRATION_MESSAGE in str(error)


def is_schema_incompatibility(error: VStreamError):
    """
    Tell whether VStream cannot build a replication plan because the table's columns changed.
    Args:
        error: the gRPC failure.
    Returns:
        True when only a historical re-sync can recover.
    """
    message = str(error)
    has_failed_precondition = (
        error.code == "FAILED_PRECONDITION" or "Code: FAILED_PRECONDITION" in message
    )
    if not has_failed_precondition or "failed to build table replication plan" not in message:
        return False
    return "cannot use column names in vstream filter" in message or (
        "column " in message and " not found in table " in message
    )


def update_progress_cursor(state: ReadState):
    """
    Remember the latest cursor with progress. Once a pass moves past a cursor that was reset for expired binlogs,
    the expiry note no longer applies.
    Args:
        state: the read state.
    """
    if has_progress(state.current):
        state.last_cursor = state.current
        if state.binlog_reset_cursor is not None and state.current != state.binlog_reset_cursor:
            state.binlog_expiration_error = None
            state.binlog_reset_cursor = None


def handle_timeout(
    state: ReadState, progressed: bool, table_name: str, listener: Listener, sleeper
):
    """
    Handle a pass that hit its deadline: lengthen the next window, and back off when the cursor did not move.
    After five timeouts in a row without progress the read stops successfully with a dashboard warning.
    Args:
        state: the read state.
        progressed: whether the timed-out pass moved the cursor.
        table_name: the table, for messages.
        listener: where to report.
        sleeper: waits a number of seconds.
    Returns:
        A ReadResult to stop with, or None to run another pass.
    """
    state.read_seconds = next_read_seconds(state.read_seconds)
    if progressed:
        listener.info("Timeout occurred after cursor progress; continuing without backoff")
        state.consecutive_timeouts, state.backoff_seconds = 0, __INITIAL_BACKOFF_SECONDS
        return None
    state.consecutive_timeouts += 1
    if state.consecutive_timeouts >= __MAX_CONSECUTIVE_NO_PROGRESS_TIMEOUTS:
        listener.info("Reached maximum consecutive no-progress timeouts, stopping sync")
        listener.warning_alert(
            f"Timeout occurred while reading table {table_name} after {state.consecutive_timeouts}"
            " consecutive attempts without cursor progress. Stopping sync."
        )
        return ReadResult(state.last_cursor, state.binlog_expiration_error)
    sleeper(state.backoff_seconds)
    state.backoff_seconds = next_backoff_seconds(state.backoff_seconds)
    return None


def handle_pass_error(state, error, progressed, table_name, listener, sleeper):
    """
    Decide what a failed pass means for the table read.
    Args:
        state: the read state.
        error: the pass failure.
        progressed: whether the pass moved the cursor.
        table_name: the table.
        listener: where to report.
        sleeper: waits a number of seconds.
    Returns:
        A ReadResult to stop with, or None to run another pass.
    """
    if not isinstance(error, VStreamError):
        listener.warning("VStream failed with non-gRPC error")
        return ReadResult(state.last_cursor, state.binlog_expiration_error, error)
    if error.code == "DEADLINE_EXCEEDED":
        return handle_timeout(state, progressed, table_name, listener, sleeper)
    if is_binlog_expiration(error):
        listener.warning(
            "Binlogs have expired. Resetting cursor position to trigger historical sync"
        )
        listener.record_binlog_expiration(state.current.keyspace, table_name, state.current.shard)
        reset = TableCursor(keyspace=state.current.keyspace, shard=state.current.shard)
        state.current = state.last_cursor = state.binlog_reset_cursor = reset
        state.binlog_expiration_error = f"Binlogs have expired. Cursor reset to trigger historical sync. Original error: {error}"
        return None
    if is_schema_incompatibility(error):
        wrapped = TableReadError(
            f"PlanetScale VStream cannot continue incremental replication for table {table_name}"
            " after a schema change; run a Fivetran historical re-sync for this connection to recover"
        )
        wrapped.__cause__ = error
        return ReadResult(state.last_cursor, state.binlog_expiration_error, wrapped)
    listener.warning(f"VStream failed with gRPC error: {error.code}")
    return ReadResult(state.last_cursor, state.binlog_expiration_error, error)


def read_table(
    client_factory,
    keyspace,
    shard,
    table_name,
    start_cursor,
    tablet_type,
    column_types,
    on_row,
    on_cursor,
    listener: Listener,
    sleeper=time.sleep,
    clock=time.monotonic,
):
    """
    Read a table shard until its cursor has caught up with the shard's current position or an error stops it.
    Args:
        client_factory: returns a new VStreamClient.
        keyspace: the keyspace.
        shard: the shard.
        table_name: the table.
        start_cursor: the saved TableCursor, or an empty one for a table read for the first time.
        tablet_type: the topodata.TabletType number.
        column_types: column name to Fivetran type.
        on_row: called with (operation, before, after).
        on_cursor: called with a TableCursor to save.
        listener: where to report progress.
        sleeper: waits a number of seconds between retries.
        clock: returns the current time in seconds.
    Returns:
        The ReadResult.
    """
    state = ReadState(
        current=normalize_cursor_identity(start_cursor, keyspace, shard),
        read_seconds=__INITIAL_READ_SECONDS,
        backoff_seconds=__INITIAL_BACKOFF_SECONDS,
    )
    while True:
        listener.info("peeking to see if there's any new rows")
        client = client_factory()
        try:
            latest = get_latest_position(
                client, state.current.keyspace, state.current.shard, table_name, tablet_type
            )
        except (VStreamError, ValueError) as error:
            wrapped = TableReadError("Unable to get latest cursor position")
            wrapped.__cause__ = error
            return ReadResult(state.last_cursor, state.binlog_expiration_error, wrapped)
        finally:
            client.close()
        if not state.current.HasField("last_known_pk") and latest == state.current.position:
            listener.info("no new rows found, exiting")
            return ReadResult(state.current, state.binlog_expiration_error)
        previous = state.current
        result = run_pass(
            client_factory,
            clock,
            keyspace,
            shard,
            table_name,
            state.current,
            latest,
            tablet_type,
            state.read_seconds,
            column_types,
            on_row,
            on_cursor,
        )
        state.current = result.cursor
        progressed = made_progress(previous, state.current)
        update_progress_cursor(state)
        if result.error is None:
            if result.outcome == STREAM_ENDED:
                listener.info("Finished reading all rows for table")
                return ReadResult(state.last_cursor, state.binlog_expiration_error)
            if progressed:
                state.consecutive_timeouts, state.backoff_seconds = 0, __INITIAL_BACKOFF_SECONDS
            continue
        stop = handle_pass_error(state, result.error, progressed, table_name, listener, sleeper)
        if stop is not None:
            return stop
