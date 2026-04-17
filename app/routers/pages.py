"""HTML page routes – serves Jinja2 templates."""

from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import (
    get_db,
    query_asset_distribution,
    query_candidate,
    query_candidate_files,
    query_candidates,
    query_candidates_for_compare,
    query_constituencies,
    query_constituency,
    query_crorepati_candidates,
    query_education_stats,
    query_ocr_progress,
    query_overall_stats,
    query_party_stats,
    search_candidates,
)
from config import AFFIDAVIT_DIR, APP_TITLE, ELECTION_DATE, TOTAL_CONSTITUENCIES

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _format_inr(value) -> str:
    if value is None:
        return "—"
    v = float(value)
    if v >= 1e7:
        return f"₹{v / 1e7:,.2f} Cr"
    if v >= 1e5:
        return f"₹{v / 1e5:,.2f} L"
    if v >= 1e3:
        return f"₹{v / 1e3:,.1f} K"
    return f"₹{v:,.0f}"


templates.env.filters["inr"] = _format_inr
templates.env.globals["total_constituencies"] = TOTAL_CONSTITUENCIES


def _ctx(request: Request, **kw):
    return {"request": request, "app_title": APP_TITLE, "election_date": ELECTION_DATE, **kw}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, q: str = Query("", alias="q")):
    conn = get_db()
    constituencies = query_constituencies(conn, search=q)
    stats = query_overall_stats(conn)
    progress = query_ocr_progress(conn)
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=_ctx(request, constituencies=constituencies, stats=stats,
                     progress=progress, search=q),
    )


@router.get("/constituency/{c_id}", response_class=HTMLResponse)
async def constituency_page(
    request: Request,
    c_id: int,
    sort: str = Query("name"),
):
    conn = get_db()
    constituency = query_constituency(conn, c_id)
    if not constituency:
        conn.close()
        return HTMLResponse("Constituency not found", status_code=404)
    candidates = query_candidates(conn, c_id, sort_by=sort)
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="constituency.html",
        context=_ctx(request, constituency=constituency, candidates=candidates, sort=sort),
    )


@router.get("/candidate/{cand_id}", response_class=HTMLResponse)
async def candidate_page(request: Request, cand_id: int):
    conn = get_db()
    candidate = query_candidate(conn, cand_id)
    if not candidate:
        conn.close()
        return HTMLResponse("Candidate not found", status_code=404)
    files = query_candidate_files(conn, cand_id)
    # Peers in same constituency for quick navigation
    peers = query_candidates(conn, candidate["constituency_id"])
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="candidate.html",
        context=_ctx(request, candidate=candidate, files=files, peers=peers),
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request, ids: str = Query("")):
    conn = get_db()
    candidates = []
    constituency = None
    all_in_constituency = []
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            candidates = query_candidates_for_compare(conn, id_list)
            if candidates:
                constituency = query_constituency(conn, candidates[0]["constituency_id"])
                all_in_constituency = query_candidates(conn, candidates[0]["constituency_id"])
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context=_ctx(request, candidates=candidates, constituency=constituency,
                     all_in_constituency=all_in_constituency, selected_ids=ids),
    )


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    conn = get_db()
    stats = query_overall_stats(conn)
    party_stats = _rows_to_dicts(query_party_stats(conn))
    edu_stats = _rows_to_dicts(query_education_stats(conn))
    asset_dist = _rows_to_dicts(query_asset_distribution(conn))
    crorepatis = _rows_to_dicts(query_crorepati_candidates(conn, limit=20))
    progress = query_ocr_progress(conn)
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context=_ctx(request, stats=stats, party_stats=party_stats,
                     edu_stats=edu_stats, asset_dist=asset_dist,
                     crorepatis=crorepatis, progress=progress),
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = Query("")):
    conn = get_db()
    results = search_candidates(conn, q) if q else []
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="search_results.html",
        context=_ctx(request, results=results, query=q),
    )


@router.get("/pdf/{constituency}/{filename}")
async def serve_pdf(constituency: str, filename: str):
    """Serve an original PDF affidavit for viewing / download."""
    path = AFFIDAVIT_DIR / constituency / filename
    if not path.exists() or not path.suffix.lower() == ".pdf":
        return HTMLResponse("File not found", status_code=404)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
    )
