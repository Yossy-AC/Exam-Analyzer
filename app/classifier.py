"""Claude APIを使った自動分類。"""

from __future__ import annotations

import asyncio
import json
import logging

import anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    CLAUDE_TEMPERATURE,
    CONCURRENT_LIMIT,
)
from app.models import ParsedQuestion, QuestionAnalysisResult, TextAnalysisResult
from app.prompts import (
    SYSTEM_PROMPT_QUESTIONS,
    SYSTEM_PROMPT_TEXT,
    USER_PROMPT_QUESTIONS,
    USER_PROMPT_TEXT,
)

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


async def _call_claude(system: str, user: str) -> str:
    """Claude APIを呼び出して応答テキストを返す。"""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    async with _semaphore:
        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=CLAUDE_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    return response.content[0].text


async def analyze_text(pq: ParsedQuestion) -> TextAnalysisResult:
    """テキストセクションを分析し、ジャンル・出典等を返す。"""
    prompt = USER_PROMPT_TEXT.format(
        university=pq.university,
        year=pq.year,
        question_number=pq.question_number,
        text_section=pq.text_section[:3000],  # トークン制限のため切り詰め
    )
    raw = await _call_claude(SYSTEM_PROMPT_TEXT, prompt)
    data = _parse_json_response(raw)
    return TextAnalysisResult(**data)


async def analyze_questions(pq: ParsedQuestion) -> QuestionAnalysisResult:
    """設問セクションを分析し、各フラグを返す。"""
    if not pq.questions_section.strip():
        return QuestionAnalysisResult()

    prompt = USER_PROMPT_QUESTIONS.format(
        university=pq.university,
        year=pq.year,
        question_number=pq.question_number,
        questions_section=pq.questions_section[:2000],
    )
    raw = await _call_claude(SYSTEM_PROMPT_QUESTIONS, prompt)
    data = _parse_json_response(raw)
    return QuestionAnalysisResult(**data)


async def classify_passage(pq: ParsedQuestion) -> dict:
    """パッセージを完全に分類する（テキスト分析 + 設問分析の2回呼び出し）。"""
    text_result, question_result = await asyncio.gather(
        analyze_text(pq),
        analyze_questions(pq),
    )

    return {
        "id": pq.passage_id,
        "university": pq.university,
        "year": pq.year,
        "faculty": pq.faculty,
        "question_number": pq.question_number,
        "passage_index": pq.passage_index,
        **text_result.model_dump(),
        **question_result.model_dump(),
    }
