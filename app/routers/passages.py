"""パッセージCRUD・インライン編集エンドポイント。"""

from __future__ import annotations

from typing import List, Optional

import sqlite3

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import GENRE_MAIN_LIST, TEXT_STYLE_LIST, TEXT_TYPE_LABELS, TEXT_TYPE_LIST
from app.db import build_filter_where, get_connection
from app.auth import is_student
from app.models import PassageUpdate

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/api/passages")
async def list_passages(
    request: Request,
    year_mode: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    university_class: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
    genre_main: str = None,
    text_type: str = None,
    reviewed: bool = None,
    university_name: str = None,
    theme: str = None,
    cefr_level: str = None,
    readonly: bool = False,
):
    """フィルタ付きパッセージ一覧。"""
    if is_student(request):
        readonly = True
    conn = get_connection()
    try:
        query = "SELECT p.*, u.is_kyutei FROM passages p LEFT JOIN universities u ON p.university = u.name WHERE 1=1"
        params: list = []

        extra, filter_params = build_filter_where(
            year_mode=year_mode, year_from=year_from, year_to=year_to,
            university_class=list(university_class), region=list(region),
            year_col="p.year", university_col="p.university",
        )
        query += extra
        params.extend(filter_params)

        if genre_main:
            query += " AND p.genre_main = ?"
            params.append(genre_main)
        if text_type:
            query += " AND p.text_type = ?"
            params.append(text_type)
        if reviewed is not None:
            query += " AND p.reviewed = ?"
            params.append(int(reviewed))
        if university_name:
            query += " AND p.university LIKE ?"
            params.append(f"%{university_name}%")
        if theme:
            query += " AND p.theme LIKE ?"
            params.append(f"%{theme}%")
        if cefr_level:
            query += " AND p.cefr_level = ?"
            params.append(cefr_level)

        query += """ ORDER BY p.year DESC,
            CASE u.university_class WHEN '旧帝大' THEN 1 WHEN '難関大' THEN 2 WHEN '準難関大' THEN 3 WHEN 'その他国立大' THEN 4 WHEN 'その他公立大' THEN 5 ELSE 6 END,
            CASE u.region WHEN '東北以北' THEN 1 WHEN '関東' THEN 2 WHEN '中部' THEN 3 WHEN '近畿' THEN 4 WHEN '中四国' THEN 5 WHEN '九州以南' THEN 6 ELSE 7 END,
            p.university, p.question_number, p.passage_index"""
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "partials/records_table.html",
        {
            "request": request,
            "passages": rows,
            "genre_list": GENRE_MAIN_LIST,
            "text_type_list": TEXT_TYPE_LIST,
            "text_type_labels": TEXT_TYPE_LABELS,
            "text_style_list": TEXT_STYLE_LIST,
            "readonly": readonly,
        },
    )


