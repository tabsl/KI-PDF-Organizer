#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Virtuelle Umgebung nicht gefunden!"
    echo "Führe zuerst ./setup.sh aus"
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "❌ Fehler: Kein Ordnername angegeben"
    echo "Verwendung: ./rename.sh <ordnername> [weitere-optionen]"
    echo "Beispiele:"
    echo "  ./rename.sh 'Dr. Müller' --dry-run"
    echo "  ./rename.sh 'IHK' --parallel 4"
    echo "  ./rename.sh 'Dr. Müller' --recursive --parallel 0"
    exit 1
fi

ORDNERNAME="$1"
shift

source "$VENV_DIR/bin/activate"
exec "$SCRIPT_DIR/rename_pdfs.py" "$ORDNERNAME" --recursive "$@"

