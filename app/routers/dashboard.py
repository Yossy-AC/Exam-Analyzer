"""ダッシュボード集計エンドポイント。"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import GENRE_MAIN_LIST
from app.db import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="templates")

GENRE_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]


def _genre_color(genre: str) -> str:
    if genre in GENRE_MAIN_LIST:
        return GENRE_COLORS[GENRE_MAIN_LIST.index(genre)]
    return "#bab0ac"


# ---------- タブ2: 大学別傾向 ----------

@router.get("/api/stats/university-profile")
async def university_profile(request: Request, university: str = "", year: int = None):
    """大学別サマリーカード（HTML partial）。"""
    if not university:
        return templates.TemplateResponse(
            "partials/university_profile.html",
            {"request": request, "empty": True},
        )

    conn = get_connection()
    try:
        query = "SELECT * FROM passages WHERE university = ? AND text_type = 'long_reading'"
        params: list = [university]
        if year:
            query += " AND year = ?"
            params.append(year)
        query += " ORDER BY year DESC, question_number"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return templates.TemplateResponse(
            "partials/university_profile.html",
            {"request": request, "empty": True},
        )

    # 長文ジャンル分布
    genre_counts = defaultdict(int)
    genre_themes = defaultdict(lambda: defaultdict(set))
    for r in rows:
        genre_counts[r["genre_main"]] += 1
        if r["genre_sub"]:
            genre_themes[r["genre_main"]][r["genre_sub"]].add(r["theme"])

    # 設問形式（全体）
    jp_written = sum(1 for r in rows if r["has_jp_written"])
    en_written = sum(1 for r in rows if r["has_en_written"])
    summary = sum(1 for r in rows if r["has_summary"])
    comp_wabun = sum(1 for r in rows if r["comp_type"] == "和文英訳")
    comp_jiyu = sum(1 for r in rows if r["comp_type"] == "自由英作文")

    # 設問形式の円グラフ用データ
    qformat_data = [jp_written, en_written, summary, comp_wabun, comp_jiyu]
    qformat_chart = {
        "labels": ["和訳", "英訳", "要約", "和文英訳", "自由英作文"],
        "data": qformat_data,
        "colors": ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"],
    }

    word_counts = [r["word_count"] for r in rows if r["word_count"]]
    avg_words = round(sum(word_counts) / len(word_counts)) if word_counts else 0

    # ジャンル別データを人気順（降順）でソート
    sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    genre_chart = {
        "labels": [g[0] for g in sorted_genres],
        "data": [g[1] for g in sorted_genres],
        "colors": [_genre_color(g[0]) for g in sorted_genres],
    }

    # ジャンル別テーマ情報（人気順）
    genre_details = {}
    for g, count in sorted_genres:
        genre_details[g] = {
            "count": count,
            "subgenres": dict((k, len(v)) for k, v in genre_themes[g].items()),
        }

    return templates.TemplateResponse(
        "partials/university_profile.html",
        {
            "request": request,
            "empty": False,
            "university": university,
            "total": len(rows),
            "genre_chart": genre_chart,
            "qformat_chart": qformat_chart,
            "avg_words": avg_words,
            "genre_details": genre_details,
        },
    )


# ---------- タブ3: 長文統計 ----------

@router.get("/api/stats/reading-stats")
async def reading_stats(year: int = None, university: str = ""):
    """長文統計データ（JSON）。"""
    conn = get_connection()
    try:
        where = "WHERE text_type = 'long_reading'"
        params: list = []
        if year:
            where += " AND year = ?"
            params.append(year)
        if university:
            where += " AND university = ?"
            params.append(university)

        genre_rows = conn.execute(
            f"SELECT genre_main, COUNT(*) as count FROM passages {where} GROUP BY genre_main ORDER BY count DESC",
            params,
        ).fetchall()

        style_rows = conn.execute(
            f"SELECT text_style, COUNT(*) as count FROM passages {where} AND text_style IS NOT NULL GROUP BY text_style ORDER BY count DESC",
            params,
        ).fetchall()

        format_row = conn.execute(
            f"""SELECT
                SUM(has_jp_translation) as jp_translation,
                SUM(has_jp_explanation) as jp_explanation,
                SUM(has_en_explanation) as en_explanation,
                SUM(has_jp_summary) as jp_summary,
                SUM(has_en_summary) as en_summary,
                COUNT(*) as total
            FROM passages {where}""",
            params,
        ).fetchone()

        # ジャンル別サブジャンル詳細
        subgenre_rows = conn.execute(
            f"""SELECT genre_main, genre_sub, COUNT(*) as count FROM passages {where}
            AND genre_sub != '' GROUP BY genre_main, genre_sub ORDER BY genre_main, count DESC""",
            params,
        ).fetchall()
    finally:
        conn.close()

    # ジャンル人気順（genre_rows の順序）に従ってサブジャンル詳細を構築
    genre_order = [r["genre_main"] for r in genre_rows]
    subgenre_detail = {genre: [] for genre in genre_order}
    for r in subgenre_rows:
        if r["genre_main"] in subgenre_detail:
            subgenre_detail[r["genre_main"]].append({
                "subgenre": r["genre_sub"],
                "count": r["count"],
            })

    return JSONResponse({
        "genre": {
            "labels": [r["genre_main"] for r in genre_rows],
            "data": [r["count"] for r in genre_rows],
            "colors": [_genre_color(g["genre_main"]) for g in genre_rows],
        },
        "style": {
            "labels": [r["text_style"] for r in style_rows],
            "data": [r["count"] for r in style_rows],
        },
        "format": {
            "labels": ["和訳", "説明（日本語）", "説明（英語）", "要約（日本語）", "要約（英語）"],
            "data": [
                format_row["jp_translation"] or 0,
                format_row["jp_explanation"] or 0,
                format_row["en_explanation"] or 0,
                format_row["jp_summary"] or 0,
                format_row["en_summary"] or 0,
            ],
            "total": format_row["total"] or 0,
        },
        "subgenres": subgenre_detail,
    })


# ---------- タブ4: 英作文統計 ----------

@router.get("/api/stats/composition-stats")
async def composition_stats(year: int = None, university: str = ""):
    """英作文統計データ（JSON）。"""
    conn = get_connection()
    try:
        where = "WHERE 1=1"
        params: list = []
        if year:
            where += " AND year = ?"
            params.append(year)
        if university:
            where += " AND university = ?"
            params.append(university)

        total = conn.execute(f"SELECT COUNT(*) as cnt FROM passages {where}", params).fetchone()["cnt"]
        comp_count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where} AND comp_type != 'none'", params
        ).fetchone()["cnt"]

        comp_rows = conn.execute(
            f"SELECT comp_type, COUNT(*) as count FROM passages {where} AND comp_type != 'none' GROUP BY comp_type",
            params,
        ).fetchall()

        visual_count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where} AND has_visual_info = 1", params
        ).fetchone()["cnt"]

        visual_type_rows = conn.execute(
            f"SELECT visual_info_type, COUNT(*) as count FROM passages {where} AND has_visual_info = 1 AND visual_info_type != '' GROUP BY visual_info_type",
            params,
        ).fetchall()

        comp_detail_rows = conn.execute(
            f"""SELECT university, year, question_number, comp_type, has_visual_info, visual_info_type
            FROM passages {where} AND comp_type != 'none'
            ORDER BY university, year, question_number""",
            params,
        ).fetchall()
    finally:
        conn.close()

    return JSONResponse({
        "presence": {
            "labels": ["英作文あり", "英作文なし"],
            "data": [comp_count, total - comp_count],
        },
        "type": {
            "labels": [r["comp_type"] for r in comp_rows],
            "data": [r["count"] for r in comp_rows],
        },
        "visual": {
            "labels": ["視覚情報あり", "視覚情報なし"],
            "data": [visual_count, max(0, comp_count - visual_count)],
        },
        "visual_type": {
            "labels": [r["visual_info_type"] for r in visual_type_rows],
            "data": [r["count"] for r in visual_type_rows],
        },
        "details": [
            {
                "university": r["university"],
                "year": r["year"],
                "question": r["question_number"],
                "comp_type": r["comp_type"],
                "has_visual": bool(r["has_visual_info"]),
                "visual_type": r["visual_info_type"] or "-",
            }
            for r in comp_detail_rows
        ],
    })


# ---------- タブ5: 経年変化 ----------

@router.get("/api/stats/yearly-trend")
async def yearly_trend(university: str = ""):
    """特定大学の経年変化データ（JSON）。"""
    if not university:
        return JSONResponse({"empty": True})

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM passages WHERE university = ? ORDER BY year, question_number",
            (university,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return JSONResponse({"empty": True})

    years = sorted(set(r["year"] for r in rows))

    genre_datasets = []
    for i, genre in enumerate(GENRE_MAIN_LIST):
        data = [sum(1 for r in rows if r["year"] == y and r["genre_main"] == genre) for y in years]
        if any(d > 0 for d in data):
            genre_datasets.append({
                "label": genre,
                "data": data,
                "backgroundColor": GENRE_COLORS[i],
            })

    format_defs = [
        ("和訳", "has_jp_written", None, "#4e79a7"),
        ("英訳", "has_en_written", None, "#f28e2b"),
        ("要約", "has_summary", None, "#e15759"),
        ("和文英訳", None, "和文英訳", "#76b7b2"),
        ("自由英作文", None, "自由英作文", "#59a14f"),
    ]
    format_datasets = []
    for label, field, comp_val, color in format_defs:
        data = []
        for y in years:
            yr_rows = [r for r in rows if r["year"] == y]
            if field:
                count = sum(1 for r in yr_rows if r[field])
            else:
                count = sum(1 for r in yr_rows if r["comp_type"] == comp_val)
            data.append(count)
        if any(d > 0 for d in data):
            format_datasets.append({
                "label": label, "data": data,
                "borderColor": color, "backgroundColor": color,
                "fill": False, "tension": 0.3,
            })

    return JSONResponse({
        "empty": False,
        "years": years,
        "genre": {"labels": years, "datasets": genre_datasets},
        "format": {"labels": years, "datasets": format_datasets},
    })


# ---------- タブ6: 大学間比較 ----------

@router.get("/api/stats/heatmap")
async def heatmap(request: Request, year: int = None):
    """大学×ジャンル ヒートマップ（HTML partial）。"""
    conn = get_connection()
    try:
        where = "WHERE 1=1"
        params: list = []
        if year:
            where += " AND year = ?"
            params.append(year)

        rows = conn.execute(
            f"SELECT university, genre_main, COUNT(*) as count FROM passages {where} GROUP BY university, genre_main",
            params,
        ).fetchall()
    finally:
        conn.close()

    universities = sorted(set(r["university"] for r in rows))
    heatmap_data = {}
    max_count = 0
    for uni in universities:
        counts = {}
        for g in GENRE_MAIN_LIST:
            c = sum(r["count"] for r in rows if r["university"] == uni and r["genre_main"] == g)
            counts[g] = c
            if c > max_count:
                max_count = c
        heatmap_data[uni] = counts

    return templates.TemplateResponse(
        "partials/heatmap.html",
        {
            "request": request,
            "genres": GENRE_MAIN_LIST,
            "heatmap_data": heatmap_data,
            "max_count": max_count,
        },
    )


@router.get("/api/stats/question-format")
async def question_format(year: int = None):
    """設問形式の大学別比較データ（JSON）。"""
    conn = get_connection()
    try:
        where = "WHERE 1=1"
        params: list = []
        if year:
            where += " AND year = ?"
            params.append(year)

        rows = conn.execute(
            f"""SELECT university,
                SUM(has_jp_written) as jp, SUM(has_en_written) as en,
                SUM(has_summary) as summary,
                SUM(CASE WHEN comp_type = '和文英訳' THEN 1 ELSE 0 END) as wabun,
                SUM(CASE WHEN comp_type = '自由英作文' THEN 1 ELSE 0 END) as jiyu
            FROM passages {where}
            GROUP BY university ORDER BY university""",
            params,
        ).fetchall()
    finally:
        conn.close()

    universities = [r["university"] for r in rows]
    datasets = [
        {"label": "和訳", "data": [r["jp"] or 0 for r in rows], "backgroundColor": "#4e79a7"},
        {"label": "英訳", "data": [r["en"] or 0 for r in rows], "backgroundColor": "#f28e2b"},
        {"label": "要約", "data": [r["summary"] or 0 for r in rows], "backgroundColor": "#e15759"},
        {"label": "和文英訳", "data": [r["wabun"] or 0 for r in rows], "backgroundColor": "#76b7b2"},
        {"label": "自由英作文", "data": [r["jiyu"] or 0 for r in rows], "backgroundColor": "#59a14f"},
    ]

    return JSONResponse({"labels": universities, "datasets": datasets})
