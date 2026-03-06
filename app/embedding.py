"""Voyage AI を用いたテキスト embedding 生成モジュール。

使用モデル: voyage-3 (1024次元)
入力長: 最大32,000トークン（英語長文に十分）
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import voyageai

from app.config import VOYAGE_API_KEY

# シングルトンクライアント（遅延初期化）
_client: voyageai.AsyncClient | None = None

VOYAGE_MODEL = "voyage-4"
EMBEDDING_DIM = 1024


def _get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=VOYAGE_API_KEY)
    return _client


async def embed_text(text: str) -> list[float] | None:
    """テキストを embedding ベクトルに変換する。

    Returns:
        1024次元のfloatリスト。APIエラー時はNone。
    """
    if not text or not VOYAGE_API_KEY:
        return None
    # 先頭20,000文字に制限（API制限対応・英語長文は十分カバー）
    truncated = text[:20000]
    client = _get_client()
    result = await client.embed([truncated], model=VOYAGE_MODEL, input_type="document")
    return result.embeddings[0]


def encode_embedding(vec: list[float]) -> bytes:
    """float リストをBLOB用のバイト列に変換する（little-endian float32）。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def decode_embedding(blob: bytes) -> list[float]:
    """BLOB バイト列を float リストに変換する。"""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """コサイン類似度を計算する（0〜1）。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
