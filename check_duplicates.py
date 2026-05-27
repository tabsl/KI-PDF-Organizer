#!/usr/bin/env python3
"""
Script zum Finden von Duplikaten in PDF-Dateien.
Unterstützt Hash-basierte (exakte Duplikate) und Dateinamen-basierte Prüfung.
"""

import os
import sys
import logging
import hashlib
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def extract_date_from_filename(filename: str) -> Optional[str]:
    """Extrahiert Datum aus Dateinamen im Format [Datum] [Absender] [Dokumenttyp].pdf
    Erwartet Datum im Format YYYY-MM-DD."""
    if not filename.endswith('.pdf'):
        return None
    
    name_without_ext = filename[:-4]
    date_pattern = r'^(\d{4}-\d{2}-\d{2})\s+'
    match = re.match(date_pattern, name_without_ext)
    
    if match:
        return match.group(1)
    return None


def calculate_file_hash(file_path: Path, chunk_size: int = 8192) -> Optional[str]:
    """Berechnet SHA256-Hash einer Datei."""
    try:
        hash_sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.debug(f"Fehler beim Berechnen des Hashs für {file_path}: {e}")
        return None


def find_duplicates_by_hash(pdf_files: List[Path], max_workers: int = 1) -> Dict[str, List[Path]]:
    """Findet Duplikate basierend auf Datei-Hash und Datum im Dateinamen."""
    hash_date_to_files: Dict[Tuple[str, Optional[str]], List[Path]] = defaultdict(list)
    
    def process_file(pdf_file: Path) -> Optional[Tuple[str, Optional[str]]]:
        """Berechnet Hash und extrahiert Datum für eine Datei."""
        file_hash = calculate_file_hash(pdf_file)
        if not file_hash:
            return None
        date = extract_date_from_filename(pdf_file.name)
        return (file_hash, date)
    
    if max_workers == 1 or len(pdf_files) == 1:
        for pdf_file in pdf_files:
            result = process_file(pdf_file)
            if result:
                hash_date_to_files[result].append(pdf_file)
    else:
        logger.info(f"Berechne Hashes für {len(pdf_files)} Dateien mit {max_workers} parallelen Workern")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(process_file, pdf_file): pdf_file
                for pdf_file in pdf_files
            }
            for future in as_completed(future_to_file):
                pdf_file = future_to_file[future]
                try:
                    result = future.result()
                    if result:
                        hash_date_to_files[result].append(pdf_file)
                except Exception as e:
                    logger.debug(f"Fehler beim Verarbeiten von {pdf_file}: {e}")
    
    duplicates = {}
    for (file_hash, date), files in hash_date_to_files.items():
        if len(files) > 1:
            hash_key = f"{file_hash}_{date if date else 'no-date'}"
            duplicates[hash_key] = files
    
    return duplicates


def find_duplicates_by_name(pdf_files: List[Path]) -> Dict[str, List[Path]]:
    """Findet Duplikate basierend auf Dateinamen."""
    name_to_files: Dict[str, List[Path]] = defaultdict(list)
    
    for pdf_file in pdf_files:
        name_to_files[pdf_file.name].append(pdf_file)
    
    duplicates = {name: files for name, files in name_to_files.items() if len(files) > 1}
    return duplicates


def find_duplicates_by_size(pdf_files: List[Path]) -> Dict[int, List[Path]]:
    """Findet Duplikate basierend auf Dateigröße."""
    size_to_files: Dict[int, List[Path]] = defaultdict(list)
    
    for pdf_file in pdf_files:
        try:
            size = pdf_file.stat().st_size
            size_to_files[size].append(pdf_file)
        except Exception as e:
            logger.debug(f"Fehler beim Lesen der Größe von {pdf_file}: {e}")
    
    duplicates = {size: files for size, files in size_to_files.items() if len(files) > 1}
    return duplicates


