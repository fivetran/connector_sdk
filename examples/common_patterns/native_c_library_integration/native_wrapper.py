"""Thin ctypes wrapper around the bundled native C library (native/libcustom.so).

Keep this module small and focused: load the compiled library once at import
time, declare argtypes/restype to match the C header exactly, and expose
plain Python functions that connector.py can call like any other helper.
"""

import ctypes
from pathlib import Path

# The shared library is compiled by drivers/installation.sh at deploy time
# (see native/custom.c). Resolve the path relative to this file so it works
# regardless of the current working directory.
library_path = Path(__file__).resolve().parent / "native" / "libcustom.so"

if not library_path.exists():
    raise FileNotFoundError(
        f"Native library not found at {library_path}. "
        "Ensure drivers/installation.sh has run to compile native/custom.c "
        "before the connector starts."
    )

library = ctypes.CDLL(str(library_path))

# Match these declarations to the library's C header (native/custom.c).
library.add.argtypes = [ctypes.c_int, ctypes.c_int]
library.add.restype = ctypes.c_int


def add(a: int, b: int) -> int:
    """Call the native `add` function from libcustom.so."""
    return library.add(a, b)
