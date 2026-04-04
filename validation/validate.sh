#!/usr/bin/env bash
set -euo pipefail

# SIQE Validation Compiler - Entry Point
# Usage: ./validate.sh <source_file.py>
#        echo "code" | ./validate.sh --stdin

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Install dependencies if needed
if [ ! -f ".deps_installed" ]; then
    echo "[SETUP] Installing validation dependencies..."
    pip install -r requirements-validation.txt -q
    touch .deps_installed
fi

# Run compiler
if [ "${1:-}" = "--stdin" ]; then
    python3 compiler.py --stdin
else
    if [ -z "${1:-}" ]; then
        echo "Usage: ./validate.sh <source_file.py>"
        echo "       echo 'code' | ./validate.sh --stdin"
        exit 1
    fi
    if [ ! -f "$1" ]; then
        echo "ERROR: File not found: $1"
        exit 1
    fi
    python3 compiler.py "$1"
fi
