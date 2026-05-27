#!/usr/bin/env python3
"""
Script zum Umbenennen von PDF-Dateien basierend auf ihrem Inhalt.
Extrahiert relevante Informationen (Datum, Absender, Dokumenttyp) und erstellt sinnvolle Dateinamen.
"""

import os
import re
import sys
import logging
from pathlib import Path
from typing import Optional
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("Fehler: pdfplumber ist nicht installiert.")
    print("Installiere es mit: pip install pdfplumber")
    sys.exit(1)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    pytesseract = None
    convert_from_path = None

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def fix_reversed_text(text: str) -> str:
    """Korrigiert rückwärts geschriebenen Text (häufig bei gescannten PDFs).
    Prüft, ob der Text rückwärts ist, indem nach bekannten deutschen Wörtern gesucht wird."""
    if not text or len(text.strip()) < 10:
        return text
    
    # Häufige deutsche Wörter, die in lesbarem Text vorkommen, beim Rückwärtslesen
    # aber zu Unsinn werden. Bewusst generisch gehalten (keine Eigennamen).
    known_terms = [
        'und', 'für', 'mit', 'von', 'GmbH', 'Rechnung', 'Datum', 'Betrag',
        'Sehr geehrte', 'Straße', 'Nummer', 'Telefon', 'freundlichen Grüßen'
    ]

    original_has_known = any(term.lower() in text.lower() for term in known_terms)
    
    if original_has_known:
        return text
    
    lines = text.split('\n')
    fixed_lines = []
    for line in lines:
        if not line.strip():
            fixed_lines.append(line)
            continue
        
        words = line.split()
        fixed_words = []
        for word in words:
            if len(word) > 2:
                reversed_word = word[::-1]
                fixed_words.append(reversed_word)
            else:
                fixed_words.append(word)
        fixed_line = ' '.join(fixed_words)
        fixed_lines.append(fixed_line)
    
    fixed_text = '\n'.join(fixed_lines)
    fixed_has_known = any(term.lower() in fixed_text.lower() for term in known_terms)
    
    if fixed_has_known:
        return fixed_text
    
    return text


def extract_text_from_pdf(pdf_path: Path, use_ocr: bool = False) -> str:
    """Extrahiert Text aus einer PDF-Datei."""
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except Exception as e:
                    logger.debug(f"Fehler beim Extrahieren von Seite {page_num} in {pdf_path}: {e}")
                    continue
        
        has_unknown_in_filename = "unbekannt" in pdf_path.name.lower()
        text_length = len(text.strip()) if text else 0
        has_known_terms = False
        
        if text and text_length > 50:
            fixed_text = fix_reversed_text(text)
            # Generische deutsche Wörter + gängige Dokumenttypen (keine Eigennamen),
            # um zu prüfen, ob die Textextraktion plausibel lesbar ist.
            known_terms = [
                'und', 'für', 'mit', 'von', 'GmbH', 'Datum', 'Betrag', 'Sehr geehrte',
                'Straße', 'Nummer', 'Telefon', 'Rechnung', 'Bescheinigung', 'Info',
                'Mahnung', 'Abrechnung', 'Bescheid', 'Vertrag'
            ]
            has_known_terms = any(term.lower() in fixed_text.lower() for term in known_terms)
            
            if not has_unknown_in_filename and has_known_terms:
                return fixed_text
        
        should_use_ocr = (
            has_unknown_in_filename or 
            not text or 
            text_length < 50 or 
            (text_length > 50 and not has_known_terms)
        )
        
        if use_ocr and should_use_ocr:
            if OCR_AVAILABLE:
                if has_unknown_in_filename:
                    logger.info("  → 'Unbekannt' im Dateinamen gefunden, verwende OCR-Fallback...")
                else:
                    logger.info("  → Textextraktion unzureichend, verwende OCR-Fallback...")
                try:
                    with pdfplumber.open(pdf_path) as pdf:
                        num_pages = len(pdf.pages)
                    images = convert_from_path(str(pdf_path), dpi=200, first_page=1, last_page=min(3, num_pages))
                    ocr_text = ""
                    for page_num, image in enumerate(images, 1):
                        try:
                            page_text = pytesseract.image_to_string(image, lang='deu+eng')
                            if page_text:
                                ocr_text += page_text + "\n"
                        except Exception as e:
                            logger.debug(f"Fehler bei OCR von Seite {page_num}: {e}")
                            continue
                    if ocr_text and len(ocr_text.strip()) > 50:
                        logger.info(f"  ✓ OCR erfolgreich ({len(ocr_text.strip())} Zeichen extrahiert)")
                        return ocr_text
                    else:
                        logger.warning("  ⚠️  OCR hat zu wenig Text extrahiert")
                except pytesseract.TesseractNotFoundError:
                    logger.warning("  ⚠️  Tesseract OCR nicht gefunden - OCR-Fallback nicht verfügbar")
                except Exception as e:
                    logger.warning(f"  ⚠️  OCR-Fehler: {e}")
            else:
                logger.info("  → Textextraktion unzureichend, aber OCR nicht verfügbar (pytesseract/pdf2image fehlt)")
        
        if text:
            fixed_text = fix_reversed_text(text)
            return fixed_text
        return text
    except pdfplumber.exceptions.PDFSyntaxError as e:
        logger.warning(f"PDF-Syntaxfehler in {pdf_path}: {e}")
        return ""
    except Exception as e:
        logger.error(f"Fehler beim Lesen von {pdf_path}: {e}")
        return ""


