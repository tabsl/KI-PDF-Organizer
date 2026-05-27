#!/usr/bin/env python3
"""
Script zum Konvertieren von JPG/PNG/PDF zu durchsuchbaren PDFs mit OCR.
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Optional, Tuple
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    pytesseract = None
    convert_from_path = None
    Image = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logging.getLogger('pdfplumber').setLevel(logging.WARNING)
logging.getLogger('pdfminer').setLevel(logging.WARNING)


def has_text_layer(pdf_path: Path) -> bool:
    """Prüft ob eine PDF einen Text-Layer hat."""
    if pdfplumber is None:
        return False
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                text = page.extract_text()
                if text and len(text.strip()) > 10:
                    return True
        return False
    except Exception:
        return False


def image_to_searchable_pdf(image_path: Path, output_path: Path, dpi: int = 200) -> bool:
    """Konvertiert ein Bild (JPG/PNG) zu einem durchsuchbaren PDF mit OCR."""
    if not OCR_AVAILABLE:
        logger.error(f"OCR ist nicht verfügbar - {image_path}")
        return False
    
    if not PYMUPDF_AVAILABLE:
        logger.error(f"PyMuPDF ist nicht verfügbar - {image_path}")
        return False
    
    try:
        image = Image.open(image_path)
        
        try:
            ocr_data = pytesseract.image_to_data(image, lang='deu+eng', output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError:
            logger.error(f"Tesseract OCR nicht gefunden - {image_path}")
            return False
        except Exception as e:
            logger.error(f"Fehler bei OCR von {image_path}: {e}")
            return False
        
        doc = fitz.open()
        page = doc.new_page(width=image.width, height=image.height)
        
        import io
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        page.insert_image(page.rect, stream=img_bytes.getvalue())
        
        n_boxes = len(ocr_data['text'])
        
        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            conf = ocr_data['conf'][i]
            
            if text and conf > 0:
                x = ocr_data['left'][i]
                y = ocr_data['top'][i]
                w = ocr_data['width'][i]
                h = ocr_data['height'][i]
                fontsize = max(h, 8)
                
                try:
                    rect = fitz.Rect(x, y, x + w, y + h)
                    page.insert_text(
                        rect.tl,
                        text,
                        fontsize=fontsize,
                        color=(0, 0, 0),
                        render_mode=3
                    )
                except Exception as e:
                    logger.debug(f"Fehler beim Hinzufügen von Text: {e}")
                    continue
        
        doc.save(str(output_path))
        doc.close()
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Konvertieren von {image_path}: {e}")
        return False


def pdf_to_searchable_pdf(pdf_path: Path, output_path: Optional[Path] = None, dpi: int = 200, force: bool = False) -> bool:
    """Konvertiert eine PDF zu einer durchsuchbaren PDF mit OCR."""
    if output_path is None:
        output_path = pdf_path
    
    if not force and has_text_layer(pdf_path):
        logger.info(f"  ✓ PDF hat bereits Text-Layer: {pdf_path.name}")
        if output_path != pdf_path:
            shutil.copy2(pdf_path, output_path)
        return True
    
    if not OCR_AVAILABLE:
        logger.error(f"OCR ist nicht verfügbar - {pdf_path}")
        return False
    
    if not PYMUPDF_AVAILABLE:
        logger.error(f"PyMuPDF ist nicht verfügbar - {pdf_path}")
        return False
    
    try:
        doc = fitz.open(str(pdf_path))
        
        try:
            images = convert_from_path(str(pdf_path), dpi=dpi)
        except Exception as e:
            logger.error(f"Fehler beim Konvertieren von PDF zu Bildern ({pdf_path}): {e}")
            doc.close()
            return False
        
        if len(images) != len(doc):
            logger.warning(f"Anzahl der Seiten stimmt nicht überein: {len(images)} Bilder, {len(doc)} PDF-Seiten")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            if page_num < len(images):
                image = images[page_num]
                
                try:
                    ocr_data = pytesseract.image_to_data(image, lang='deu+eng', output_type=pytesseract.Output.DICT)
                except pytesseract.TesseractNotFoundError:
                    logger.error(f"Tesseract OCR nicht gefunden - {pdf_path}")
                    doc.close()
                    return False
                except Exception as e:
                    logger.warning(f"Fehler bei OCR von Seite {page_num + 1} in {pdf_path}: {e}")
                    continue
                
                page_rect = page.rect
                img_width = image.width
                img_height = image.height
                
                scale_x = page_rect.width / img_width
                scale_y = page_rect.height / img_height
                
                n_boxes = len(ocr_data['text'])
                
                for i in range(n_boxes):
                    text = ocr_data['text'][i].strip()
                    conf = ocr_data['conf'][i]
                    
                    if text and conf > 0:
                        x = ocr_data['left'][i] * scale_x
                        y = ocr_data['top'][i] * scale_y
                        w = ocr_data['width'][i] * scale_x
                        h = ocr_data['height'][i] * scale_y
                        fontsize = max(ocr_data['height'][i] * scale_y, 8)
                        
                        try:
                            rect = fitz.Rect(x, y, x + w, y + h)
                            page.insert_text(
                                rect.tl,
                                text,
                                fontsize=fontsize,
                                color=(0, 0, 0),
                                render_mode=3
                            )
                        except Exception as e:
                            logger.debug(f"Fehler beim Hinzufügen von Text auf Seite {page_num + 1}: {e}")
                            continue
        
        doc.save(str(output_path))
        doc.close()
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Konvertieren von {pdf_path}: {e}")
        return False


def find_files(path: Path, recursive: bool = True, extensions: List[str] = None) -> List[Path]:
    """Findet alle Dateien mit den angegebenen Endungen."""
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.pdf']
    
    files = []
    
    if path.is_file():
        if path.suffix.lower() in extensions:
            files.append(path)
    elif path.is_dir():
        if recursive:
            for file_path in path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in extensions:
                    files.append(file_path)
        else:
            for file_path in path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in extensions:
                    files.append(file_path)
    
    return files


def convert_file(file_path: Path, output_dir: Optional[Path] = None, dpi: int = 200, force: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
    """Konvertiert eine einzelne Datei."""
    try:
        suffix = file_path.suffix.lower()
        
        if suffix in ['.jpg', '.jpeg', '.png']:
            if output_dir:
                output_path = output_dir / f"{file_path.stem}.pdf"
            else:
                output_path = file_path.parent / f"{file_path.stem}.pdf"
            
            if dry_run:
                return True, f"Würde konvertieren: {file_path.name} → {output_path.name}"
            
            logger.info(f"Konvertiere Bild: {file_path.name}")
            success = image_to_searchable_pdf(file_path, output_path, dpi)
            if success:
                return True, f"✓ Konvertiert: {file_path.name} → {output_path.name}"
            else:
                return False, f"✗ Fehler bei: {file_path.name}"
        
        elif suffix == '.pdf':
            if output_dir:
                output_path = output_dir / file_path.name
            else:
                output_path = file_path
            
            if dry_run:
                if force or not has_text_layer(file_path):
                    return True, f"Würde konvertieren: {file_path.name}"
                else:
                    return True, f"Überspringen (hat bereits Text-Layer): {file_path.name}"
            
            logger.info(f"Konvertiere PDF: {file_path.name}")
            success = pdf_to_searchable_pdf(file_path, output_path, dpi, force)
            if success:
                if output_path == file_path:
                    return True, f"✓ Aktualisiert: {file_path.name}"
                else:
                    return True, f"✓ Konvertiert: {file_path.name} → {output_path.name}"
            else:
                return False, f"✗ Fehler bei: {file_path.name}"
        
        else:
            return False, f"Unbekannter Dateityp: {file_path.name}"
    
    except Exception as e:
        return False, f"Fehler bei {file_path.name}: {e}"


def main():
    parser = argparse.ArgumentParser(
        description='Konvertiert JPG/PNG/PDF zu durchsuchbaren PDFs mit OCR',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s .                          # Konvertiert alle Dateien im aktuellen Verzeichnis
  %(prog)s bild.jpg                    # Konvertiert ein einzelnes Bild
  %(prog)s . --output output/          # Speichert konvertierte Dateien in output/
  %(prog)s . --force                   # Konvertiert auch PDFs mit Text-Layer
  %(prog)s . --dry-run                 # Zeigt an, was konvertiert würde
  %(prog)s . --parallel 4              # Verwendet 4 parallele Worker
        """
    )
    
    parser.add_argument('path', type=str, help='Pfad zu Datei oder Verzeichnis')
    parser.add_argument('--output', '-o', type=str, help='Ausgabe-Verzeichnis (optional)')
    parser.add_argument('--recursive', '-r', action='store_true', default=True, help='Rekursiv durchsuchen (Standard: aktiviert)')
    parser.add_argument('--no-recursive', action='store_true', help='Nicht rekursiv durchsuchen')
    parser.add_argument('--dpi', type=int, default=200, help='DPI für OCR (Standard: 200)')
    parser.add_argument('--force', action='store_true', help='Konvertiert auch PDFs mit Text-Layer')
    parser.add_argument('--dry-run', action='store_true', help='Zeigt an, was konvertiert würde, ohne zu konvertieren')
    parser.add_argument('--parallel', '-p', type=int, default=1, help='Anzahl paralleler Worker (Standard: 1, 0 = automatisch)')
    
    args = parser.parse_args()
    
    if not OCR_AVAILABLE:
        logger.error("❌ OCR ist nicht verfügbar!")
        logger.error("Installiere: pip install pytesseract pdf2image Pillow")
        logger.error("Und installiere Tesseract:")
        logger.error("  macOS: brew install tesseract tesseract-lang")
        logger.error("  Linux: sudo apt-get install tesseract-ocr tesseract-ocr-deu")
        sys.exit(1)
    
    if not PYMUPDF_AVAILABLE:
        logger.error("❌ PyMuPDF ist nicht verfügbar!")
        logger.error("Installiere: pip install PyMuPDF")
        sys.exit(1)
    
    path = Path(args.path)
    if not path.exists():
        logger.error(f"❌ Pfad existiert nicht: {path}")
        sys.exit(1)
    
    recursive = args.recursive and not args.no_recursive
    
    output_dir = None
    if args.output:
        output_dir = Path(args.output)
        if not output_dir.exists():
            if not args.dry_run:
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                logger.info(f"Würde Ausgabe-Verzeichnis erstellen: {output_dir}")
    
    files = find_files(path, recursive)
    
    if not files:
        logger.info("Keine Dateien gefunden (JPG/PNG/PDF)")
        return
    
    logger.info(f"Gefunden: {len(files)} Dateien")
    
    if args.dry_run:
        logger.info("🔍 Dry-Run Modus - keine Dateien werden konvertiert")
    
    num_workers = args.parallel
    if num_workers == 0:
        num_workers = os.cpu_count() or 1
    
    successful = 0
    failed = 0
    
    if num_workers == 1:
        for file_path in files:
            success, message = convert_file(file_path, output_dir, args.dpi, args.force, args.dry_run)
            logger.info(message)
            if success:
                successful += 1
            else:
                failed += 1
    else:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(convert_file, file_path, output_dir, args.dpi, args.force, args.dry_run): file_path 
                      for file_path in files}
            
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    success, message = future.result()
                    logger.info(message)
                    if success:
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Fehler bei {file_path}: {e}")
                    failed += 1
    
    logger.info("")
    logger.info(f"✓ Erfolgreich: {successful}")
    if failed > 0:
        logger.info(f"✗ Fehlgeschlagen: {failed}")

if __name__ == '__main__':
    main()

