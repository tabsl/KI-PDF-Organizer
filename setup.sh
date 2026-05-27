#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PYTHON_CMD="python3"

echo "📦 Richte virtuelle Umgebung ein..."

if [ -d "$VENV_DIR" ]; then
    echo "⚠️  Virtuelle Umgebung existiert bereits. Überspringe Erstellung."
else
    echo "Erstelle virtuelle Umgebung in $VENV_DIR..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

echo "Aktiviere virtuelle Umgebung..."
source "$VENV_DIR/bin/activate"

echo "Aktualisiere pip..."
pip install --upgrade pip --quiet

echo "Installiere Abhängigkeiten..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "Mache rename_pdfs.py ausführbar..."
chmod +x "$SCRIPT_DIR/rename_pdfs.py"

echo ""
echo "🔍 Prüfe Ollama-Installation..."

OLLAMA_INSTALLED=false
OLLAMA_RUNNING=false
OLLAMA_MODELS=0

if command -v ollama &> /dev/null; then
    OLLAMA_INSTALLED=true
    echo "  ✓ Ollama ist installiert"
    
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        OLLAMA_RUNNING=true
        echo "  ✓ Ollama läuft"
        
        if ollama list 2>/dev/null | grep -q .; then
            OLLAMA_MODELS=$(ollama list 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
            if [ "$OLLAMA_MODELS" -gt 0 ]; then
                echo "  ✓ $OLLAMA_MODELS Modell(e) installiert:"
                ollama list 2>/dev/null | tail -n +2 | sed 's/^/    - /'
            else
                echo "  ⚠️  Keine Modelle installiert"
            fi
        else
            echo "  ⚠️  Keine Modelle installiert"
        fi
    else
        echo "  ⚠️  Ollama läuft nicht (starte mit: brew services start ollama)"
    fi
else
    echo "  ⚠️  Ollama ist nicht installiert"
fi

echo ""
echo "✅ Installation abgeschlossen!"
echo ""
echo "KI-Konfiguration:"
echo ""

if [ "$OLLAMA_INSTALLED" = true ] && [ "$OLLAMA_RUNNING" = true ] && [ "$OLLAMA_MODELS" -gt 0 ]; then
    echo "  ✅ Ollama ist bereit! Du kannst es sofort verwenden:"
    echo "     # In .env: AI_PROVIDER=ollama"
    echo "     # Oder: ./rename.sh <ordner> --provider ollama"
    echo ""
fi

echo "  Option 1: Ollama (lokal, empfohlen für Datenschutz)"
if [ "$OLLAMA_INSTALLED" = false ]; then
    echo "    brew install ollama"
fi
if [ "$OLLAMA_RUNNING" = false ] && [ "$OLLAMA_INSTALLED" = true ]; then
    echo "    brew services start ollama"
fi
if [ "$OLLAMA_MODELS" -eq 0 ]; then
    echo "    ollama pull llama3.2:3b"
fi
echo "    # In .env: AI_PROVIDER=ollama"
echo ""
echo "  Option 2: OpenAI (Cloud)"
echo "    export OPENAI_API_KEY='sk-...'"
echo "    export AI_PROVIDER=openai"
echo ""
echo "  Option 3: Anthropic (Cloud)"
echo "    export ANTHROPIC_API_KEY='sk-ant-...'"
echo "    export AI_PROVIDER=anthropic"
echo ""
echo "  Oder erstelle eine .env Datei basierend auf .env.example"
echo ""
echo "Verwendung:"
echo "  1. Aktiviere die virtuelle Umgebung:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Führe das Script aus:"
echo "     python3 rename_pdfs.py --dry-run"
echo "     python3 rename_pdfs.py <verzeichnis>"
echo ""
echo "  3. Oder verwende das Wrapper-Script:"
echo "     ./rename.sh <ordnername> --dry-run"
echo "     ./rename.sh 'Dr. Müller'"
echo ""
echo "  Ohne API-Key wird automatisch die regelbasierte Methode verwendet."
echo ""

