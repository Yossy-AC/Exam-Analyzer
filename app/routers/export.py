"""CSV/JSON/DBエクスポートエンドポイント。"""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.auth import is_student
from app.config import DB_PATH
from app.db import get_connection

router = APIRouter()

EXPORT_COLUMNS = [
    "id", "university", "year", "faculty", "question_number", "passage_index",
    "text_type", "text_style", "word_count",
    "source_title", "source_author", "source_year",
    "genre_main", "genre_sub", "theme",
    "has_jp_written", "has_en_written", "has_summary",
    "has_wabun_eiyaku", "has_jiyu_eisakubun",
    "has_jp_translation", "has_jp_explanation", "has_en_explanation",
    "has_jp_summary", "has_en_summary",
    "has_visual_info", "visual_info_type",
    "low_confidence", "low_confidence_fields",
    "reviewed", "notes",
]


def _build_query(year: int = None, university: str = None, genre_main: str = None) -> tuple[str, list]:
    query = """
        SELECT p.*, u.is_kyutei, u.is_national, u.is_private
        FROM passages p
        LEFT JOIN universities u ON p.university = u.name
        WHERE 1=1
    """
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
    query += " ORDER BY p.year, p.university, p.question_number, p.passage_index"
    return query, params


@router.get("/api/export/csv")
async def export_csv(year: int = None, university: str = None, genre_main: str = None):
    """CSV出力（BOM付きUTF-8）。"""
    conn = get_connection()
    try:
        query, params = _build_query(year, university, genre_main)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    # BOM付きUTF-8
    output.write("\ufeff")
    writer = csv.DictWriter(
        output,
        fieldnames=EXPORT_COLUMNS + ["is_kyutei", "is_national", "is_private"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        safe_row = {}
        for k, v in dict(row).items():
            # CSV数式インジェクション対策: Excel で数式として実行される文字をエスケープ
            if isinstance(v, str) and v and v[0] in ("=", "+", "-", "@", "\t", "\r"):
                v = "'" + v
            safe_row[k] = v
        writer.writerow(safe_row)

    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=exam_passages.csv"},
    )


@router.get("/api/export/json")
async def export_json(year: int = None, university: str = None, genre_main: str = None):
    """JSON出力。"""
    conn = get_connection()
    try:
        query, params = _build_query(year, university, genre_main)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    data = [dict(row) for row in rows]
    content = json.dumps(data, ensure_ascii=False, indent=2)

    return Response(
        content=content.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=exam_passages.json"},
    )


@router.get("/api/export/db")
async def export_db(request: Request):
    """SQLiteファイルダウンロード。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    db_path = Path(DB_PATH)
    if not db_path.exists():
        return Response("Database not found", status_code=404)

    return Response(
        content=db_path.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=exam.db"},
    )
