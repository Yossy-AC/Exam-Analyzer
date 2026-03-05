"""Claude APIを使った自動分類。"""

from __future__ import annotations

import asyncio
import json
import logging

import anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL_DEFAULT,
    CLAUDE_MODEL_PREMIUM,
    CLAUDE_TEMPERATURE,
    CONCURRENT_LIMIT,
    PREMIUM_UNIVERSITY_CLASSES,
)
from app.db import get_connection
from app.models import ClassificationResult, ParsedQuestion
from app.prompts import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

_semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)


def _parse_json_response(text: str) -> dict:
    """Claude応答からJSONを抽出してパースする。"""
    text = text.strip()
    # コードブロックが含まれている場合の処理
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            inner = text[start:end]
            # ```json\n の後ろから取得
            newline = inner.find("\n")
            if newline != -1:
                text = inner[newline + 1:]
            else:
                text = inner[3:]
    # 先頭・末尾の非JSON文字を除去
    text = text.strip()
    if not text.startswith("{"):
        idx = text.find("{")
        if idx != -1:
            text = text[idx:]
    if not text.endswith("}"):
        idx = text.rfind("}")
        if idx != -1:
            text = text[:idx + 1]
    return json.loads(text)


def _select_model(university: str) -> str:
    """大学クラスに基づいてAPIモデルを選択する。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT university_class FROM universities WHERE name = ?",
            (university,),
        ).fetchone()
    finally:
        conn.close()
    if row and row["university_class"] in PREMIUM_UNIVERSITY_CLASSES:
        return CLAUDE_MODEL_PREMIUM
    return CLAUDE_MODEL_DEFAULT


async def _call_claude(system: str, user: str, model: str) -> str:
    """Claude APIを呼び出して応答テキストを返す。"""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)
    async with _semaphore:
        response = await client.messages.create(
            model=model,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=CLAUDE_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    return response.content[0].text


def _validate_question_flags(text_type: str, questions_section: str, result: ClassificationResult) -> ClassificationResult:
    """text_typeと設問内容の整合性をバリデーションする。

    composition問題で設問セクションに具体的な和訳・説明指示がない場合、
    LLMが誤ってフラグを立てる問題を防ぐ。
    """
    if text_type not in ("composition", "others"):
        return result

    # 日本語記述指示の明確なキーワードがなければリセット
    jp_trans_keywords = ["日本語に訳", "和訳", "日本語で表", "日本語に直", "邦訳"]
    if result.has_jp_translation and not any(kw in questions_section for kw in jp_trans_keywords):
        result.has_jp_translation = False

    jp_expl_keywords = ["日本語で説明", "日本語で述べ", "日本語で答え", "日本語で書", "日本語で記述"]
    if result.has_jp_explanation and not any(kw in questions_section for kw in jp_expl_keywords):
        result.has_jp_explanation = False

    jp_summary_keywords = ["要約", "要旨", "まとめ", "summarize"]
    if result.has_jp_summary and not any(kw in questions_section for kw in jp_summary_keywords):
        result.has_jp_summary = False

    return result


async def classify_passage(pq: ParsedQuestion) -> dict:
    """パッセージを完全に分類する（統合プロンプトで1回のAPI呼び出し）。"""
    prompt = USER_PROMPT.format(
        university=pq.university,
        year=pq.year,
        question_number=pq.question_number,
        text_section=pq.text_section[:3000],
        questions_section=pq.questions_section[:2000] if pq.questions_section.strip() else "(設問なし)",
    )
    model = _select_model(pq.university)
    logger.info("Using model %s for %s", model, pq.university)
    raw = await _call_claude(SYSTEM_PROMPT, prompt, model)
    data = _parse_json_response(raw)

    # low_confidence_fields を抽出してから ClassificationResult に変換
    low_confidence_fields = data.pop("low_confidence_fields", [])
    result = ClassificationResult(**data)
    result.low_confidence_fields = low_confidence_fields if isinstance(low_confidence_fields, list) else []

    # バリデーション
    result = _validate_question_flags(result.text_type, pq.questions_section, result)

    # others/listening は文体・ジャンル等を全てクリア、語数もNULL
    if result.text_type in ("others", "listening"):
        result.text_style = ""
        result.genre_main = ""
        result.genre_sub = ""
        result.theme = ""
        result.word_count = None

    # composition は語数NULL
    if result.text_type == "composition":
        result.word_count = None
        # 自由英作文のみ（和文英訳なし）の場合、text_style をクリア
        if result.has_jiyu_eisakubun and not result.has_wabun_eiyaku:
            result.text_style = ""

    # 語数は警告対象から除外（LLMの語数カウントは目安のため）
    result.low_confidence_fields = [f for f in result.low_confidence_fields if f not in ("語数", "word_count")]

    # 旧互換フィールドの導出
    has_jp_written = result.has_jp_translation or result.has_jp_explanation or result.has_jp_summary
    has_en_written = result.has_en_explanation or result.has_en_summary or result.has_wabun_eiyaku or result.has_jiyu_eisakubun
    has_summary = result.has_jp_summary or result.has_en_summary

    # low_confidence判定
    low_confidence = len(result.low_confidence_fields) > 0

    return {
        "id": pq.passage_id,
        "university": pq.university,
        "year": pq.year,
        "faculty": pq.faculty,
        "question_number": pq.question_number,
        "passage_index": pq.passage_index,
        "text_type": result.text_type,
        "text_style": result.text_style,
        "word_count": result.word_count,
        "source_title": result.source_title,
        "source_author": result.source_author,
        "source_year": result.source_year,
        "genre_main": result.genre_main,
        "genre_sub": result.genre_sub,
        "theme": result.theme,
        "has_jp_written": has_jp_written,
        "has_en_written": has_en_written,
        "has_summary": has_summary,
        "has_wabun_eiyaku": result.has_wabun_eiyaku,
        "has_jiyu_eisakubun": result.has_jiyu_eisakubun,
        "has_jp_translation": result.has_jp_translation,
        "has_jp_explanation": result.has_jp_explanation,
        "has_en_explanation": result.has_en_explanation,
        "has_jp_summary": result.has_jp_summary,
        "has_en_summary": result.has_en_summary,
        "has_visual_info": result.has_visual_info,
        "visual_info_type": result.visual_info_type,
        "low_confidence": low_confidence,
        "low_confidence_fields": ",".join(result.low_confidence_fields),
    }
