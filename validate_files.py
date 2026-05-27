#!/usr/bin/env python3
"""
Script zum Prüfen auf Nicht-PDF-Dateien und PDFs ohne Inhalt/OCR.
"""

import os
import sys
import logging
import re
from pathlib import Path
from typing import List, Tuple
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("Fehler: pdfplumber ist nicht installiert.")
    print("Installiere es mit: pip install pdfplumber")
    sys.exit(1)

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logging.getLogger('pdfplumber').setLevel(logging.WARNING)
logging.getLogger('pdfminer').setLevel(logging.WARNING)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extrahiert Text aus einer PDF-Datei (Text-Layer)."""
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
        return text
    except Exception as e:
        logger.debug(f"Fehler beim Lesen von {pdf_path}: {e}")
        return ""


def extract_text_with_ocr(pdf_path: Path) -> str:
    """Extrahiert Text aus einer PDF-Datei mit OCR (für gescannte PDFs)."""
    if not OCR_AVAILABLE:
        return ""
    
    try:
        text = ""
        try:
            images = convert_from_path(str(pdf_path), dpi=200)
        except Exception as e:
            logger.debug(f"Fehler beim Konvertieren von PDF zu Bildern ({pdf_path}): {e}")
            return ""
        
        for page_num, image in enumerate(images, 1):
            try:
                page_text = pytesseract.image_to_string(image, lang='deu+eng')
                if page_text:
                    text += page_text + "\n"
            except pytesseract.TesseractNotFoundError:
                logger.debug(f"Tesseract OCR nicht gefunden - OCR wird übersprungen")
                return ""
            except Exception as e:
                logger.debug(f"Fehler bei OCR von Seite {page_num} in {pdf_path}: {e}")
                continue
        
        return text
    except Exception as e:
        logger.debug(f"Fehler bei OCR-Verarbeitung von {pdf_path}: {e}")
        return ""


def check_pdf_has_content(pdf_path: Path) -> Tuple[bool, str]:
    """Prüft ob eine PDF-Datei Text-Inhalt hat (Text-Layer oder OCR)."""
    try:
        text = extract_text_from_pdf(pdf_path)
        text_cleaned = text.strip()
        
        if text_cleaned:
            return True, ""
        
        if OCR_AVAILABLE:
            ocr_text = extract_text_with_ocr(pdf_path)
            ocr_text_cleaned = ocr_text.strip()
            if ocr_text_cleaned:
                return True, ""
            return False, "Kein Text-Inhalt gefunden (weder Text-Layer noch OCR)"
        else:
            return False, "Kein Text-Inhalt gefunden"
    except Exception as e:
        return False, f"Fehler beim Lesen: {e}"


def should_ignore_path(file_path: Path) -> bool:
    """Prüft ob ein Pfad ignoriert werden sollte."""
    parts = file_path.parts
    ignore_dirs = {'.git', 'venv', '__pycache__', '.pytest_cache', 'node_modules'}
    ignore_patterns = ['.DS_Store']
    
    for part in parts:
        if part in ignore_dirs:
            return True
        if any(pattern in part for pattern in ignore_patterns):
            return True
        if part.startswith('.') and part != '.':
            return True
    
    return False


def has_valid_date_prefix(filename: str) -> bool:
    """Prüft ob der Dateiname mit einem gültigen Datum im Format YYYY-MM-DD beginnt."""
    if not filename:
        return False
    
    date_pattern = r'^(\d{4}-\d{2}-\d{2})'
    match = re.match(date_pattern, filename)
    
    if not match:
        return False
    
    date_str = match.group(1)
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def find_non_pdf_files(path: Path, recursive: bool = True) -> List[Path]:
    """Findet alle Dateien, die keine PDF-Dateien sind."""
    non_pdf_files = []
    
    if path.is_file():
        if path.suffix.lower() != '.pdf' and not should_ignore_path(path):
            non_pdf_files.append(path)
    elif path.is_dir():
        if recursive:
            for file_path in path.rglob('*'):
                if file_path.is_file() and not should_ignore_path(file_path):
                    if file_path.suffix.lower() != '.pdf':
                        non_pdf_files.append(file_path)
        else:
            for file_path in path.iterdir():
                if file_path.is_file() and not should_ignore_path(file_path):
                    if file_path.suffix.lower() != '.pdf':
                        non_pdf_files.append(file_path)
    
    return non_pdf_files


def find_pdfs_without_content(pdf_files: List[Path], max_workers: int = 1) -> List[Tuple[Path, str]]:
    """Findet PDF-Dateien ohne Text-Inhalt."""
    pdfs_without_content = []
    
    def process_pdf(pdf_file: Path) -> Tuple[Path, bool, str]:
        """Prüft eine PDF-Datei auf Inhalt."""
        has_content, reason = check_pdf_has_content(pdf_file)
        return (pdf_file, has_content, reason)
    
    if max_workers == 1 or len(pdf_files) == 1:
        for pdf_file in pdf_files:
            pdf_path, has_content, reason = process_pdf(pdf_file)
            if not has_content:
                pdfs_without_content.append((pdf_path, reason))
    else:
        logger.info(f"Prüfe {len(pdf_files)} PDF-Dateien auf Inhalt mit {max_workers} parallelen Workern...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(process_pdf, pdf_file): pdf_file
                for pdf_file in pdf_files
            }
            for future in as_completed(future_to_file):
                pdf_file = future_to_file[future]
                try:
                    pdf_path, has_content, reason = future.result()
                    if not has_content:
                        pdfs_without_content.append((pdf_path, reason))
                except Exception as e:
                    logger.debug(f"Fehler beim Verarbeiten von {pdf_file}: {e}")
                    pdfs_without_content.append((pdf_file, f"Fehler: {e}"))
    
    return pdfs_without_content


def find_pdf_files(path: Path, recursive: bool = True) -> List[Path]:
    """Findet alle PDF-Dateien."""
    pdf_files = []
    
    if path.is_file() and path.suffix.lower() == '.pdf':
        pdf_files = [path]
    elif path.is_dir():
        if recursive:
            pdf_files = [f for f in path.rglob('*.pdf') if not should_ignore_path(f)]
            pdf_files.extend([f for f in path.rglob('*.PDF') if not should_ignore_path(f)])
        else:
            pdf_files = [f for f in path.glob('*.pdf') if not should_ignore_path(f)]
            pdf_files.extend([f for f in path.glob('*.PDF') if not should_ignore_path(f)])
    
    return pdf_files


def find_pdfs_without_date(pdf_files: List[Path]) -> List[Tuple[Path, str]]:
    """Findet PDF-Dateien ohne gültiges Datum am Anfang des Dateinamens."""
    pdfs_without_date = []
    
    for pdf_file in pdf_files:
        filename = pdf_file.stem
        if not has_valid_date_prefix(filename):
            pdfs_without_date.append((pdf_file, "Kein gültiges Datum am Anfang des Dateinamens (Format: YYYY-MM-DD)"))
    
    return pdfs_without_date


def format_size(size_bytes: int) -> str:
    """Formatiert Dateigröße in lesbares Format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def report_non_pdf_files(non_pdf_files: List[Path]) -> None:
    """Erstellt Bericht über Nicht-PDF-Dateien."""
    if not non_pdf_files:
        logger.info("✓ Keine Nicht-PDF-Dateien gefunden")
        return
    
    logger.info(f"\n🔍 Gefunden: {len(non_pdf_files)} Nicht-PDF-Datei(en)")
    logger.info("=" * 80)
    
    for file_path in sorted(non_pdf_files):
        try:
            size = file_path.stat().st_size
            logger.info(f"   {file_path} ({format_size(size)})")
        except Exception:
            logger.info(f"   {file_path}")


