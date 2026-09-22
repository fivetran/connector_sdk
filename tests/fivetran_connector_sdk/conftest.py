import pytest

from fivetran_connector_sdk import constants


@pytest.fixture(autouse=True)
def _restore_global_constants():
    """Snapshot and restore module-level globals mutated by production code as side effects.

    Individual tests exercise flows (e.g. `Connector.debug()`) that flip these flags with no
    corresponding reset. Left unguarded, a leaked `constants.DEBUGGING = True` causes every later
    test's `Update()` call to spin up a real `DebugMemoryTracker` background thread instead of the
    inert `SyncMemoryTracker`, and `DebugMemoryTracker.stop()` is an intentional no-op (it assumes
    the process exits shortly after, which isn't true in a shared pytest run) - so those threads
    never stop, accumulating over the run.
    """
    original_debugging = constants.DEBUGGING
    original_executed_via_cli = constants.EXECUTED_VIA_CLI
    yield
    constants.DEBUGGING = original_debugging
    constants.EXECUTED_VIA_CLI = original_executed_via_cli
