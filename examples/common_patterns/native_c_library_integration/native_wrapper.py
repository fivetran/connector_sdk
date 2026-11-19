"""Thin ctypes wrapper around a bundled, custom C library.

native/libnative_math.so is compiled from native/native_math.c. This wrapper
loads it at import time, declares argtypes/restype for each exported function,
and exposes plain Python helpers that connector.py can call.
"""

# For loading and calling the native library's compiled functions
import ctypes

# For resolving the path to the bundled library file
from pathlib import Path

# The compiled library bundled with this connector.
_LIBRARY_PATH = Path(__file__).resolve().parent / "native" / "libnative_math.so"

# Load the bundled library into this process so its functions can be called directly.
library = ctypes.CDLL(str(_LIBRARY_PATH))

# Match these declarations to the function signatures in native/native_math.c.
library.connector_power.argtypes = [ctypes.c_double, ctypes.c_double]
library.connector_power.restype = ctypes.c_double

library.connector_square_root.argtypes = [ctypes.c_double]
library.connector_square_root.restype = ctypes.c_double

library.connector_safe_ratio.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
library.connector_safe_ratio.restype = ctypes.c_double


def power(base: float, exponent: float) -> float:
    """
    Call the native `connector_power` function from the bundled library.
    Args:
        base: the base value to raise to a power.
        exponent: the exponent to raise the base to.
    Returns:
        The result of base raised to the power of exponent.
    """
    return library.connector_power(base, exponent)


def square_root(value: float) -> float:
    """
    Call the native `connector_square_root` function from the bundled library.
    Args:
        value: the value to compute the square root of.
    Returns:
        The square root of value.
    """
    return library.connector_square_root(value)


def safe_ratio(numerator: float, denominator: float, default_value: float) -> float:
    """
    Call the native `connector_safe_ratio` function from the bundled library.
    Args:
        numerator: the value in the numerator position.
        denominator: the value in the denominator position.
        default_value: the fallback value returned when denominator is zero.
    Returns:
        The computed ratio or default_value when denominator is zero.
    """
    return library.connector_safe_ratio(numerator, denominator, default_value)
