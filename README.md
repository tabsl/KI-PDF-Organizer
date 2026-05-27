# KI-PDF-Organizer

Ein Python-Script zum automatischen Organisieren von PDF-Dateien. Das Tool nutzt KI (OpenAI, Anthropic oder Ollama lokal) zum Umbenennen, Sortieren und Aufsplitten von PDF-Stapeln in Einzeldokumente. Zusätzlich findet es Duplikate, validiert Dateien und konvertiert Bilder bzw. gescannte PDFs per OCR in durchsuchbare PDFs.

## Inhaltsverzeichnis

- [Features](#features)
- [Datenschutzhinweis](#datenschutzhinweis)
- [Installation](#installation)
- [Verwendung](#verwendung)
  - [Umbennen von PDF-Dateien](#umbennen-von-pdf-dateien)
  - [Aufsplitten von PDF-Stapeln](#aufsplitten-von-pdf-stapeln)
  - [Sortieren von PDF-Dateien](#sortieren-von-pdf-dateien)
  - [Duplikate finden](#duplikate-finden)
  - [Dateien validieren](#dateien-validieren)
  - [OCR-Converter](#ocr-converter)
- [Dateinamen-Format](#dateinamen-format)
- [Konfiguration](#konfiguration)
  - [Umgebungsvariablen](#umgebungsvariablen)
  - [Empfohlene Modelle](#empfohlene-modelle)
- [Kommandozeilen-Optionen](#kommandozeilen-optionen)
  - [rename.sh](#renamesh)
  - [split.sh](#splitsh)
  - [sort.sh](#sortsh)
  - [check_duplicates.sh](#check_duplicatessh)
  - [validate_files.sh](#validate_filessh)
  - [ocr_converter.sh](#ocr_convertersh)
- [Dateistruktur](#dateistruktur)
- [Funktionsweise](#funktionsweise)
- [Entwicklung](#entwicklung)
- [Lizenz](#lizenz)

## Features

- 🤖 **KI-basierte Dateinamensgenerierung** mit OpenAI, Anthropic oder Ollama (lokal)
- ✂️ **PDF-Stapel aufsplitten** - Erkennt per KI/OCR die Grenzen einzelner Dokumente in einem Sammel-Scan und schneidet die Datei in benannte Einzeldokumente
- 📄 **Automatische Text-Extraktion** aus PDF-Dateien (robust gegen fehlerhafte Seiten)
- 📅 **Intelligente Erkennung** von Datum, Absender und Dokumenttyp durch KI
- 📁 **Automatische Sortierung** von PDFs in Ordner basierend auf Dateinamen
- 🧠 **KI-Normalisierung** für konsistente Gruppierung (normalisiert Absender und Dokumenttypen)
- 🔍 **Duplikatsprüfung** - Findet exakte Duplikate, Dateinamen-Duplikate und Größen-Duplikate
- 🚫 **Dateien validieren** - Findet Nicht-PDF-Dateien, PDFs ohne Inhalt/OCR und PDFs ohne gültiges Datum am Anfang (mit OCR-Unterstützung für gescannte PDFs)
- 📸 **OCR-Converter** - Konvertiert JPG/PNG/PDF zu durchsuchbaren PDFs mit OCR-Text-Layer
- ⚡ **Parallele Verarbeitung** für schnelle Bearbeitung vieler PDFs
- 🛡️ **Robuste Fehlerbehandlung** mit detailliertem Logging
- ⚙️ **Konfigurierbar** über Umgebungsvariablen

## Datenschutzhinweis

**WICHTIG:** Bei Verwendung von **OpenAI oder Anthropic** sendet dieses Script PDF-Inhalte (die ersten 1000 Zeichen) an externe KI-APIs zur Analyse. 

- **Sensible Daten:** Bei Dokumenten mit persönlichen, vertraulichen oder geschäftskritischen Informationen (z.B. Rechnungen, Beitragsbescheide, Mahnungen, Verträge) werden diese Daten an Drittanbieter übertragen.
- **Datenverarbeitung:** Die Anbieter können diese Daten gemäß ihren Datenschutzbestimmungen verarbeiten. Es gibt keine Garantie, dass die Daten nicht gespeichert oder für Training verwendet werden.
- **Empfehlung:** 
  - **Für sensible Daten:** Verwende **Ollama** (lokal) - alle Daten bleiben auf deinem Rechner, keine Übertragung nach außen
  - **Für nicht-sensible Daten:** OpenAI/Anthropic sind in Ordnung, wenn du mit der Datenübertragung einverstanden bist

## Installation

### 1. Repository klonen oder herunterladen

```bash
git clone https://github.com/tabsl/KI-PDF-Organizer
```

### 2. Setup-Script ausführen

```bash
./setup.sh
```

Das Script erstellt automatisch:
- Eine virtuelle Python-Umgebung (`venv/`)
- Installiert alle benötigten Abhängigkeiten
- Macht die Scripts ausführbar

**Hinweis für OCR-Funktionalität:**
Für die Erkennung von gescannten PDFs wird Tesseract OCR benötigt:
- **macOS**: `brew install tesseract tesseract-lang`
- **Linux**: `sudo apt-get install tesseract-ocr tesseract-ocr-deu` (oder entsprechendes Paket)
- **Windows**: Download von https://github.com/UB-Mannheim/tesseract/wiki

Ohne Tesseract funktioniert die Prüfung weiterhin, erkennt aber nur PDFs mit Text-Layer (keine gescannten PDFs).

### 3. KI-Konfiguration (erforderlich)

Für KI-basierte Dateinamensgenerierung:

1. Kopiere `.env.example` zu `.env`:
   ```bash
   cp .env.example .env
   ```

2. Wähle einen Provider und konfiguriere ihn:

   **Option A: Ollama (lokal, empfohlen für Datenschutz)**
   ```bash
   # Kein API-Key nötig! Alle Daten bleiben lokal.
   AI_PROVIDER=ollama
   OLLAMA_MODEL=llama3.2:3b
   ```
   
   **Ollama Installation:**
   ```bash
   # macOS
   brew install ollama
   brew services start ollama
   ollama pull llama3.2:3b
   ```
   
   **Vorteile:**
   - ✅ Keine Datenübertragung nach außen
   - ✅ Keine API-Keys nötig
   - ✅ Komplett lokal und datenschutzfreundlich
   - ✅ Kostenlos

   **Option B: OpenAI (Cloud)**
   ```bash
   OPENAI_API_KEY=sk-...
   AI_PROVIDER=openai
   OPENAI_MODEL=gpt-4o-mini
   ```
   
   **Option C: Anthropic (Cloud)**
   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   AI_PROVIDER=anthropic
   ANTHROPIC_MODEL=claude-3-5-haiku-20241022
   ```

**API-Keys erhalten:**
- OpenAI: https://platform.openai.com/api-keys
- Anthropic: https://console.anthropic.com/

**WICHTIG:** 
- Für **Ollama**: Kein API-Key nötig, aber Ollama muss laufen
- Für **OpenAI/Anthropic**: Ein API-Key ist erforderlich

## Verwendung

### Umbennen von PDF-Dateien

```bash
# Einzelnes Verzeichnis verarbeiten
./rename.sh "Dr. Müller"

# Mit Dry-Run (zeigt an, was umbenannt würde)
./rename.sh "Dr. Müller" --dry-run

# Rekursiv alle PDFs in einem Verzeichnis verarbeiten
./rename.sh "IHK" --recursive

# Rekursiv mit Dry-Run (kombiniert beide Optionen)
./rename.sh "IHK" --recursive --dry-run

# Mit Parallelisierung (4 parallele Worker)
./rename.sh "Dr. Müller" --parallel 4

# Automatische Parallelisierung (nutzt alle CPU-Kerne)
./rename.sh "IHK" --parallel 0 --recursive

# Mit Ollama (lokal, überschreibt .env)
./rename.sh "Dr. Müller" --provider ollama

# Mit OpenAI (überschreibt .env)
./rename.sh "IHK" --provider openai

# Nur Dateien umbenennen, die "Unbekannt" im Dateinamen haben
./rename.sh "docs/unbekannt" --filter "Unbekannt"

# Nur Dateien umbenennen, die eines von mehreren Wörtern enthalten
./rename.sh "docs" --filter "Unbekannt,Info,Test" --recursive
```

**OCR-Fallback für gescannte PDFs:**
- Das Script verwendet automatisch OCR (Tesseract), wenn:
  - "Unbekannt" im Dateinamen vorkommt (z.B. bei bereits umbenannten Dateien mit schlechter Textextraktion)
  - Die normale Textextraktion zu wenig Text liefert (< 50 Zeichen)
  - Die Textextraktion keine bekannten Begriffe enthält (z.B. bei rückwärts geschriebenem Text)
- OCR wird nur verwendet, wenn Tesseract installiert ist (siehe Installation)
- Die Verwendung von OCR wird in der Ausgabe angezeigt: `→ 'Unbekannt' im Dateinamen gefunden, verwende OCR-Fallback...` oder `→ Textextraktion unzureichend, verwende OCR-Fallback...`
- Bei erfolgreicher OCR: `✓ OCR erfolgreich (X Zeichen extrahiert)`

### Aufsplitten von PDF-Stapeln

Wenn mehrere Dokumente am Stück in eine einzige PDF gescannt wurden, zerlegt `split.sh` die Datei wieder in einzelne Dokumente. Die KI entscheidet seitenweise, wo ein neues Dokument beginnt; anschließend wird jedes Teildokument direkt KI-basiert benannt (`Datum Absender Dokumenttyp`).

```bash
# Stapel-PDF in Einzeldokumente aufsplitten
./split.sh test_files/splittest.pdf

# Nur anzeigen, welche Dokumentgrenzen erkannt würden (ohne Dateien zu schreiben)
./split.sh test_files/splittest.pdf --dry-run

# Alle PDFs eines Verzeichnisses aufsplitten
./split.sh ./scans

# Mit Ollama (lokal, überschreibt .env)
./split.sh splittest.pdf --provider ollama

# Mit OpenAI (überschreibt .env) - deutlich schneller bei vielen Seiten
./split.sh splittest.pdf --provider openai

# OCR-Auflösung anpassen (Standard: 200)
./split.sh splittest.pdf --dpi 300
```

**Funktionsweise:**
- Jede Seite wird einzeln ausgewertet. Seiten ohne eingebettete Textebene (reine Scans) werden per OCR (Tesseract) gelesen.
- Für jeden Seitenübergang fragt die KI fokussiert: neues Dokument (`NEU`) oder Fortsetzung (`FORTSETZUNG`)?
- (Fast) leere Seiten (z.B. gescannte Rückseiten/Trennblätter) werden ohne KI-Aufruf als Fortsetzung des laufenden Dokuments gewertet.
- Die Einzeldokumente landen in einem Unterordner `<dateiname>_split/` neben der Quelldatei; die Originaldatei bleibt unverändert.
- Schlägt die KI-Benennung eines Teildokuments fehl, wird ein nummerierter Name (`<dateiname>_01.pdf`) vergeben. Diese lassen sich später mit `rename.sh` nachbenennen.

**Hinweis zur Geschwindigkeit:** Die seitenweise Analyse erfordert pro Seite einen KI-Aufruf. Mit einem lokalen Ollama-Reasoning-Modell (z.B. `gemma4:26b`) kann ein großer Stapel mehrere Minuten dauern. Für viele Seiten sind die Cloud-Provider (`--provider openai` / `anthropic`) deutlich schneller und meist auch präziser – beachte dafür den [Datenschutzhinweis](#datenschutzhinweis).

### Sortieren von PDF-Dateien

PDFs können basierend auf ihren Dateinamen in Ordner sortiert werden. Das Script nutzt **KI zur Normalisierung** von Absendernamen und Dokumenttypen für konsistente Gruppierung.

**KI-Funktionen:**
- Normalisiert Absendernamen (z.B. "Dr. Müller" und "Dr. Thomas Müller" werden zusammengeführt)
- Normalisiert Dokumenttypen (z.B. "Rechnung", "Rechnungen", "Rechnung 2023" werden zu "Rechnung")
- Erstellt konsistente Ordnerstrukturen

#### Separates Sortier-Script (empfohlen)

```bash
# Sortiert nach Absender (KI-Normalisierung aktiviert)
./sort.sh . --sort sender

# Sortiert nach Jahr
./sort.sh . --sort year

# Sortiert nach Dokumenttyp
./sort.sh . --sort type

# Sortiert nach Absender/Dokumenttyp (zweistufig)
./sort.sh . --sort sender_type

# Sortiert nach Jahr/Absender (zweistufig)
./sort.sh . --sort year_sender

# Mit Dry-Run (zeigt an, was verschoben würde)
./sort.sh . --sort sender --dry-run

# Rekursiv und mit Parallelisierung
./sort.sh . --sort sender --recursive --parallel 4

# KI deaktivieren (nur Regex-Parsing)
./sort.sh . --sort sender --no-ai

# Custom-Sortierung: KI wählt aus vorgegebenen Ordnern
# Mit --folders Argument
./sort.sh . --sort custom --folders "Rechnungen,Verträge,Mahnungen,Beiträge"
./sort.sh . --sort custom --folders "Wichtig,Dringend,Archiv" --dry-run

# Oder mit CUSTOM_FOLDERS aus .env (kein --folders nötig)
./sort.sh . --sort custom

# Mit Ollama (lokal, überschreibt .env)
./sort.sh . --sort sender --provider ollama

# Mit OpenAI (überschreibt .env)
./sort.sh . --sort sender --provider openai
```

**Sortieroptionen:**
- `sender` - Erstellt Ordner nach Absender (z.B. "Dr. Müller", "IHK")
- `year` - Erstellt Ordner nach Jahr (z.B. "2013", "2016", "2022")
- `type` - Erstellt Ordner nach Dokumenttyp (z.B. "Rechnung", "Mahnung", "Beitragsbescheid")
- `sender_type` - Erstellt Ordner nach Absender, dann nach Dokumenttyp
- `year_sender` - Erstellt Ordner nach Jahr, dann nach Absender
- `custom` - KI wählt den passendsten Ordner aus vorgegebenen Ordnern (erfordert `--folders`)

**KI-Normalisierung:**
- Standardmäßig aktiviert, wenn API-Key vorhanden (OpenAI/Anthropic) oder Ollama läuft
- Normalisiert Absendernamen für konsistente Gruppierung
- Normalisiert Dokumenttypen (Singular, konsistent)
- Kann mit `--no-ai` deaktiviert werden (nicht bei custom-Sortierung)

**Custom-Sortierung:**
- KI analysiert den Dateinamen und wählt den passendsten Ordner aus der vorgegebenen Liste
- Ideal für individuelle Ordnerstrukturen (z.B. "Wichtig", "Dringend", "Archiv")
- Ordner können über `--folders` Argument oder `CUSTOM_FOLDERS` in `.env` angegeben werden
- `--folders` überschreibt `CUSTOM_FOLDERS` aus `.env`
- KI ist bei custom-Sortierung zwingend erforderlich
- Dateien, für die kein passender Ordner gefunden wird, werden nach `_unsortiert` verschoben

Dateien, die nicht im erwarteten Format sind, werden nach `_unsortiert` verschoben.

### Duplikate finden

Das Script kann verschiedene Arten von Duplikaten in PDF-Dateien finden:

```bash
# Prüft auf Hash-Duplikate (exakte Duplikate) - Standard
./check_duplicates.sh .

# Prüft auf Dateinamen-Duplikate
./check_duplicates.sh . --name

# Prüft auf Größen-Duplikate (gleiche Dateigröße)
./check_duplicates.sh . --size

# Prüft auf alle Arten von Duplikaten
./check_duplicates.sh . --all

# Hash-Duplikate automatisch löschen (behält erste Datei jeder Gruppe)
./check_duplicates.sh . --hash --delete

# Mit Dry-Run (zeigt an, was gelöscht würde)
./check_duplicates.sh . --hash --delete --dry-run

# Mit Parallelisierung für Hash-Berechnung
./check_duplicates.sh . --hash --parallel 4
```

**Duplikat-Typen:**
- `--hash` - Exakte Duplikate basierend auf SHA256-Hash UND Datum im Dateinamen (Standard)
- `--name` - Dateien mit identischem Dateinamen (aber unterschiedlichen Pfaden)
- `--size` - Dateien mit identischer Dateigröße (kann auf Duplikate hinweisen, ist aber nicht sicher)
- `--all` - Prüft auf alle drei Typen

**Hinweise:**
- Hash-Duplikate sind exakte Kopien derselben Datei **mit gleichem Datum** im Dateinamen
- Dateien mit unterschiedlichem Datum werden nicht als Duplikate betrachtet, auch bei gleichem Hash
- Dateinamen-Duplikate können unterschiedliche Dateien mit gleichem Namen sein
- Größen-Duplikate sind nur ein Hinweis, keine Garantie für echte Duplikate
- Mit `--delete` werden Hash-Duplikate gelöscht (behält die erste Datei jeder Gruppe)

**Dry-Run Modus:**
- **Ohne `--delete`**: `--dry-run` hat keinen Effekt, da nichts gelöscht wird
- **Mit `--delete --dry-run`**: Zeigt an, welche Dateien gelöscht würden, löscht aber **nichts**
- **Mit `--delete` (ohne `--dry-run`)**: Löscht die Duplikate **tatsächlich**
- **Empfehlung**: Immer zuerst mit `--delete --dry-run` testen, bevor ohne `--dry-run` gelöscht wird

### Dateien validieren

Das Script kann Nicht-PDF-Dateien, PDFs ohne Inhalt/OCR und PDFs ohne gültiges Datum am Anfang finden:

```bash
# Prüft auf alle Probleme (Standard)
./validate_files.sh .

# Prüft nur auf Nicht-PDF-Dateien
./validate_files.sh . --non-pdf

# Prüft nur auf PDFs ohne Inhalt/OCR
./validate_files.sh . --no-content

# Prüft nur auf PDFs ohne gültiges Datum am Anfang
./validate_files.sh . --no-date

# Mit Parallelisierung für PDF-Prüfung
./validate_files.sh . --parallel 4
```

**Prüfungen:**
- `--non-pdf` - Findet alle Dateien, die keine PDF-Dateien sind
- `--no-content` - Findet PDFs ohne Text-Inhalt (prüft Text-Layer und OCR)
- `--no-date` - Findet PDFs ohne gültiges Datum am Anfang des Dateinamens (Format: YYYY-MM-DD)
- `--all` - Prüft auf alle Probleme (Standard, wenn keine Option angegeben)

**OCR-Funktionalität:**
- Das Script prüft zuerst den Text-Layer im PDF
- Falls kein Text-Layer vorhanden ist, wird automatisch OCR durchgeführt (falls Tesseract installiert ist)
- Gescannte PDFs werden so erkannt und nicht mehr als "ohne Inhalt" gemeldet
- Ohne Tesseract werden nur PDFs mit Text-Layer erkannt

**Datumsprüfung:**
- Prüft ob der Dateiname mit einem gültigen Datum im Format YYYY-MM-DD beginnt
- Beispiel für gültiges Format: `2013-12-20 Dr. Müller Rechnung.pdf`
- Beispiel für ungültiges Format: `Rechnung.pdf` oder `12-20-2013 Rechnung.pdf`

**Hinweise:**
- Nicht-PDF-Dateien werden mit ihrer Größe angezeigt
- PDFs ohne Inhalt werden mit Grund angezeigt (z.B. "Kein Text-Inhalt gefunden (weder Text-Layer noch OCR)")
- PDFs ohne gültiges Datum werden mit Grund angezeigt
- Die Prüfung erfolgt rekursiv durch alle Verzeichnisse (keine Ausnahmen)
- OCR ist langsamer als Text-Layer-Prüfung, wird aber nur bei Bedarf verwendet

### OCR-Converter

Das Script konvertiert JPG/PNG/PDF zu durchsuchbaren PDFs mit OCR-Text-Layer:

```bash
# Konvertiert alle Dateien im aktuellen Verzeichnis
./ocr_converter.sh .

# Konvertiert ein einzelnes Bild
./ocr_converter.sh bild.jpg

# Speichert konvertierte Dateien in output/
./ocr_converter.sh . --output output/

# Konvertiert auch PDFs mit Text-Layer (überschreibt vorhandenen Text-Layer)
./ocr_converter.sh . --force

# Zeigt an, was konvertiert würde (ohne zu konvertieren)
./ocr_converter.sh . --dry-run

# Mit Parallelisierung (4 parallele Worker)
./ocr_converter.sh . --parallel 4

# Automatische Parallelisierung (nutzt alle CPU-Kerne)
./ocr_converter.sh . --parallel 0

# Nicht rekursiv durchsuchen
./ocr_converter.sh . --no-recursive

# Andere DPI-Einstellung (Standard: 200)
./ocr_converter.sh . --dpi 300
```

**Funktionen:**
- **JPG/PNG → PDF**: Konvertiert Bilder zu durchsuchbaren PDFs mit OCR
- **PDF → PDF**: Fügt Text-Layer zu gescannten PDFs hinzu (ohne Text-Layer)
- **Intelligente Erkennung**: PDFs mit vorhandenem Text-Layer werden standardmäßig übersprungen
- **Parallele Verarbeitung**: Schnellere Bearbeitung bei vielen Dateien

**Hinweise:**
- Bilder werden als PDF gespeichert (Original bleibt erhalten)
- PDFs werden standardmäßig überschrieben (außer mit `--output`)
- PDFs mit Text-Layer werden standardmäßig übersprungen (außer mit `--force`)
- OCR ist langsamer, aber erstellt durchsuchbare PDFs
- Benötigt Tesseract OCR (siehe Installation)

## Dateinamen-Format

Das Script generiert Dateinamen im folgenden Format:

```
[Datum] [Absender] [Dokumenttyp].pdf
```

**Beispiele:**
- `2013-12-20 Dr. Thomas Müller Rechnung.pdf`
- `2016-02-01 IHK Beitragsbescheid.pdf`
- `2022-11-11 IHK Mahnung.pdf`

**Reihenfolge:**
1. **Datum** (Format: YYYY-MM-DD) - steht immer am Anfang, alphabetisch chronologisch sortierbar
2. **Absender/Organisation** (z.B. "Dr. Müller", "IHK")
3. **Dokumenttyp** (z.B. "Rechnung", "Beitragsbescheid", "Mahnung")

## Konfiguration

### Umgebungsvariablen

Die Konfiguration erfolgt über Umgebungsvariablen in der `.env`-Datei:

```bash
# API-Keys (nur für OpenAI/Anthropic, nicht für Ollama)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Provider-Auswahl (openai, anthropic oder ollama)
AI_PROVIDER=openai

# Modell-Auswahl
OPENAI_MODEL=gpt-4o-mini          # Standard: gpt-4o-mini (empfohlen)
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
OLLAMA_MODEL=llama3.2:3b          # Standard: llama3.2:3b (lokal)

# Custom-Sortierung: Komma-getrennte Liste von Ordnernamen
# Wird verwendet, wenn --sort custom ohne --folders Argument verwendet wird
CUSTOM_FOLDERS=Rechnungen,Verträge,Mahnungen,Beiträge

# Textlänge für KI-Analyse (Standard: 1000 Zeichen)
# Wird automatisch auf 1000 gesetzt (ausreichend für die meisten Dokumente)
```

### Empfohlene Modelle

**Cloud (OpenAI/Anthropic):**
- **gpt-4o-mini** (Standard) - Beste Kosten/Leistung für diese Aufgabe
- **claude-3-5-haiku** - Alternative, ähnlich günstig und schnell

**Lokal (Ollama):**
- **llama3.2:3b** (Standard) - Schnell, klein, gut für diese Aufgabe
- **mistral** - Alternative, ähnliche Performance
- **llama3.1:8b** - Größer, bessere Qualität, langsamer

Größere Modelle (gpt-4o, claude-3-5-sonnet) sind für diese Aufgabe nicht notwendig.

## Kommandozeilen-Optionen

### rename.sh

```bash
./rename.sh <ORDNERNAME> [OPTIONEN]

Optionen:
  --dry-run          Zeigt an, was umbenannt würde, ohne tatsächlich umzubenennen
  --recursive, -r    Durchsucht Verzeichnisse rekursiv (automatisch aktiviert)
  --parallel, -p N   Anzahl paralleler Verarbeitungen (Standard: 1, 0 = automatisch)
  --sort MODUS       Sortiert PDFs in Ordner: sender, year, type, sender_type, year_sender
  --provider PROV    KI-Provider: openai, anthropic oder ollama (überschreibt AI_PROVIDER aus .env)
  --filter WÖRTER    Nur Dateien umbenennen, die eines oder mehrere der angegebenen Wörter im Dateinamen enthalten (komma-getrennt, z.B. "Unbekannt,Info")
  --contains WÖRTER  Alias für --filter
```

### split.sh

```bash
./split.sh <PDF-DATEI-ODER-ORDNER> [OPTIONEN]

Optionen:
  --dry-run          Zeigt die erkannten Dokumentgrenzen an, ohne Dateien zu schreiben
  --provider PROV    KI-Provider: openai, anthropic oder ollama (überschreibt AI_PROVIDER aus .env)
  --dpi N            OCR-Auflösung für Seiten ohne Textebene (Standard: 200)
```

### sort.sh

```bash
./sort.sh [PFAD] [OPTIONEN]

Optionen:
  --sort MODUS       Sortierkriterium (Standard: sender)
                     sender, year, type, sender_type, year_sender, custom
  --folders LISTE    Komma-getrennte Liste von Ordnernamen für custom-Sortierung
                     (z.B. "Rechnungen,Verträge,Mahnungen")
  --dry-run          Zeigt an, was verschoben würde, ohne tatsächlich zu verschieben
  --recursive, -r    Durchsucht Verzeichnisse rekursiv (automatisch aktiviert)
  --parallel, -p N   Anzahl paralleler Verarbeitungen (Standard: 1, 0 = automatisch)
  --no-ai            Deaktiviert KI-Normalisierung, verwendet nur Regex-Parsing
                     (nicht erlaubt bei custom-Sortierung)
  --provider PROV    KI-Provider: openai, anthropic oder ollama (überschreibt AI_PROVIDER aus .env)
```

### check_duplicates.sh

```bash
./check_duplicates.sh [PFAD] [OPTIONEN]

Optionen:
  --hash             Prüft auf Hash-Duplikate (exakte Duplikate) - Standard
  --name             Prüft auf Dateinamen-Duplikate
  --size             Prüft auf Größen-Duplikate (gleiche Dateigröße)
  --all              Prüft auf alle Arten von Duplikaten
  --delete           Löscht Hash-Duplikate (behält erste Datei jeder Gruppe)
  --dry-run          Zeigt an, was gelöscht würde, ohne tatsächlich zu löschen
  --recursive, -r    Durchsucht Verzeichnisse rekursiv (automatisch aktiviert)
  --parallel, -p N   Anzahl paralleler Verarbeitungen für Hash-Berechnung (Standard: 1, 0 = automatisch)
```

### validate_files.sh

```bash
./validate_files.sh [PFAD] [OPTIONEN]

Optionen:
  --non-pdf          Prüft nur auf Nicht-PDF-Dateien
  --no-content       Prüft nur auf PDFs ohne Inhalt/OCR
  --no-date          Prüft nur auf PDFs ohne gültiges Datum am Anfang
  --all              Prüft auf alle Probleme (Standard)
  --recursive, -r    Durchsucht Verzeichnisse rekursiv (Standard: aktiviert)
  --parallel, -p N   Anzahl paralleler Verarbeitungen für PDF-Prüfung (Standard: 1, 0 = automatisch)
```

### ocr_converter.sh

```bash
./ocr_converter.sh [PFAD] [OPTIONEN]

Optionen:
  --output, -o DIR   Ausgabe-Verzeichnis (optional, Standard: überschreibt Original)
  --recursive, -r    Durchsucht Verzeichnisse rekursiv (Standard: aktiviert)
  --no-recursive     Nicht rekursiv durchsuchen
  --dpi N            DPI für OCR (Standard: 200)
  --force            Konvertiert auch PDFs mit Text-Layer
  --dry-run          Zeigt an, was konvertiert würde, ohne zu konvertieren
  --parallel, -p N   Anzahl paralleler Verarbeitungen (Standard: 1, 0 = automatisch)
```

**Beispiele:**
- `--parallel 4` - Verwendet 4 parallele Worker
- `--parallel 0` - Automatisch: nutzt alle verfügbaren CPU-Kerne
- Ohne `--parallel` - Sequenzielle Verarbeitung (Standard)

## Dateistruktur

```
dateinamen/
├── rename_pdfs.py          # Hauptscript für Umbenennung
├── split_pdfs.py           # Script zum Aufsplitten von PDF-Stapeln
├── sort_pdfs.py            # Separates Script für Sortierung
├── check_duplicates.py     # Script für Duplikatsprüfung
├── validate_files.py        # Script für Validierung von Dateien
├── ocr_converter.py        # Script für OCR-Konvertierung
├── rename.sh               # Wrapper-Script für Umbenennung
├── split.sh                # Wrapper-Script für PDF-Splitting
├── sort.sh                 # Wrapper-Script für Sortierung
├── check_duplicates.sh     # Wrapper-Script für Duplikatsprüfung
├── validate_files.sh       # Wrapper-Script für Validierung von Dateien
├── ocr_converter.sh        # Wrapper-Script für OCR-Konvertierung
├── setup.sh                # Setup-Script
├── requirements.txt        # Python-Abhängigkeiten
├── .env.example           # Beispiel-Konfiguration
├── .env                   # Eigene Konfiguration (nicht im Git)
├── venv/                  # Virtuelle Umgebung (wird erstellt)
└── README.md             # Diese Datei
```

## Funktionsweise

1. Extrahiert Text aus der PDF (erste 1000 Zeichen, robust gegen fehlerhafte Seiten)
2. Sendet Text an KI-API (OpenAI, Anthropic oder Ollama lokal)
3. KI analysiert Text und generiert Dateinamen
4. Datei wird umbenannt

**Hinweis:** Bei Verwendung von Ollama bleiben alle Daten lokal auf deinem Rechner.

**Vorteile:**
- Präzise Erkennung von Dokumenttypen
- Bessere Absender-Erkennung
- Erkennt auch komplexe Dokumente
- Robuste Text-Extraktion: Fehlerhafte PDF-Seiten werden übersprungen
- Parallele Verarbeitung: Schnellere Bearbeitung bei vielen PDFs
- Strukturiertes Logging: Bessere Fehlerdiagnose und Nachverfolgbarkeit

## Entwicklung

### Abhängigkeiten aktualisieren

```bash
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

**Hinweis:** Die Shell-Scripts (`rename.sh`, `sort.sh`) aktivieren automatisch die virtuelle Umgebung. Direkte Python-Aufrufe sind nicht notwendig.

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

**Hinweis zu Abhängigkeiten:** Das Split-Feature nutzt [PyMuPDF](https://pymupdf.readthedocs.io/), das unter der **AGPL-3.0** (oder einer kommerziellen Lizenz) steht. Der MIT-lizenzierte Code dieses Projekts bleibt davon unberührt, da PyMuPDF nur als Abhängigkeit über `pip` installiert (nicht mitgeliefert) wird. Wer das Gesamtwerk inklusive PyMuPDF weiterverbreitet, muss jedoch die AGPL-Bedingungen von PyMuPDF beachten.