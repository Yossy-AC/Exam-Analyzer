"""既存DBを削除して全MDファイルを再処理するスクリプト。

使い方:
    cd Exam-Analyzer
    python rebuild_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import DB_PATH, INPUT_MD_DIR
from app.db import get_connection, init_db
from app.parser import parse_md
from app.classifier import classify_passage


def _save_passage(data: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, is_kyutei, is_national, is_private) VALUES (?, 0, 1, 0)",
            (data["university"],),
        )
        conn.execute(
            """INSERT OR IGNORE INTO passages
            (id, university, year, faculty, question_number, passage_index,
             text_type, text_style, word_count,
             source_title, source_author, source_year,
             genre_main, genre_sub, theme,
             has_jp_written, has_en_written, has_summary, comp_type,
             has_jp_translation, has_jp_explanation, has_en_explanation,
             has_jp_summary, has_en_summary,
             has_visual_info, visual_info_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["id"], data["university"], data["year"], data["faculty"],
                data["question_number"], data["passage_index"],
                data["text_type"], data.get("text_style"),
                data.get("word_count"),
                data.get("source_title"), data.get("source_author"),
                data.get("source_year"),
                data["genre_main"], data.get("genre_sub", ""),
                data.get("theme", ""),
                data.get("has_jp_written", False),
                data.get("has_en_written", False),
                data.get("has_summary", False),
                data.get("comp_type", "none"),
                data.get("has_jp_translation", False),
                data.get("has_jp_explanation", False),
                data.get("has_en_explanation", False),
                data.get("has_jp_summary", False),
                data.get("has_en_summary", False),
                data.get("has_visual_info", False),
                data.get("visual_info_type", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def process_file(filepath: Path) -> int:
    content = filepath.read_text(encoding="utf-8")
    passages = parse_md(content, filepath.name)
    if not passages:
        print(f"  スキップ: パッセージなし ({filepath.name})")
        return 0

    count = 0
    for pq in passages:
        try:
            result = await classify_passage(pq)
            _save_passage(result)
            count += 1
            print(f"  ✓ {result['id']}")
        except Exception as e:
            print(f"  ✗ {pq.passage_id}: {e}")
    return count


async def main() -> None:
    db_path = Path(DB_PATH)
    if db_path.exists():
        db_path.unlink()
        print(f"既存DB削除: {db_path}")

    init_db()
    print("DB初期化完了")

    md_files = sorted(Path(INPUT_MD_DIR).glob("*.md"))
    if not md_files:
        print(f"MDファイルが見つかりません: {INPUT_MD_DIR}")
        return

    print(f"\n{len(md_files)}件のMDファイルを処理します...\n")

    total = 0
    for i, filepath in enumerate(md_files, 1):
        print(f"[{i}/{len(md_files)}] {filepath.name}")
        count = await process_file(filepath)
        total += count

    print(f"\n完了: {total}件のパッセージを登録しました")


if __name__ == "__main__":
    asyncio.run(main())
