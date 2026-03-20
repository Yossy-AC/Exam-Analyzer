"""4種LLM（Claude, Gemini, ChatGPT, Grok）の非同期クライアント + 並列呼び出し。"""

from __future__ import annotations

import asyncio
import logging
import time

import anthropic
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.config import (
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    TRANSLATE_CLAUDE_MODEL,
    TRANSLATE_GEMINI_MODEL,
    TRANSLATE_MAX_TOKENS,
    TRANSLATE_OPENAI_MODEL,
    TRANSLATE_TIMEOUT,
    TRANSLATE_GROK_MODEL,
    XAI_API_KEY,
)

logger = logging.getLogger(__name__)


async def call_claude(system: str, user: str, model: str | None = None, max_tokens: int | None = None) -> str:
    """Claude APIを非同期で呼び出す。"""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=TRANSLATE_TIMEOUT)
    response = await client.messages.create(
        model=model or TRANSLATE_CLAUDE_MODEL,
        max_tokens=max_tokens or TRANSLATE_MAX_TOKENS,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


async def call_gemini(system: str, user: str, model: str | None = None, max_tokens: int | None = None) -> str:
    """Gemini APIを非同期で呼び出す。system_instructionでsystem/user分離。"""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY が設定されていません")
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens or TRANSLATE_MAX_TOKENS,
        temperature=0,
        http_options=types.HttpOptions(timeout=TRANSLATE_TIMEOUT * 1000),
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model or TRANSLATE_GEMINI_MODEL,
        contents=user,
        config=config,
    )
    return response.text


async def call_openai(system: str, user: str, model: str | None = None, max_tokens: int | None = None) -> str:
    """OpenAI (ChatGPT) APIを非同期で呼び出す。"""
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=TRANSLATE_TIMEOUT)
    response = await client.chat.completions.create(
        model=model or TRANSLATE_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens or TRANSLATE_MAX_TOKENS,
        temperature=0,
    )
    return response.choices[0].message.content


async def call_grok(system: str, user: str, model: str | None = None, max_tokens: int | None = None) -> str:
    """Grok (xAI) APIを非同期で呼び出す。OpenAI互換API。"""
    client = AsyncOpenAI(
        base_url="https://api.x.ai/v1",
        api_key=XAI_API_KEY,
        timeout=TRANSLATE_TIMEOUT,
    )
    response = await client.chat.completions.create(
        model=model or TRANSLATE_GROK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens or TRANSLATE_MAX_TOKENS,
        temperature=0,
    )
    return response.choices[0].message.content


_LLM_CALLERS = {
    "claude": call_claude,
    "gemini": call_gemini,
    "chatgpt": call_openai,
    "grok": call_grok,
}


async def call_all_llms(
    system: str,
    user: str,
    timeout: int | None = None,
) -> tuple[dict[str, str], dict[str, int]]:
    """4種LLMに並列でリクエストし、結果と所要時間を返す。

    1つが失敗しても他は続行。失敗分は '[ERROR] ...' 文字列。

    Returns:
        (results, times): results={llm_name: text}, times={llm_name: ms}
    """
    _timeout = timeout or TRANSLATE_TIMEOUT

    async def _timed_call(name: str, func, system: str, user: str) -> tuple[str, str, int]:
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(func(system, user), timeout=_timeout)
            elapsed = int((time.monotonic() - start) * 1000)
            return name, result, elapsed
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("LLM %s timed out after %dms", name, elapsed)
            return name, f"[ERROR] Timeout after {_timeout}s", elapsed
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error("LLM %s failed: %s", name, e)
            return name, f"[ERROR] {type(e).__name__}: {e}", elapsed

    tasks = [_timed_call(name, func, system, user) for name, func in _LLM_CALLERS.items()]
    completed = await asyncio.gather(*tasks)

    results = {name: text for name, text, _ in completed}
    times = {name: elapsed for name, _, elapsed in completed}

    succeeded = sum(1 for t in results.values() if not t.startswith("[ERROR]"))
    logger.info("call_all_llms: %d/4 succeeded", succeeded)

    return results, times
