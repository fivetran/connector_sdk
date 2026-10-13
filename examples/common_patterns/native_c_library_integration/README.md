# Native C Library Integration Connector Example

## Connector overview
This connector demonstrates how to call a native C library from a Connector SDK connector using Python's built-in [`ctypes`](https://docs.python.org/3/library/ctypes.html) module. It simulates a scenario where a connector needs to reuse an existing calculation that is already implemented and validated in C instead of reimplementing that logic in Python and risking it drifting out of sync with the canonical version. For example, a formula shared with other internal systems.

The example calls `libm`, the C standard math library. `libm` ships with every Linux and macOS system, including the Fivetran Connector SDK hosted production base image, so this example requires no bundling or compilation step, and `native_wrapper.py` loads it directly via `ctypes.util.find_library("m")`. The same `ctypes` pattern applies if you need to call your own compiled, proprietary, or third-party C library instead: bundle the compiled `.so` file alongside your connector code and load it from a fixed path with `ctypes.CDLL(...)`. See `native_wrapper.py` for details on both approaches.

Refer to the [Technical Reference documentation](https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update) and the [Best Practices documentation](https://fivetran.com/docs/connector-sdk/best-practices) for more details.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns/native_c_library_integration
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates loading and calling a native C library from Python using `ctypes`.
- Declares `argtypes`/`restype` so Python and C agree on how arguments and return values are marshalled.
- Shows calling an already-installed system library (`libm`) with no bundling required.
- Explains how to adapt the same pattern to load your own bundled `.so` file instead.


## Configuration file
This example does not require any configuration inputs.

```json
{}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any external dependencies. `ctypes` and `ctypes.util` are part of the Python standard library, so no `requirements.txt` is needed.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is used, as the connector operates on hardcoded sample data. In a real connector, you would call the native library's functions on data fetched from your source API, database, or file system.


## Pagination
Not applicable — this example syncs static data only. To support pagination, you could modify `update()` to loop through pages of records before calling into the native library for each one.


## Data handling
- `native_wrapper.py` resolves `libm`'s path with `ctypes.util.find_library("m")`, loads it with `ctypes.CDLL`, and declares `argtypes`/`restype` for the `pow` and `sqrt` functions to match `math.h`.
- `connector.py` calls `native_wrapper.power()` and `native_wrapper.square_root()` for each sample row and upserts the inputs alongside the native library's results.
- If you bundle your own compiled library instead, place the `.so` file under a `native/` folder and resolve its path relative to the connector file, for example:
  ```python
  import ctypes
  from pathlib import Path

  library_path = Path(__file__).resolve().parent / "native" / "libcustom.so"
  library = ctypes.CDLL(str(library_path))
  # Match these declarations to the library's C header.
  library.your_function.argtypes = [ctypes.c_int, ctypes.c_int]
  library.your_function.restype = ctypes.c_int
  ```

Ensure any bundled `.so` file is compiled for the Fivetran Connector SDK hosted production platform (Linux amd64/x86_64), not just your local development machine.


## Error handling
- `native_wrapper.py` raises an `OSError` at import time if `libm` cannot be located, so the connector fails fast with a clear error instead of failing later with a confusing `ctypes` error.
- Always declare `argtypes` and `restype` for every native function you call. Without them, `ctypes` assumes `int` arguments and return values, which silently corrupts data for other types (for example, truncating `double` values).


## Tables created
The connector creates the `CALCULATIONS` table:

```
{
  "table": "calculations",
  "primary_key": ["id"],
  "columns": {
    "id": "LONG",
    "base": "DOUBLE",
    "exponent": "DOUBLE",
    "power_result": "DOUBLE",
    "sqrt_result": "DOUBLE"
  }
}
```


## Additional files

The connector uses one additional file, `native_wrapper.py`, which is a thin `ctypes` wrapper that loads `libm` and exposes `power()` and `square_root()` helpers for `connector.py` to call.


## Additional considerations
- If you bundle your own `.so` file, it must be compiled for the target platform (Linux amd64/x86_64), not for the platform you're developing on (for example, macOS arm64). Cross-compile with a tool like Docker, or build the library in a Linux CI environment, before committing the binary.
- We recommend using an already-installed system library (like this example's use of `libm`) over bundling your own binary whenever possible. This avoids the complexity of cross-compilation and keeps your connector's footprint small.
- Only bundle a compiled library when the logic isn't available as a system library or a pip-installable Python package, for example proprietary business logic that already exists as validated C code elsewhere in your organization.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