def report_pdfs_without_content(pdfs_without_content: List[Tuple[Path, str]]) -> None:
    """Erstellt Bericht über PDFs ohne Inhalt."""
    if not pdfs_without_content:
        logger.info("✓ Keine PDFs ohne Inhalt gefunden")
        return
    
    logger.info(f"\n🔍 Gefunden: {len(pdfs_without_content)} PDF(s) ohne Inhalt/OCR")
    logger.info("=" * 80)
    
    for pdf_path, reason in sorted(pdfs_without_content, key=lambda x: x[0]):
        try:
            size = pdf_path.stat().st_size
            logger.info(f"   {pdf_path} ({format_size(size)}) - {reason}")
        except Exception:
            logger.info(f"   {pdf_path} - {reason}")


def report_pdfs_without_date(pdfs_without_date: List[Tuple[Path, str]]) -> None:
    """Erstellt Bericht über PDFs ohne gültiges Datum."""
    if not pdfs_without_date:
        logger.info("✓ Keine PDFs ohne gültiges Datum gefunden")
        return
    
    logger.info(f"\n🔍 Gefunden: {len(pdfs_without_date)} PDF(s) ohne gültiges Datum am Anfang")
    logger.info("=" * 80)
    
    for pdf_path, reason in sorted(pdfs_without_date, key=lambda x: x[0]):
        try:
            size = pdf_path.stat().st_size
            logger.info(f"   {pdf_path} ({format_size(size)}) - {reason}")
        except Exception:
            logger.info(f"   {pdf_path} - {reason}")


