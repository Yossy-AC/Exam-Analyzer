"""語彙分析モジュール: 英文テキストの語彙レベル・構文難易度を計算する。"""

from __future__ import annotations

import csv
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from nltk.corpus import wordnet
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

WORDLISTS_DIR = Path(__file__).parent / "wordlists"

_lemmatizer = WordNetLemmatizer()


@lru_cache(maxsize=1)
def _load_ngsl() -> set[str]:
    path = WORDLISTS_DIR / "ngsl.txt"
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


@lru_cache(maxsize=1)
def _load_nawl() -> set[str]:
    path = WORDLISTS_DIR / "nawl.txt"
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


@lru_cache(maxsize=1)
def _load_cefr_j() -> dict[str, str]:
    """CEFR-J語彙リストを読み込む。{word: level} の辞書を返す。"""
    path = WORDLISTS_DIR / "cefr_j.csv"
    result: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["word"].strip().lower()] = row["level"]
    return result


@lru_cache(maxsize=1)
def _load_junior_high() -> set[str]:
    """小中学校語彙リストをセットで返す。"""
    path = WORDLISTS_DIR / "junior_high.txt"
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


@lru_cache(maxsize=1)
def _load_target1900() -> list[str]:
    """ターゲット1900の見出し語を順序付きリストで返す。"""
    path = WORDLISTS_DIR / "target1900.txt"
    return [line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


@lru_cache(maxsize=1)
def _load_leap() -> list[str]:
    """LEAPの見出し語を順序付きリストで返す。"""
    path = WORDLISTS_DIR / "leap.txt"
    return [line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


@lru_cache(maxsize=1)
def _load_saikyou() -> list[str]:
    """最強単語リストの見出し語を順序付きリストで返す。"""
    path = WORDLISTS_DIR / "saikyou.txt"
    return [line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def _calc_wordbook_profile(
    lemmas: list[str], wordlist: list[str], step: int = 100,
    base_words: set[str] | None = None,
) -> dict:
    """単語帳の100語刻みカバー率プロファイルを計算する。

    Args:
        base_words: 基本語彙セット（小中学語彙など）。指定時は最初からカバー済みとして加算。

    Returns:
        {
            "coverage": float,  # 全体カバー率（base_words + 単語帳全体）
            "profile": {"100": float, "200": float, ...}  # 累積カバー率
        }
    """
    if not wordlist or not lemmas:
        return {"coverage": None, "profile": {}}

    total = len(lemmas)
    lemma_set = set(lemmas)

    # base_wordsがある場合、最初からカバー済みとして含める
    cumulative_words: set[str] = set()
    if base_words:
        cumulative_words = {w for w in base_words if w in lemma_set}

    # 各単語帳エントリが本文に出現するか（複数語フレーズも対応）
    profile: dict[str, float] = {}
    for i, word in enumerate(wordlist, 1):
        parts = word.split()
        for part in parts:
            if part in lemma_set:
                cumulative_words.add(part)
        if i % step == 0 or i == len(wordlist):
            covered = sum(1 for lemma in lemmas if lemma in cumulative_words)
            profile[str(i)] = round(covered / total, 4)

    # 全体カバー率（base_words + 単語帳全体）
    all_words = set(cumulative_words)
    for word in wordlist:
        for part in word.split():
            all_words.add(part)
    all_covered = sum(1 for lemma in lemmas if lemma in all_words)
    coverage = round(all_covered / total, 4)

    return {"coverage": coverage, "profile": profile}


def _is_english_word(token: str) -> bool:
    """英単語かどうかを判定する（数字・記号・HTMLタグ等を除外）。"""
    return bool(re.match(r"^[a-zA-Z]{2,}$", token))


def _lemmatize(word: str) -> str:
    """単語をレンマ化する。名詞→動詞の順で試行。"""
    w = word.lower()
    # 名詞としてレンマ化
    lemma_n = _lemmatizer.lemmatize(w, wordnet.NOUN)
    # 動詞としてレンマ化
    lemma_v = _lemmatizer.lemmatize(w, wordnet.VERB)
    # 形容詞としてレンマ化
    lemma_a = _lemmatizer.lemmatize(w, wordnet.ADJ)
    # 最も短い結果を返す（通常レンマ形が最短）
    return min([lemma_n, lemma_v, lemma_a], key=len)


def tokenize_and_lemmatize(text: str) -> list[str]:
    """テキストをトークン化し、英単語のみレンマ化して返す。"""
    # HTMLタグ・マークダウン記法を除去
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"<!--.*?-->", " ", clean)
    clean = re.sub(r"\*+", " ", clean)
    clean = re.sub(r"_+", " ", clean)
    # 脚注参照（\*1 等）を除去
    clean = re.sub(r"\\\*\d+", " ", clean)

    tokens = word_tokenize(clean)
    return [_lemmatize(t) for t in tokens if _is_english_word(t)]


def calc_avg_sentence_length(text: str) -> float | None:
    """平均文長（語数/文数）を計算する。"""
    # HTMLタグ・コメント除去
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"<!--.*?-->", " ", clean)

    # 文末記号で分割
    sentences = re.split(r"[.!?]+", clean)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return None

    total_words = 0
    valid_sentences = 0
    for sent in sentences:
        words = [w for w in sent.split() if re.match(r"[a-zA-Z]", w)]
        if words:
            total_words += len(words)
            valid_sentences += 1

    return round(total_words / valid_sentences, 1) if valid_sentences else None


def analyze_vocab(text: str) -> dict:
    """テキストの語彙分析を実行し、全指標を返す。

    Returns:
        {
            "avg_sentence_length": float,
            "cefr_j_beyond_rate": float,
            "cefr_j_profile": {"A1": float, ...},
            "ngsl_uncovered_rate": float,
            "nawl_rate": float,
            "target1900_coverage": float,
            "target1900_profile": {"100": float, "200": float, ...},
            "leap_coverage": float,
            "leap_profile": {"100": float, "200": float, ...},
        }
    """
    lemmas = tokenize_and_lemmatize(text)
    if not lemmas:
        return {
            "avg_sentence_length": None,
            "cefr_j_beyond_rate": None,
            "cefr_j_profile": {},
            "ngsl_uncovered_rate": None,
            "nawl_rate": None,
            "target1900_coverage": None,
            "target1900_profile": {},
            "leap_coverage": None,
            "leap_profile": {},
            "saikyou_coverage": None,
            "saikyou_profile": {},
        }

    total = len(lemmas)

    # CEFR-J分析
    cefr_j = _load_cefr_j()
    level_counts: Counter[str] = Counter()
    for lemma in lemmas:
        level = cefr_j.get(lemma, "beyond")
        level_counts[level] += 1

    cefr_j_profile = {}
    for lv in ("A1", "A2", "B1", "B2", "beyond"):
        cefr_j_profile[lv] = round(level_counts[lv] / total, 4)
    cefr_j_beyond_rate = cefr_j_profile["beyond"]

    # NGSL未カバー率
    ngsl = _load_ngsl()
    ngsl_uncovered = sum(1 for lemma in lemmas if lemma not in ngsl)
    ngsl_uncovered_rate = round(ngsl_uncovered / total, 4)

    # NAWL率
    nawl = _load_nawl()
    nawl_count = sum(1 for lemma in lemmas if lemma in nawl)
    nawl_rate = round(nawl_count / total, 4)

    # ターゲット1900・LEAPプロファイル（小中学語彙をベースに加算）
    junior_high = _load_junior_high()
    t1900_result = _calc_wordbook_profile(lemmas, _load_target1900(), base_words=junior_high)
    leap_result = _calc_wordbook_profile(lemmas, _load_leap(), base_words=junior_high)
    saikyou_result = _calc_wordbook_profile(lemmas, _load_saikyou(), base_words=junior_high)

    return {
        "avg_sentence_length": calc_avg_sentence_length(text),
        "cefr_j_beyond_rate": cefr_j_beyond_rate,
        "cefr_j_profile": cefr_j_profile,
        "ngsl_uncovered_rate": ngsl_uncovered_rate,
        "nawl_rate": nawl_rate,
        "target1900_coverage": t1900_result["coverage"],
        "target1900_profile": t1900_result["profile"],
        "leap_coverage": leap_result["coverage"],
        "leap_profile": leap_result["profile"],
        "saikyou_coverage": saikyou_result["coverage"],
        "saikyou_profile": saikyou_result["profile"],
    }
