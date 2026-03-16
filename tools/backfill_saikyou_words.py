"""既存DBにsaikyou_words（各長文に出現する最強リスト語のセット）を一括追加するスクリプト。

API呼び出し不要。ローカル処理のみ。

使い方:
    cd exam-analyzer
    uv run python backfill_saikyou_words.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection, init_db
from app.xray_tokenizer import extract_saikyou_words


def main() -> None:
    init_db()

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, text_body FROM passages
            WHERE text_type = 'long_reading'
              AND text_body IS NOT NULL AND text_body != ''
              AND (saikyou_words IS NULL OR saikyou_words = '')"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("全対象パッセージにsaikyou_wordsが設定済みです")
        return

    print(f"{len(rows)}件のパッセージにsaikyou_wordsを追加します\n")

    updated = 0

    for row in rows:
        passage_id = row["id"]
        text_body = row["text_body"]

        words = extract_saikyou_words(text_body)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE passages SET saikyou_words = ? WHERE id = ?",
                (json.dumps(words), passage_id),
            )
            conn.commit()
        finally:
            conn.close()

        updated += 1
        print(f"  {passage_id} [{len(words)}語]")

    print(f"\n完了: {updated}件更新")


if __name__ == "__main__":
    main()
