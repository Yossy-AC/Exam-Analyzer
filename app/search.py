"""類似長文検索。

embeddingがある場合はコサイン類似度、ない場合はCEFRスコア・語彙指標の加重距離で類似度を計算する。
"""

from __future__ import annotations

import json
import logging

from app.db import get_connection
from app.embedding import cosine_similarity, decode_embedding

logger = logging.getLogger(__name__)


_CEFR_LEVELS = [(1.0, "A2"), (2.0, "B1"), (3.0, "B2"), (3.5, "C1"), (4.0, "C2")]


def cefr_display(score, level=None) -> str:
    """CEFRスコアを表示用文字列に変換する。例: 2.5 → 'B1~B2'。"""
    if score is None:
        return level or ""
    score = float(score)
    for val, name in _CEFR_LEVELS:
        if abs(score - val) < 0.01:
            return name
    lower = upper = None
    for val, name in _CEFR_LEVELS:
        if val < score:
            lower = name
        elif val > score and upper is None:
            upper = name
    if lower and upper:
        return f"{lower}~{upper}"
    return level or ""


def _safe_float(val) -> float | None:
    """DBから取得した値をfloatに変換する。NULLはNoneを返す。"""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _compute_similarity(source: dict, candidate: dict) -> float:
    """2パッセージ間の類似度（0〜1）を計算する。

    embeddingが両方にある場合: コサイン類似度を使用。
    ない場合: 特徴量の加重距離（後方互換）。
    """
    src_blob = source.get("embedding")
    cand_blob = candidate.get("embedding")

    if src_blob and cand_blob:
        # embedding ベースのコサイン類似度
        logger.debug("embedding使用: %s vs %s", source.get("id"), candidate.get("id"))
        src_vec = decode_embedding(bytes(src_blob))
        cand_vec = decode_embedding(bytes(cand_blob))
        sim = cosine_similarity(src_vec, cand_vec)
        # ジャンル一致ボーナス（+0.02、embedding時は控えめに）
        if (source.get("genre_main") and candidate.get("genre_main")
                and source["genre_main"] == candidate["genre_main"]):
            sim = min(1.0, sim + 0.02)
        return round(sim, 4)

    # fallback: 特徴量ベース
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
        cv = _safe_float(candidate.get(field))
        if sv is None or cv is None:
            continue
        dist = min(abs(sv - cv) / max_diff, 1.0)
        weighted_dist += weight * dist
        total_weight += weight

    if total_weight == 0:
        return 0.0

    base_similarity = 1.0 - (weighted_dist / total_weight)

    if (source.get("genre_main") and candidate.get("genre_main")
            and source["genre_main"] == candidate["genre_main"]):
        base_similarity = min(1.0, base_similarity + 0.05)

    return round(base_similarity, 4)


