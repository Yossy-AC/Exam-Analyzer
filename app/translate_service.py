"""Multi-LLM英訳機能のビジネスロジック。"""

from __future__ import annotations

import json
import logging
import re
import time

from pydantic import BaseModel

from app.db import get_connection
from app.llm_clients import call_all_llms, call_claude
from app.config import TRANSLATE_INTEGRATION_MODEL, TRANSLATE_MAX_TOKENS
from app.translate_prompts import (
    BATCH_INTEGRATE_SYSTEM_PROMPT,
    BATCH_INTEGRATE_USER_TEMPLATE,
    BATCH_TRANSLATE_USER_TEMPLATE,
    INTEGRATE_SYSTEM_PROMPT,
    INTEGRATE_TEMPLATES,
    REVIEW_INTEGRATE_SYSTEM_PROMPT,
    REVIEW_INTEGRATE_TEMPLATE,
    REVIEW_SYSTEM_PROMPT,
    TRANSLATE_SYSTEM_PROMPT,
    build_batch_constraints,
    build_batch_numbered_list,
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


async def ask_about_result(
    question: str,
    japanese_text: str,
    integrated_result: str,
    raw_translations: dict[str, str],
    conversation: list[dict[str, str]] | None = None,
) -> dict:
    """統合結果に対する質問にClaudeが回答する。会話履歴対応。"""
    import anthropic
    from app.config import ANTHROPIC_API_KEY, TRANSLATE_TIMEOUT

    system = """\
あなたは翻訳の専門家です。
ユーザーが日本語文の英訳について質問しています。
以下のコンテキスト（原文・4LLMの英訳・統合結果）を踏まえて、質問に的確に回答してください。
回答はMarkdown形式で、簡潔に。"""

    raw_text = "\n".join(f"### {k}\n{v}" for k, v in raw_translations.items())
    context_msg = f"""## 原文
{japanese_text}

## 各LLMの英訳
{raw_text}

## 統合結果
{integrated_result}

---
上記を踏まえて、以下の質問に回答してください。"""

    messages = [{"role": "user", "content": context_msg}]

    # 会話履歴
    if conversation:
        for turn in conversation:
            messages.append({"role": turn["role"], "content": turn["content"]})

    # 今回の質問
    messages.append({"role": "user", "content": question})

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=TRANSLATE_TIMEOUT)
    response = await client.messages.create(
        model=TRANSLATE_INTEGRATION_MODEL,
        max_tokens=TRANSLATE_MAX_TOKENS,
        temperature=0,
        system=system,
        messages=messages,
    )
    return {"answer": response.content[0].text}


# ---------------------------------------------------------------------------
# バッチ英訳
# ---------------------------------------------------------------------------

class BatchItem(BaseModel):
    number: int
    japanese_text: str
    force_words: list[str] = []
    ban_words: list[str] = []
    hint: str | None = None


_DIRECTIVE_RE = re.compile(r"\s+/(force|ban|hint)\s+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\s*(\d+)\s*[.)\uff09]\s*")


def parse_batch_input(input_text: str) -> list[BatchItem]:
    """入力テキストをBatchItemリストにパースする。"""
    items = []
    auto_num = 0
    for line in input_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 行頭番号を抽出
        m = _NUMBER_RE.match(line)
        if m:
            number = int(m.group(1))
            rest = line[m.end():]
        else:
            auto_num += 1
            number = auto_num
            rest = line

        # ディレクティブを検出・分離
        force_words = []
        ban_words = []
        hint = None

        # 最初のディレクティブの位置を探す
        first_match = _DIRECTIVE_RE.search(rest)
        if first_match:
            japanese_text = rest[:first_match.start()].strip()
            directive_part = rest[first_match.start():]
            # ディレクティブを順に処理
            parts = _DIRECTIVE_RE.split(directive_part)
            # parts = ['', 'force', 'to /ban few', 'ban', 'few', ...] のようになるが
            # re.splitではキャプチャグループが含まれるので [空, type, value, type, value, ...]
            i = 1
            while i < len(parts) - 1:
                dtype = parts[i].lower()
                # 次のディレクティブの開始位置を探して値を取得
                value_part = parts[i + 1].strip()
                # value_partの中にさらに /force /ban /hint があるかチェック
                inner = re.split(r"\s+/(?=force|ban|hint)", value_part, flags=re.IGNORECASE)
                actual_value = inner[0].strip()

                if dtype == "force" and actual_value:
                    force_words.extend(w.strip() for w in actual_value.split(",") if w.strip())
                elif dtype == "ban" and actual_value:
                    ban_words.extend(w.strip() for w in actual_value.split(",") if w.strip())
                elif dtype == "hint" and actual_value:
                    hint = actual_value

                # 残りの /xxx 部分を再処理
                for remaining in inner[1:]:
                    rm = re.match(r"(force|ban|hint)\s+(.*)", remaining, re.IGNORECASE)
                    if rm:
                        rd = rm.group(1).lower()
                        rv = rm.group(2).strip()
                        if rd == "force" and rv:
                            force_words.extend(w.strip() for w in rv.split(",") if w.strip())
                        elif rd == "ban" and rv:
                            ban_words.extend(w.strip() for w in rv.split(",") if w.strip())
                        elif rd == "hint" and rv:
                            hint = rv

                i += 2
        else:
            japanese_text = rest.strip()

        if japanese_text:
            items.append(BatchItem(
                number=number,
                japanese_text=japanese_text,
                force_words=force_words,
                ban_words=ban_words,
                hint=hint,
            ))

    return items


