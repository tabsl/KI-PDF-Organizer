#!/usr/bin/env python3
"""
Script zum Aufsplitten einer großen PDF-Datei (Stapel-Scan) in einzelne Dokumente.

Erkennt anhand des (ggf. per OCR gewonnenen) Seiteninhalts, wo ein neues Dokument
beginnt, schneidet die Datei an diesen Grenzen und benennt jedes Teildokument
direkt KI-basiert (Datum Absender Dokumenttyp).
"""

import os
import re
import sys
import logging
from pathlib import Path
from typing import Optional
import argparse

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Fehler: PyMuPDF ist nicht installiert.")
    print("Installiere es mit: pip install PyMuPDF")
    sys.exit(1)

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

# Hilfsfunktionen aus dem Rename-Script wiederverwenden (gleiche Logik für
# Dateinamens-Bereinigung, KI-Benennung und Ollama-Erreichbarkeit).
from rename_pdfs import (
    sanitize_filename,
    generate_filename,
    check_ollama_available,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def extract_page_texts(pdf_path: Path, dpi: int = 200) -> list[str]:
    """Extrahiert den Text jeder Seite einzeln.

    Versucht zuerst die eingebettete Textebene (pdfplumber). Seiten ohne
    nutzbaren Text werden per OCR nachgezogen (nötig bei reinen Scans).
    Gibt eine Liste mit einem Text-Eintrag pro Seite zurück.
    """
    page_texts: list[str] = []
    pages_needing_ocr: list[int] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            page_texts.append(page_text)

    for i, text in enumerate(page_texts):
        if len(text.strip()) < 30:
            pages_needing_ocr.append(i)

    if pages_needing_ocr:
        if not OCR_AVAILABLE:
            logger.warning(
                f"  ⚠️  {len(pages_needing_ocr)} Seite(n) ohne Textebene, aber OCR "
                "nicht verfügbar (pytesseract/pdf2image fehlt) – diese Seiten bleiben leer"
            )
        else:
            logger.info(
                f"  → {len(pages_needing_ocr)} Seite(n) ohne Textebene, führe OCR aus (dpi={dpi})..."
            )
            try:
                # In Batches konvertieren, um RAM bei großen Stapeln zu schonen.
                batch_size = 10
                ocr_done = 0
                for batch_start in range(0, len(page_texts), batch_size):
                    batch_end = min(batch_start + batch_size, len(page_texts))
                    # Nur konvertieren, wenn der Batch OCR-bedürftige Seiten enthält.
                    if not any(batch_start <= p < batch_end for p in pages_needing_ocr):
                        continue
                    images = convert_from_path(
                        str(pdf_path), dpi=dpi,
                        first_page=batch_start + 1, last_page=batch_end
                    )
                    for offset, image in enumerate(images):
                        page_idx = batch_start + offset
                        if page_idx not in pages_needing_ocr:
                            continue
                        try:
                            ocr_text = pytesseract.image_to_string(image, lang='deu+eng')
                            page_texts[page_idx] = ocr_text or ""
                            ocr_done += 1
                            logger.info(f"    OCR: Seite {page_idx + 1}/{len(page_texts)}")
                        except Exception as e:
                            logger.debug(f"OCR-Fehler auf Seite {page_idx + 1}: {e}")
                logger.info(f"  ✓ OCR abgeschlossen ({ocr_done} Seite(n))")
            except pytesseract.TesseractNotFoundError:
                logger.warning("  ⚠️  Tesseract OCR nicht gefunden - OCR nicht möglich")
            except Exception as e:
                logger.warning(f"  ⚠️  OCR-Fehler: {e}")

    return page_texts


def _build_ai_client(provider: str):
    """Erstellt den passenden KI-Client. Gibt (client, art) oder (None, None) zurück."""
    if provider == "ollama":
        if not OPENAI_AVAILABLE:
            logger.warning("  ⚠️  OpenAI-Bibliothek benötigt für Ollama-Support")
            return None, None
        if not check_ollama_available():
            logger.warning("  ⚠️  Ollama läuft nicht oder ist nicht erreichbar (http://localhost:11434)")
            return None, None
        return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), "openai"
    if provider == "openai":
        if not OPENAI_AVAILABLE:
            logger.warning("  ⚠️  OpenAI-Bibliothek nicht verfügbar")
            return None, None
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("  ⚠️  Kein OpenAI API-Key gefunden")
            return None, None
        return OpenAI(api_key=api_key), "openai"
    if provider == "anthropic":
        if not ANTHROPIC_AVAILABLE:
            logger.warning("  ⚠️  Anthropic-Bibliothek nicht verfügbar")
            return None, None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("  ⚠️  Kein Anthropic API-Key gefunden")
            return None, None
        return Anthropic(api_key=api_key), "anthropic"
    logger.warning(f"  ⚠️  Unbekannter Provider: {provider}")
    return None, None


