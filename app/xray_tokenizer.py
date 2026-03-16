"""X-ray用トークナイザー: spaCyベースでテキストをトークン化し、語彙カテゴリを付与する。"""

from __future__ import annotations

import re
from functools import lru_cache

import spacy
from spacy.tokens import Token

from app.vocab_analyzer import (
    _load_junior_high,
    _load_leap,
    _load_ngsl,
    _load_saikyou,
    _load_target1900,
)

# 縮約形の後半部分（spaCyが分割した結果）
_CONTRACTION_PARTS = {"'s", "'re", "'ve", "'ll", "'d", "'m", "n't",
                       "'s", "\u2019s", "\u2019re", "\u2019ve", "\u2019ll", "\u2019d", "\u2019m", "n\u2019t"}

# 派生語ストリッピング対象の接尾辞（長い順にソート）
_DERIVATIVE_SUFFIXES = sorted(
    ["ly", "ness", "ment", "ful", "less", "ive", "al", "er", "ist", "ory", "able", "ible"],
    key=len, reverse=True,
)

MAX_TEXT_LENGTH = 10_000


@lru_cache(maxsize=1)
def _get_nlp():
    """spaCyモデルをロードする（初回のみ）。"""
    return spacy.load("en_core_web_sm", disable=["parser"])


@lru_cache(maxsize=1)
def _build_target1900_index() -> dict[str, int]:
    """target1900の見出し語 → インデックス(1-based)のマップ。"""
    return {word: i + 1 for i, word in enumerate(_load_target1900())}


@lru_cache(maxsize=1)
def _build_leap_index() -> dict[str, int]:
    """LEAPの見出し語 → インデックス(1-based)のマップ。"""
    return {word: i + 1 for i, word in enumerate(_load_leap())}


def _preprocess_text(text: str) -> tuple[str, set[str]]:
    """テキストを前処理し、クリーンなテキストと注釈付き語のセットを返す。

    Returns:
        (cleaned_text, glossed_words)
    """
    # ## Vocabulary セクション以降を除去
    text = re.split(r"^##\s*Vocabulary", text, flags=re.MULTILINE)[0]

    # HTMLコメント除去
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)

    # HTMLタグ除去（中身は保持）
    text = re.sub(r"<[^>]+>", " ", text)

    # 注釈マーカー検出: word*1, word*2 など
    glossed_words: set[str] = set()
    for match in re.finditer(r"(\w+)\*(\d+)", text):
        glossed_words.add(match.group(1).lower())

    # 注釈マーカー除去
    text = re.sub(r"\*\d+", " ", text)

    # マークダウン記法除去（空欄マーカー統一より先に実行）
    text = re.sub(r"\*+", " ", text)
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"#+\s", " ", text)

    # 空欄マーカー統一（MD除去後に実行 — _ が先に消されるため）
    text = re.sub(r"\[\s*\([A-Za-z0-9]+\)\s*\]", "[___]", text)
    text = re.sub(r"\[\s+\]", "[___]", text)
    text = re.sub(r"\[\s*\]", "[___]", text)

    # 日本語行除去（日本語文字比率 > 30%の行）
    lines = text.split("\n")
    filtered_lines = []
    for line in lines:
        if not line.strip():
            filtered_lines.append(line)
            continue
        jp_chars = len(re.findall(r"[\u3000-\u9fff\uff00-\uffef]", line))
        total_chars = len(line.strip())
        if total_chars > 0 and jp_chars / total_chars > 0.3:
            continue
        filtered_lines.append(line)

    return "\n".join(filtered_lines), glossed_words


def _split_paragraphs(text: str) -> list[str]:
    """テキストを段落に分割する。"""
    # 空行で分割
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _strip_suffix(word: str) -> str | None:
    """派生語の接尾辞をストリップし、基本形の候補を返す。"""
    for suffix in _DERIVATIVE_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return None