def parse_numbered_sections(text: str) -> dict[int, str]:
    """【N】で区切られたセクションをパースする。"""
    sections = {}
    pattern = r"【(\d+)】"
    parts = re.split(pattern, text)
    for i in range(1, len(parts) - 1, 2):
        num = int(parts[i])
        content = parts[i + 1].strip()
        sections[num] = content
    return sections


async def generate_batch(
    input_text: str,
    university: str | None = None,
    university_custom: str | None = None,
) -> dict:
    """バッチ英訳: 4LLM一括→Claude統合。"""
    start = time.monotonic()

    items = parse_batch_input(input_text)
    if not items:
        return {"error": "有効な日本語文が見つかりません"}

    numbered_list = build_batch_numbered_list(items)

    # 4LLM並列呼び出し
    system = inject_university(TRANSLATE_SYSTEM_PROMPT, university, university_custom)
    user = BATCH_TRANSLATE_USER_TEMPLATE.format(numbered_list=numbered_list)
    raw_translations, llm_times = await call_all_llms(system, user)

    # 各LLM応答をセクション分割
    raw_sections = {}
    for llm_name, raw_text in raw_translations.items():
        raw_sections[llm_name] = parse_numbered_sections(raw_text)

    # 統合フェーズ
    constraints = build_batch_constraints(items)
    integrate_system = inject_university(
        BATCH_INTEGRATE_SYSTEM_PROMPT, university, university_custom,
    )
    integrate_user = BATCH_INTEGRATE_USER_TEMPLATE.format(
        numbered_list=numbered_list,
        claude_result=raw_translations.get("claude", "[N/A]"),
        gemini_result=raw_translations.get("gemini", "[N/A]"),
        chatgpt_result=raw_translations.get("chatgpt", "[N/A]"),
        grok_result=raw_translations.get("grok", "[N/A]"),
        constraints=constraints,
    )
    integrated_text = await call_claude(
        system=integrate_system,
        user=integrate_user,
        model=TRANSLATE_INTEGRATION_MODEL,
        max_tokens=TRANSLATE_MAX_TOKENS,
    )

    integrated_sections = parse_numbered_sections(integrated_text)

    total_ms = int((time.monotonic() - start) * 1000)

    # レスポンス構築
    result_items = []
    for item in items:
        n = item.number
        # 統合結果からベスト英訳を抽出
        detail = integrated_sections.get(n, "")
        best = ""
        for line in detail.split("\n"):
            if line.startswith("ベスト英訳:"):
                best = line[len("ベスト英訳:"):].strip()
                break

        result_items.append({
            "number": n,
            "japanese_text": item.japanese_text,
            "force_words": item.force_words,
            "ban_words": item.ban_words,
            "hint": item.hint,
            "best_translation": best or detail.split("\n")[0] if detail else "",
            "integrated_detail": detail,
            "raw_translations": {
                llm: raw_sections.get(llm, {}).get(n, "")
                for llm in ["claude", "gemini", "chatgpt", "grok"]
            },
        })

    # DB保存
    record_id = _save_to_db(
        mode="batch",
        japanese_text=input_text,
        user_translation=None,
        context=None,
        output_format=None,
        university=university,
        options={"university_custom": university_custom},
        raw_results=raw_translations,
        integrated_result=integrated_text,
        processing_time_ms=total_ms,
        llm_times=llm_times,
    )

    return {
        "id": record_id,
        "items": result_items,
        "metadata": {
            "total_items": len(items),
            "processing_time_ms": total_ms,
            "llm_times": llm_times,
        },
    }
