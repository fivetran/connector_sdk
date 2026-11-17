# Native C Library Integration Connector Example

## Connector overview
This connector demonstrates how to call a native C library from a Connector SDK connector using Python's built-in [`ctypes`](https://docs.python.org/3/library/ctypes.html) module. It simulates a scenario where a connector needs to reuse an existing calculation already implemented in C, for example a formula shared with other internal systems, instead of reimplementing that logic in Python.

The example bundles a custom-compiled C library as `native/libnative_math.so`. `native_wrapper.py` loads it from a fixed path with `ctypes.CDLL(...)`. The library is built from `native/native_math.c` using `native/Makefile`, so this example includes a complete C source and build flow.

## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (x86_64). `native/libnative_math.so` is built for this environment, matching the Fivetran Connector SDK hosted production environment.
  - macOS and Windows are not supported by this example as provided. `native/libnative_math.so` is a Linux ELF binary; macOS (Mach-O) and Windows (PE/`.dll`) use different binary formats and cannot load it.


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init --template examples/common_patterns/native_c_library_integration
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Demonstrates bundling a precompiled `.so` file with a connector and loading it with `ctypes`.
- Declares `argtypes`/`restype` so Python and C agree on how arguments and return values are converted between the two languages.
- Shows loading the bundled library from a fixed path, the same way you would for your own compiled, proprietary, or third-party C library.
- Includes a C source file and `Makefile` so you can build a custom shared library (`libnative_math.so`) with `make`.


## Configuration file
This example does not require any configuration inputs.

```json
{}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any external dependencies. `ctypes` is part of the Python standard library, so no `requirements.txt` is needed.

> Note: [Some packages](https://fivetran.com/docs/connector-sdk/technical-reference#preinstalledpackages) are pre-installed in the Connector SDK runtime environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
No authentication is used, as the connector operates on hardcoded sample data. In a real connector, you would call the native library's functions on data fetched from your source API, database, or file system.


## Pagination
Not applicable — this example syncs static data only. To support pagination, you could modify `update()` to loop through pages of records before calling into the native library for each one.


## Data handling
- `native_wrapper.py` resolves the bundled library's path relative to the connector file (`native/libnative_math.so`), loads it with `ctypes.CDLL`, and declares `argtypes`/`restype` for `connector_power`, `connector_square_root`, and `connector_safe_ratio`.
- `connector.py` calls `native_wrapper.power()`, `native_wrapper.square_root()`, and `native_wrapper.safe_ratio()` for each sample row and upserts the results.
- `native/native_math.c` and `native/Makefile` demonstrate how to build your own Linux shared library:
  ```bash
  cd native
  make
  ```
  This produces `native/libnative_math.so`, which you can load from `native_wrapper.py` when adapting this example for your own native code.
- To bundle your own compiled library, place its `.so` file under a `native/` folder and resolve its path the same way, for example:
  ```python
  import ctypes
  from pathlib import Path

  library_path = Path(__file__).resolve().parent / "native" / "your_library.so"
  library = ctypes.CDLL(str(library_path))
  # Match these declarations to the library's C header.
  library.your_function.argtypes = [ctypes.c_int, ctypes.c_int]
  library.your_function.restype = ctypes.c_int
  ```



## Error handling
- `native_wrapper.py` lets `ctypes.CDLL(...)` raise an `OSError` at import time if `native/libnative_math.so` is missing or cannot be loaded (for example, because it was built for a different platform), so the connector fails fast with a clear error instead of failing later with a confusing `ctypes` error.
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
    "sqrt_result": "DOUBLE",
    "power_to_sqrt_ratio": "DOUBLE"
  }
}
```


## Additional files

The connector uses four additional files:
- `native_wrapper.py`: a thin `ctypes` wrapper that loads the bundled custom native library and exposes `power()`, `square_root()`, and `safe_ratio()` helpers for `connector.py` to call.
- `native/libnative_math.so`: the compiled, bundled C library, built for Linux x86_64.
- `native/native_math.c`: example C source with exported functions (`connector_power`, `connector_square_root`) that call `pow`/`sqrt`.
- `native/Makefile`: build recipe for compiling `native/native_math.c` into a shared library (`libnative_math.so`).


## Additional considerations
A bundled `.so` file must be compiled for the target platform (Linux x86_64), not necessarily the platform you're developing on (for example, macOS arm64). `native/libnative_math.so` in this example is compiled for Linux x86_64; see the Requirements section above for how this affects running this example locally.
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