def _categorize_token(
    token: Token,
    lemma: str,
    glossed_words: set[str],
    junior_high: set[str],
    saikyou_set: set[str],
    ngsl: set[str],
    target1900_idx: dict[str, int],
    leap_idx: dict[str, int],
    target1900_progress: int,
    leap_progress: int,
) -> str:
    """トークンのカテゴリを優先順位に従い決定する。"""
    text_lower = token.text.lower()

    # 0: 句読点・スペース・縮約形
    if token.is_punct or token.is_space:
        return "punctuation"
    if text_lower in _CONTRACTION_PARTS:
        return "punctuation"

    # 1: 中学語彙
    if lemma in junior_high:
        return "junior_high"

    # 2: 単語帳既習（進捗範囲内）
    t1900_pos = target1900_idx.get(lemma)
    leap_pos = leap_idx.get(lemma)
    if (t1900_pos is not None and t1900_pos <= target1900_progress) or \
       (leap_pos is not None and leap_pos <= leap_progress):
        return "wordbook_mastered"

    # 3: 最強リスト
    if lemma in saikyou_set:
        return "saikyou"

    # 4: NGSL
    if lemma in ngsl:
        return "ngsl"

    # 5: 固有名詞
    if token.pos_ == "PROPN" or token.ent_type_:
        return "propn"

    # 6: 数字
    if token.like_num or token.pos_ == "NUM":
        return "number"

    # 7: 注釈付き語
    if text_lower in glossed_words or lemma in glossed_words:
        return "glossed"

    # 8: 派生語フォールバック
    base = _strip_suffix(lemma)
    if base:
        if base in junior_high:
            return "junior_high"
        if (target1900_idx.get(base, 99999) <= target1900_progress) or \
           (leap_idx.get(base, 99999) <= leap_progress):
            return "wordbook_mastered"
        if base in saikyou_set:
            return "saikyou"
        if base in ngsl:
            return "ngsl"

    return "unknown"


def tokenize_for_xray(
    text: str,
    target1900_progress: int = 0,
    leap_progress: int = 0,
) -> list[list[dict]]:
    """テキストをX-ray用にトークナイズし、語彙カテゴリ付きのトークン配列を返す。

    Args:
        text: 分析対象の英文テキスト
        target1900_progress: ターゲット1900の自己申告進捗（0-1900）
        leap_progress: LEAPの自己申告進捗（0-2300）

    Returns:
        段落単位のトークン配列。各トークンは {"text", "lemma", "category"} の辞書。
    """
    if not text or not text.strip():
        return []

    # テキスト長制限
    text = text[:MAX_TEXT_LENGTH]

    # 前処理
    cleaned, glossed_words = _preprocess_text(text)
    paragraphs = _split_paragraphs(cleaned)

    if not paragraphs:
        return []

    # ワードリストロード
    junior_high = _load_junior_high()
    saikyou_list = _load_saikyou()
    saikyou_set = set(saikyou_list)
    ngsl = _load_ngsl()
    target1900_idx = _build_target1900_index()
    leap_idx = _build_leap_index()

    nlp = _get_nlp()
    result: list[list[dict]] = []

    for para_text in paragraphs:
        doc = nlp(para_text)
        tokens: list[dict] = []
        for token in doc:
            lemma = token.lemma_.lower()
            category = _categorize_token(
                token, lemma, glossed_words,
                junior_high, saikyou_set, ngsl,
                target1900_idx, leap_idx,
                target1900_progress, leap_progress,
            )
            tokens.append({
                "text": token.text,
                "lemma": lemma,
                "category": category,
            })
        result.append(tokens)

    return result


def extract_saikyou_words(text: str) -> list[str]:
    """テキストに出現する最強リスト語のlemmaセットを返す（バックフィル用）。

    NLTKベースのtokenize_and_lemmatizeを使用（既存vocab_analyzerと一貫性保持）。
    """
    from app.vocab_analyzer import tokenize_and_lemmatize

    saikyou_set = set(_load_saikyou())
    lemmas = tokenize_and_lemmatize(text)
    found = sorted(set(lemma for lemma in lemmas if lemma in saikyou_set))
    return found
