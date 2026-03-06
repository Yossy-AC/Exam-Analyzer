"""既存DBにtext_bodyと語彙分析結果を一括追加するスクリプト。

Claude API呼び出し不要。ローカル処理のみ。

使い方:
    cd exam-analyzer
    uv run python backfill_text.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import DB_PATH, INPUT_MD_DIR
from app.db import get_connection, init_db
from app.parser import parse_md
from app.vocab_analyzer import analyze_vocab


def main() -> None:
    init_db()

    conn = get_connection()
    try:
        # text_bodyが空のパッセージを取得
        rows = conn.execute(
            "SELECT id, text_type FROM passages WHERE text_body = '' OR text_body IS NULL"
        ).fetchall()
        empty_ids = {r["id"]: r["text_type"] for r in rows}
    finally:
        conn.close()

    if not empty_ids:
        print("全パッセージにtext_bodyが設定済みです")
        return

    print(f"{len(empty_ids)}件のパッセージにtext_bodyを追加します\n")

    # MDファイルから再パースしてtext_bodyを取得
    md_files = sorted(Path(INPUT_MD_DIR).glob("*.md"))
    if not md_files:
        print(f"MDファイルが見つかりません: {INPUT_MD_DIR}")
        return

    updated = 0
    analyzed = 0

    for filepath in md_files:
        content = filepath.read_text(encoding="utf-8")
        passages = parse_md(content, filepath.name)

        for pq in passages:
            if pq.passage_id not in empty_ids:
                continue

            text_body = pq.text_section
            text_type = empty_ids[pq.passage_id]

            # 語彙分析（long_readingのみ）
            vocab = {}
            if text_type == "long_reading" and text_body:
                vocab = analyze_vocab(text_body)
                analyzed += 1

            conn = get_connection()
            try:
                conn.execute(
                    """UPDATE passages SET
                        text_body = ?,
                        avg_sentence_length = ?,
                        cefr_j_beyond_rate = ?,
                        cefr_j_profile = ?,
                        ngsl_uncovered_rate = ?,
                        nawl_rate = ?,
                        target1900_coverage = ?,
                        target1900_profile = ?,
                        leap_coverage = ?,
                        leap_profile = ?
                    WHERE id = ?""",
                    (
                        text_body,
                        vocab.get("avg_sentence_length"),
                        vocab.get("cefr_j_beyond_rate"),
                        json.dumps(vocab.get("cefr_j_profile", {})),
                        vocab.get("ngsl_uncovered_rate"),
                        vocab.get("nawl_rate"),
                        vocab.get("target1900_coverage"),
                        json.dumps(vocab.get("target1900_profile", {})),
                        vocab.get("leap_coverage"),
                        json.dumps(vocab.get("leap_profile", {})),
                        pq.passage_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            updated += 1
            print(f"  {pq.passage_id} ({text_type})"
                  + (f" [語彙分析済]" if vocab else ""))

    print(f"\n完了: {updated}件更新（うち{analyzed}件を語彙分析）")


if __name__ == "__main__":
    main()
