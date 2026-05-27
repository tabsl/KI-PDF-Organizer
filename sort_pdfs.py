#!/usr/bin/env python3
"""
Script zum Sortieren von PDF-Dateien in Ordner basierend auf ihren Dateinamen.
Erwartet Dateinamen im Format: [Datum] [Absender] [Dokumenttyp].pdf
Nutzt KI zur Normalisierung von Absendernamen und Dokumenttypen.
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

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


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


def check_ollama_available() -> bool:
    """Prüft, ob Ollama läuft und erreichbar ist."""
    try:
        req = urllib.request.Request('http://localhost:11434/api/tags')
        urllib.request.urlopen(req, timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def select_folder_with_ai(filename: str, available_folders: list[str], provider: str = "openai", parsed_data: Optional[dict] = None) -> Optional[str]:
    """Wählt mit KI den passendsten Ordner für ein Dokument aus."""
    api_key = None
    client = None
    
    if provider == "ollama":
        if not OPENAI_AVAILABLE:
            return None
        if not check_ollama_available():
            return None
        try:
            client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama"
            )
        except Exception:
            return None
    elif provider == "openai" and OPENAI_AVAILABLE:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            client = OpenAI(api_key=api_key)
        except Exception:
            return None
    elif provider == "anthropic" and ANTHROPIC_AVAILABLE:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            client = Anthropic(api_key=api_key)
        except Exception:
            return None
    else:
        return None
    
    folders_str = ", ".join(available_folders)
    
    context_info = ""
    if parsed_data:
        sender = parsed_data.get('sender', '')
        doc_type = parsed_data.get('document_type', '')
        date = parsed_data.get('date', '')
        context_info = f"""
Dokumentdetails:
- Datum: {date}
- Absender: {sender}
- Dokumenttyp: {doc_type}

"""
    
    prompt = f"""Analysiere das folgende Dokument und wähle den passendsten Ordner aus.

Dateiname: {filename}
{context_info}Verfügbare Ordner: {folders_str}

Dateinamen-Format: [Datum] [Absender] [Dokumenttyp].pdf

WICHTIG: 
- Analysiere den Dokumenttyp (letztes Wort vor .pdf) als Hauptkriterium
- Berücksichtige auch den Absender, wenn relevant
- Wähle den Ordner, der am besten zur Dokumentkategorie passt
- Gib NUR den exakten Ordnernamen zurück, keine Erklärung

