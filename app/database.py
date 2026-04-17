"""SQLite database – schema, population from filenames, and query helpers."""

import re
import sqlite3
from pathlib import Path

from config import AFFIDAVIT_DIR, DB_PATH, PARTY_FULL_NAMES


# ---------------------------------------------------------------------------
# Name formatting
# ---------------------------------------------------------------------------

def format_candidate_name(raw: str) -> str:
    """Convert CamelCase filename name to readable form.

    MKStalin     → M.K. Stalin
    TMAnbarasan  → T.M. Anbarasan
    MaheshKumar  → Mahesh Kumar
    JanarthananP → Janarthanan P.
    """
    tokens: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch.isupper():
            # Peek ahead to decide: initial letter vs start of a word
            if i + 1 < len(raw) and raw[i + 1].isupper():
                tokens.append(ch + ".")
                i += 1
            elif i + 1 < len(raw) and raw[i + 1].islower():
                word = ch
                i += 1
                while i < len(raw) and raw[i].islower():
                    word += raw[i]
                    i += 1
                tokens.append(word)
            else:
                tokens.append(ch + ".")
                i += 1
        else:
            i += 1
    return " ".join(tokens)


def format_constituency_name(folder: str) -> str:
    """ANNA_NAGAR → Anna Nagar, CHEPAUK-THIRUVALLIKENI → Chepauk-Thiruvallikeni."""
    parts = folder.split("-")
    formatted = []
    for part in parts:
        sub = part.replace("_", " ").strip()
        formatted.append(sub.title())
    return "-".join(formatted)


def parse_filename(fname: str):
    """Parse '{Name}-{Party}-{N}.pdf' → (raw_name, party, affidavit_num)."""
    stem = Path(fname).stem
    parts = stem.rsplit("-", 2)
    if len(parts) == 3:
        return parts[0], parts[1], int(parts[2])
    if len(parts) == 2:
        try:
            return parts[0], parts[1], 1
        except ValueError:
            return stem, "Unknown", 1
    return stem, "Unknown", 1