@router.put("/api/passages/{passage_id}")
async def update_passage(request: Request, passage_id: str):
    """パッセージの個別フィールドを更新する（インライン編集）。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    form = await request.form()
    conn = get_connection()
    try:
        updates = []
        params = []
        # ホワイトリスト: フォームから受け付けるカラム名（SQLインジェクション防止）
        _TEXT_COLS = {"text_type", "text_style", "genre_main", "genre_sub", "theme", "notes"}
        _BOOL_COLS = {"has_jp_written", "has_en_written", "has_summary", "reviewed"}
        for key in form:
            if key in _TEXT_COLS:
                updates.append(f"{key} = ?")
                params.append(form[key])
            elif key in _BOOL_COLS:
                updates.append(f"{key} = ?")
                params.append(1 if form[key] in ("true", "1", "on") else 0)

        if updates:
            params.append(passage_id)
            conn.execute(
                f"UPDATE passages SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        row = conn.execute(
            "SELECT p.*, u.is_kyutei FROM passages p LEFT JOIN universities u ON p.university = u.name WHERE p.id = ?",
            (passage_id,),
        ).fetchone()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "partials/record_row.html",
        {
            "request": request,
            "p": row,
            "genre_list": GENRE_MAIN_LIST,
            "text_type_labels": TEXT_TYPE_LABELS,
            "text_style_list": TEXT_STYLE_LIST,
        },
    )


@router.post("/api/passages")
async def create_passage(request: Request):
    """パッセージを手動で新規追加する。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    body = await request.json()

    university = (body.get("university") or "").strip()
    year_raw = body.get("year")
    question_number = (body.get("question_number") or "I").strip()
    passage_index = int(body.get("passage_index") or 1)

    if not university or not year_raw:
        return JSONResponse({"error": "大学名と年度は必須です"}, status_code=400)

    year = int(year_raw)
    passage_id = f"{year}_{university}_{question_number}_{passage_index}"

    word_count_raw = body.get("word_count")
    word_count = int(word_count_raw) if word_count_raw else None

    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_kyutei, is_national, is_private) VALUES (?, 0, 1, 0)",
            (university,),
        )
        conn.execute(
            """INSERT INTO passages (
                id, university, year, faculty, question_number, passage_index,
                text_type, text_style, word_count,
                genre_main, genre_sub, theme,
                has_wabun_eiyaku, has_jiyu_eisakubun, reviewed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                passage_id, university, year,
                (body.get("faculty") or ""),
                question_number, passage_index,
                (body.get("text_type") or "long_reading"),
                (body.get("text_style") or ""),
                word_count,
                (body.get("genre_main") or "その他"),
                (body.get("genre_sub") or ""),
                (body.get("theme") or ""),
                bool(body.get("has_wabun_eiyaku")),
                bool(body.get("has_jiyu_eisakubun")),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return JSONResponse({"error": f"ID '{passage_id}' は既に存在します"}, status_code=409)
    finally:
        conn.close()

    return JSONResponse({"id": passage_id}, status_code=201)


_SUB_GENRE_MAP: dict[str, list[str]] = {
    "科学・技術": ["AI・ロボット","宇宙・天文","エネルギー","情報技術","バイオ・遺伝子","材料・化学","動物行動・生態","科学史・哲学","その他科技"],
    "医療・健康": ["病気・治療","食事・栄養","メンタルヘルス","医療制度","運動・身体","神経科学・脳","長寿・老化","その他医療"],
    "心理・行動": ["認知・思考","感情・幸福","行動・習慣","人間関係","意思決定","その他心理"],
    "教育・学習": ["学校・制度","言語学習","子育て・発達","創造性・才能","その他教育"],
    "環境・自然": ["地球温暖化","生物多様性","廃棄物・汚染","エコ・持続可能性","自然現象","その他環境"],
    "社会・文化": ["観光","メディア","多様性","移民・難民","食文化","スポーツ","芸術","ジェンダー","家族・個人","犯罪・法律","地域・都市","高齢化・人口","その他社会"],
    "経済・ビジネス": ["消費・市場","国際経済","労働・雇用","農業・食料","テクノロジー経済","その他経済"],
    "歴史・哲学": ["歴史","宗教・文化遺産","倫理・道徳","文明","その他歴史"],
    "言語・コミュニケーション": ["言語変化","翻訳・多言語","SNS・デジタル","対話・説得","言語理論・習得","手話・非言語","文学・文章論","その他言語"],
}


@router.patch("/api/passages/bulk-review")
async def bulk_review(request: Request):
    """選択したパッセージを一括で確認済みにする。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    body = await request.json()
    ids = body.get("ids", [])
    if not ids:
        return JSONResponse({"error": "IDが指定されていません"}, status_code=400)
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"UPDATE passages SET reviewed = 1 WHERE id IN ({placeholders})", ids)
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"updated": len(ids)})


@router.post("/api/passages/reclassify-sub")
async def reclassify_sub_genres(request: Request):
    """genre_sub が「その他○○」の既存パッセージをClaude APIで再分類する。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    import anthropic
    from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, genre_main, theme, genre_sub FROM passages WHERE genre_sub LIKE 'その他%'"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return JSONResponse({"updated": 0, "message": "対象データなし"})

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    updated = 0
    results = []

    for row in rows:
        genre_main = row["genre_main"]
        theme = row["theme"]
        options = _SUB_GENRE_MAP.get(genre_main, [])
        if not options:
            continue

        options_str = " / ".join(options)
        prompt = (
            f"以下のパッセージのメインジャンルとテーマから最も適切なサブジャンルを1つだけ返してください。\n\n"
            f"メインジャンル: {genre_main}\n"
            f"テーマ: {theme}\n\n"
            f"サブジャンル選択肢: {options_str}\n\n"
            f"選択肢の中から1つだけを正確に返してください（余分な文字不要）。"
        )
        try:
            resp = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            new_sub = resp.content[0].text.strip()
            if new_sub in options and new_sub != row["genre_sub"]:
                conn = get_connection()
                try:
                    conn.execute("UPDATE passages SET genre_sub=? WHERE id=?", (new_sub, row["id"]))
                    conn.commit()
                finally:
                    conn.close()
                results.append({"id": row["id"], "old": row["genre_sub"], "new": new_sub})
                updated += 1
        except Exception as e:
            results.append({"id": row["id"], "error": str(e)})

    return JSONResponse({"updated": updated, "results": results})


@router.delete("/api/passages/{passage_id}")
async def delete_passage(request: Request, passage_id: str):
    """パッセージを削除する。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM passages WHERE id = ?", (passage_id,))
        conn.commit()
    finally:
        conn.close()
    return HTMLResponse("", status_code=200)
