#!/usr/bin/env python3
"""
OCR extraction pipeline – converts image-based PDF affidavits to structured data.

Run this in the background while the web app serves basic info from filenames.
Progress is stored in the DB so the web UI can show a live progress bar.

Usage:
    python scripts/ocr_extract.py                 # process all pending
    python scripts/ocr_extract.py --constituency KOLATHUR  # single constituency
    python scripts/ocr_extract.py --workers 4      # set parallelism
    python scripts/ocr_extract.py --reset          # re-process everything
"""

import argparse
import logging
import multiprocessing as mp
import re
import sqlite3
import sys
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import AFFIDAVIT_DIR, DB_PATH, OCR_DPI, OCR_LANG, OCR_WORKERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DB_PATH.parent / "ocr.log"),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

def pdf_to_text(pdf_path: Path, dpi: int = OCR_DPI) -> str:
    """Convert an image-based PDF to text via Tesseract."""
    from pdf2image import convert_from_path
    import pytesseract

    pages = convert_from_path(str(pdf_path), dpi=dpi)
    texts = []
    for page_img in pages:
        text = pytesseract.image_to_string(page_img, lang=OCR_LANG)
        texts.append(text)
        page_img.close()
    return "\n\n--- PAGE BREAK ---\n\n".join(texts)


# ---------------------------------------------------------------------------
# Structured field extraction from OCR text
# ---------------------------------------------------------------------------

