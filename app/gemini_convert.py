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


_SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
]


class RecitationError(RuntimeError):
    """Gemini APIがRECITATION（著作権再現フィルタ）でブロックした場合のエラー。"""


async def _call_gemini(client: genai.Client, pdf_bytes: bytes, prompt: str) -> tuple[str, int, int]:
    """Gemini APIを1回呼び出す。RECITATION検出時はRecitationErrorを送出。"""
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            http_options=types.HttpOptions(timeout=300_000),
            safety_settings=_SAFETY_SETTINGS,
        ),
    )
    usage = response.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
    text = response.text
    if not text:
        # ブロック理由を判定
        finish_reason = None
        if response.candidates:
            finish_reason = getattr(response.candidates[0], "finish_reason", None)
            logger.warning("Gemini finish_reason: %s", finish_reason)
        if finish_reason and "RECITATION" in str(finish_reason):
            raise RecitationError("RECITATION フィルタによりブロックされました")
        raise RuntimeError("Gemini APIが空レスポンスを返しました（安全フィルタ等の可能性）")
    return text, input_tokens, output_tokens


def _split_pdf_bytes(pdf_path: str, chunk_pages: int = 5) -> list[bytes]:
    """PDFをchunk_pagesページずつに分割し、各チャンクのバイト列を返す。"""
    import io
    doc = fitz.open(pdf_path)
    total = len(doc)
    chunks = []
    for start in range(0, total, chunk_pages):
        end = min(start + chunk_pages, total)
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
        buf = io.BytesIO()
        new_doc.save(buf)
        new_doc.close()
        chunks.append(buf.getvalue())
    doc.close()
    return chunks


async def convert_pdf_to_markdown(pdf_path: str, prompt: str) -> tuple[str, int, int]:
    """PDFをGemini APIに投げてMarkdownとトークン使用量を返す。

    RECITATION（著作権フィルタ）でブロックされた場合、PDFをページ分割して
    チャンクごとに変換し、結果を結合するフォールバックを実行する。

    Returns:
        tuple: (markdown_text, input_tokens, output_tokens)
    """
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    client = _get_client()

    # まず全体を一括で試行
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            return await _call_gemini(client, pdf_bytes, prompt)
        except RecitationError:
            logger.warning("RECITATION検出 → ページ分割フォールバックに切り替えます: %s", pdf_path)
            break  # フォールバックへ
        except Exception as e:
            logger.warning("Gemini APIエラー（試行 %d/%d）: %s", attempt, GEMINI_MAX_RETRIES, e)
            if attempt < GEMINI_MAX_RETRIES:
                await asyncio.sleep(GEMINI_RETRY_WAIT_SEC)
            else:
                raise

    # フォールバック: ページ分割して変換
    chunks = _split_pdf_bytes(pdf_path, chunk_pages=5)
    logger.info("ページ分割フォールバック: %d チャンクに分割", len(chunks))

    all_texts: list[str] = []
    total_input = 0
    total_output = 0

    for i, chunk_bytes in enumerate(chunks):
        chunk_prompt = (
            f"以下はPDFの一部（パート {i + 1}/{len(chunks)}）です。"
            f"前後のパートと結合されるため、frontmatter（---で囲むメタデータ）は最初のパートのみ出力してください。"
            f"それ以外のパートではfrontmatterを出力せず、# Question から始めてください。\n\n{prompt}"
        )
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            try:
                text, inp, out = await _call_gemini(client, chunk_bytes, chunk_prompt)
                all_texts.append(text)
                total_input += inp
                total_output += out
                logger.info("チャンク %d/%d 変換完了（%d入力, %d出力トークン）",
                            i + 1, len(chunks), inp, out)
                break
            except RecitationError:
                logger.warning("チャンク %d/%d もRECITATIONでブロック → スキップ", i + 1, len(chunks))
                all_texts.append(
                    f"<!-- COPYRIGHT_OMITTED: パート{i + 1}がGemini RECITATIONフィルタによりブロック -->"
                )
                break
            except Exception as e:
                logger.warning("チャンク %d/%d エラー（試行 %d/%d）: %s",
                               i + 1, len(chunks), attempt, GEMINI_MAX_RETRIES, e)
                if attempt < GEMINI_MAX_RETRIES:
                    await asyncio.sleep(GEMINI_RETRY_WAIT_SEC)
                else:
                    raise
        # チャンク間のレート制限
        if i < len(chunks) - 1:
            await asyncio.sleep(GEMINI_RETRY_WAIT_SEC)

    combined = "\n\n".join(all_texts)
    if not combined.strip():
        raise RuntimeError("全チャンクがブロックされました")
    return combined, total_input, total_output
