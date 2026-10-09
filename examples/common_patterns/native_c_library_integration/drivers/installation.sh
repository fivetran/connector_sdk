#!/bin/bash

# Script to compile the bundled C source into a shared library (libcustom.so)
# that the connector loads at runtime via ctypes.
#
# This script is executed automatically at deploy time, before connector.py
# runs, so the compiled library is always rebuilt for the target production
# platform (Linux amd64/x86_64). `build-essential` (which provides `gcc`) is
# already pre-installed in the Fivetran Connector SDK base image, so no
# additional packages need to be installed here.
#
# If you already ship a pre-built libcustom.so under native/, you can remove
# the compilation step below and simply verify the file is present instead.

OS=$(uname -s)

echo '{"level":"INFO", "message": "Detected OS: '$OS'", "message-origin": "installation_sh"}'

compile_native_library() {
  if [[ "$OS" == "Linux" ]]; then
    gcc -shared -fPIC -o native/libcustom.so native/custom.c
  else
    echo '{"level":"INFO", "message": "Unsupported OS for compiling the native library. Native libraries must be built for Linux amd64/x86_64, the hosted production platform.", "message-origin": "installation_sh"}'
    exit 1
  fi
}

compile_native_library

echo '{"level":"INFO", "message": "native/libcustom.so compilation complete.", "message-origin": "installation_sh"}'