def _find_number(text: str, patterns: list[str]) -> float | None:
    """Search for a rupee amount near one of the given patterns."""
    for pat in patterns:
        match = re.search(
            pat + r"[^\d₹]*?[₹Rs.]*\s*([\d,]+(?:\.\d+)?)",
            text, re.IGNORECASE,
        )
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _find_int(text: str, patterns: list[str]) -> int | None:
    for pat in patterns:
        match = re.search(pat + r"\s*[:\-]?\s*(\d+)", text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def parse_affidavit_text(text: str) -> dict:
    """Extract structured fields from OCR text of an ECI Form-26 affidavit."""
    data: dict = {}

    # Age
    age = _find_int(text, [r"age", r"aged"])
    if age and 18 <= age <= 120:
        data["age"] = age

    # Education
    edu_patterns = [
        (r"post\s*graduate|post[\s-]?graduation|m\.?a|m\.?sc|m\.?com|m\.?b\.?a|m\.?tech|m\.?e\b|ph\.?d|doctorate", "Post Graduate"),
        (r"graduate|b\.?a\b|b\.?sc|b\.?com|b\.?tech|b\.?e\b|bachelor|degree", "Graduate"),
        (r"12th|hsc|higher\s*secondary|plus\s*two|\+2|intermediate|xii", "12th Pass"),
        (r"10th|sslc|secondary|matric|xth|class\s*10|std\s*10", "10th Pass"),
        (r"8th|8th\s*pass|middle\s*school|class\s*8", "8th Pass"),
        (r"5th|5th\s*pass|primary|class\s*5", "5th Pass"),
        (r"literate|can\s*read", "Literate"),
        (r"illiterate|not\s*literate|cannot\s*read", "Illiterate"),
        (r"professional|doctor|engineer|lawyer|advocate|chartered\s*accountant", "Professional"),
    ]
    for pattern, label in edu_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            data["education"] = label
            break

    # Profession
    prof_match = re.search(
        r"(?:profession|occupation|source\s*of\s*income)[:\s\-]*([\w\s,/&]+)",
        text, re.IGNORECASE,
    )
    if prof_match:
        prof = prof_match.group(1).strip()[:100]
        if len(prof) > 2:
            data["profession"] = prof

    # Criminal cases
    data["criminal_cases_pending"] = 0
    data["criminal_cases_convicted"] = 0

    pending_section = re.search(
        r"pending\s*criminal\s*case", text, re.IGNORECASE
    )
    if pending_section:
        nil_check = text[pending_section.start():pending_section.start() + 300]
        if re.search(r"\bnil\b|\bnone\b|\bno\b|not\s*applicable", nil_check, re.IGNORECASE):
            data["criminal_cases_pending"] = 0
        else:
            cases = re.findall(r"(?:case|fir|cr\.?\s*no|cc\s*no)[.\s]*\d+", nil_check, re.IGNORECASE)
            data["criminal_cases_pending"] = max(len(cases), 1) if cases else 0

    convicted_section = re.search(
        r"(?:convicted|conviction)", text, re.IGNORECASE
    )
    if convicted_section:
        nil_check = text[convicted_section.start():convicted_section.start() + 300]
        if re.search(r"\bnil\b|\bnone\b|\bno\b|not\s*applicable", nil_check, re.IGNORECASE):
            data["criminal_cases_convicted"] = 0
        else:
            cases = re.findall(r"(?:case|fir|cr\.?\s*no|cc\s*no)[.\s]*\d+", nil_check, re.IGNORECASE)
            data["criminal_cases_convicted"] = max(len(cases), 1) if cases else 0

    # Assets
    movable = _find_number(text, [
        r"total.*movable\s*assets",
        r"grand\s*total.*movable",
        r"total\s*value.*movable",
    ])
    immovable = _find_number(text, [
        r"total.*immovable\s*assets",
        r"grand\s*total.*immovable",
        r"total\s*value.*immovable",
    ])

    if movable is not None:
        data["total_movable_assets"] = movable
    if immovable is not None:
        data["total_immovable_assets"] = immovable
    if movable is not None or immovable is not None:
        data["total_assets"] = (movable or 0) + (immovable or 0)

    # Liabilities
    liabilities = _find_number(text, [
        r"total\s*liabilit",
        r"grand\s*total.*liabilit",
    ])
    if liabilities is not None:
        data["total_liabilities"] = liabilities

    # Gender heuristic
    male_signals = len(re.findall(r"\b(?:son\s+of|s/o|father)\b", text, re.IGNORECASE))
    female_signals = len(re.findall(r"\b(?:daughter\s+of|d/o|wife\s+of|w/o|mother)\b", text, re.IGNORECASE))
    if male_signals > female_signals:
        data["gender"] = "Male"
    elif female_signals > male_signals:
        data["gender"] = "Female"

    return data


# ---------------------------------------------------------------------------
# Process a single candidate
# ---------------------------------------------------------------------------

def process_candidate(args: tuple) -> tuple[int, bool, str]:
    """Process one candidate's affidavits. Returns (candidate_id, success, message)."""
    cand_id, file_paths = args

    try:
        all_text_parts = []
        for fp in file_paths:
            full_path = AFFIDAVIT_DIR.parent / fp
            if full_path.exists():
                text = pdf_to_text(full_path)
                all_text_parts.append(text)

        full_text = "\n\n=== NEXT AFFIDAVIT ===\n\n".join(all_text_parts)

        if not full_text.strip():
            return cand_id, False, "No text extracted"

        parsed = parse_affidavit_text(full_text)

        conn = sqlite3.connect(str(DB_PATH))
        updates = []
        params = []
        for field, value in parsed.items():
            updates.append(f"{field} = ?")
            params.append(value)
        updates.append("ocr_text = ?")
        params.append(full_text)
        updates.append("ocr_status = ?")
        params.append("completed")
        params.append(cand_id)

        conn.execute(
            f"UPDATE candidates SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()

        return cand_id, True, f"OK – {len(parsed)} fields extracted"

    except Exception as e:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                "UPDATE candidates SET ocr_status = 'failed' WHERE id = ?",
                (cand_id,),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        return cand_id, False, str(e)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(constituency: str | None = None, workers: int = OCR_WORKERS, reset: bool = False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if reset:
        log.info("Resetting all OCR status to pending...")
        conn.execute(
            "UPDATE candidates SET ocr_status='pending', ocr_text=NULL, "
            "age=NULL, gender=NULL, education=NULL, profession=NULL, "
            "criminal_cases_pending=NULL, criminal_cases_convicted=NULL, "
            "total_movable_assets=NULL, total_immovable_assets=NULL, "
            "total_assets=NULL, total_liabilities=NULL"
        )
        conn.commit()

    query = (
        "SELECT c.id, GROUP_CONCAT(af.relative_path, '|||') as paths "
        "FROM candidates c "
        "JOIN affidavit_files af ON af.candidate_id = c.id "
    )
    conditions = ["c.ocr_status = 'pending'"]

    if constituency:
        conditions.append(
            "c.constituency_id IN ("
            "  SELECT id FROM constituencies WHERE folder_name = ? OR name LIKE ?"
            ")"
        )

    query += "WHERE " + " AND ".join(conditions)
    query += " GROUP BY c.id"

    if constituency:
        rows = conn.execute(query, (constituency, f"%{constituency}%")).fetchall()
    else:
        rows = conn.execute(query).fetchall()

    tasks = [(row["id"], row["paths"].split("|||")) for row in rows]
    total = len(tasks)
    conn.close()

    if total == 0:
        log.info("No pending candidates to process.")
        return

    log.info(f"Processing {total} candidates with {workers} workers...")

    done = 0
    failed = 0
    start = time.time()

    with mp.Pool(workers) as pool:
        for cand_id, success, msg in pool.imap_unordered(process_candidate, tasks):
            done += 1
            if not success:
                failed += 1
                log.warning(f"  FAIL [{done}/{total}] candidate {cand_id}: {msg}")
            else:
                log.info(f"  OK   [{done}/{total}] candidate {cand_id}: {msg}")

            if done % 10 == 0:
                _update_progress(done, failed, total)

    elapsed = time.time() - start
    log.info(f"Done. {done - failed}/{total} succeeded, {failed} failed in {elapsed:.0f}s")
    _update_progress(done, failed, total)

    # Rebuild FTS index
    _rebuild_fts()


def _update_progress(done: int, failed: int, total: int):
    conn = sqlite3.connect(str(DB_PATH))
    completed = conn.execute(
        "SELECT COUNT(*) FROM candidates WHERE ocr_status='completed'"
    ).fetchone()[0]
    failed_count = conn.execute(
        "SELECT COUNT(*) FROM candidates WHERE ocr_status='failed'"
    ).fetchone()[0]
    total_count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    conn.execute(
        "UPDATE ocr_progress SET total=?, completed=?, failed=?, in_progress=0 WHERE id=1",
        (total_count, completed, failed_count),
    )
    conn.commit()
    conn.close()


def _rebuild_fts():
    """Rebuild the full-text search index."""
    log.info("Rebuilding FTS index...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM candidates_fts")
    conn.execute("""
        INSERT INTO candidates_fts (rowid, name, party, party_full, constituency_name, education, profession, ocr_text)
        SELECT c.id, c.name, c.party, c.party_full, co.name, c.education, c.profession, c.ocr_text
        FROM candidates c
        JOIN constituencies co ON c.constituency_id = co.id
        WHERE c.ocr_status = 'completed'
    """)
    conn.commit()
    conn.close()
    log.info("FTS index rebuilt.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR extraction pipeline")
    parser.add_argument("--constituency", help="Process only this constituency folder")
    parser.add_argument("--workers", type=int, default=OCR_WORKERS)
    parser.add_argument("--reset", action="store_true", help="Re-process all candidates")
    args = parser.parse_args()

    run_pipeline(
        constituency=args.constituency,
        workers=args.workers,
        reset=args.reset,
    )
