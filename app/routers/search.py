"""類似長文検索エンドポイント。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import GENRE_MAIN_LIST
from app.db import get_connection
from app.search import cefr_display, find_similar

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/api/search/passages")
async def list_passages(request: Request):
    """類似検索のパッセージ選択用一覧（long_readingのみ）。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT p.id, p.university, p.year, p.question_number, p.passage_index,
                      p.theme, p.genre_main, p.cefr_score, p.cefr_level, p.word_count,
                      u.university_class, u.region
               FROM passages p LEFT JOIN universities u ON p.university = u.name
               WHERE p.text_type = 'long_reading' AND p.text_body != ''
               ORDER BY p.year DESC,
                 CASE u.university_class WHEN '旧帝大' THEN 1 WHEN '難関大' THEN 2 WHEN '準難関大' THEN 3 WHEN 'その他国立大' THEN 4 WHEN 'その他公立大' THEN 5 ELSE 6 END,
                 CASE u.region WHEN '東北以北' THEN 1 WHEN '関東' THEN 2 WHEN '中部' THEN 3 WHEN '近畿' THEN 4 WHEN '中四国' THEN 5 WHEN '九州以南' THEN 6 ELSE 7 END,
                 p.university, p.question_number, p.passage_index"""
        ).fetchall()
    finally:
        conn.close()

    passages = []
    for r in rows:
        passages.append({
            "id": r["id"],
            "university": r["university"],
            "year": r["year"],
            "question_number": r["question_number"],
            "passage_index": r["passage_index"],
            "theme": r["theme"] or "",
            "cefr_level": r["cefr_level"] or "",
            "cefr_display": cefr_display(r["cefr_score"], r["cefr_level"]),
            "university_class": r["university_class"] or "",
            "region": r["region"] or "",
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
    wordbook: str = "",
    wordbook_milestone: Optional[int] = None,
    vocab_coverage_min: Optional[float] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """類似長文検索（HTMXパーシャル）。"""
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
        wordbook=wordbook or None,
        wordbook_milestone=wordbook_milestone,
        vocab_coverage_min=vocab_coverage_min,
        university_class=list(university_class) or None,
        region=list(region) or None,
    )

    if source is None:
        return templates.TemplateResponse(
            "partials/similar_results.html",
            {"request": request, "source": None, "results": [], "error": "パッセージが見つかりません"},
        )

    # 単語帳の表示名
    wordbook_label = ""
    if wordbook == "target1900":
        wordbook_label = "T19"
    elif wordbook == "leap":
        wordbook_label = "LP"

    return templates.TemplateResponse(
        "partials/similar_results.html",
        {
            "request": request,
            "source": source,
            "results": results,
            "error": None,
            "wordbook": wordbook or "",
            "wordbook_label": wordbook_label,
            "wordbook_milestone": wordbook_milestone,
        },
    )