def party_full_name(code: str) -> str:
    return PARTY_FULL_NAMES.get(code, code)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS constituencies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    folder_name     TEXT    NOT NULL UNIQUE,
    candidate_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    constituency_id         INTEGER NOT NULL REFERENCES constituencies(id),
    name                    TEXT    NOT NULL,
    raw_name                TEXT    NOT NULL,
    party                   TEXT    NOT NULL,
    party_full              TEXT,
    affidavit_count         INTEGER DEFAULT 1,

    -- OCR-extracted fields (NULL until OCR completes)
    age                     INTEGER,
    gender                  TEXT,
    education               TEXT,
    profession              TEXT,
    criminal_cases_pending  INTEGER,
    criminal_cases_convicted INTEGER,
    total_movable_assets    REAL,
    total_immovable_assets  REAL,
    total_assets            REAL,
    total_liabilities       REAL,

    ocr_text                TEXT,
    ocr_status              TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS affidavit_files (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id     INTEGER NOT NULL REFERENCES candidates(id),
    file_name        TEXT    NOT NULL,
    relative_path    TEXT    NOT NULL,
    affidavit_number INTEGER DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS candidates_fts USING fts5(
    name, party, party_full, constituency_name, education, profession, ocr_text,
    content='', content_rowid=''
);

CREATE TABLE IF NOT EXISTS ocr_progress (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    total           INTEGER DEFAULT 0,
    completed       INTEGER DEFAULT 0,
    failed          INTEGER DEFAULT 0,
    in_progress     INTEGER DEFAULT 0
);
"""


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables and populate from the filesystem if the DB is empty."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)

    count = conn.execute("SELECT COUNT(*) FROM constituencies").fetchone()[0]
    if count == 0:
        _populate_from_filesystem(conn)

    # Ensure progress row exists
    conn.execute(
        "INSERT OR IGNORE INTO ocr_progress (id, total, completed, failed, in_progress) "
        "VALUES (1, 0, 0, 0, 0)"
    )
    total = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    completed = conn.execute(
        "SELECT COUNT(*) FROM candidates WHERE ocr_status = 'completed'"
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM candidates WHERE ocr_status = 'failed'"
    ).fetchone()[0]
    conn.execute(
        "UPDATE ocr_progress SET total=?, completed=?, failed=? WHERE id=1",
        (total, completed, failed),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Filesystem → DB
# ---------------------------------------------------------------------------

def _populate_from_filesystem(conn: sqlite3.Connection):
    """Scan affidavit folders and create constituency + candidate rows."""
    if not AFFIDAVIT_DIR.exists():
        return

    for folder in sorted(AFFIDAVIT_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        display_name = format_constituency_name(folder.name)
        conn.execute(
            "INSERT INTO constituencies (name, folder_name) VALUES (?, ?)",
            (display_name, folder.name),
        )
        c_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Group files by (raw_name, party)
        candidate_files: dict[tuple[str, str], list[tuple[str, int]]] = {}
        for pdf in sorted(folder.glob("*.pdf")):
            raw_name, party, anum = parse_filename(pdf.name)
            key = (raw_name, party)
            candidate_files.setdefault(key, []).append((pdf.name, anum))

        for (raw_name, party), files in candidate_files.items():
            display = format_candidate_name(raw_name)
            conn.execute(
                "INSERT INTO candidates "
                "(constituency_id, name, raw_name, party, party_full, affidavit_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (c_id, display, raw_name, party, party_full_name(party), len(files)),
            )
            cand_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for fname, anum in files:
                rel = f"{folder.name}/{fname}"
                conn.execute(
                    "INSERT INTO affidavit_files "
                    "(candidate_id, file_name, relative_path, affidavit_number) "
                    "VALUES (?, ?, ?, ?)",
                    (cand_id, fname, rel, anum),
                )

        cand_count = len(candidate_files)
        conn.execute(
            "UPDATE constituencies SET candidate_count = ? WHERE id = ?",
            (cand_count, c_id),
        )

    conn.commit()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def query_constituencies(conn: sqlite3.Connection, search: str = ""):
    sql = "SELECT * FROM constituencies"
    params: list = []
    if search:
        sql += " WHERE name LIKE ?"
        params.append(f"%{search}%")
    sql += " ORDER BY name"
    return conn.execute(sql, params).fetchall()


def query_constituency(conn: sqlite3.Connection, c_id: int):
    return conn.execute("SELECT * FROM constituencies WHERE id = ?", (c_id,)).fetchone()


def query_constituency_by_folder(conn: sqlite3.Connection, folder: str):
    return conn.execute(
        "SELECT * FROM constituencies WHERE folder_name = ?", (folder,)
    ).fetchone()


def query_candidates(conn: sqlite3.Connection, constituency_id: int, sort_by: str = "name"):
    valid_sorts = {
        "name": "c.name",
        "party": "c.party",
        "assets": "COALESCE(c.total_assets, 0) DESC",
        "criminal": "COALESCE(c.criminal_cases_pending, 0) DESC",
    }
    order = valid_sorts.get(sort_by, "c.name")
    # If sort already contains DESC, don't add ASC
    if "DESC" not in order:
        order += " ASC"
    return conn.execute(
        f"SELECT c.*, co.name as constituency_name, co.folder_name "
        f"FROM candidates c JOIN constituencies co ON c.constituency_id = co.id "
        f"WHERE c.constituency_id = ? ORDER BY {order}",
        (constituency_id,),
    ).fetchall()


def query_candidate(conn: sqlite3.Connection, cand_id: int):
    return conn.execute(
        "SELECT c.*, co.name as constituency_name, co.folder_name "
        "FROM candidates c JOIN constituencies co ON c.constituency_id = co.id "
        "WHERE c.id = ?",
        (cand_id,),
    ).fetchone()


def query_candidate_files(conn: sqlite3.Connection, cand_id: int):
    return conn.execute(
        "SELECT * FROM affidavit_files WHERE candidate_id = ? ORDER BY affidavit_number",
        (cand_id,),
    ).fetchall()


def search_candidates(conn: sqlite3.Connection, q: str, limit: int = 50):
    like = f"%{q}%"
    return conn.execute(
        "SELECT c.*, co.name as constituency_name, co.folder_name "
        "FROM candidates c JOIN constituencies co ON c.constituency_id = co.id "
        "WHERE c.name LIKE ? OR c.party LIKE ? OR c.party_full LIKE ? "
        "OR co.name LIKE ? OR c.education LIKE ? "
        "ORDER BY c.name LIMIT ?",
        (like, like, like, like, like, limit),
    ).fetchall()


def query_party_stats(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT party, party_full, COUNT(*) as count, "
        "AVG(total_assets) as avg_assets, "
        "SUM(CASE WHEN criminal_cases_pending > 0 THEN 1 ELSE 0 END) as with_cases, "
        "AVG(total_assets) as avg_assets_val, "
        "MAX(total_assets) as max_assets "
        "FROM candidates "
        "GROUP BY party "
        "ORDER BY count DESC"
    ).fetchall()


def query_overall_stats(conn: sqlite3.Connection):
    row = conn.execute(
        "SELECT COUNT(*) as total_candidates, "
        "COUNT(DISTINCT constituency_id) as total_constituencies, "
        "COUNT(DISTINCT party) as total_parties, "
        "SUM(CASE WHEN ocr_status = 'completed' THEN 1 ELSE 0 END) as ocr_done, "
        "AVG(CASE WHEN total_assets IS NOT NULL THEN total_assets END) as avg_assets, "
        "MAX(total_assets) as max_assets, "
        "SUM(CASE WHEN criminal_cases_pending > 0 THEN 1 ELSE 0 END) as with_criminal "
        "FROM candidates"
    ).fetchone()
    return row


def query_ocr_progress(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM ocr_progress WHERE id = 1").fetchone()


def query_candidates_for_compare(conn: sqlite3.Connection, ids: list[int]):
    placeholders = ",".join("?" * len(ids))
    return conn.execute(
        f"SELECT c.*, co.name as constituency_name, co.folder_name "
        f"FROM candidates c JOIN constituencies co ON c.constituency_id = co.id "
        f"WHERE c.id IN ({placeholders})",
        ids,
    ).fetchall()


def query_education_stats(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT education, COUNT(*) as count FROM candidates "
        "WHERE education IS NOT NULL AND education != '' "
        "GROUP BY education ORDER BY count DESC"
    ).fetchall()


def query_asset_distribution(conn: sqlite3.Connection):
    """Bucket candidates into asset ranges."""
    return conn.execute("""
        SELECT
            CASE
                WHEN total_assets IS NULL THEN 'Data Pending'
                WHEN total_assets < 1000000 THEN 'Under ₹10 Lakh'
                WHEN total_assets < 10000000 THEN '₹10 Lakh – ₹1 Cr'
                WHEN total_assets < 100000000 THEN '₹1 Cr – ₹10 Cr'
                WHEN total_assets < 1000000000 THEN '₹10 Cr – ₹100 Cr'
                ELSE 'Above ₹100 Cr'
            END as bucket,
            COUNT(*) as count
        FROM candidates
        GROUP BY bucket
        ORDER BY
            CASE bucket
                WHEN 'Under ₹10 Lakh' THEN 1
                WHEN '₹10 Lakh – ₹1 Cr' THEN 2
                WHEN '₹1 Cr – ₹10 Cr' THEN 3
                WHEN '₹10 Cr – ₹100 Cr' THEN 4
                WHEN 'Above ₹100 Cr' THEN 5
                ELSE 6
            END
    """).fetchall()


def query_crorepati_candidates(conn: sqlite3.Connection, limit: int = 20):
    return conn.execute(
        "SELECT c.*, co.name as constituency_name "
        "FROM candidates c JOIN constituencies co ON c.constituency_id = co.id "
        "WHERE c.total_assets >= 10000000 "
        "ORDER BY c.total_assets DESC LIMIT ?",
        (limit,),
    ).fetchall()
