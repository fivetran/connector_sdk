"""Thin ctypes wrapper around a bundled, pre-built third-party C library.

native/libm.so is the real, pre-built C standard math library, compiled for
Linux x86_64 and bundled with this connector so it is available wherever the
connector runs, instead of relying on it being separately installed. Load it
once at import time, declare argtypes/restype to match its real C API, and
expose plain Python functions that connector.py can call like any other
helper.

The same pattern applies to any other compiled, proprietary, or third-party
C library you need to bundle: resolve the path to your library's .so file,
load it with ctypes.CDLL, and declare argtypes/restype to match your
library's C header.
"""

# For loading and calling the native library's compiled functions
import ctypes

# For resolving the path to the bundled library file
from pathlib import Path

# The compiled library bundled with this connector.
_LIBRARY_PATH = Path(__file__).resolve().parent / "native" / "libm.so"

# Load the bundled library into this process so its functions can be called directly.
library = ctypes.CDLL(str(_LIBRARY_PATH))

# Match these declarations to libm's C header (math.h).
library.pow.argtypes = [ctypes.c_double, ctypes.c_double]
library.pow.restype = ctypes.c_double

library.sqrt.argtypes = [ctypes.c_double]
library.sqrt.restype = ctypes.c_double


def power(base: float, exponent: float) -> float:
    """
    Call the native `pow` function from the bundled library.
    Args:
        base: the base value to raise to a power.
        exponent: the exponent to raise the base to.
    Returns:
        The result of base raised to the power of exponent.
    """
    return library.pow(base, exponent)


def square_root(value: float) -> float:
    """
    Call the native `sqrt` function from the bundled library.
    Args:
        value: the value to compute the square root of.
    Returns:
        The square root of value.
    """
    return library.sqrt(value)
