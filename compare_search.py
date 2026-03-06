"""embedding搭載前後の類似長文検索結果を比較するスクリプト。

使い方:
    cd exam-analyzer
    uv run python compare_search.py [passage_id]

passage_idを省略すると、DBから最初のlong_readingを自動選択。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Windows コンソールの文字化け対策
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.db import get_connection
from app.embedding import cosine_similarity, decode_embedding


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def sim_embedding(source: dict, cand: dict) -> float:
    """コサイン類似度（embedding使用）"""
    src_blob = source.get("embedding")
    cand_blob = cand.get("embedding")
    if not src_blob or not cand_blob:
        return 0.0
    src_vec = decode_embedding(bytes(src_blob))
    cand_vec = decode_embedding(bytes(cand_blob))
    sim = cosine_similarity(src_vec, cand_vec)
    if source.get("genre_main") == cand.get("genre_main") and source.get("genre_main"):
        sim = min(1.0, sim + 0.02)
    return round(sim, 4)


def sim_feature(source: dict, cand: dict) -> float:
    """特徴量ベース類似度（embedding無視）"""
    METRICS = [
        ("cefr_score",          4.0,   0.50),
        ("avg_sentence_length", 20.0,  0.20),
        ("ngsl_uncovered_rate", 0.30,  0.15),
        ("nawl_rate",           0.15,  0.15),
    ]
    total_weight = 0.0
    weighted_dist = 0.0
    for field, max_diff, weight in METRICS:
        sv = _safe_float(source.get(field))
        cv = _safe_float(cand.get(field))
        if sv is None or cv is None:
            continue
        dist = min(abs(sv - cv) / max_diff, 1.0)
        weighted_dist += weight * dist
        total_weight += weight
    if total_weight == 0:
        return 0.0
    base = 1.0 - (weighted_dist / total_weight)
    if source.get("genre_main") == cand.get("genre_main") and source.get("genre_main"):
        base = min(1.0, base + 0.05)
    return round(base, 4)


def main() -> None:
    conn = get_connection()
    try:
        if len(sys.argv) >= 2:
            passage_id = sys.argv[1]
            source_row = conn.execute(
                """SELECT id, university, year, question_number, passage_index,
                          genre_main, theme, cefr_level, cefr_score,
                          avg_sentence_length, ngsl_uncovered_rate, nawl_rate,
                          word_count, text_body, embedding
                   FROM passages WHERE id = ?""",
                (passage_id,),
            ).fetchone()
            if source_row is None:
                print(f"passage_id '{passage_id}' が見つかりません")
                return
        else:
            source_row = conn.execute(
                """SELECT id, university, year, question_number, passage_index,
                          genre_main, theme, cefr_level, cefr_score,
                          avg_sentence_length, ngsl_uncovered_rate, nawl_rate,
                          word_count, text_body, embedding
                   FROM passages
                   WHERE text_type = 'long_reading' AND text_body != '' AND embedding IS NOT NULL
                   ORDER BY university, year LIMIT 1"""
            ).fetchone()
            if source_row is None:
                print("対象パッセージがありません")
                return

        source = dict(source_row)

        candidates_rows = conn.execute(
            """SELECT id, university, year, question_number, passage_index,
                      genre_main, theme, cefr_level, cefr_score,
                      avg_sentence_length, ngsl_uncovered_rate, nawl_rate,
                      word_count, text_body, embedding
               FROM passages
               WHERE text_type = 'long_reading'
                 AND text_body != ''
                 AND id != ?
                 AND university != ?""",
            (source["id"], source["university"]),
        ).fetchall()
    finally:
        conn.close()

    candidates = [dict(r) for r in candidates_rows]

    # 両方の方法でスコアリング
    emb_results = sorted(candidates, key=lambda c: sim_embedding(source, c), reverse=True)[:10]
    feat_results = sorted(candidates, key=lambda c: sim_feature(source, c), reverse=True)[:10]

    # 表示
    src_preview = (source.get("text_body") or "")[:100].replace("\n", " ")
    print(f"=== 検索元パッセージ ===")
    print(f"ID      : {source['id']}")
    print(f"大学    : {source['university']} {source['year']}")
    print(f"ジャンル: {source.get('genre_main')} / {source.get('theme')}")
    print(f"CEFR    : {source.get('cefr_level')} (score={source.get('cefr_score')})")
    print(f"平均文長: {source.get('avg_sentence_length')}")
    print(f"語数    : {source.get('word_count')}")
    print(f"本文冒頭: {src_preview}")
    print()

    # 横並び比較
    print(f"{'─'*60} embedding（コサイン類似度） {'─'*60}   {'─'*60} 特徴量ベース {'─'*60}")
    header = f"{'順位':<4} {'類似度':<7} {'大学':<18} {'年':<5} {'CEFR':<5} {'ジャンル':<12} {'テーマ':<20}"
    print(f"{header}   {header}")
    print(f"{'─'*80}   {'─'*80}")

    for i, (e, f) in enumerate(zip(emb_results, feat_results), 1):
        e_sim = sim_embedding(source, e)
        f_sim = sim_feature(source, f)

        def fmt(row, sim):
            univ = (row.get('university') or '')[:16]
            genre = (row.get('genre_main') or '')[:10]
            theme = (row.get('theme') or '')[:18]
            return f"{i:<4} {sim:<7.4f} {univ:<18} {row.get('year',''):<5} {row.get('cefr_level',''):<5} {genre:<12} {theme:<20}"

        print(f"{fmt(e, e_sim)}   {fmt(f, f_sim)}")

    print()

    # ランキング差の大きいものを表示
    emb_ids = [r["id"] for r in emb_results]
    feat_ids = [r["id"] for r in feat_results]

    emb_only = [rid for rid in emb_ids if rid not in feat_ids]
    feat_only = [rid for rid in feat_ids if rid not in emb_ids]

    if emb_only:
        print("[+] embeddingで上位に入った（特徴量では上位10外）:")
        for rid in emb_only:
            r = next(c for c in candidates if c["id"] == rid)
            print(f"  {rid}  {r.get('university')} {r.get('year')}  CEFR={r.get('cefr_level')}  {r.get('genre_main')} / {r.get('theme')}")

    if feat_only:
        print("[-] 特徴量で上位に入った（embeddingでは上位10外）:")
        for rid in feat_only:
            r = next(c for c in candidates if c["id"] == rid)
            print(f"  {rid}  {r.get('university')} {r.get('year')}  CEFR={r.get('cefr_level')}  {r.get('genre_main')} / {r.get('theme')}")


if __name__ == "__main__":
    main()