def sanitize_filename(name: str) -> str:
    """Bereinigt Dateinamen von ungültigen Zeichen."""
    invalid_chars = r'[<>:"/\\|?*]'
    name = re.sub(invalid_chars, '', name)
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    # Führende/anhängende Punkte entfernen: neutralisiert "." und ".."
    # als eigenständiges Pfad-Segment (Path-Traversal-Schutz)
    name = name.strip('.').strip()
    return name or "_unbekannt"


def is_within_base(base_path: Path, target_dir: Path) -> bool:
    """Prüft, ob target_dir innerhalb von base_path liegt (Path-Traversal-Schutz)."""
    try:
        base_resolved = base_path.resolve()
        target_resolved = target_dir.resolve()
    except OSError:
        return False
    return base_resolved == target_resolved or base_resolved in target_resolved.parents


def clean_ollama_response(text: str) -> str:
    """Bereinigt Ollama-Antworten, die Erklärungen enthalten."""
    text = text.strip()
    
    patterns_to_remove = [
        r'^Basierend auf dem PDF-Text.*?Der Dateiname wäre also\s+',
        r'^Basierend auf dem PDF-Text.*?Die Datei würde also folgender Name haben\s+',
        r'^Basierend auf dem PDF-Text.*?kann ich den Dateinamen wie folgt erstellen\s+',
        r'^Basierend auf dem PDF-Text.*?kann ich folgendes extrahieren.*?Der Dateiname wäre also\s+',
        r'^Basierend auf dem PDF-Text.*?Die Datei würde also folgender Name haben\s+',
        r'^.*?Der Dateiname wäre also\s+',
        r'^.*?Die Datei würde also folgender Name haben\s+',
        r'^.*?kann ich den Dateinamen wie folgt erstellen\s+',
        r'^.*?Dateiname:\s*',
        r'^.*?wäre\s+',
        r'^.*?hätte\s+',
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    text = text.strip()
    
    date_pattern = r'(\d{2}\.\d{2}\.\d{4})'
    match = re.search(date_pattern, text)
    if match:
        start_pos = match.start()
        text = text[start_pos:]
    
    lines = text.split('\n')
    if lines:
        first_line = lines[0].strip()
        if re.match(r'^\d{2}\.\d{2}\.\d{4}', first_line):
            text = first_line
    
    return text.strip()


def check_ollama_available() -> bool:
    """Prüft, ob Ollama läuft und erreichbar ist."""
    try:
        req = urllib.request.Request('http://localhost:11434/api/tags')
        urllib.request.urlopen(req, timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def generate_filename_with_ai(text: str, provider: str = "openai") -> Optional[str]:
    """Generiert einen Dateinamen mit KI basierend auf dem PDF-Text."""
    api_key = None
    client = None
    
    if provider == "ollama":
        if not OPENAI_AVAILABLE:
            logger.warning("  ⚠️  OpenAI-Bibliothek benötigt für Ollama-Support")
            return None
        if not check_ollama_available():
            logger.warning("  ⚠️  Ollama läuft nicht oder ist nicht erreichbar (http://localhost:11434)")
            logger.warning("  ⚠️  Starte Ollama mit: brew services start ollama")
            return None
        try:
            ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama"
            )
        except Exception as e:
            logger.warning(f"  ⚠️  Fehler beim Erstellen des Ollama Clients: {e}")
            return None
    elif provider == "openai" and OPENAI_AVAILABLE:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("  ⚠️  Kein OpenAI API-Key gefunden")
            return None
        try:
            client = OpenAI(api_key=api_key)
        except Exception as e:
            logger.warning(f"  ⚠️  Fehler beim Erstellen des OpenAI Clients: {e}")
            return None
    elif provider == "anthropic" and ANTHROPIC_AVAILABLE:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("  ⚠️  Kein Anthropic API-Key gefunden")
            return None
        try:
            client = Anthropic(api_key=api_key)
        except Exception as e:
            logger.warning(f"  ⚠️  Fehler beim Erstellen des Anthropic Clients: {e}")
            return None
    else:
        if provider == "openai" and not OPENAI_AVAILABLE:
            logger.warning("  ⚠️  OpenAI-Bibliothek nicht verfügbar")
        elif provider == "anthropic" and not ANTHROPIC_AVAILABLE:
            logger.warning("  ⚠️  Anthropic-Bibliothek nicht verfügbar")
        else:
            logger.warning(f"  ⚠️  Unbekannter Provider: {provider}")
        return None
    
    text_preview = text[:3000]
    
    if provider == "ollama":
        prompt = """Gib NUR den Dateinamen zurück, KEINE Erklärung!

Format: [Datum] [Absender] [Dokumenttyp]

Extrahiere aus dem PDF-Text:
1. Datum (YYYY-MM-DD)
2. Absender (vollständiger Name)
3. Dokumenttyp (Rechnung, Abrechnung, etc.)

NUR der Dateiname, sonst nichts!

Beispiele:
2013-12-20 Musterfirma GmbH Abrechnung
2004-12-02 Beispiel AG Rechnung
2009-01-07 Test Versicherung Kündigung

PDF-Text:
{text}

Dateiname:"""
    else:
        prompt = """Analysiere den folgenden PDF-Text und erstelle einen präzisen, aussagekräftigen Dateinamen.

Format: [Datum] [Absender/Organisation] [DokUMENTtyp]

ABSOLUT KRITISCHE REGELN - KEINE AUSNAHMEN:
1. DATUM - MUSS IMMER VORHANDEN SEIN:
   - Das Datum MUSS IMMER am Anfang stehen
   - Format: YYYY-MM-DD (z.B. "2023-10-30", "2020-06-07")
   - Extrahiere das Datum NUR AUS DEM DOKUMENT-TEXT, niemals erfinden oder raten
   - Suche nach: Datum, Datum:, vom, vom:, erstellt am, erstellt:, etc.
   - Wenn der Text gescannt/verzerrt ist, suche nach Zahlenfolgen wie "2023.10.30", "30.10.2023", "2023-10-30"
   - WICHTIG: Bei gescannten PDFs kann der Text RÜCKWÄRTS geschrieben sein (z.B. "g n u n h c e R" = "Rechnung")
   - Wenn du rückwärts geschriebenen Text erkennst, interpretiere ihn korrekt
   - Prüfe sorgfältig: Jahreszahl (4 Ziffern), Monat (01-12), Tag (01-31) müssen korrekt sein
   - Wenn mehrere Daten vorhanden sind, verwende das Dokumentdatum (Datum des Dokuments, nicht Rechnungsdatum)
   - Bei Behördenbriefen: Verwende das Datum des Briefes (meist oben rechts oder im Briefkopf), nicht das Datum von Ereignissen im Text
   - Wenn kein Datum im Dokument gefunden wird, versuche es aus anderen Hinweisen zu extrahieren (z.B. aus dem Kontext)

2. ABSENDER:
   - Extrahiere den vollständigen Namen der Organisation/Person
   - Suche nach: Absender, Von, Anbieter, Firma, Unternehmen, Behörde, Amt, etc.
   - Suche auch in Kopfzeilen, Fußzeilen, Briefkopf, Logo-Bereich
   - WICHTIG: Bei gescannten PDFs kann der Text verzerrt oder RÜCKWÄRTS geschrieben sein
   - Beispiel rückwärts: "g n u n h c e R" = "Rechnung", "t m a z n a n i F" = "Finanzamt"
   - Wenn du rückwärts geschriebenen Text erkennst, interpretiere ihn korrekt und extrahiere den Absender
   - Typische Absender sind Firmen (GmbH, AG), Behörden/Ämter (Finanzamt, Stadt, Bundesamt), Versicherungen, Kanzleien, Praxen, Kliniken
   - Suche auch nach Teilen des Namens, auch wenn sie verzerrt oder rückwärts geschrieben sind
   - Verwende "Unbekannt" NUR wenn wirklich kein Absender identifizierbar ist (nach gründlicher Suche im gesamten Text)
   - WICHTIG: Versuche IMMER einen Absender zu finden - suche nach Firmennamen, Behörden, Organisationen, Absendern, etc.
   - Nur wenn wirklich KEIN Absender gefunden werden kann, verwende "Unbekannt" (aber das sollte sehr selten sein)
   - Kürze lange Namen sinnvoll (z.B. "Beispiel Versicherung AG" → "Beispiel Versicherung")

3. DOKUMENTTYP:
   - Rechnung, Abrechnung, Beitragsbescheid, Mahnung, Kostenvoranschlag, Info, Einverständniserklärung, Fragebogen, Bescheinigung, Betroffenen-Anhörungsbogen, etc.
   - Verwende präzise Bezeichnungen aus dem Dokument

4. FORMAT - STRENG EINHALTEN:
   - Reihenfolge: Datum → Absender → Dokumenttyp
   - Nur der Dateiname, keine Erklärung, keine Anführungszeichen, keine zusätzlichen Wörter
   - Maximal 100 Zeichen
   - Keine Dateiendung (.pdf) hinzufügen
   - Starte IMMER mit dem Datum im Format YYYY-MM-DD

Beispiele korrekter Dateinamen:
- 2023-10-30 Stadtverwaltung Info
- 2020-06-07 Musterfirma GmbH Kostenvoranschlag
- 2021-06-21 Unbekannt Info (nur wenn wirklich kein Absender gefunden)
- 2022-07-29 Beispiel Versicherung Bescheinigung
- 2023-10-20 Unbekannt Anhörungsbogen

WICHTIG: Der Dateiname MUSS mit einem Datum im Format YYYY-MM-DD beginnen. Suche gründlich nach Daten im Text, auch wenn der Text gescannt oder verzerrt ist.

PDF-Text:
{text}

Dateiname:"""

    try:
        if provider == "ollama":
            ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            response = client.chat.completions.create(
                model=ollama_model,
                messages=[
                    {"role": "system", "content": "Du bist ein präziser Experte für Dokumentenanalyse. Du extrahierst exakt Datum, Absender und Dokumenttyp aus PDF-Texten und erstellst präzise Dateinamen ohne Fehler."},
                    {"role": "user", "content": prompt.format(text=text_preview)}
                ],
                temperature=0.1,
                # Hoch genug, damit auch Reasoning-Modelle (z.B. gemma4) durch ihren
                # internen Denkprozess kommen und danach den eigentlichen Dateinamen
                # in content liefern. Klassische Modelle stoppen ohnehin früher.
                max_tokens=4000
            )
            filename = response.choices[0].message.content.strip()
        elif provider == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Du bist ein präziser Experte für Dokumentenanalyse. Du extrahierst exakt Datum, Absender und Dokumenttyp aus PDF-Texten und erstellst präzise Dateinamen. Du prüfst sorgfältig, dass das Datum korrekt aus dem Dokument extrahiert wurde und nicht verfälscht ist."},
                    {"role": "user", "content": prompt.format(text=text_preview)}
                ],
                temperature=0.2,
                max_tokens=100
            )
            filename = response.choices[0].message.content.strip()
        else:
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
            response = client.messages.create(
                model=model,
                max_tokens=100,
                temperature=0.2,
                system="Du bist ein präziser Experte für Dokumentenanalyse. Du extrahierst exakt Datum, Absender und Dokumenttyp aus PDF-Texten und erstellst präzise Dateinamen. Du prüfst sorgfältig, dass das Datum korrekt aus dem Dokument extrahiert wurde und nicht verfälscht ist.",
                messages=[
                    {"role": "user", "content": prompt.format(text=text_preview)}
                ]
            )
            filename = response.content[0].text.strip()
        
        if not filename:
            logger.warning("  ⚠️  KI hat leere Antwort zurückgegeben")
            return None
        
        if provider == "ollama":
            filename = clean_ollama_response(filename)
        
        filename = filename.strip('"\'')
        if filename.endswith('.pdf'):
            filename = filename[:-4]
        
        filename = sanitize_filename(filename)
        if filename and len(filename) > 0:
            return filename
        return None
        
    except Exception as e:
        logger.warning(f"  ⚠️  KI-Fehler: {e}")
        import traceback
        if os.getenv("DEBUG", "0") == "1":
            traceback.print_exc()
        return None


