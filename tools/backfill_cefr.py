"""既存DBのlong_readingパッセージにCEFRスコアを一括付与するスクリプト。

使い方:
    cd exam-analyzer
    uv run python backfill_cefr.py

注意: Claude API呼び出しを伴うため、APIキーが必要。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import estimate_cefr
from app.db import get_connection, init_db


async def process_passage(row: dict, semaphore: asyncio.Semaphore) -> tuple[str, dict | None]:
    """1パッセージのCEFR推定（セマフォ制御）。"""
    async with semaphore:
        await asyncio.sleep(1.0)  # レート制限回避
        vocab = {
            "cefr_j_beyond_rate": row["cefr_j_beyond_rate"],
            "cefr_j_profile": row["cefr_j_profile"],
            "ngsl_uncovered_rate": row["ngsl_uncovered_rate"],
            "nawl_rate": row["nawl_rate"],
            "avg_sentence_length": row["avg_sentence_length"],
        }
        result = await estimate_cefr(
            passage_id=row["id"],
            text_body=row["text_body"],
            university=row["university"],
            year=row["year"],
            text_style=row["text_style"] or "",
            vocab=vocab,
        )
        return row["id"], result


def _save_result(passage_id: str, result: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE passages SET cefr_score=?, cefr_level=?, cefr_confidence=? WHERE id=?",
            (
                result["cefr_score"],
                result["cefr_level"],
                result["cefr_confidence"],
                passage_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def main() -> None:
    init_db()

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, university, year, text_style, text_body,
                      cefr_j_beyond_rate, cefr_j_profile,
                      ngsl_uncovered_rate, nawl_rate, avg_sentence_length
               FROM passages
               WHERE text_type = 'long_reading'
                 AND (cefr_score IS NULL)
                 AND text_body != ''
               ORDER BY university, year"""
        ).fetchall()
        targets = [dict(r) for r in rows]
    finally:
        conn.close()

    if not targets:
        print("推定対象のパッセージがありません")
        return

    print(f"{len(targets)}件のパッセージにCEFRスコアを付与します\n")

    semaphore = asyncio.Semaphore(2)
    tasks = [process_passage(row, semaphore) for row in targets]

    completed = 0
    errors = 0
    for coro in asyncio.as_completed(tasks):
        try:
            passage_id, result = await coro
            _save_result(passage_id, result)
            completed += 1
            score = result["cefr_score"]
            level = result["cefr_level"]
            conf = result["cefr_confidence"]
            print(f"  {passage_id}: {level}（{score}）[{conf}]")
        except Exception as e:
            errors += 1
            print(f"  エラー: {e}")

    print(f"\n完了: {completed}件推定（エラー {errors}件）")


if __name__ == "__main__":
    asyncio.run(main())