def _extract_coverage_at_milestone(profile_json: str | None, milestone: int) -> float | None:
    """プロファイルJSONから指定マイルストーンのカバー率を取得する。"""
    if not profile_json:
        return None
    try:
        profile = json.loads(profile_json)
        val = profile.get(str(milestone))
        return float(val) if val is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def find_similar(
    source_id: str,
    top_k: int = 10,
    cefr_min: float | None = None,
    cefr_max: float | None = None,
    genre_main: str | None = None,
    exclude_same_university: bool = True,
    wordbook: str | None = None,
    wordbook_milestone: int | None = None,
    vocab_coverage_min: float | None = None,
    university_class: list | None = None,
    region: list | None = None,
) -> tuple[dict | None, list[dict]]:
    """指定パッセージに類似した長文を検索する。

    Returns:
        (source_passage, similar_passages_sorted_by_similarity)
        source_passageが見つからない場合は (None, [])
    """
    conn = get_connection()
    try:
        source_row = conn.execute(
            """SELECT id, university, year, faculty, question_number, passage_index,
                      text_type, text_style, word_count, genre_main, genre_sub, theme,
                      cefr_score, cefr_level, cefr_confidence,
                      avg_sentence_length, cefr_j_beyond_rate,
                      ngsl_uncovered_rate, nawl_rate,
                      target1900_coverage, leap_coverage,
                      target1900_profile, leap_profile, embedding
               FROM passages WHERE id = ?""",
            (source_id,),
        ).fetchone()

        if source_row is None:
            return None, []

        source = dict(source_row)

        # 候補: long_reading かつ text_body あり、自分自身を除く
        conditions = [
            "text_type = 'long_reading'",
            "text_body != ''",
            "id != ?",
        ]
        params: list = [source_id]

        if exclude_same_university:
            conditions.append("university != ?")
            params.append(source["university"])

        if cefr_min is not None:
            conditions.append("(cefr_score IS NULL OR cefr_score >= ?)")
            params.append(cefr_min)
        if cefr_max is not None:
            conditions.append("(cefr_score IS NULL OR cefr_score <= ?)")
            params.append(cefr_max)
        if genre_main:
            conditions.append("genre_main = ?")
            params.append(genre_main)

        if university_class or region:
            uc_list = ["" if v == "未設定" else v for v in (university_class or [])]
            rgn_list = ["" if v == "未設定" else v for v in (region or [])]
            sub_parts: list[str] = []
            sub_params: list = []
            if uc_list:
                ph = ",".join("?" * len(uc_list))
                sub_parts.append(f"university_class IN ({ph})")
                sub_params.extend(uc_list)
            if rgn_list:
                ph = ",".join("?" * len(rgn_list))
                sub_parts.append(f"region IN ({ph})")
                sub_params.extend(rgn_list)
            conditions.append(
                f"university IN (SELECT name FROM universities WHERE {' AND '.join(sub_parts)})"
            )
            params.extend(sub_params)

        where = " AND ".join(conditions)
        candidates = conn.execute(
            f"""SELECT id, university, year, question_number, passage_index,
                       text_style, word_count, genre_main, genre_sub, theme,
                       cefr_score, cefr_level, cefr_confidence,
                       avg_sentence_length, cefr_j_beyond_rate,
                       ngsl_uncovered_rate, nawl_rate,
                       target1900_coverage, leap_coverage,
                       target1900_profile, leap_profile, embedding
                FROM passages WHERE {where}""",
            params,
        ).fetchall()
    finally:
        conn.close()

    # wordbook に応じたプロファイルキーを決定
    profile_key = None
    if wordbook == "target1900":
        profile_key = "target1900_profile"
    elif wordbook == "leap":
        profile_key = "leap_profile"

    results = []
    for row in candidates:
        cand = dict(row)
        sim = _compute_similarity(source, cand)
        cand["similarity"] = sim
        cand["cefr_display"] = cefr_display(cand.get("cefr_score"), cand.get("cefr_level"))

        # カバー率抽出
        if profile_key and wordbook_milestone:
            cand["vocab_coverage"] = _extract_coverage_at_milestone(
                cand.get(profile_key), wordbook_milestone)
        else:
            cand["vocab_coverage"] = None

        # カバー率フィルタ
        if vocab_coverage_min is not None and profile_key and wordbook_milestone:
            cov = cand["vocab_coverage"]
            if cov is None or cov < vocab_coverage_min:
                continue

        cand.pop("embedding", None)
        cand.pop("target1900_profile", None)
        cand.pop("leap_profile", None)
        results.append(cand)

    results.sort(key=lambda x: x["similarity"], reverse=True)

    # sourceにもカバー率を付与
    if profile_key and wordbook_milestone:
        source["vocab_coverage"] = _extract_coverage_at_milestone(
            source.get(profile_key), wordbook_milestone)
    else:
        source["vocab_coverage"] = None

    source.pop("embedding", None)
    source.pop("target1900_profile", None)
    source.pop("leap_profile", None)
    source["cefr_display"] = cefr_display(source.get("cefr_score"), source.get("cefr_level"))

    return source, results[:top_k]
