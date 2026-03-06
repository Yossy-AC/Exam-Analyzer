"""既存DBの long_reading パッセージに embedding を一括付与するスクリプト。

使い方:
    cd exam-analyzer
    uv run python backfill_embedding.py

注意: Voyage AI API呼び出しを伴うため、VOYAGE_API_KEYが必要。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db import get_connection, init_db
from app.embedding import decode_embedding, embed_text, encode_embedding


async def process_passage(row: dict, semaphore: asyncio.Semaphore) -> tuple[str, bytes | None]:
    """1パッセージの embedding 生成（セマフォ制御）。

    Tier 1 制限: 2,000 RPM / 8M TPM
    安全設定: 並行5 + 0.1秒スリープ → 最大50 RPM（制限の2.5%）
    """
    async with semaphore:
        await asyncio.sleep(0.1)  # 安全マージン（2,000 RPM制限に対し余裕を持たせる）
        vec = await embed_text(row["text_body"])
        if vec is None:
            return row["id"], None
        return row["id"], encode_embedding(vec)


def _save_embedding(passage_id: str, blob: bytes) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE passages SET embedding=? WHERE id=?",
            (blob, passage_id),
        )
        conn.commit()
    finally:
        conn.close()


async def main() -> None:
    init_db()

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, text_body
               FROM passages
               WHERE text_type = 'long_reading'
                 AND text_body != ''
                 AND embedding IS NULL
               ORDER BY university, year"""
        ).fetchall()
        targets = [dict(r) for r in rows]
    finally:
        conn.close()

    if not targets:
        print("embedding付与対象のパッセージがありません")
        return

    print(f"{len(targets)}件のパッセージにembeddingを付与します\n")

    # Tier 1: 2,000 RPM / 8M TPM
    # 並行5 + 0.1秒スリープ = 最大50 RPM（制限の2.5%）→ 請求は発生しない（無料枠200M tokens内）
    semaphore = asyncio.Semaphore(5)
    tasks = [process_passage(row, semaphore) for row in targets]

    completed = 0
    errors = 0
    for coro in asyncio.as_completed(tasks):
        try:
            passage_id, blob = await coro
            if blob is None:
                errors += 1
                print(f"  {passage_id}: スキップ（テキストなし or APIキー未設定）")
            else:
                _save_embedding(passage_id, blob)
                completed += 1
                print(f"  {passage_id}: OK ({len(blob) // 4}次元)")
        except Exception as e:
            errors += 1
            print(f"  エラー: {e}")

    print(f"\n完了: {completed}件付与（エラー {errors}件）")


if __name__ == "__main__":
    asyncio.run(main())