def extract_date_from_filename(filename: str) -> Optional[str]:
    """Extrahiert ein Datum aus einem Dateinamen im Format YYYY-MM-DD."""
    date_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', filename)
    if date_match:
        try:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            if 1900 <= year <= datetime.now().year + 1 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass
    return None


def generate_filename(text: str, original_path: Path, provider: Optional[str] = None) -> Optional[str]:
    """Generiert einen neuen Dateinamen basierend auf dem PDF-Inhalt mit KI."""
    if provider is None:
        provider = os.getenv("AI_PROVIDER", "openai").lower()
    else:
        provider = provider.lower()
    if provider in ["openai", "anthropic", "ollama"]:
        filename = generate_filename_with_ai(text, provider=provider)
        if filename:
            if filename.endswith('.pdf'):
                filename = filename[:-4]
            date_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', filename)
            if not date_match:
                existing_date = extract_date_from_filename(original_path.stem)
                if existing_date:
                    logger.info(f"  → Verwende Datum aus Dateinamen: {existing_date}")
                    filename = f"{existing_date} {filename}"
                else:
                    logger.warning(f"  ⚠️  Kein Datum im Format YYYY-MM-DD gefunden im generierten Dateinamen: {filename}")
                    logger.warning("  ⚠️  Kein Datum gefunden - weder im Dokument noch im Dateinamen")
                    return None
            
            if "unbekannt" in filename.lower():
                logger.warning("  ⚠️  KI hat 'Unbekannt' als Absender zurückgegeben - Dateiname wird nicht akzeptiert")
                logger.warning("  ⚠️  Bitte prüfe das Dokument manuell oder verwende OCR für bessere Textextraktion")
                return None
            
            date_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', filename)
            if date_match:
                try:
                    year = int(date_match.group(1))
                    month = int(date_match.group(2))
                    day = int(date_match.group(3))
                    current_year = datetime.now().year
                    if year < 1900 or year > current_year + 1:
                        logger.warning(f"  ⚠️  Unplausibles Jahr {year} im Dateinamen - möglicherweise falsch extrahiert")
                    if month < 1 or month > 12:
                        logger.warning(f"  ⚠️  Ungültiger Monat {month} im Dateinamen")
                    if day < 1 or day > 31:
                        logger.warning(f"  ⚠️  Ungültiger Tag {day} im Dateinamen")
                except ValueError:
                    logger.warning(f"  ⚠️  Fehler beim Parsen des Datums im Dateinamen: {filename}")
                    return None
            
            return filename + '.pdf'
        return None
    return None


