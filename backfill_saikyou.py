"""既存DBにsaikyou_coverage/saikyou_profileを一括追加するスクリプト。

Claude API呼び出し不要。ローカル処理のみ。

使い方:
    cd exam-analyzer
    uv run python backfill_saikyou.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db import get_connection, init_db
from app.vocab_analyzer import (
    _calc_wordbook_profile,
    _load_junior_high,
    _load_saikyou,
    tokenize_and_lemmatize,
)


def main() -> None:
    init_db()

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, text_body FROM passages
            WHERE text_type = 'long_reading'
              AND text_body IS NOT NULL AND text_body != ''
              AND (saikyou_coverage IS NULL)"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("全対象パッセージにsaikyou_coverageが設定済みです")
        return

    print(f"{len(rows)}件のパッセージにsaikyou_coverageを追加します\n")

    junior_high = _load_junior_high()
    saikyou = _load_saikyou()
    updated = 0

    for row in rows:
        passage_id = row["id"]
        text_body = row["text_body"]

        lemmas = tokenize_and_lemmatize(text_body)
        if not lemmas:
            print(f"  {passage_id} [スキップ: トークンなし]")
            continue

        result = _calc_wordbook_profile(lemmas, saikyou, base_words=junior_high)

        conn = get_connection()
        try:
            conn.execute(
                """UPDATE passages SET
                    saikyou_coverage = ?,
                    saikyou_profile = ?
                WHERE id = ?""",
                (
                    result["coverage"],
                    json.dumps(result["profile"]),
                    passage_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        updated += 1
        cov = result["coverage"]
        print(f"  {passage_id} coverage={cov:.4f}" if cov else f"  {passage_id} [カバー率なし]")

    print(f"\n完了: {updated}件更新")


if __name__ == "__main__":
    main()
