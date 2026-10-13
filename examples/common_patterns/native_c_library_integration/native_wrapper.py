"""Thin ctypes wrapper around libm, the C standard math library.

libm ships with every Linux and macOS system (including the Fivetran
Connector SDK hosted production base image), so no bundling or compilation
step is required. Load it once at import time, declare argtypes/restype to
match the real C API exactly, and expose plain Python functions that
connector.py can call like any other helper.

If you need to call your own proprietary/compiled C library instead of a
system library like libm, follow the same pattern: resolve the path to your
.so file (bundled with the connector or installed via a drivers/installation.sh
script), load it with ctypes.CDLL, and declare argtypes/restype to match your
library's C header.
"""

# For loading and calling the native library's compiled functions
import ctypes

# For locating the system's installed libm library by name
import ctypes.util

# Resolve the platform's math library (libm.so.6 on Linux, libm.dylib on macOS).
_library_path = ctypes.util.find_library("m")

if not _library_path:
    raise OSError("Could not locate libm (the C standard math library) on this system.")

# Load the compiled library into this process so its functions can be called directly.
library = ctypes.CDLL(_library_path)

# Match these declarations to libm's C header (math.h).
library.pow.argtypes = [ctypes.c_double, ctypes.c_double]
library.pow.restype = ctypes.c_double

library.sqrt.argtypes = [ctypes.c_double]
library.sqrt.restype = ctypes.c_double


def power(base: float, exponent: float) -> float:
    """
    Call the native `pow` function from libm.
    Args:
        base: the base value to raise to a power.
        exponent: the exponent to raise the base to.
    Returns:
        The result of base raised to the power of exponent.
    """
    return library.pow(base, exponent)


def square_root(value: float) -> float:
    """
    Call the native `sqrt` function from libm.
    Args:
        value: the value to compute the square root of.
    Returns:
        The square root of value.
    """
    return library.sqrt(value)
