"""JSON API routes for AJAX calls and data export."""

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.database import (
    get_db,
    query_candidates,
    query_candidates_for_compare,
    query_constituencies,
    query_ocr_progress,
    query_overall_stats,
    query_party_stats,
    search_candidates,
)

router = APIRouter()


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


@router.get("/stats")
async def api_stats():
    conn = get_db()
    stats = _row_to_dict(query_overall_stats(conn))
    progress = _row_to_dict(query_ocr_progress(conn))
    conn.close()
    return {"stats": stats, "progress": progress}


@router.get("/constituencies")
async def api_constituencies(q: str = Query("")):
    conn = get_db()
    rows = query_constituencies(conn, search=q)
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/candidates/{constituency_id}")
async def api_candidates(constituency_id: int, sort: str = Query("name")):
    conn = get_db()
    rows = query_candidates(conn, constituency_id, sort_by=sort)
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/search")
async def api_search(q: str = Query("")):
    if not q:
        return []
    conn = get_db()
    rows = search_candidates(conn, q)
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/compare")
async def api_compare(ids: str = Query("")):
    if not ids:
        return []
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    conn = get_db()
    rows = query_candidates_for_compare(conn, id_list)
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/party-stats")
async def api_party_stats():
    conn = get_db()
    rows = query_party_stats(conn)
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/progress")
async def api_progress():
    conn = get_db()
    progress = _row_to_dict(query_ocr_progress(conn))
    conn.close()
    return progress


@router.get("/export/candidates")
async def export_candidates_csv(constituency_id: int = Query(None)):
    """Export candidate data as CSV for journalists."""
    conn = get_db()
    if constituency_id:
        rows = query_candidates(conn, constituency_id)
    else:
        rows = conn.execute(
            "SELECT c.*, co.name as constituency_name "
            "FROM candidates c JOIN constituencies co ON c.constituency_id = co.id "
            "ORDER BY co.name, c.name"
        ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Constituency", "Name", "Party", "Party (Full)", "Age",
        "Education", "Profession", "Criminal Cases (Pending)",
        "Criminal Cases (Convicted)", "Movable Assets (₹)",
        "Immovable Assets (₹)", "Total Assets (₹)", "Liabilities (₹)",
    ])
    for r in rows:
        writer.writerow([
            r["constituency_name"], r["name"], r["party"], r["party_full"],
            r["age"] or "", r["education"] or "", r["profession"] or "",
            r["criminal_cases_pending"] if r["criminal_cases_pending"] is not None else "",
            r["criminal_cases_convicted"] if r["criminal_cases_convicted"] is not None else "",
            r["total_movable_assets"] or "", r["total_immovable_assets"] or "",
            r["total_assets"] or "", r["total_liabilities"] or "",
        ])

    output.seek(0)
    filename = "tn_candidates.csv"
    if constituency_id:
        filename = f"candidates_constituency_{constituency_id}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
