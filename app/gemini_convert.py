"""Gemini APIを使ったPDF→Markdown変換。pdf-converterから移植。"""

from __future__ import annotations

import asyncio
import logging
import re

import fitz  # PyMuPDF
from google import genai
from google.genai import types

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MAX_RETRIES,
    GEMINI_MODEL_NAME,
    GEMINI_RETRY_WAIT_SEC,
)

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Geminiクライアントをlazy初期化して返す。"""
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY が設定されていません")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def is_scanned_pdf(pdf_path: str, threshold: int = 100) -> bool:
    """PDFがスキャン由来かどうかを判定する。"""
    doc = fitz.open(pdf_path)
    total_chars = sum(len(page.get_text()) for page in doc)
    doc.close()
    return total_chars < threshold


def parse_filename(stem: str) -> tuple[str, str]:
    """ファイル名からyearとuniversityを抽出する。

    例: '2025大阪大（外国語以外）_問題' → ('2025', '大阪大（外国語以外）')
    """
    m = re.match(r"^(\d{4})(.+?)_問題", stem)
    if m:
        return m.group(1), m.group(2)
    return "", stem


async def convert_pdf_to_markdown(pdf_path: str, prompt: str) -> tuple[str, int, int]:
    """PDFをGemini APIに投げてMarkdownとトークン使用量を返す。

    Returns:
        tuple: (markdown_text, input_tokens, output_tokens)
    """
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    client = _get_client()

    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL_NAME,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=300_000),
                ),
            )
            usage = response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            return response.text, input_tokens, output_tokens

        except Exception as e:
            logger.warning("Gemini APIエラー（試行 %d/%d）: %s", attempt, GEMINI_MAX_RETRIES, e)
            if attempt < GEMINI_MAX_RETRIES:
                await asyncio.sleep(GEMINI_RETRY_WAIT_SEC)
            else:
                raise
