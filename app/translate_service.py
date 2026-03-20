"""Multi-LLM英訳機能のビジネスロジック。"""

from __future__ import annotations

import json
import logging
import time

from app.db import get_connection
from app.llm_clients import call_all_llms, call_claude
from app.config import TRANSLATE_INTEGRATION_MODEL, TRANSLATE_MAX_TOKENS
from app.translate_prompts import (
    INTEGRATE_SYSTEM_PROMPT,
    INTEGRATE_TEMPLATES,
    REVIEW_INTEGRATE_SYSTEM_PROMPT,
    REVIEW_INTEGRATE_TEMPLATE,
    REVIEW_SYSTEM_PROMPT,
    TRANSLATE_SYSTEM_PROMPT,
    build_compare_fragment,
    build_review_user_prompt,
    build_scoring_fragment,
    build_translate_user_prompt,
    inject_university,
)

logger = logging.getLogger(__name__)


def _save_to_db(
    mode: str,
    japanese_text: str,
    user_translation: str | None,
    context: str | None,
    output_format: int | None,
    university: str | None,
    options: dict,
    raw_results: dict[str, str],
    integrated_result: str,
    processing_time_ms: int,
    llm_times: dict[str, int],
) -> int:
    """翻訳結果をDBに保存し、IDを返す。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO translations
            (mode, japanese_text, user_translation, context, output_format,
             university, options_json, raw_results_json, integrated_result,
             processing_time_ms, llm_times_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mode,
                japanese_text,
                user_translation,
                context,
                output_format,
                university,
                json.dumps(options, ensure_ascii=False),
                json.dumps(raw_results, ensure_ascii=False),
                integrated_result,
                processing_time_ms,
                json.dumps(llm_times),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


async def generate_translations(
    japanese_text: str,
    output_format: int = 1,
    context: str | None = None,
    university: str | None = None,
    university_custom: str | None = None,
) -> dict:
    """4LLM並列英訳→Claude統合。"""
    start = time.monotonic()

    # 4LLM並列呼び出し
    system = inject_university(TRANSLATE_SYSTEM_PROMPT, university, university_custom)
    user = build_translate_user_prompt(japanese_text, context)
    raw_translations, llm_times = await call_all_llms(system, user)

    # 統合フェーズ
    integrate_template = INTEGRATE_TEMPLATES.get(output_format, INTEGRATE_TEMPLATES[1])
    integrate_user = integrate_template.format(
        japanese_text=japanese_text,
        claude_result=raw_translations.get("claude", "[N/A]"),
        gemini_result=raw_translations.get("gemini", "[N/A]"),
        chatgpt_result=raw_translations.get("chatgpt", "[N/A]"),
        grok_result=raw_translations.get("grok", "[N/A]"),
    )
    integrate_system = inject_university(INTEGRATE_SYSTEM_PROMPT, university, university_custom)

    integrated_result = await call_claude(
        system=integrate_system,
        user=integrate_user,
        model=TRANSLATE_INTEGRATION_MODEL,
        max_tokens=TRANSLATE_MAX_TOKENS,
    )

    total_ms = int((time.monotonic() - start) * 1000)

    # DB保存
    record_id = _save_to_db(
        mode="translate",
        japanese_text=japanese_text,
        user_translation=None,
        context=context,
        output_format=output_format,
        university=university,
        options={"university_custom": university_custom},
        raw_results=raw_translations,
        integrated_result=integrated_result,
        processing_time_ms=total_ms,
        llm_times=llm_times,
    )

    return {
        "id": record_id,
        "raw_translations": raw_translations,
        "integrated_result": integrated_result,
        "output_format": output_format,
        "options_applied": {
            "university": university,
            "university_custom": university_custom,
        },
        "metadata": {
            "processing_time_ms": total_ms,
            "llm_times": llm_times,
        },
    }


async def reformat_translations(
    japanese_text: str,
    raw_translations: dict[str, str],
    output_format: int = 1,
    university: str | None = None,
    university_custom: str | None = None,
) -> dict:
    """統合のみ再実行（4LLM再呼び出しなし）。DB保存しない。"""
    start = time.monotonic()

    integrate_template = INTEGRATE_TEMPLATES.get(output_format, INTEGRATE_TEMPLATES[1])
    integrate_user = integrate_template.format(
        japanese_text=japanese_text,
        claude_result=raw_translations.get("claude", "[N/A]"),
        gemini_result=raw_translations.get("gemini", "[N/A]"),
        chatgpt_result=raw_translations.get("chatgpt", "[N/A]"),
        grok_result=raw_translations.get("grok", "[N/A]"),
    )
    integrate_system = inject_university(INTEGRATE_SYSTEM_PROMPT, university, university_custom)

    integrated_result = await call_claude(
        system=integrate_system,
        user=integrate_user,
        model=TRANSLATE_INTEGRATION_MODEL,
        max_tokens=TRANSLATE_MAX_TOKENS,
    )

    total_ms = int((time.monotonic() - start) * 1000)

    return {
        "integrated_result": integrated_result,
        "output_format": output_format,
        "metadata": {
            "processing_time_ms": total_ms,
        },
    }


async def review_translation(
    japanese_text: str,
    user_translation: str,
    context: str | None = None,
    university: str | None = None,
    university_custom: str | None = None,
    scoring_simulation: bool = False,
    compare_with_generated: bool = False,
    previous_translations: dict[str, str] | None = None,
) -> dict:
    """ユーザー英訳を4LLMがレビュー→Claude統合レポート。"""
    start = time.monotonic()

    # 4LLM並列レビュー
    system = inject_university(REVIEW_SYSTEM_PROMPT, university, university_custom)
    user = build_review_user_prompt(japanese_text, user_translation, context)
    raw_reviews, llm_times = await call_all_llms(system, user)

    # 統合フェーズ
    integrate_user = REVIEW_INTEGRATE_TEMPLATE.format(
        japanese_text=japanese_text,
        user_translation=user_translation,
        claude_result=raw_reviews.get("claude", "[N/A]"),
        gemini_result=raw_reviews.get("gemini", "[N/A]"),
        chatgpt_result=raw_reviews.get("chatgpt", "[N/A]"),
        grok_result=raw_reviews.get("grok", "[N/A]"),
    )
    integrate_system = inject_university(
        REVIEW_INTEGRATE_SYSTEM_PROMPT, university, university_custom,
    )

    # オプション注入
    if scoring_simulation:
        integrate_user += "\n\n" + build_scoring_fragment(university)
    if compare_with_generated and previous_translations:
        integrate_user += "\n\n" + build_compare_fragment(previous_translations)

    integrated_review = await call_claude(
        system=integrate_system,
        user=integrate_user,
        model=TRANSLATE_INTEGRATION_MODEL,
        max_tokens=TRANSLATE_MAX_TOKENS,
    )

    total_ms = int((time.monotonic() - start) * 1000)

    options_applied = {
        "university": university,
        "university_custom": university_custom,
        "scoring_simulation": scoring_simulation,
        "compare_with_generated": compare_with_generated,
    }

    # DB保存
    record_id = _save_to_db(
        mode="review",
        japanese_text=japanese_text,
        user_translation=user_translation,
        context=context,
        output_format=None,
        university=university,
        options=options_applied,
        raw_results=raw_reviews,
        integrated_result=integrated_review,
        processing_time_ms=total_ms,
        llm_times=llm_times,
    )

    return {
        "id": record_id,
        "raw_reviews": raw_reviews,
        "integrated_review": integrated_review,
        "options_applied": options_applied,
        "metadata": {
            "processing_time_ms": total_ms,
            "llm_times": llm_times,
        },
    }