def parse_filename(filename: str) -> Optional[dict]:
    """Parst einen Dateinamen im Format [Datum] [Absender] [Dokumenttyp].pdf
    Erwartet Datum im Format YYYY-MM-DD."""
    if not filename.endswith('.pdf'):
        return None
    
    name_without_ext = filename[:-4]
    
    date_pattern = r'^(\d{4})-(\d{2})-(\d{2})\s+(.+)$'
    match = re.match(date_pattern, name_without_ext)
    
    if not match:
        return None
    
    year = match.group(1)
    month = match.group(2)
    day = match.group(3)
    rest = match.group(4).strip()
    date_str = f"{year}-{month}-{day}"
    
    try:
        year_int = int(year)
        month_int = int(month)
    except ValueError:
        return None
    
    parts = rest.split()
    if len(parts) < 2:
        return None
    
    document_type = parts[-1]
    sender = ' '.join(parts[:-1])
    
    return {
        'date': date_str,
        'year': year_int,
        'month': month_int,
        'sender': sender,
        'document_type': document_type,
        'original': filename
    }


def sort_pdf(pdf_path: Path, base_path: Path, sort_by: str = "sender", dry_run: bool = False) -> bool:
    """Sortiert eine PDF-Datei in einen Ordner basierend auf dem Dateinamen."""
    logger.info(f"\nVerarbeite: {pdf_path}")
    
    parsed = parse_filename(pdf_path.name)
    
    if not parsed:
        logger.warning(f"  ⚠️  Konnte Dateinamen nicht parsen: {pdf_path.name}")
        logger.warning("  ⚠️  Verschiebe nach _unsortiert")
        
        unsorted_dir = base_path / "_unsortiert"
        
        if dry_run:
            logger.info(f"  [DRY-RUN] Würde verschieben nach: {unsorted_dir / pdf_path.name}")
            return True
        
        try:
            unsorted_dir.mkdir(exist_ok=True)
            new_path = unsorted_dir / pdf_path.name
            
            if new_path.exists():
                counter = 1
                while new_path.exists():
                    name_part = pdf_path.stem
                    new_path = unsorted_dir / f"{name_part}-{counter}.pdf"
                    counter += 1
            
            pdf_path.rename(new_path)
            logger.info(f"  ✓ Verschoben nach: {new_path}")
            return True
        except Exception as e:
            logger.error(f"  ✗ Fehler beim Verschieben: {e}")
            return False
    
    if sort_by == "sender":
        target_dir = base_path / sanitize_filename(parsed['sender'])
    elif sort_by == "year":
        target_dir = base_path / str(parsed['year'])
    elif sort_by == "type":
        target_dir = base_path / sanitize_filename(parsed['document_type'])
    elif sort_by == "sender_type":
        sender_dir = sanitize_filename(parsed['sender'])
        type_dir = sanitize_filename(parsed['document_type'])
        target_dir = base_path / sender_dir / type_dir
    elif sort_by == "year_sender":
        year_dir = str(parsed['year'])
        sender_dir = sanitize_filename(parsed['sender'])
        target_dir = base_path / year_dir / sender_dir
    else:
        logger.error(f"  ✗ Unbekanntes Sortierkriterium: {sort_by}")
        return False

    if not is_within_base(base_path, target_dir):
        logger.error(f"  ✗ Ungültiges Zielverzeichnis (Path-Traversal abgewehrt): {target_dir}")
        return False

    new_path = target_dir / pdf_path.name

    if new_path == pdf_path:
        logger.info("  ✓ Datei ist bereits im richtigen Ordner")
        return True
    
    if dry_run:
        logger.info(f"  [DRY-RUN] Würde verschieben nach: {new_path}")
        return True
    
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        
        if new_path.exists():
            counter = 1
            while new_path.exists():
                name_part = pdf_path.stem
                new_path = target_dir / f"{name_part}-{counter}.pdf"
                counter += 1
            logger.info(f"  → Verwende: {new_path.name}")
        
        pdf_path.rename(new_path)
        logger.info(f"  ✓ Verschoben nach: {new_path}")
        return True
    except OSError as e:
        logger.error(f"  ✗ Fehler beim Verschieben (OS-Fehler): {e}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Fehler beim Verschieben: {e}")
        return False


