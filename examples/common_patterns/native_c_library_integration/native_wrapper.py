"""Thin ctypes wrapper around a bundled, pre-built third-party C library.

native/libm.so is the real, pre-built C standard math library, compiled for
Linux x86_64 and bundled with this connector so it is available wherever the
connector runs in production, instead of relying on it being separately
installed. _load_library() loads it from that fixed path on Linux, declares
argtypes/restype to match its real C API, and the module then exposes plain
Python functions that connector.py can call like any other helper.

On macOS, _load_library() instead falls back to ctypes.util.find_library("m")
purely so `fivetran debug` can run locally during development; macOS no
longer ships libm as a standalone file you could bundle in its place. This
fallback is not used in production: deployed connectors always run on Linux.

The same bundling pattern applies to any other compiled, proprietary, or
third-party C library you need to ship: resolve the path to your library's
.so file, load it with ctypes.CDLL, and declare argtypes/restype to match
your library's C header.
"""

# For loading and calling the native library's compiled functions
import ctypes

# For locating libm on macOS when developing locally (see _load_library below)
import ctypes.util

# For resolving the path to the bundled library file and checking the OS
import platform
from pathlib import Path


def _load_library() -> ctypes.CDLL:
    """
    Load the native math library this connector depends on.
    Returns:
        The loaded library, ready for argtypes/restype declarations and calls.
    """
    if platform.system() == "Linux":
        # The compiled library bundled with this connector. It was built for
        # Linux x86_64, which matches the Fivetran Connector SDK hosted
        # production environment, so no separate build step is required to
        # deploy this connector.
        library_path = Path(__file__).resolve().parent / "native" / "libm.so"
        return ctypes.CDLL(str(library_path))

    # macOS no longer ships libm as a standalone file you can bundle, so this
    # branch exists only so you can run `fivetran debug` locally on macOS.
    # It is not used in production: deployed connectors always run on Linux.
    library_path = ctypes.util.find_library("m")
    if not library_path:
        raise OSError("Could not locate libm (the C standard math library) on this system.")
    return ctypes.CDLL(library_path)


# Load the library into this process so its functions can be called directly.
library = _load_library()

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