def format_size(size_bytes: int) -> str:
    """Formatiert Dateigröße in lesbares Format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def report_hash_duplicates(duplicates: Dict[str, List[Path]], delete: bool = False, dry_run: bool = False) -> int:
    """Erstellt Bericht über Hash-Duplikate und löscht optional Duplikate."""
    if not duplicates:
        logger.info("✓ Keine Hash-Duplikate gefunden")
        return 0
    
    logger.info(f"\n🔍 Gefunden: {len(duplicates)} Hash-Duplikat-Gruppen")
    logger.info("=" * 80)
    
    total_duplicates = 0
    deleted_count = 0
    
    for hash_key, files in duplicates.items():
        total_duplicates += len(files) - 1
        
        file_hash = hash_key.split('_')[0]
        date_info = hash_key.split('_', 1)[1] if '_' in hash_key else 'no-date'
        
        if date_info != 'no-date':
            logger.info(f"\n📄 Hash: {file_hash[:16]}... | Datum: {date_info} ({len(files)} Dateien)")
        else:
            logger.info(f"\n📄 Hash: {file_hash[:16]}... | Kein Datum im Dateinamen ({len(files)} Dateien)")
        
        try:
            file_size = files[0].stat().st_size
            logger.info(f"   Größe: {format_size(file_size)}")
        except Exception:
            pass
        
        for i, file_path in enumerate(files, 1):
            relative_path = file_path.relative_to(file_path.parents[len(file_path.parts) - 2] if len(file_path.parts) > 2 else Path.cwd())
            logger.info(f"   {i}. {file_path}")
        
        if delete:
            files_to_delete = sorted(files)[1:]
            for file_to_delete in files_to_delete:
                if dry_run:
                    logger.info(f"   [DRY-RUN] Würde löschen: {file_to_delete}")
                else:
                    try:
                        file_to_delete.unlink()
                        logger.info(f"   ✓ Gelöscht: {file_to_delete}")
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"   ✗ Fehler beim Löschen: {e}")
    
    logger.info(f"\n📊 Zusammenfassung:")
    logger.info(f"   Duplikat-Gruppen: {len(duplicates)}")
    logger.info(f"   Gesamt-Duplikate: {total_duplicates}")
    if delete:
        logger.info(f"   Gelöscht: {deleted_count}")
    
    return total_duplicates


def report_name_duplicates(duplicates: Dict[str, List[Path]]) -> int:
    """Erstellt Bericht über Dateinamen-Duplikate."""
    if not duplicates:
        logger.info("✓ Keine Dateinamen-Duplikate gefunden")
        return 0
    
    logger.info(f"\n🔍 Gefunden: {len(duplicates)} Dateinamen-Duplikate")
    logger.info("=" * 80)
    
    total_duplicates = 0
    
    for filename, files in duplicates.items():
        total_duplicates += len(files) - 1
        logger.info(f"\n📄 Dateiname: {filename} ({len(files)} Dateien)")
        
        for i, file_path in enumerate(files, 1):
            logger.info(f"   {i}. {file_path}")
    
    logger.info(f"\n📊 Zusammenfassung:")
    logger.info(f"   Duplikat-Gruppen: {len(duplicates)}")
    logger.info(f"   Gesamt-Duplikate: {total_duplicates}")
    
    return total_duplicates


def report_size_duplicates(duplicates: Dict[int, List[Path]]) -> int:
    """Erstellt Bericht über Größen-Duplikate."""
    if not duplicates:
        logger.info("✓ Keine Größen-Duplikate gefunden")
        return 0
    
    logger.info(f"\n🔍 Gefunden: {len(duplicates)} Größen-Duplikat-Gruppen")
    logger.info("=" * 80)
    
    total_duplicates = 0
    
    for size, files in duplicates.items():
        total_duplicates += len(files) - 1
        logger.info(f"\n📄 Größe: {format_size(size)} ({len(files)} Dateien)")
        
        for i, file_path in enumerate(files, 1):
            logger.info(f"   {i}. {file_path.name} ({file_path})")
    
    logger.info(f"\n📊 Zusammenfassung:")
    logger.info(f"   Duplikat-Gruppen: {len(duplicates)}")
    logger.info(f"   Gesamt-Duplikate: {total_duplicates}")
    logger.info(f"\n⚠️  Hinweis: Gleiche Größe bedeutet nicht automatisch Duplikat!")
    logger.info(f"   Verwende --hash für exakte Duplikat-Prüfung.")
    
    return total_duplicates


def main():
    parser = argparse.ArgumentParser(
        description='Findet Duplikate in PDF-Dateien'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Pfad zu PDF-Dateien oder Verzeichnis (Standard: aktuelles Verzeichnis)'
    )
    parser.add_argument(
        '--hash',
        action='store_true',
        help='Prüft auf Hash-Duplikate (exakte Duplikate)'
    )
    parser.add_argument(
        '--name',
        action='store_true',
        help='Prüft auf Dateinamen-Duplikate'
    )
    parser.add_argument(
        '--size',
        action='store_true',
        help='Prüft auf Größen-Duplikate (gleiche Dateigröße)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Prüft auf alle Arten von Duplikaten'
    )
    parser.add_argument(
        '--delete',
        action='store_true',
        help='Löscht Hash-Duplikate (behält erste Datei jeder Gruppe)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Zeigt an, was gelöscht würde, ohne tatsächlich zu löschen'
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
        help='Anzahl paralleler Verarbeitungen für Hash-Berechnung (Standard: 1, 0 = automatisch)'
    )
    
    args = parser.parse_args()
    
    if not args.hash and not args.name and not args.size and not args.all:
        args.hash = True
    
    if args.all:
        args.hash = True
        args.name = True
        args.size = True
    
    if args.delete and not args.hash:
        logger.error("❌ --delete kann nur mit --hash verwendet werden")
        sys.exit(1)
    
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
    
    if args.delete and args.dry_run:
        logger.info("DRY-RUN Modus: Es werden keine Dateien gelöscht")
    elif args.delete:
        logger.warning("⚠️  LÖSCH-MODUS: Duplikate werden gelöscht!")
        logger.warning("⚠️  Verwende --dry-run zuerst, um zu sehen, was gelöscht würde!")
    
    max_workers = args.parallel if args.parallel > 0 else min(len(pdf_files), os.cpu_count() or 1)
    
    if args.hash:
        logger.info("\n🔍 Prüfe auf Hash-Duplikate (exakte Duplikate)...")
        hash_duplicates = find_duplicates_by_hash(pdf_files, max_workers=max_workers)
        report_hash_duplicates(hash_duplicates, delete=args.delete, dry_run=args.dry_run)
    
    if args.name:
        logger.info("\n🔍 Prüfe auf Dateinamen-Duplikate...")
        name_duplicates = find_duplicates_by_name(pdf_files)
        report_name_duplicates(name_duplicates)
    
    if args.size:
        logger.info("\n🔍 Prüfe auf Größen-Duplikate...")
        size_duplicates = find_duplicates_by_size(pdf_files)
        report_size_duplicates(size_duplicates)


if __name__ == '__main__':
    main()