def main():
    parser = argparse.ArgumentParser(
        description='Prüft auf Nicht-PDF-Dateien, PDFs ohne Inhalt/OCR und PDFs ohne gültiges Datum'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Pfad zu Dateien oder Verzeichnis (Standard: aktuelles Verzeichnis)'
    )
    parser.add_argument(
        '--non-pdf',
        action='store_true',
        help='Prüft nur auf Nicht-PDF-Dateien'
    )
    parser.add_argument(
        '--no-content',
        action='store_true',
        help='Prüft nur auf PDFs ohne Inhalt/OCR'
    )
    parser.add_argument(
        '--no-date',
        action='store_true',
        help='Prüft nur auf PDFs ohne gültiges Datum am Anfang'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Prüft auf alle Probleme (Standard)'
    )
    parser.add_argument(
        '--recursive',
        '-r',
        action='store_true',
        help='Durchsucht Verzeichnisse rekursiv (Standard: aktiviert)'
    )
    parser.add_argument(
        '--parallel',
        '-p',
        type=int,
        default=1,
        metavar='N',
        help='Anzahl paralleler Verarbeitungen für PDF-Prüfung (Standard: 1, 0 = automatisch)'
    )
    
    args = parser.parse_args()
    
    if not args.non_pdf and not args.no_content and not args.no_date and not args.all:
        args.all = True
    
    if args.all:
        args.non_pdf = True
        args.no_content = True
        args.no_date = True
    
    recursive = args.recursive if args.recursive else True
    
    path = Path(args.path)
    
    if not path.exists():
        logger.error(f"Fehler: Pfad existiert nicht: {path}")
        sys.exit(1)
    
    if args.non_pdf:
        logger.info("🔍 Suche nach Nicht-PDF-Dateien...")
        non_pdf_files = find_non_pdf_files(path, recursive=recursive)
        report_non_pdf_files(non_pdf_files)
    
    pdf_files = []
    if args.no_content or args.no_date:
        logger.info("\n🔍 Suche nach PDF-Dateien...")
        pdf_files = find_pdf_files(path, recursive=recursive)
        
        if not pdf_files:
            logger.info("Keine PDF-Dateien gefunden.")
    
    if args.no_date and pdf_files:
        logger.info(f"Gefunden: {len(pdf_files)} PDF-Datei(en)")
        logger.info("🔍 Prüfe PDFs auf gültiges Datum am Anfang...")
        pdfs_without_date = find_pdfs_without_date(pdf_files)
        report_pdfs_without_date(pdfs_without_date)
    
    if args.no_content and pdf_files:
        if not args.no_date:
            logger.info(f"Gefunden: {len(pdf_files)} PDF-Datei(en)")
        logger.info("\n🔍 Prüfe PDFs auf Inhalt/OCR...")
        
        max_workers = args.parallel if args.parallel > 0 else min(len(pdf_files), os.cpu_count() or 1)
        pdfs_without_content = find_pdfs_without_content(pdf_files, max_workers=max_workers)
        report_pdfs_without_content(pdfs_without_content)
    
    logger.info("\n✓ Prüfung abgeschlossen")


if __name__ == '__main__':
    main()