def _model_for(provider: str) -> str:
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")


def _ai_text(client, kind: str, provider: str, system: str, prompt: str,
             max_tokens: int) -> tuple[str, Optional[str]]:
    """Ruft die KI auf und gibt (text, finish_reason) zurück.

    Reasoning-Modelle legen ihren Denkprozess in einem separaten Kanal ab; der
    eigentliche Text steht erst danach in content. Das Token-Budget muss daher
    groß genug sein, damit content nicht leer bleibt.
    """
    if kind == "openai":
        response = client.chat.completions.create(
            model=_model_for(provider),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip(), response.choices[0].finish_reason
    response = client.messages.create(
        model=_model_for(provider),
        max_tokens=max_tokens,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip(), response.stop_reason


def _is_new_document(prev_text: str, cur_text: str, client, kind: str,
                     provider: str) -> bool:
    """Fragt die KI, ob die aktuelle Seite ein neues Dokument beginnt.

    Bewusst als fokussierte Ja/Nein-Entscheidung über nur zwei Seiten gestaltet:
    kurze Prompts funktionieren zuverlässig mit jedem Modell (auch Reasoning-
    Modellen) und skalieren auf beliebig große Stapel.
    """
    prev = re.sub(r'\s+', ' ', prev_text.strip())[-400:] or "(leer)"
    cur = re.sub(r'\s+', ' ', cur_text.strip())[:400] or "(leer)"

    system = (
        "Du segmentierst gescannte Dokumentenstapel. Du entscheidest, ob eine Seite "
        "ein neues Dokument beginnt, und antwortest mit genau einem Wort: NEU oder FORTSETZUNG."
    )
    prompt = f"""Zwei aufeinanderfolgende Seiten eines Scan-Stapels. Beginnt auf der ZWEITEN Seite ein NEUES, eigenständiges Dokument (neuer Briefkopf, anderer Absender, neuer Betreff, neues Datum, neue Anrede), oder ist es die FORTSETZUNG des vorherigen Dokuments (Folgeseite, Anlage, Tabellenfortsetzung)?

Antworte mit EINEM Wort: NEU oder FORTSETZUNG.

== Ende vorherige Seite ==
{prev}

== Anfang aktuelle Seite ==
{cur}

Antwort:"""

    try:
        raw, finish = _ai_text(client, kind, provider, system, prompt, max_tokens=4000)
    except Exception as e:
        logger.warning(f"      ⚠️  KI-Fehler bei Seitenübergang: {e} - werte als FORTSETZUNG")
        return False

    if not raw:
        if finish in ("length", "max_tokens"):
            logger.warning("      ⚠️  KI-Antwort leer (Token-Budget) - werte als FORTSETZUNG")
        return False

    # Erstes klares Schlüsselwort gewinnt (robust gegen Zusatztext).
    upper = raw.upper()
    pos_new = upper.find("NEU")
    pos_cont = upper.find("FORTSETZUNG")
    if pos_new == -1:
        return False
    if pos_cont == -1:
        return True
    return pos_new < pos_cont


# Eindeutige Textmarker, die eine KI-Entscheidung überflüssig machen. Sie greifen
# v.a. bei seriellen, optisch fast identischen Dokumenten (z.B. monatliche
# Lohnabrechnungen), bei denen die reine Bildähnlichkeit das Modell in die Irre führt.

_CONTINUATION_PATTERNS = [
    re.compile(r'\b(seite|blatt)\s*[2-9]\b', re.IGNORECASE),
    re.compile(r'\bseite\s*[2-9]\s*(von|/)', re.IGNORECASE),
]

_START_PATTERNS = [
    re.compile(r'\b(seite|blatt)\s*1\s*(von|/)', re.IGNORECASE),
    re.compile(r'\bblatt\s*1\b', re.IGNORECASE),
    # DATEV-Lohnabrechnung: jede Monatsabrechnung trägt diese eigene Kopfzeile,
    # Folgeseiten (Beitrags-/Steuertabellen) hingegen nicht.
    re.compile(r'abrechnung der brutto', re.IGNORECASE),
    # Jahres-Lohnsteuerbescheinigung als eigenständiges Dokument.
    re.compile(r'lohnsteuerbescheinigung', re.IGNORECASE),
]


def _has_continuation_marker(text: str) -> bool:
    """True, wenn die Seite sich klar als Folgeseite ausweist (z.B. 'Seite 2 von 3')."""
    return any(p.search(text) for p in _CONTINUATION_PATTERNS)


def _has_start_marker(text: str) -> bool:
    """True, wenn die Seite einen eindeutigen Dokumentanfang trägt (z.B. 'Blatt 1')."""
    return any(p.search(text) for p in _START_PATTERNS)


# Dokumenttypen (spezifischere zuerst, da der erste Treffer gewinnt). Dienen als
# Wächter gegen falsches Zusammenführen: zwei Seiten mit gemeinsamer ID, aber
# unterschiedlichem Typ (z.B. Rechnung vs. Annahmebeleg) sind verschiedene Dokumente.
_DOC_TYPES = [
    'annahmebeleg', 'lohnsteuerbescheinigung', 'kostenvoranschlag',
    'renteninformation', 'frachtbrief', 'rechnung', 'abrechnung',
    'bescheid', 'mahnung', 'vereinbarung',
]


def _doc_type(text: str) -> Optional[str]:
    """Grober Dokumenttyp anhand eines Schlüsselworts (Wortgrenzen), sonst None."""
    tl = text.lower()
    for w in _DOC_TYPES:
        if re.search(r'\b' + w + r'\b', tl):
            return w
    return None


def _shared_document_id(prev_text: str, cur_text: str) -> bool:
    """True, wenn beide Seiten dieselbe markante lange Zahl (>=7 Ziffern) tragen
    UND sich kein Dokumenttyp-Wechsel zeigt.

    Eine geteilte Akten-/Service-/Kundennummer ist ein starkes Signal dafür, dass
    eine Folgeseite zum selben Dokument gehört (z.B. mehrseitiger Annahmebeleg).
    Der Typ-Wächter verhindert, dass Dokumente desselben Absenders mit gemeinsamer
    Footer-/Steuernummer (z.B. eine Rechnung vs. ein Annahmebeleg derselben Firma)
    verschmolzen werden.
    """
    nums_prev = set(re.findall(r'\d{7,}', re.sub(r'[^0-9]', ' ', prev_text)))
    nums_cur = set(re.findall(r'\d{7,}', re.sub(r'[^0-9]', ' ', cur_text)))
    if not (nums_prev & nums_cur):
        return False
    tp, tc = _doc_type(prev_text), _doc_type(cur_text)
    if tp and tc and tp != tc:
        return False
    return True


def detect_document_boundaries(
    page_texts: list[str], provider: str
) -> list[tuple[int, int]]:
    """Bestimmt seitenweise, wo neue Dokumente beginnen.

    Liefert eine Liste von (start, end)-Seitenbereichen (1-basiert, inklusiv).
    (Fast) leere Seiten werden ohne KI-Aufruf als Fortsetzung gewertet
    (Rück-/Trennseiten gehören zum vorherigen Dokument). Ist keine KI verfügbar,
    wird die gesamte Datei als ein Dokument behandelt.
    """
    num_pages = len(page_texts)
    if num_pages <= 1:
        return [(1, num_pages)]

    client, kind = _build_ai_client(provider)
    if client is None:
        logger.warning("  ⚠️  Keine KI verfügbar - behandle gesamte Datei als ein Dokument")
        return [(1, num_pages)]

    starts = [1]  # Seite 1 beginnt immer ein Dokument.
    for i in range(2, num_pages + 1):
        cur_text = page_texts[i - 1]
        if len(cur_text.strip()) < 20:
            # Leere/Trennseite -> gehört zum laufenden Dokument.
            logger.info(f"    Seite {i}: (leer) → Fortsetzung")
            continue
        # Eindeutige Marker zuerst prüfen (spart KI-Aufruf und ist zuverlässiger
        # als die Bildähnlichkeit bei seriellen Dokumenten).
        if _has_continuation_marker(cur_text):
            logger.info(f"    Seite {i}: Marker 'Folgeseite' → Fortsetzung")
            continue
        if _has_start_marker(cur_text):
            logger.info(f"    Seite {i}: Marker 'Dokumentanfang' → NEU")
            starts.append(i)
            continue
        # Vergleichstext der letzten nicht-leeren Vorseite verwenden.
        prev_text = page_texts[i - 2]
        # Geteilte Dokument-ID (ohne Typwechsel) = selbe Akte/Sendung → Fortsetzung.
        if _shared_document_id(prev_text, cur_text):
            logger.info(f"    Seite {i}: gemeinsame Dokument-ID → Fortsetzung")
            continue
        is_new = _is_new_document(prev_text, cur_text, client, kind, provider)
        logger.info(f"    Seite {i}: {'NEU – neues Dokument' if is_new else 'Fortsetzung'}")
        if is_new:
            starts.append(i)

    ranges: list[tuple[int, int]] = []
    for idx, start in enumerate(starts):
        end = (starts[idx + 1] - 1) if idx + 1 < len(starts) else num_pages
        ranges.append((start, end))
    return ranges


def split_pdf(
    pdf_path: Path,
    provider: str,
    dry_run: bool = False,
    dpi: int = 200,
) -> int:
    """Splittet eine PDF in Einzeldokumente. Gibt die Anzahl erzeugter Dateien zurück."""
    logger.info(f"\nVerarbeite: {pdf_path}")

    try:
        with fitz.open(pdf_path) as probe:
            num_pages = probe.page_count
    except Exception as e:
        logger.error(f"  ✗ Konnte PDF nicht öffnen: {e}")
        return 0

    if num_pages == 0:
        logger.warning("  ⚠️  PDF hat keine Seiten")
        return 0

    logger.info(f"  → {num_pages} Seite(n) gefunden")

    page_texts = extract_page_texts(pdf_path, dpi=dpi)
    ranges = detect_document_boundaries(page_texts, provider=provider)

    logger.info(f"  → {len(ranges)} Dokument(e) erkannt:")
    for start, end in ranges:
        span = f"Seite {start}" if start == end else f"Seiten {start}-{end}"
        logger.info(f"      • {span}")

    output_dir = pdf_path.parent / f"{pdf_path.stem}_split"

    if dry_run:
        logger.info(f"  [DRY-RUN] Würde {len(ranges)} Datei(en) anlegen in: {output_dir}")
        return len(ranges)

    output_dir.mkdir(exist_ok=True)
    created = 0

    with fitz.open(pdf_path) as src:
        for idx, (start, end) in enumerate(ranges, 1):
            # Text der zum Dokument gehörenden Seiten für die KI-Benennung zusammenführen.
            doc_text = "\n".join(page_texts[start - 1:end]).strip()

            new_name = None
            if doc_text and len(doc_text) >= 10:
                # generate_filename erwartet einen Originalpfad (für Datums-Fallback);
                # wir geben den geplanten nummerierten Namen mit.
                placeholder = output_dir / f"{pdf_path.stem}_{idx:02d}.pdf"
                new_name = generate_filename(doc_text, placeholder, provider=provider)

            if not new_name:
                new_name = f"{pdf_path.stem}_{idx:02d}.pdf"
                logger.info(f"      → Kein KI-Name möglich, verwende: {new_name}")

            target = output_dir / new_name
            counter = 1
            while target.exists():
                stem = new_name[:-4] if new_name.endswith('.pdf') else new_name
                target = output_dir / f"{stem}-{counter}.pdf"
                counter += 1

            try:
                out = fitz.open()
                out.insert_pdf(src, from_page=start - 1, to_page=end - 1)
                out.save(str(target))
                out.close()
                created += 1
                logger.info(f"  ✓ {target.name}  (Seiten {start}-{end})")
            except Exception as e:
                logger.error(f"  ✗ Fehler beim Speichern von Dokument {idx}: {e}")

    logger.info(f"  ✓ {created}/{len(ranges)} Dokument(e) gespeichert in: {output_dir}")
    return created


def main():
    parser = argparse.ArgumentParser(
        description='Splittet große PDF-Stapel in einzelne Dokumente (KI-basierte Erkennung & Benennung)'
    )
    parser.add_argument(
        'path',
        help='Pfad zu einer PDF-Datei oder einem Verzeichnis mit PDF-Dateien'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Zeigt erkannte Dokumentgrenzen an, ohne Dateien zu schreiben'
    )
    parser.add_argument(
        '--provider',
        choices=['openai', 'anthropic', 'ollama'],
        help='KI-Provider: openai, anthropic oder ollama (überschreibt AI_PROVIDER aus .env)'
    )
    parser.add_argument(
        '--dpi',
        type=int,
        default=200,
        help='OCR-Auflösung für Seiten ohne Textebene (Standard: 200)'
    )

    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        logger.error(f"Fehler: Pfad existiert nicht: {path}")
        sys.exit(1)

    if path.is_file() and path.suffix.lower() == '.pdf':
        pdf_files = [path]
    elif path.is_dir():
        pdf_files = sorted(list(path.glob('*.pdf')) + list(path.glob('*.PDF')))
    else:
        logger.error(f"Fehler: {path} ist weder eine PDF-Datei noch ein Verzeichnis")
        sys.exit(1)

    if not pdf_files:
        logger.info("Keine PDF-Dateien gefunden.")
        sys.exit(0)

    provider = args.provider.lower() if args.provider else os.getenv("AI_PROVIDER", "openai").lower()

    # KI-Verfügbarkeit vorab prüfen (Splitting ohne KI ergibt nur ein Dokument).
    if provider == "ollama":
        if not check_ollama_available():
            logger.error("❌ Ollama läuft nicht oder ist nicht erreichbar!")
            logger.error("   Starte Ollama mit: brew services start ollama")
            sys.exit(1)
    else:
        api_key = os.getenv("OPENAI_API_KEY") if provider == "openai" else os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("❌ Kein API-Key gefunden!")
            logger.error("   Setze OPENAI_API_KEY oder ANTHROPIC_API_KEY (oder nutze --provider ollama).")
            sys.exit(1)

    if args.dry_run:
        logger.info("DRY-RUN Modus: Es werden keine Dateien geschrieben")
    logger.info(f"🤖 Verwende KI ({provider}) für Dokumenterkennung und Benennung")
    logger.info(f"Gefunden: {len(pdf_files)} PDF-Datei(en)")

    total = 0
    for pdf_file in pdf_files:
        total += split_pdf(pdf_file, provider=provider, dry_run=args.dry_run, dpi=args.dpi)

    logger.info(f"\n✓ Insgesamt {total} Einzeldokument(e) {'erkannt' if args.dry_run else 'erstellt'}")


if __name__ == '__main__':
    main()
