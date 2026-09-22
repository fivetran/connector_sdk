import pytest

from fivetran_connector_sdk import constants
from fivetran_connector_sdk import operation_stream


@pytest.fixture(autouse=True)
def _restore_global_constants():
    """Snapshot and restore module-level globals mutated by production code and tests as side
    effects, with no corresponding reset of their own.

    Left unguarded, a leaked `constants.DEBUGGING = True` causes every later test's `Update()`
    call to spin up a real `DebugMemoryTracker` background thread instead of the inert
    `SyncMemoryTracker`, and `DebugMemoryTracker.stop()` is an intentional no-op (it assumes the
    process exits shortly after, which isn't true in a shared pytest run) - so those threads never
    stop, accumulating over the run.

    Similarly, `init_no_yield_spec.py` and `operations_spec.py` rebind
    `operation_stream.MAX_RECORDS_IN_BATCH = 1` in their own `setUp` (to force single-record
    batches) without ever restoring it. `_build_next_batch` reads that name as a module-global
    lookup at call time, not a value frozen at import time, so once leaked, every later test in the
    process - including all of `operation_stream_spec.py` - permanently sees batch size 1 instead
    of 100. That corrupts both the tests' own batch-size assertions and the producer/consumer
    queue's blocking behavior (the queue fills up because 2 pulls only drains 2 records instead of
    up to 200, so the producer blocks forever waiting for space that a bounded number of
    `next()` calls will never free).
    """
    original_debugging = constants.DEBUGGING
    original_executed_via_cli = constants.EXECUTED_VIA_CLI
    original_max_records_in_batch = operation_stream.MAX_RECORDS_IN_BATCH
    yield
    constants.DEBUGGING = original_debugging
    constants.EXECUTED_VIA_CLI = original_executed_via_cli
    operation_stream.MAX_RECORDS_IN_BATCH = original_max_records_in_batch