def rename_pdf(pdf_path: Path, dry_run: bool = False, provider: Optional[str] = None) -> bool:
    """Benennt eine PDF-Datei um."""
    logger.info(f"\nVerarbeite: {pdf_path}")
    
    text = extract_text_from_pdf(pdf_path, use_ocr=True)
    if not text or len(text.strip()) < 10:
        logger.warning("  ⚠️  Konnte keinen Text extrahieren - verschiebe nach _check")
        
        check_dir = pdf_path.parent / "_check"
        
        if dry_run:
            logger.info(f"  [DRY-RUN] Würde verschieben nach: {check_dir / pdf_path.name}")
            return True
        
        try:
            check_dir.mkdir(exist_ok=True)
            new_path = check_dir / pdf_path.name
            
            if new_path.exists():
                counter = 1
                while new_path.exists():
                    name_part = pdf_path.stem
                    new_path = check_dir / f"{name_part}-{counter}.pdf"
                    counter += 1
            
            pdf_path.rename(new_path)
            logger.info(f"  ✓ Verschoben nach: {new_path}")
            return True
        except OSError as e:
            logger.error(f"  ✗ Fehler beim Verschieben (OS-Fehler): {e}")
            return False
        except Exception as e:
            logger.error(f"  ✗ Fehler beim Verschieben: {e}")
            return False
    
    new_filename = generate_filename(text, pdf_path, provider=provider)
    
    if not new_filename:
        logger.warning("  ⚠️  Konnte keinen Dateinamen generieren")
        return False
    
    new_path = pdf_path.parent / new_filename
    
    if new_path == pdf_path:
        logger.info("  ✓ Dateiname ist bereits korrekt")
        return True
    
    if new_path.exists():
        logger.warning(f"  ⚠️  Ziel-Datei existiert bereits: {new_filename}")
        counter = 1
        while new_path.exists():
            name_part = new_filename.rsplit('.pdf', 1)[0]
            new_filename = f"{name_part}-{counter}.pdf"
            new_path = pdf_path.parent / new_filename
            counter += 1
        logger.info(f"  → Verwende: {new_filename}")
    
    if dry_run:
        logger.info(f"  [DRY-RUN] Würde umbenennen zu: {new_filename}")
        return True
    
    try:
        pdf_path.rename(new_path)
        logger.info(f"  ✓ Umbenannt zu: {new_filename}")
        return True
    except OSError as e:
        logger.error(f"  ✗ Fehler beim Umbenennen (OS-Fehler): {e}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Fehler beim Umbenennen: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Benennt PDF-Dateien basierend auf ihrem Inhalt um oder sortiert sie in Ordner'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Pfad zu PDF-Dateien oder Verzeichnis (Standard: aktuelles Verzeichnis)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Zeigt an, was umbenannt würde, ohne tatsächlich umzubenennen'
    )
    parser.add_argument(
        '--recursive',
        '-r',
        action='store_true',
        help='Durchsucht Verzeichnisse rekursiv'
    )
    parser.add_argument(
        '--parallel',
        '-p',
        type=int,
        default=1,
        metavar='N',
        help='Anzahl paralleler Verarbeitungen (Standard: 1, 0 = automatisch)'
    )
    parser.add_argument(
        '--sort',
        choices=['sender', 'year', 'type', 'sender_type', 'year_sender'],
        help='Sortiert PDFs in Ordner: sender (nach Absender), year (nach Jahr), type (nach Dokumenttyp), sender_type (nach Absender/Dokumenttyp), year_sender (nach Jahr/Absender)'
    )
    parser.add_argument(
        '--provider',
        choices=['openai', 'anthropic', 'ollama'],
        help='KI-Provider: openai, anthropic oder ollama (überschreibt AI_PROVIDER aus .env)'
    )
    parser.add_argument(
        '--filter',
        '--contains',
        type=str,
        help='Nur Dateien umbenennen, die eines oder mehrere der angegebenen Wörter im Dateinamen enthalten (komma-getrennt, z.B. "Unbekannt,Info")'
    )
    
    args = parser.parse_args()
    
    path = Path(args.path)
    
    if not path.exists():
        logger.error(f"Fehler: Pfad existiert nicht: {path}")
        sys.exit(1)
    
    pdf_files = []
    
    if path.is_file() and path.suffix.lower() == '.pdf':
        pdf_files = [path]
    elif path.is_dir():
        if args.recursive:
            pdf_files = [f for f in path.rglob('*.pdf') if '_check' not in f.parts]
            pdf_files.extend([f for f in path.rglob('*.PDF') if '_check' not in f.parts])
        else:
            pdf_files = list(path.glob('*.pdf'))
            pdf_files.extend(list(path.glob('*.PDF')))
    else:
        logger.error(f"Fehler: {path} ist weder eine PDF-Datei noch ein Verzeichnis")
        sys.exit(1)
    
    if not pdf_files:
        logger.info("Keine PDF-Dateien gefunden.")
        sys.exit(0)
    
    if args.filter:
        filter_words_raw = [word.strip() for word in args.filter.split(',')]
        filter_words = [word.lower() for word in filter_words_raw]
        original_count = len(pdf_files)
        pdf_files = [
            f for f in pdf_files
            if any(word in f.name.lower() for word in filter_words)
        ]
        if len(pdf_files) < original_count:
            logger.info(f"Gefiltert: {len(pdf_files)}/{original_count} PDF-Datei(en) enthalten eines der Wörter: {', '.join(filter_words_raw)}")
        if not pdf_files:
            logger.info("Keine PDF-Dateien gefunden, die den Filterkriterien entsprechen.")
            sys.exit(0)
    
    logger.info(f"Gefunden: {len(pdf_files)} PDF-Datei(en)")
    
    if args.sort:
        if args.dry_run:
            logger.info("DRY-RUN Modus: Es werden keine Dateien verschoben")
        logger.info(f"📁 Sortiere Dateien nach: {args.sort}")
        
        base_path = path if path.is_dir() else path.parent
        
        success_count = 0
        max_workers = args.parallel if args.parallel > 0 else min(len(pdf_files), os.cpu_count() or 1)
        
        if max_workers == 1 or len(pdf_files) == 1:
            for pdf_file in pdf_files:
                if sort_pdf(pdf_file, base_path, sort_by=args.sort, dry_run=args.dry_run):
                    success_count += 1
        else:
            logger.info(f"Verarbeite {len(pdf_files)} Dateien mit {max_workers} parallelen Workern")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(sort_pdf, pdf_file, base_path, args.sort, args.dry_run): pdf_file
                    for pdf_file in pdf_files
                }
                for future in as_completed(future_to_file):
                    if future.result():
                        success_count += 1
        
        logger.info(f"\n✓ {success_count}/{len(pdf_files)} Dateien erfolgreich sortiert")
        return
    
    if args.dry_run:
        logger.info("DRY-RUN Modus: Es werden keine Dateien umbenannt")
    
    ai_provider = args.provider.lower() if args.provider else os.getenv("AI_PROVIDER", "openai").lower()
    if ai_provider == "ollama":
        if not check_ollama_available():
            logger.error("❌ Ollama läuft nicht oder ist nicht erreichbar!")
            logger.error("   Starte Ollama mit: brew services start ollama")
            logger.error("   Stelle sicher, dass ein Modell installiert ist: ollama pull llama3.2:3b")
            sys.exit(1)
    else:
        api_key = os.getenv("OPENAI_API_KEY") if ai_provider == "openai" else os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("❌ Kein API-Key gefunden!")
            logger.error("   Setze OPENAI_API_KEY oder ANTHROPIC_API_KEY Umgebungsvariable.")
            logger.error("   Das Script benötigt einen API-Key für die KI-basierte Dateinamensgenerierung.")
            sys.exit(1)
    
    logger.info(f"🤖 Verwende KI ({ai_provider}) für Dateinamensgenerierung")
    
    success_count = 0
    max_workers = args.parallel if args.parallel > 0 else min(len(pdf_files), os.cpu_count() or 1)
    
    if max_workers == 1 or len(pdf_files) == 1:
        for pdf_file in pdf_files:
            if rename_pdf(pdf_file, dry_run=args.dry_run, provider=ai_provider):
                success_count += 1
    else:
        logger.info(f"Verarbeite {len(pdf_files)} Dateien mit {max_workers} parallelen Workern")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(rename_pdf, pdf_file, args.dry_run, ai_provider): pdf_file
                for pdf_file in pdf_files
            }
            for future in as_completed(future_to_file):
                if future.result():
                    success_count += 1
    
    logger.info(f"\n✓ {success_count}/{len(pdf_files)} Dateien erfolgreich verarbeitet")


if __name__ == '__main__':
    main()

