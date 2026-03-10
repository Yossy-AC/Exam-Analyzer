"""ダッシュボード集計エンドポイント。"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import GENRE_MAIN_LIST
from app.db import build_filter_where, get_connection

router = APIRouter()
templates = Jinja2Templates(directory="templates")

GENRE_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]

TEXT_TYPE_LABELS = {
    "long_reading": "長文読解",
    "short_translation": "短文和訳",
    "composition": "英作文",
    "listening": "リスニング",
}
TEXT_TYPE_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2"]


def _genre_color(genre: str) -> str:
    if genre in GENRE_MAIN_LIST:
        return GENRE_COLORS[GENRE_MAIN_LIST.index(genre)]
    return "#bab0ac"


# ---------- タブ1: ダッシュボード ----------

@router.get("/api/stats/dashboard")
async def dashboard_partial(
    request: Request,
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """ダッシュボード概要パーシャル（HTML）。"""
    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
        )
        where = f"WHERE COALESCE(copyright_omitted, 0) = 0{extra}"
        params: list = filter_params

        total_passages = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where}", params
        ).fetchone()["cnt"]

        total_universities = conn.execute(
            f"SELECT COUNT(DISTINCT university) as cnt FROM passages {where}", params
        ).fetchone()["cnt"]

        year_row = conn.execute(
            f"SELECT MIN(year) as y_min, MAX(year) as y_max FROM passages {where}", params
        ).fetchone()

        text_type_rows = conn.execute(
            f"SELECT text_type, COUNT(*) as count FROM passages {where} GROUP BY text_type",
            params,
        ).fetchall()

        top_genre_rows = conn.execute(
            f"SELECT genre_main, COUNT(*) as count FROM passages {where} AND text_type = 'long_reading' GROUP BY genre_main ORDER BY count DESC",
            params,
        ).fetchall()

        # 長文集計: 文体グループ別
        style_rows = conn.execute(
            f"SELECT text_style, COUNT(*) as count FROM passages {where} AND text_type = 'long_reading' GROUP BY text_style ORDER BY count DESC",
            params,
        ).fetchall()

        # ダッシュボード用ジャンル分布（長文全体）
        genre_all_rows = conn.execute(
            f"SELECT genre_main, COUNT(*) as count FROM passages {where} AND text_type = 'long_reading' GROUP BY genre_main ORDER BY count DESC",
            params,
        ).fetchall()

        # 英作文出題の有無（大学ベース）
        comp_uni_count = conn.execute(
            f"SELECT COUNT(DISTINCT university) as cnt FROM passages {where} AND (has_wabun_eiyaku = 1 OR has_jiyu_eisakubun = 1)", params
        ).fetchone()["cnt"]

        # CEFR分布（long_readingかつスコアあり）
        cefr_rows = conn.execute(
            f"SELECT cefr_level, COUNT(*) as count FROM passages {where} AND text_type = 'long_reading' AND cefr_level != '' GROUP BY cefr_level",
            params,
        ).fetchall()
    finally:
        conn.close()

    tt_map = {r["text_type"]: r["count"] for r in text_type_rows}
    tt_order = ["long_reading", "short_translation", "composition", "listening"]
    # text_type_distに「その他」を追加
    known_total = sum(tt_map.get(k, 0) for k in tt_order)
    other_count = total_passages - known_total
    text_type_dist = {
        "labels": [TEXT_TYPE_LABELS[k] for k in tt_order] + (["その他"] if other_count > 0 else []),
        "data": [tt_map.get(k, 0) for k in tt_order] + ([other_count] if other_count > 0 else []),
    }

    # 文体グループ集計
    LOGICAL_STYLES = {"説明文", "論説文", "ニュース・レポート"}
    logical_total = sum(r["count"] for r in style_rows if r["text_style"] in LOGICAL_STYLES)
    style_summary = []
    if logical_total > 0:
        style_summary.append({"label": "論理的説明文", "count": logical_total})
    for r in style_rows:
        if r["text_style"] not in LOGICAL_STYLES:
            style_summary.append({"label": r["text_style"], "count": r["count"]})

    # CEFR分布（A2→C2の順に並べる）
    cefr_order = ["A2", "B1", "B2", "C1", "C2"]
    cefr_map = {r["cefr_level"]: r["count"] for r in cefr_rows}
    cefr_dist = {
        "labels": [lv for lv in cefr_order if cefr_map.get(lv, 0) > 0],
        "data": [cefr_map[lv] for lv in cefr_order if cefr_map.get(lv, 0) > 0],
        "total": sum(cefr_map.values()),
    }

    return templates.TemplateResponse(
        "partials/dashboard.html",
        {
            "request": request,
            "total_passages": total_passages,
            "total_universities": total_universities,
            "year_min": year_row["y_min"] or "—",
            "year_max": year_row["y_max"] or "—",
            "text_type_dist": text_type_dist,
            "top_genres": [{"genre": r["genre_main"], "count": r["count"]} for r in top_genre_rows],
            "style_summary": style_summary,
            "genre_all": {
                "labels": [r["genre_main"] for r in genre_all_rows],
                "data": [r["count"] for r in genre_all_rows],
                "colors": [_genre_color(r["genre_main"]) for r in genre_all_rows],
            },
            "comp_presence": {
                "labels": ["出題あり", "出題なし"],
                "data": [comp_uni_count, total_universities - comp_uni_count],
            },
            "cefr_dist": cefr_dist,
        },
    )


# ---------- タブ6: 大学別傾向 ----------

@router.get("/api/stats/university-profile")
async def university_profile(
    request: Request,
    university: str = "",
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
):
    """大学別サマリーカード（HTML partial）。"""
    if not university:
        return templates.TemplateResponse(
            "partials/university_profile.html",
            {"request": request, "empty": True},
        )

    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
        )
        # 長文読解のみ（ジャンル・記述種別用）
        query = f"SELECT * FROM passages WHERE university = ? AND text_type = 'long_reading'{extra} ORDER BY year DESC, question_number"
        params: list = [university, *filter_params]
        rows = conn.execute(query, params).fetchall()

        # 全 text_type（問題形式・英作文形式用）
        all_query = f"SELECT * FROM passages WHERE university = ?{extra} ORDER BY year"
        all_rows = conn.execute(all_query, params).fetchall()
    finally:
        conn.close()

    if not rows and not all_rows:
        return templates.TemplateResponse(
            "partials/university_profile.html",
            {"request": request, "empty": True},
        )

    # 問題形式（text_type）分布
    tt_counts = Counter(r["text_type"] for r in all_rows)
    tt_order = ["long_reading", "short_translation", "composition", "listening"]
    text_type_chart = {
        "labels": [TEXT_TYPE_LABELS[k] for k in tt_order],
        "data": [tt_counts.get(k, 0) for k in tt_order],
        "colors": TEXT_TYPE_COLORS,
    }

    # 英作文形式分布
    wabun_count = sum(1 for r in all_rows if r["has_wabun_eiyaku"])
    jiyu_count = sum(1 for r in all_rows if r["has_jiyu_eisakubun"])
    comp_type_chart = {
        "labels": ["和文英訳", "自由英作文"],
        "data": [wabun_count, jiyu_count],
        "colors": ["#59a14f", "#edc948"],
    }

    if not rows:
        return templates.TemplateResponse(
            "partials/university_profile.html",
            {"request": request, "empty": False, "university": university,
             "total": len(all_rows), "no_reading": True,
             "text_type_chart": text_type_chart, "comp_type_chart": comp_type_chart,
             "genre_chart": {"labels": [], "data": [], "colors": []},
             "qformat_chart": {"labels": [], "data": [], "colors": []},
             "avg_words": 0, "genre_details": {}},
        )

    # 長文ジャンル分布
    genre_counts = defaultdict(int)
    genre_themes = defaultdict(lambda: defaultdict(set))
    for r in rows:
        genre_counts[r["genre_main"]] += 1
        if r["genre_sub"]:
            genre_themes[r["genre_main"]][r["genre_sub"]].add(r["theme"])

    # 記述種別（5分類）
    jp_translation = sum(1 for r in rows if r["has_jp_translation"])
    jp_explanation = sum(1 for r in rows if r["has_jp_explanation"])
    en_explanation = sum(1 for r in rows if r["has_en_explanation"])
    jp_summary = sum(1 for r in rows if r["has_jp_summary"])
    en_summary = sum(1 for r in rows if r["has_en_summary"])

    qformat_chart = {
        "labels": ["和訳", "説明（日）", "説明（英）", "要約（日）", "要約（英）"],
        "data": [jp_translation, jp_explanation, en_explanation, jp_summary, en_summary],
        "colors": ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"],
    }

    word_counts = [r["word_count"] for r in rows if r["word_count"]]
    avg_words = round(sum(word_counts) / len(word_counts)) if word_counts else 0

    sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    genre_chart = {
        "labels": [g[0] for g in sorted_genres],
        "data": [g[1] for g in sorted_genres],
        "colors": [_genre_color(g[0]) for g in sorted_genres],
    }

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
            "total": len(all_rows),
            "text_type_chart": text_type_chart,
            "genre_chart": genre_chart,
            "comp_type_chart": comp_type_chart,
            "qformat_chart": qformat_chart,
            "avg_words": avg_words,
            "genre_details": genre_details,
        },
    )


# ---------- タブ3: 長文統計 ----------

@router.get("/api/stats/reading-stats")
async def reading_stats(
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """長文統計データ（JSON）。"""
    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
        )
        where = f"WHERE text_type = 'long_reading' AND COALESCE(copyright_omitted, 0) = 0{extra}"
        params: list = filter_params

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

        # 論理的説明文のジャンル別サブジャンル詳細（エッセイ・評論/物語文を除外）
        # genre_subが空の場合は「その他」として集計
        subgenre_rows = conn.execute(
            f"""SELECT genre_main,
                CASE WHEN genre_sub = '' THEN 'その他' ELSE genre_sub END as genre_sub,
                COUNT(*) as count FROM passages {where}
            AND text_style NOT IN ('エッセイ・評論', '物語文')
            GROUP BY genre_main, genre_sub ORDER BY genre_main, count DESC""",
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

    # 文体データにグループ情報を付加
    LOGICAL_STYLES = {"説明文", "論説文", "ニュース・レポート"}
    style_labels = [r["text_style"] for r in style_rows]
    style_data = [r["count"] for r in style_rows]
    # 内側リング: 論理的説明文（3種統合）/ エッセイ・評論 / 物語文
    group_labels = []
    group_data = []
    logical_total = sum(d for l, d in zip(style_labels, style_data) if l in LOGICAL_STYLES)
    if logical_total > 0:
        group_labels.append("論理的説明文")
        group_data.append(logical_total)
    for l, d in zip(style_labels, style_data):
        if l not in LOGICAL_STYLES:
            group_labels.append(l)
            group_data.append(d)

    return JSONResponse({
        "genre": {
            "labels": [r["genre_main"] for r in genre_rows],
            "data": [r["count"] for r in genre_rows],
            "colors": [_genre_color(g["genre_main"]) for g in genre_rows],
        },
        "style": {
            "labels": style_labels,
            "data": style_data,
            "group_labels": group_labels,
            "group_data": group_data,
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
async def composition_stats(
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """英作文統計データ（JSON）。"""
    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
        )
        where = f"WHERE COALESCE(copyright_omitted, 0) = 0{extra}"
        params: list = filter_params

        # 大学ベースの英作文出題有無
        total_uni = conn.execute(
            f"SELECT COUNT(DISTINCT university) as cnt FROM passages {where}", params
        ).fetchone()["cnt"]
        comp_uni = conn.execute(
            f"SELECT COUNT(DISTINCT university) as cnt FROM passages {where} AND (has_wabun_eiyaku = 1 OR has_jiyu_eisakubun = 1)", params
        ).fetchone()["cnt"]

        wabun_count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where} AND has_wabun_eiyaku = 1", params
        ).fetchone()["cnt"]
        jiyu_count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where} AND has_jiyu_eisakubun = 1", params
        ).fetchone()["cnt"]

        # 自由英作文の総数と視覚情報あり数
        free_comp_total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where} AND has_jiyu_eisakubun = 1", params
        ).fetchone()["cnt"]
        visual_count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM passages {where} AND has_jiyu_eisakubun = 1 AND has_visual_info = 1", params
        ).fetchone()["cnt"]

        visual_type_rows = conn.execute(
            f"SELECT visual_info_type, COUNT(*) as count FROM passages {where} AND has_visual_info = 1 AND visual_info_type != '' GROUP BY visual_info_type",
            params,
        ).fetchall()
    finally:
        conn.close()

    return JSONResponse({
        "presence": {
            "labels": ["出題あり", "出題なし"],
            "data": [comp_uni, total_uni - comp_uni],
        },
        "type": {
            "labels": ["和文英訳", "自由英作文"],
            "data": [wabun_count, jiyu_count],
        },
        "visual": {
            "labels": ["図表あり", "図表なし"],
            "data": [visual_count, max(0, free_comp_total - visual_count)],
        },
        "visual_type": {
            "labels": [r["visual_info_type"] for r in visual_type_rows],
            "data": [r["count"] for r in visual_type_rows],
        },
    })


# ---------- タブ7: 経年変化 ----------

@router.get("/api/stats/yearly-trend")
async def yearly_trend(university: str = ""):
    """特定大学の経年変化データ（JSON）。"""
    if not university:
        return JSONResponse({"empty": True})

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM passages WHERE university = ? AND COALESCE(copyright_omitted, 0) = 0 ORDER BY year, question_number",
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
        ("和訳", "has_jp_translation", "#4e79a7"),
        ("説明（日）", "has_jp_explanation", "#f28e2b"),
        ("説明（英）", "has_en_explanation", "#e15759"),
        ("要約（日）", "has_jp_summary", "#76b7b2"),
        ("要約（英）", "has_en_summary", "#59a14f"),
        ("和文英訳", "has_wabun_eiyaku", "#b07aa1"),
        ("自由英作文", "has_jiyu_eisakubun", "#edc948"),
    ]
    format_datasets = []
    for label, field, color in format_defs:
        data = []
        for y in years:
            yr_rows = [r for r in rows if r["year"] == y]
            count = sum(1 for r in yr_rows if r[field])
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


# ---------- タブ5: 大学間比較 ----------

@router.get("/api/stats/compare-universities")
async def compare_universities(
    uni1: str = "",
    uni2: str = "",
    uni3: str = "",
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
):
    """3大学の設問形式比較データ（JSON）。"""
    unis = [u for u in [uni1, uni2, uni3] if u]
    if not unis:
        return JSONResponse({"labels": [], "datasets": []})

    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
        )
        placeholders = ",".join("?" * len(unis))
        query = f"""SELECT university,
            SUM(has_jp_translation) as jp_translation,
            SUM(has_jp_explanation) as jp_explanation,
            SUM(has_en_explanation) as en_explanation,
            SUM(has_jp_summary) as jp_summary,
            SUM(has_en_summary) as en_summary
        FROM passages
        WHERE university IN ({placeholders}) AND text_type = 'long_reading' AND COALESCE(copyright_omitted, 0) = 0{extra}
        GROUP BY university"""
        params: list = [*unis, *filter_params]
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    row_map = {r["university"]: r for r in rows}
    uni_colors = ["#4e79a7", "#f28e2b", "#e15759"]
    datasets = []
    for i, uni in enumerate(unis):
        r = row_map.get(uni)
        datasets.append({
            "label": uni,
            "data": [
                r["jp_translation"] or 0 if r else 0,
                r["jp_explanation"] or 0 if r else 0,
                r["en_explanation"] or 0 if r else 0,
                r["jp_summary"] or 0 if r else 0,
                r["en_summary"] or 0 if r else 0,
            ],
            "backgroundColor": uni_colors[i],
        })

    return JSONResponse({
        "labels": ["和訳", "説明（日）", "説明（英）", "要約（日）", "要約（英）"],
        "datasets": datasets,
    })


# ---------- タブ4: 問題形式選択 ----------

@router.get("/api/stats/practice-list")
async def practice_list(
    request: Request,
    text_type: str = "",
    has_jp_translation: Optional[int] = None,
    has_jp_explanation: Optional[int] = None,
    has_en_explanation: Optional[int] = None,
    has_jp_summary: Optional[int] = None,
    has_en_summary: Optional[int] = None,
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """問題形式別パッセージ一覧（HTML partial）。"""
    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
        )
        conditions = ["COALESCE(copyright_omitted, 0) = 0"]
        params: list = list(filter_params)

        if text_type:
            conditions.append("text_type = ?")
            params.insert(0, text_type)

        # 長文読解のサブフィルター（OR条件）
        if text_type == "long_reading":
            sub_filters = []
            for field, val in [
                ("has_jp_translation", has_jp_translation),
                ("has_jp_explanation", has_jp_explanation),
                ("has_en_explanation", has_en_explanation),
                ("has_jp_summary", has_jp_summary),
                ("has_en_summary", has_en_summary),
            ]:
                if val is not None and val == 1:
                    sub_filters.append(f"{field} = 1")
            if sub_filters:
                conditions.append(f"({' OR '.join(sub_filters)})")

        where = "WHERE " + " AND ".join(conditions) + extra
        query = f"""SELECT p.university, p.year, p.theme, p.genre_main, p.genre_sub, p.text_type,
            p.has_jp_translation, p.has_jp_explanation, p.has_en_explanation,
            p.has_jp_summary, p.has_en_summary
        FROM passages p LEFT JOIN universities u ON p.university = u.name {where}
        ORDER BY p.year DESC,
            CASE u.university_class WHEN '共通テスト' THEN 0 WHEN '旧帝大' THEN 1 WHEN '難関大' THEN 2 WHEN '準難関大' THEN 3 WHEN 'その他国立大' THEN 4 WHEN 'その他公立大' THEN 5 ELSE 6 END,
            CASE u.region WHEN '東北以北' THEN 1 WHEN '関東' THEN 2 WHEN '中部' THEN 3 WHEN '近畿' THEN 4 WHEN '中四国' THEN 5 WHEN '九州以南' THEN 6 ELSE 7 END,
            p.university"""
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "partials/question_format_practice.html",
        {"request": request, "passages": rows, "count": len(rows)},
    )


# 旧エンドポイント（後方互換のため残す）
@router.get("/api/stats/heatmap")
async def heatmap(
    request: Request,
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """大学×ジャンル ヒートマップ（HTML partial）。"""
    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
        )
        where = f"WHERE COALESCE(copyright_omitted, 0) = 0{extra}"
        params: list = filter_params

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
async def question_format(
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
):
    """設問形式の大学別比較データ（JSON）。"""
    conn = get_connection()
    try:
        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
        )
        where = f"WHERE COALESCE(copyright_omitted, 0) = 0{extra}"
        params: list = filter_params

        rows = conn.execute(
            f"""SELECT university,
                SUM(has_jp_translation) as jp_translation,
                SUM(has_jp_explanation) as jp_explanation,
                SUM(has_en_explanation) as en_explanation,
                SUM(has_jp_summary) as jp_summary,
                SUM(has_en_summary) as en_summary
            FROM passages {where}
            GROUP BY university ORDER BY university""",
            params,
        ).fetchall()
    finally:
        conn.close()

    universities = [r["university"] for r in rows]
    datasets = [
        {"label": "和訳", "data": [r["jp_translation"] or 0 for r in rows], "backgroundColor": "#4e79a7"},
        {"label": "説明（日）", "data": [r["jp_explanation"] or 0 for r in rows], "backgroundColor": "#f28e2b"},
        {"label": "説明（英）", "data": [r["en_explanation"] or 0 for r in rows], "backgroundColor": "#e15759"},
        {"label": "要約（日）", "data": [r["jp_summary"] or 0 for r in rows], "backgroundColor": "#76b7b2"},
        {"label": "要約（英）", "data": [r["en_summary"] or 0 for r in rows], "backgroundColor": "#59a14f"},
    ]

    return JSONResponse({"labels": universities, "datasets": datasets})
