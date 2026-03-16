"""X-ray APIエンドポイント: 語彙カテゴリ付きトークナイズ。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import is_student
from app.db import get_connection
from app.xray_tokenizer import MAX_TEXT_LENGTH, tokenize_for_xray

router = APIRouter()


@router.get("/api/xray/passages")
async def list_xray_passages(request: Request):
    """X-ray用のlong_readingパッセージ一覧（メタデータのみ）。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT p.id, p.university, p.year, p.question_number, p.passage_index,
                      p.word_count, p.cefr_level, p.genre_main,
                      u.university_class, u.region
               FROM passages p LEFT JOIN universities u ON p.university = u.name
               WHERE p.text_type = 'long_reading'
                 AND p.text_body != ''
                 AND COALESCE(p.copyright_omitted, 0) = 0
               ORDER BY p.year DESC,
                 CASE u.university_class
                   WHEN '共通テスト' THEN 0 WHEN '旧帝大' THEN 1 WHEN '難関大' THEN 2
                   WHEN '準難関大' THEN 3 WHEN 'その他国立大' THEN 4
                   WHEN 'その他公立大' THEN 5 ELSE 6 END,
                 CASE u.region
                   WHEN '東北以北' THEN 1 WHEN '関東' THEN 2 WHEN '中部' THEN 3
                   WHEN '近畿' THEN 4 WHEN '中四国' THEN 5 WHEN '九州以南' THEN 6 ELSE 7 END,
                 p.university, p.question_number, p.passage_index"""
        ).fetchall()
    finally:
        conn.close()

    passages = [
        {
            "id": r["id"],
            "university": r["university"],
            "year": r["year"],
            "questionNumber": r["question_number"],
            "passageIndex": r["passage_index"],
            "wordCount": r["word_count"],
            "cefrLevel": r["cefr_level"] or "",
            "genreMain": r["genre_main"] or "",
            "universityClass": r["university_class"] or "",
            "region": r["region"] or "",
        }
        for r in rows
    ]
    return JSONResponse(passages)


@router.get("/api/xray/passage/{passage_id:path}")
async def get_xray_passage(
    request: Request,
    passage_id: str,
    target1900_progress: int = 0,
    leap_progress: int = 0,
):
    """本文をトークナイズしてカテゴリ付きで返す（staff only）。"""
    if is_student(request):
        return JSONResponse({"error": "権限がありません"}, status_code=403)

    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT p.id, p.university, p.year, p.question_number, p.word_count,
                      p.cefr_level, p.genre_main, p.text_body
               FROM passages p
               WHERE p.id = ? AND p.text_type = 'long_reading'""",
            (passage_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return JSONResponse({"error": "パッセージが見つかりません"}, status_code=404)

    text_body = row["text_body"] or ""
    if not text_body.strip():
        return JSONResponse({"error": "本文データがありません"}, status_code=404)

    paragraphs = tokenize_for_xray(text_body, target1900_progress, leap_progress)

    return JSONResponse({
        "id": row["id"],
        "university": row["university"],
        "year": row["year"],
        "questionNumber": row["question_number"],
        "wordCount": row["word_count"],
        "cefrLevel": row["cefr_level"] or "",
        "genreMain": row["genre_main"] or "",
        "paragraphs": paragraphs,
    })


class AnalyzeRequest(BaseModel):
    text: str
    target1900_progress: int = 0
    leap_progress: int = 0


@router.post("/api/xray/analyze")
async def analyze_xray(request: Request, body: AnalyzeRequest):
    """任意テキストをトークナイズしてカテゴリ付きで返す。"""
    if not body.text or not body.text.strip():
        return JSONResponse({"error": "テキストが空です"}, status_code=400)

    if len(body.text) > MAX_TEXT_LENGTH:
        return JSONResponse(
            {"error": f"テキストが長すぎます（最大{MAX_TEXT_LENGTH}文字）"},
            status_code=400,
        )

    paragraphs = tokenize_for_xray(
        body.text, body.target1900_progress, body.leap_progress
    )

    return JSONResponse({"paragraphs": paragraphs})
