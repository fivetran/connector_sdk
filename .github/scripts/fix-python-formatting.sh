#!/bin/bash

set -euo pipefail

echo "Checking if 'black' is installed..."
if ! command -v black &> /dev/null; then
    echo "Installing black via pip..."
    if command -v pip3 &> /dev/null; then
        pip3 install --user black
        export PATH="$HOME/.local/bin:$PATH"
    elif command -v pip &> /dev/null; then
        pip install --user black
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "pip not found. Please install pip to continue."
        exit 1
    fi
fi

echo "Finding all Python files..."
py_files=$(find . -type f -name '*.py' -not -name '*_pb2.py' -not -name '*_pb2_grpc.py')

if [ -z "$py_files" ]; then
    echo "No Python files found to format."
    exit 0
fi

echo "Formatting all Python files with black (line length = 99)..."
black --line-length 99 $py_files

echo "All Python files are now formatted!"
