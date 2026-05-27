#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Virtuelle Umgebung nicht gefunden!"
    echo "Führe zuerst ./setup.sh aus"
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "❌ Fehler: Keine PDF-Datei angegeben"
    echo "Verwendung: ./split.sh <pdf-datei-oder-ordner> [weitere-optionen]"
    echo "Beispiele:"
    echo "  ./split.sh splittest.pdf"
    echo "  ./split.sh splittest.pdf --dry-run"
    echo "  ./split.sh . --provider ollama"
    exit 1
fi

source "$VENV_DIR/bin/activate"
exec "$SCRIPT_DIR/split_pdfs.py" "$@"
