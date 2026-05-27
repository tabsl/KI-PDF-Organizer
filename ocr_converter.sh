#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Virtuelle Umgebung nicht gefunden!"
    echo "Führe zuerst ./setup.sh aus"
    exit 1
fi

source "$VENV_DIR/bin/activate"
exec "$SCRIPT_DIR/ocr_converter.py" --recursive "$@"

