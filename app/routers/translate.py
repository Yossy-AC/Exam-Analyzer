"""Multi-LLM英訳機能のAPIルーター。"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.auth import is_student
from app.db import get_connection
from app.translate_service import (
    generate_translations,
    reformat_translations,
    review_translation,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TranslateRequest(BaseModel):
    japanese_text: str
    output_format: int = 1
    context: str | None = None
    university: str | None = None
    university_custom: str | None = None


class ReformatRequest(BaseModel):
    japanese_text: str
    raw_translations: dict[str, str]
    output_format: int = 1
    university: str | None = None
    university_custom: str | None = None


class AskRequest(BaseModel):
    question: str
    japanese_text: str
    integrated_result: str
    raw_translations: dict[str, str]
    conversation: list[dict[str, str]] = []  # [{role: "user"/"assistant", content: "..."}]


class ReviewRequest(BaseModel):
    japanese_text: str
    user_translation: str
    context: str | None = None
    university: str | None = None
    university_custom: str | None = None
    scoring_simulation: bool = False
    compare_with_generated: bool = False
    previous_translations: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/staff/translate")
async def api_translate(request: Request, body: TranslateRequest):
    """英訳生成: 4LLM並列 + Claude統合。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")
    if not body.japanese_text.strip():
        raise HTTPException(status_code=400, detail="japanese_text is required")
    if body.output_format not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="output_format must be 1, 2, or 3")

    result = await generate_translations(
        japanese_text=body.japanese_text,
        output_format=body.output_format,
        context=body.context,
        university=body.university,
        university_custom=body.university_custom,
    )
    return result


@router.post("/api/staff/translate/reformat")
async def api_reformat(request: Request, body: ReformatRequest):
    """形式変更: 統合のみ再実行（4LLM再呼び出しなし）。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")
    if body.output_format not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="output_format must be 1, 2, or 3")

    result = await reformat_translations(
        japanese_text=body.japanese_text,
        raw_translations=body.raw_translations,
        output_format=body.output_format,
        university=body.university,
        university_custom=body.university_custom,
    )
    return result


@router.post("/api/staff/translate/ask")
async def api_ask(request: Request, body: AskRequest):
    """統合結果に対する質問に回答する。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    from app.translate_service import ask_about_result
    result = await ask_about_result(
        question=body.question,
        japanese_text=body.japanese_text,
        integrated_result=body.integrated_result,
        raw_translations=body.raw_translations,
        conversation=body.conversation,
    )
    return result


@router.post("/api/staff/review")
async def api_review(request: Request, body: ReviewRequest):
    """英訳レビュー: 4LLM並列レビュー + Claude統合レポート。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")
    if not body.japanese_text.strip():
        raise HTTPException(status_code=400, detail="japanese_text is required")
    if not body.user_translation.strip():
        raise HTTPException(status_code=400, detail="user_translation is required")

    result = await review_translation(
        japanese_text=body.japanese_text,
        user_translation=body.user_translation,
        context=body.context,
        university=body.university,
        university_custom=body.university_custom,
        scoring_simulation=body.scoring_simulation,
        compare_with_generated=body.compare_with_generated,
        previous_translations=body.previous_translations,
    )
    return result


@router.get("/api/staff/translate/history")
async def api_history(request: Request, limit: int = 50, offset: int = 0):
    """翻訳履歴を取得する。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, mode, japanese_text, user_translation, context,
                      output_format, university, options_json,
                      processing_time_ms, created_at
               FROM translations
               ORDER BY id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    finally:
        conn.close()

    return {
        "items": [
            {
                "id": r["id"],
                "mode": r["mode"],
                "japanese_text": r["japanese_text"][:100],
                "user_translation": (r["user_translation"] or "")[:100],
                "context": r["context"],
                "output_format": r["output_format"],
                "university": r["university"],
                "processing_time_ms": r["processing_time_ms"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/api/staff/translate/history/{record_id}")
async def api_history_detail(request: Request, record_id: int):
    """翻訳履歴の詳細を取得する。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM translations WHERE id = ?", (record_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    return {
        "id": row["id"],
        "mode": row["mode"],
        "japanese_text": row["japanese_text"],
        "user_translation": row["user_translation"],
        "context": row["context"],
        "output_format": row["output_format"],
        "university": row["university"],
        "options_json": row["options_json"],
        "raw_results_json": row["raw_results_json"],
        "integrated_result": row["integrated_result"],
        "processing_time_ms": row["processing_time_ms"],
        "llm_times_json": row["llm_times_json"],
        "created_at": row["created_at"],
    }


@router.delete("/api/staff/translate/history/{record_id}")
async def api_history_delete(request: Request, record_id: int):
    """翻訳履歴を削除する。"""
    if is_student(request):
        raise HTTPException(status_code=403, detail="Staff only")

    conn = get_connection()
    try:
        result = conn.execute("DELETE FROM translations WHERE id = ?", (record_id,))
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
    finally:
        conn.close()

    return {"ok": True}