Ordner:"""

    try:
        if provider == "ollama":
            ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            response = client.chat.completions.create(
                model=ollama_model,
                messages=[
                    {"role": "system", "content": "Du bist ein Experte für Dokumentenkategorisierung. Du wählst den passendsten Ordner aus einer Liste aus."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            result = response.choices[0].message.content.strip()
            logger.debug(f"KI-Rohantwort (ollama): {repr(result)}")
        elif provider == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Du bist ein Experte für Dokumentenkategorisierung. Du wählst den passendsten Ordner aus einer Liste aus."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            result = response.choices[0].message.content.strip()
            logger.debug(f"KI-Rohantwort (openai): {repr(result)}")
        else:
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
            response = client.messages.create(
                model=model,
                max_tokens=50,
                temperature=0.1,
                system="Du bist ein Experte für Dokumentenkategorisierung. Du wählst den passendsten Ordner aus einer Liste aus.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            result = response.content[0].text.strip()
            logger.debug(f"KI-Rohantwort (anthropic): {repr(result)}")
        
        if not result:
            logger.debug("KI hat leere Antwort zurückgegeben")
            raise ValueError("Leere KI-Antwort")
        
        result = result.strip('"\'')
        result = sanitize_filename(result)
        
        logger.debug(f"KI-Antwort (bereinigt): {repr(result)}")
        
        if result and result in available_folders:
            logger.debug(f"Exakter Match: {result}")
            return result
        
        if result:
            for folder in available_folders:
                if result.lower() == folder.lower() or folder.lower() in result.lower() or result.lower() in folder.lower():
                    logger.debug(f"Fuzzy Match: {result} -> {folder}")
                    return folder
        
        if parsed_data and parsed_data.get('document_type'):
            doc_type = parsed_data['document_type'].lower()
            logger.debug(f"Fallback: Prüfe Dokumenttyp '{doc_type}' gegen Ordner")
            
            for folder in available_folders:
                folder_lower = folder.lower()
                if doc_type in folder_lower or folder_lower in doc_type:
                    logger.debug(f"Fallback: Match gefunden - '{doc_type}' -> '{folder}'")
                    return folder
            
            type_mapping = {
                'rechnung': ['rechnungen', 'rechnung'],
                'jahresrechnung': ['rechnungen', 'rechnung'],
                'mahnung': ['mahnungen', 'mahnung'],
                'vertrag': ['verträge', 'vertrag', 'mietvertrag'],
                'kündigung': ['kündigungen', 'kündigung'],
                'bestätigung': ['bestätigungen', 'bestätigung', 'abmeldebestätigung', 'zulassungsbescheinigung'],
                'info': ['informationen', 'info'],
                'bescheid': ['bescheide', 'bescheid', 'beitragsbescheid', 'bußgeldbescheid'],
                'beitrag': ['beiträge', 'beitrag'],
                'zulassungsbescheinigung': ['auto'],
                'kartenführerschein': ['auto'],
                'vollmacht': ['rechtliches'],
                'bußgeldbescheid': ['rechtliches'],
                'finanzierungsanfrage': ['bank'],
            }
            
            for key, values in type_mapping.items():
                if key in doc_type:
                    for folder in available_folders:
                        folder_lower = folder.lower()
                        if any(v in folder_lower for v in values):
                            logger.debug(f"Fallback: Typ-Mapping '{key}' -> '{folder}'")
                            return folder
        
        if parsed_data and parsed_data.get('sender'):
            sender = parsed_data['sender'].lower()
            logger.debug(f"Fallback: Prüfe Absender '{sender}' gegen Ordner")
            
            sender_mapping = {
                'aok': ['arzt', 'versicherung'],
                'krankenkasse': ['arzt', 'versicherung'],
                'versicherung': ['versicherung'],
                'bank': ['bank'],
                'sparkasse': ['bank'],
                'finanzamt': ['finanzamt'],
                'polizei': ['rechtliches'],
                'gericht': ['rechtliches'],
                'anwalt': ['rechtliches'],
                'bmw': ['auto'],
                'auto': ['auto'],
                'zulassung': ['auto'],
            }
            
            for key, values in sender_mapping.items():
                if key in sender:
                    for folder in available_folders:
                        folder_lower = folder.lower()
                        if any(v in folder_lower for v in values):
                            logger.debug(f"Fallback: Absender-Mapping '{key}' -> '{folder}'")
                            return folder
        
        logger.debug(f"Kein Match gefunden für '{filename}'")
        
        return None
    except Exception as e:
        logger.debug(f"KI-Fehler bei Ordnerauswahl: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    if parsed_data and parsed_data.get('document_type'):
        doc_type = parsed_data['document_type'].lower()
        logger.debug(f"Fallback: Prüfe Dokumenttyp '{doc_type}' direkt")
        
        for folder in available_folders:
            if doc_type == folder.lower():
                logger.info(f"  ✓ Fallback-Match: '{doc_type}' -> '{folder}'")
                return folder
        
        type_mapping = {
            'rechnung': ['rechnungen', 'rechnung'],
            'jahresrechnung': ['rechnungen', 'rechnung'],
            'vertrag': ['verträge', 'vertrag', 'mietvertrag'],
            'kündigung': ['kündigungen', 'kündigung'],
            'zulassungsbescheinigung': ['auto'],
            'bußgeldbescheid': ['rechtliches'],
        }
        
        for key, values in type_mapping.items():
            if key in doc_type:
                for folder in available_folders:
                    folder_lower = folder.lower()
                    if any(v in folder_lower for v in values):
                        logger.info(f"  ✓ Fallback-Mapping: '{key}' -> '{folder}'")
                        return folder
    
    return None


def normalize_with_ai(sender: str, document_type: str, provider: str = "openai") -> Optional[dict]:
    """Normalisiert Absender und Dokumenttyp mit KI für konsistente Gruppierung."""
    api_key = None
    client = None
    
    if provider == "ollama":
        if not OPENAI_AVAILABLE:
            return None
        if not check_ollama_available():
            return None
        try:
            client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama"
            )
        except Exception:
            return None
    elif provider == "openai" and OPENAI_AVAILABLE:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            client = OpenAI(api_key=api_key)
        except Exception:
            return None
    elif provider == "anthropic" and ANTHROPIC_AVAILABLE:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            client = Anthropic(api_key=api_key)
        except Exception:
            return None
    else:
        return None
    
    prompt = f"""Normalisiere die folgenden Informationen für eine konsistente Ordnerstruktur:

Absender: {sender}
Dokumenttyp: {document_type}

WICHTIG: Gib NUR zwei Zeilen zurück:
1. Normalisierter Absendername (konsistent, z.B. "Dr. Müller" statt "Dr. Thomas Müller")
2. Normalisierter Dokumenttyp (konsistent, z.B. "Rechnung" statt "Rechnungen" oder "Rechnung 2023")

Regeln:
- Absender: Verwende die kürzeste, konsistente Form (z.B. "Dr. Müller" für alle Varianten)
- Dokumenttyp: Singular, konsistent (z.B. "Rechnung", "Mahnung", "Beitragsbescheid")
- Keine Erklärungen, nur die zwei Zeilen
- Maximal 50 Zeichen pro Zeile

Normalisierter Absender:
Normalisierter Dokumenttyp:"""

    try:
        if provider == "ollama":
            ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            response = client.chat.completions.create(
                model=ollama_model,
                messages=[
                    {"role": "system", "content": "Du bist ein Experte für Datenorganisation und Normalisierung."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            result = response.choices[0].message.content.strip()
        elif provider == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Du bist ein Experte für Datenorganisation und Normalisierung."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            result = response.choices[0].message.content.strip()
        else:
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
            response = client.messages.create(
                model=model,
                max_tokens=100,
                temperature=0.1,
                system="Du bist ein Experte für Datenorganisation und Normalisierung.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            result = response.content[0].text.strip()
        
        lines = [line.strip() for line in result.split('\n') if line.strip()]
        if len(lines) >= 2:
            normalized_sender = lines[0].split(':', 1)[-1].strip() if ':' in lines[0] else lines[0]
            normalized_type = lines[1].split(':', 1)[-1].strip() if ':' in lines[1] else lines[1]
            
            normalized_sender = sanitize_filename(normalized_sender)
            normalized_type = sanitize_filename(normalized_type)
            
            if normalized_sender and normalized_type:
                return {
                    'sender': normalized_sender,
                    'document_type': normalized_type
                }
        
        return None
    except Exception as e:
        logger.debug(f"KI-Fehler bei Normalisierung: {e}")
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


def sort_pdf(pdf_path: Path, base_path: Path, sort_by: str = "sender", dry_run: bool = False, use_ai: bool = True, provider: Optional[str] = None, custom_folders: Optional[list[str]] = None) -> bool:
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
    
    if sort_by == "custom":
        if not custom_folders:
            logger.error("  ✗ Keine Ordner für custom-Sortierung angegeben")
            return False
        
        if not use_ai:
            logger.error("  ✗ KI ist für custom-Sortierung erforderlich")
            return False
        
        ai_provider = provider.lower() if provider else os.getenv("AI_PROVIDER", "openai").lower()
        selected_folder = select_folder_with_ai(pdf_path.name, custom_folders, provider=ai_provider, parsed_data=parsed)
        
        if not selected_folder:
            logger.warning(f"  ⚠️  KI konnte keinen passenden Ordner finden für: {pdf_path.name}")
            if parsed and parsed.get('document_type'):
                doc_type = parsed['document_type'].lower()
                logger.info(f"  💡 Versuche Fallback mit Dokumenttyp '{doc_type}'")
                
                for folder in custom_folders:
                    if doc_type == folder.lower():
                        selected_folder = folder
                        logger.info(f"  ✓ Fallback-Match: '{doc_type}' -> '{folder}'")
                        break
                
                if not selected_folder:
                    type_mapping = {
                        'rechnung': ['rechnungen', 'rechnung'],
                        'jahresrechnung': ['rechnungen', 'rechnung'],
                        'vertrag': ['verträge', 'vertrag', 'mietvertrag'],
                        'mietvertrag': ['vertrag'],
                        'kündigung': ['kündigungen', 'kündigung'],
                        'zulassungsbescheinigung': ['auto'],
                        'kartenführerschein': ['auto'],
                        'bußgeldbescheid': ['rechtliches'],
                        'bescheid': ['rechtliches'],
                        'beitragsbescheid': ['rechtliches'],
                    }
                    
                    for key, values in type_mapping.items():
                        if key in doc_type:
                            for folder in custom_folders:
                                folder_lower = folder.lower()
                                if any(v in folder_lower for v in values):
                                    selected_folder = folder
                                    logger.info(f"  ✓ Fallback-Mapping: '{key}' -> '{folder}'")
                                    break
                            if selected_folder:
                                break
                
                if not selected_folder and parsed.get('sender'):
                    sender = parsed['sender'].lower()
                    logger.info(f"  💡 Versuche Fallback mit Absender '{sender}'")
                    
                    sender_mapping = {
                        'zulassungsbescheinigung': ['auto'],
                        'kartenführerschein': ['auto'],
                        'aok': ['arzt', 'versicherung'],
                        'versicherung': ['versicherung'],
                        'bank': ['bank'],
                        'sparkasse': ['bank'],
                        'finanzamt': ['finanzamt'],
                        'polizei': ['rechtliches'],
                        'gericht': ['rechtliches'],
                    }
                    
                    for key, values in sender_mapping.items():
                        if key in sender:
                            for folder in custom_folders:
                                folder_lower = folder.lower()
                                if any(v in folder_lower for v in values):
                                    selected_folder = folder
                                    logger.info(f"  ✓ Fallback-Absender-Mapping: '{key}' -> '{folder}'")
                                    break
                            if selected_folder:
                                break
            
            if not selected_folder:
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
        
        target_dir = base_path / sanitize_filename(selected_folder)
        if selected_folder:
            logger.info(f"  🤖 Ordner ausgewählt: {selected_folder}")
    else:
        sender = parsed['sender']
        document_type = parsed['document_type']
        
        if use_ai:
            ai_provider = provider.lower() if provider else os.getenv("AI_PROVIDER", "openai").lower()
            normalized = normalize_with_ai(sender, document_type, provider=ai_provider)
            if normalized:
                sender = normalized['sender']
                document_type = normalized['document_type']
                logger.debug(f"  🤖 KI-Normalisierung: {parsed['sender']} → {sender}, {parsed['document_type']} → {document_type}")
            else:
                logger.debug(f"  ⚠️  KI-Normalisierung fehlgeschlagen, verwende Originalwerte")
        
        if sort_by == "sender":
            target_dir = base_path / sanitize_filename(sender)
        elif sort_by == "year":
            target_dir = base_path / str(parsed['year'])
        elif sort_by == "type":
            target_dir = base_path / sanitize_filename(document_type)
        elif sort_by == "sender_type":
            sender_dir = sanitize_filename(sender)
            type_dir = sanitize_filename(document_type)
            target_dir = base_path / sender_dir / type_dir
        elif sort_by == "year_sender":
            year_dir = str(parsed['year'])
            sender_dir = sanitize_filename(sender)
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


def main():
    parser = argparse.ArgumentParser(
        description='Sortiert PDF-Dateien in Ordner basierend auf ihren Dateinamen'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Pfad zu PDF-Dateien oder Verzeichnis (Standard: aktuelles Verzeichnis)'
    )
    parser.add_argument(
        '--sort',
        choices=['sender', 'year', 'type', 'sender_type', 'year_sender', 'custom'],
        default='sender',
        help='Sortierkriterium: sender (nach Absender), year (nach Jahr), type (nach Dokumenttyp), sender_type (nach Absender/Dokumenttyp), year_sender (nach Jahr/Absender), custom (KI wählt aus vorgegebenen Ordnern)'
    )
    parser.add_argument(
        '--folders',
        type=str,
        help='Komma-getrennte Liste von Ordnernamen für custom-Sortierung (z.B. "Rechnungen,Verträge,Mahnungen")'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Zeigt an, was verschoben würde, ohne tatsächlich zu verschieben'
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
        '--no-ai',
        action='store_true',
        help='Deaktiviert KI-Normalisierung, verwendet nur Regex-Parsing'
    )
    parser.add_argument(
        '--provider',
        choices=['openai', 'anthropic', 'ollama'],
        help='KI-Provider: openai, anthropic oder ollama (überschreibt AI_PROVIDER aus .env)'
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
            pdf_files = [f for f in path.rglob('*.pdf') if '_check' not in f.parts and '_unsortiert' not in f.parts]
            pdf_files.extend([f for f in path.rglob('*.PDF') if '_check' not in f.parts and '_unsortiert' not in f.parts])
        else:
            pdf_files = list(path.glob('*.pdf'))
            pdf_files.extend(list(path.glob('*.PDF')))
    else:
        logger.error(f"Fehler: {path} ist weder eine PDF-Datei noch ein Verzeichnis")
        sys.exit(1)
    
    if not pdf_files:
        logger.info("Keine PDF-Dateien gefunden.")
        sys.exit(0)
    
    logger.info(f"Gefunden: {len(pdf_files)} PDF-Datei(en)")
    if args.dry_run:
        logger.info("DRY-RUN Modus: Es werden keine Dateien verschoben")
    logger.info(f"📁 Sortiere Dateien nach: {args.sort}")
    
    custom_folders = None
    if args.sort == "custom":
        if args.folders:
            custom_folders = [f.strip() for f in args.folders.split(',') if f.strip()]
        else:
            env_folders = os.getenv("CUSTOM_FOLDERS", "")
            if env_folders:
                custom_folders = [f.strip() for f in env_folders.split(',') if f.strip()]
        
        if not custom_folders:
            logger.error("❌ Fehler: Keine Ordner für custom-Sortierung gefunden")
            logger.error("   Gib --folders an oder setze CUSTOM_FOLDERS in .env")
            logger.error("   Beispiel: --sort custom --folders 'Rechnungen,Verträge,Mahnungen'")
            logger.error("   Oder in .env: CUSTOM_FOLDERS=Rechnungen,Verträge,Mahnungen")
            sys.exit(1)
        
        logger.info(f"📂 Vorgegebene Ordner: {', '.join(custom_folders)}")
    
    use_ai = not args.no_ai
    if args.sort == "custom" and not use_ai:
        logger.error("❌ Fehler: KI ist für custom-Sortierung erforderlich (--no-ai nicht erlaubt)")
        sys.exit(1)
    
    ai_provider = None
    if use_ai:
        ai_provider = args.provider.lower() if args.provider else os.getenv("AI_PROVIDER", "openai").lower()
        if ai_provider == "ollama":
            if check_ollama_available():
                logger.info(f"🤖 KI-Normalisierung aktiviert ({ai_provider}) - lokal")
            else:
                logger.warning("⚠️  Ollama läuft nicht, deaktiviere KI-Normalisierung")
                use_ai = False
        else:
            api_key = os.getenv("OPENAI_API_KEY") if ai_provider == "openai" else os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                logger.info(f"🤖 KI-Normalisierung aktiviert ({ai_provider})")
            else:
                logger.warning("⚠️  Kein API-Key gefunden, deaktiviere KI-Normalisierung")
                use_ai = False
    else:
        logger.info("📋 Verwende nur Regex-Parsing (KI deaktiviert)")
    
    base_path = path if path.is_dir() else path.parent
    
    success_count = 0
    max_workers = args.parallel if args.parallel > 0 else min(len(pdf_files), os.cpu_count() or 1)
    
    if max_workers == 1 or len(pdf_files) == 1:
        for pdf_file in pdf_files:
            if sort_pdf(pdf_file, base_path, sort_by=args.sort, dry_run=args.dry_run, use_ai=use_ai, provider=ai_provider, custom_folders=custom_folders):
                success_count += 1
    else:
        logger.info(f"Verarbeite {len(pdf_files)} Dateien mit {max_workers} parallelen Workern")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(sort_pdf, pdf_file, base_path, args.sort, args.dry_run, use_ai, ai_provider, custom_folders): pdf_file
                for pdf_file in pdf_files
            }
            for future in as_completed(future_to_file):
                if future.result():
                    success_count += 1
    
    logger.info(f"\n✓ {success_count}/{len(pdf_files)} Dateien erfolgreich sortiert")


if __name__ == '__main__':
    main()


