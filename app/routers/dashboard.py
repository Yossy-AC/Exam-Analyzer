"""ダッシュボード集計エンドポイント。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import GENRE_MAIN_LIST
from app.db import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/api/stats/genre-trend")
async def genre_trend(year_from: int = None, year_to: int = None):
    """ジャンルトレンドデータ（Chart.js用JSON）。"""
    conn = get_connection()
    try:
        query = """
            SELECT year, genre_main, COUNT(*) as count
            FROM passages WHERE 1=1
        """
        params = []
        if year_from:
            query += " AND year >= ?"
            params.append(year_from)
        if year_to:
            query += " AND year <= ?"
            params.append(year_to)
        query += " GROUP BY year, genre_main ORDER BY year"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    # Chart.js用に変換
    years = sorted(set(r["year"] for r in rows))
    datasets = []
    colors = [
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
        "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    ]
    for i, genre in enumerate(GENRE_MAIN_LIST):
        data = []
        for year in years:
            count = sum(r["count"] for r in rows if r["year"] == year and r["genre_main"] == genre)
            data.append(count)
        datasets.append({
            "label": genre,
            "data": data,
            "backgroundColor": colors[i % len(colors)],
        })

    return JSONResponse({
        "labels": years,
        "datasets": datasets,
    })


@router.get("/api/stats/university-compare")
async def university_compare(year: int = None):
    """大学別比較データ（Chart.js用JSON）。"""
    conn = get_connection()
    try:
        query = """
            SELECT university, text_type, COUNT(*) as count
            FROM passages WHERE 1=1
        """
        params = []
        if year:
            query += " AND year = ?"
            params.append(year)
        query += " GROUP BY university, text_type ORDER BY university"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    universities = sorted(set(r["university"] for r in rows))
    text_types = ["long_reading", "short_translation", "composition"]
    type_colors = {"long_reading": "#4e79a7", "short_translation": "#f28e2b", "composition": "#e15759"}

    datasets = []
    for tt in text_types:
        data = []
        for uni in universities:
            count = sum(r["count"] for r in rows if r["university"] == uni and r["text_type"] == tt)
            data.append(count)
        datasets.append({
            "label": tt,
            "data": data,
            "backgroundColor": type_colors[tt],
        })

    return JSONResponse({
        "labels": universities,
        "datasets": datasets,
    })


@router.get("/api/stats/question-matrix")
async def question_matrix(request: Request, year: int = None):
    """問題構成マトリクス（HTMXテーブル）。"""
    conn = get_connection()
    try:
        query = "SELECT * FROM passages WHERE 1=1"
        params = []
        if year:
            query += " AND year = ?"
            params.append(year)
        query += " ORDER BY university, year, question_number"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "partials/question_matrix.html",
        {"request": request, "passages": rows},
    )
