"""パッセージCRUD・インライン編集エンドポイント。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import COMP_TYPE_LIST, GENRE_MAIN_LIST, TEXT_STYLE_LIST, TEXT_TYPE_LIST
from app.db import get_connection
from app.models import PassageUpdate

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/api/passages")
async def list_passages(
    request: Request,
    year: int = None,
    university: str = None,
    genre_main: str = None,
    text_type: str = None,
    reviewed: bool = None,
):
    """フィルタ付きパッセージ一覧。"""
    conn = get_connection()
    try:
        query = "SELECT p.*, u.is_kyutei FROM passages p LEFT JOIN universities u ON p.university = u.name WHERE 1=1"
        params = []

        if year:
            query += " AND p.year = ?"
            params.append(year)
        if university:
            query += " AND p.university = ?"
            params.append(university)
        if genre_main:
            query += " AND p.genre_main = ?"
            params.append(genre_main)
        if text_type:
            query += " AND p.text_type = ?"
            params.append(text_type)
        if reviewed is not None:
            query += " AND p.reviewed = ?"
            params.append(int(reviewed))

        query += " ORDER BY p.year DESC, p.university, p.question_number, p.passage_index"
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
            "text_style_list": TEXT_STYLE_LIST,
            "comp_type_list": COMP_TYPE_LIST,
        },
    )


@router.put("/api/passages/{passage_id}")
async def update_passage(request: Request, passage_id: str):
    """パッセージの個別フィールドを更新する（インライン編集）。"""
    form = await request.form()
    conn = get_connection()
    try:
        updates = []
        params = []
        for key in (
            "text_type", "text_style", "genre_main", "genre_sub", "theme",
            "comp_type", "notes",
        ):
            if key in form:
                updates.append(f"{key} = ?")
                params.append(form[key])
        for key in ("has_jp_written", "has_en_written", "has_summary", "reviewed"):
            if key in form:
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
            "text_style_list": TEXT_STYLE_LIST,
            "comp_type_list": COMP_TYPE_LIST,
        },
    )


@router.post("/api/passages/bulk-replace")
async def bulk_replace(request: Request):
    """ジャンルの一括置換。"""
    form = await request.form()
    old_value = form.get("old_value", "")
    new_value = form.get("new_value", "")
    field = form.get("field", "genre_main")

    if old_value and new_value and field in ("genre_main", "genre_sub", "text_style"):
        conn = get_connection()
        try:
            conn.execute(
                f"UPDATE passages SET {field} = ? WHERE {field} = ?",
                (new_value, old_value),
            )
            conn.commit()
        finally:
            conn.close()

    # 更新後の一覧を返す
    return await list_passages(request)


@router.delete("/api/passages/{passage_id}")
async def delete_passage(passage_id: str):
    """パッセージを削除する。"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM passages WHERE id = ?", (passage_id,))
        conn.commit()
    finally:
        conn.close()
    # 削除成功時は 200 で空レスポンス返す（HTMX が要素を削除）
    return HTMLResponse("", status_code=200)


@router.delete("/api/passages")
async def delete_passages_by_year_university(year: int = Query(None), university: str = Query(None)):
    """年度と大学で指定されたパッセージをまとめて削除する。"""
    if not year or not university:
        return HTMLResponse("年度と大学の両方を指定してください", status_code=400)

    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM passages WHERE year = ? AND university = ?",
            (year, university),
        )
        conn.commit()
    finally:
        conn.close()

    # 削除成功時は JSON で削除件数を返す
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "deleted", "year": year, "university": university})
