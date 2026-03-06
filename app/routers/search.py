"""類似長文検索エンドポイント。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.auth import is_student
from app.config import GENRE_MAIN_LIST
from app.db import get_connection
from app.search import find_similar

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/api/search/passages")
async def list_passages(request: Request):
    """類似検索のパッセージ選択用一覧（long_readingのみ）。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, university, year, question_number, passage_index,
                      theme, genre_main, cefr_score, cefr_level, word_count
               FROM passages
               WHERE text_type = 'long_reading' AND text_body != ''
               ORDER BY university, year, question_number, passage_index"""
        ).fetchall()
    finally:
        conn.close()

    passages = []
    for r in rows:
        label_parts = [r["university"], f"{r['year']}年"]
        if r["theme"]:
            label_parts.append(r["theme"])
        if r["cefr_level"]:
            label_parts.append(f"[{r['cefr_level']}]")
        passages.append({
            "id": r["id"],
            "label": " ".join(label_parts),
            "university": r["university"],
            "year": r["year"],
            "cefr_level": r["cefr_level"] or "",
            "cefr_score": r["cefr_score"],
        })

    return JSONResponse(passages)


@router.get("/api/search/similar")
async def search_similar(
    request: Request,
    passage_id: str = "",
    top_k: int = 10,
    cefr_min: Optional[float] = None,
    cefr_max: Optional[float] = None,
    genre_main: str = "",
    exclude_same_university: int = 1,
):
    """類似長文検索（HTMXパーシャル）。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)

    if not passage_id:
        return templates.TemplateResponse(
            "partials/similar_results.html",
            {"request": request, "source": None, "results": [], "error": "パッセージを選択してください"},
        )

    source, results = find_similar(
        source_id=passage_id,
        top_k=top_k,
        cefr_min=cefr_min,
        cefr_max=cefr_max,
        genre_main=genre_main or None,
        exclude_same_university=bool(exclude_same_university),
    )

    if source is None:
        return templates.TemplateResponse(
            "partials/similar_results.html",
            {"request": request, "source": None, "results": [], "error": "パッセージが見つかりません"},
        )

    return templates.TemplateResponse(
        "partials/similar_results.html",
        {"request": request, "source": source, "results": results, "error": None},
    )
