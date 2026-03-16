"""X-rayトークナイザーのテスト。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.xray_tokenizer import (
    MAX_TEXT_LENGTH,
    _CONTRACTION_PARTS,
    _preprocess_text,
    _split_paragraphs,
    _strip_suffix,
    _categorize_token,
    extract_saikyou_words,
    tokenize_for_xray,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_wordlists():
    """全語彙リストが空の状態。"""
    return {
        "glossed_words": set(),
        "junior_high": set(),
        "saikyou_set": set(),
        "ngsl": set(),
        "target1900_idx": {},
        "leap_idx": {},
        "target1900_progress": 0,
        "leap_progress": 0,
    }


def _make_token(text, pos_="NOUN", ent_type_="", like_num=False, lemma_=None,
                is_punct=False, is_space=False):
    """spaCy Token のモックを作成する。"""
    tok = MagicMock()
    tok.text = text
    tok.pos_ = pos_
    tok.ent_type_ = ent_type_
    tok.like_num = like_num
    tok.lemma_ = lemma_ if lemma_ is not None else text.lower()
    tok.is_punct = is_punct
    tok.is_space = is_space
    return tok


# ---------------------------------------------------------------------------
# _categorize_token
# ---------------------------------------------------------------------------

class TestCategorizeToken:
    def test_punctuation_token(self, empty_wordlists):
        tok = _make_token(".", is_punct=True)
        assert _categorize_token(tok, ".", **empty_wordlists) == "punctuation"

    def test_space_token(self, empty_wordlists):
        tok = _make_token(" ", is_space=True)
        assert _categorize_token(tok, " ", **empty_wordlists) == "punctuation"

    def test_contraction_s(self, empty_wordlists):
        tok = _make_token("'s")
        assert _categorize_token(tok, "'s", **empty_wordlists) == "punctuation"

    def test_contraction_nt(self, empty_wordlists):
        tok = _make_token("n't")
        assert _categorize_token(tok, "n't", **empty_wordlists) == "punctuation"

    def test_contraction_re(self, empty_wordlists):
        tok = _make_token("'re")
        assert _categorize_token(tok, "'re", **empty_wordlists) == "punctuation"

    def test_contraction_ve(self, empty_wordlists):
        tok = _make_token("'ve")
        assert _categorize_token(tok, "'ve", **empty_wordlists) == "punctuation"

    def test_contraction_ll(self, empty_wordlists):
        tok = _make_token("'ll")
        assert _categorize_token(tok, "'ll", **empty_wordlists) == "punctuation"

    def test_contraction_d(self, empty_wordlists):
        tok = _make_token("'d")
        assert _categorize_token(tok, "'d", **empty_wordlists) == "punctuation"

    def test_contraction_m(self, empty_wordlists):
        tok = _make_token("'m")
        assert _categorize_token(tok, "'m", **empty_wordlists) == "punctuation"

    def test_contraction_curly_quote(self, empty_wordlists):
        """カーリー引用符の縮約形も punctuation になる。"""
        tok = _make_token("\u2019s")
        assert _categorize_token(tok, "\u2019s", **empty_wordlists) == "punctuation"

    def test_junior_high(self, empty_wordlists):
        wl = {**empty_wordlists, "junior_high": {"go"}}
        tok = _make_token("go")
        assert _categorize_token(tok, "go", **wl) == "junior_high"

    def test_wordbook_mastered_target1900(self, empty_wordlists):
        wl = {**empty_wordlists,
              "target1900_idx": {"evolve": 100},
              "target1900_progress": 200}
        tok = _make_token("evolve")
        assert _categorize_token(tok, "evolve", **wl) == "wordbook_mastered"

    def test_wordbook_mastered_leap(self, empty_wordlists):
        wl = {**empty_wordlists,
              "leap_idx": {"evolve": 50},
              "leap_progress": 100}
        tok = _make_token("evolve")
        assert _categorize_token(tok, "evolve", **wl) == "wordbook_mastered"

    def test_wordbook_not_mastered_beyond_progress(self, empty_wordlists):
        """進捗範囲外の単語帳語は mastered にならない。"""
        wl = {**empty_wordlists,
              "target1900_idx": {"evolve": 500},
              "target1900_progress": 100}
        tok = _make_token("evolve")
        assert _categorize_token(tok, "evolve", **wl) != "wordbook_mastered"

    def test_saikyou(self, empty_wordlists):
        wl = {**empty_wordlists, "saikyou_set": {"elaborate"}}
        tok = _make_token("elaborate")
        assert _categorize_token(tok, "elaborate", **wl) == "saikyou"

    def test_ngsl(self, empty_wordlists):
        wl = {**empty_wordlists, "ngsl": {"environment"}}
        tok = _make_token("environment")
        assert _categorize_token(tok, "environment", **wl) == "ngsl"

    def test_propn(self, empty_wordlists):
        tok = _make_token("Tokyo", pos_="PROPN")
        assert _categorize_token(tok, "tokyo", **empty_wordlists) == "propn"

    def test_entity_as_propn(self, empty_wordlists):
        tok = _make_token("Japan", ent_type_="GPE")
        assert _categorize_token(tok, "japan", **empty_wordlists) == "propn"

    def test_number_like_num(self, empty_wordlists):
        tok = _make_token("42", pos_="NUM", like_num=True)
        assert _categorize_token(tok, "42", **empty_wordlists) == "number"

    def test_number_pos(self, empty_wordlists):
        tok = _make_token("hundred", pos_="NUM")
        assert _categorize_token(tok, "hundred", **empty_wordlists) == "number"

    def test_glossed(self, empty_wordlists):
        wl = {**empty_wordlists, "glossed_words": {"ubiquitous"}}
        tok = _make_token("ubiquitous")
        assert _categorize_token(tok, "ubiquitous", **wl) == "glossed"

    def test_unknown(self, empty_wordlists):
        tok = _make_token("xyz")
        assert _categorize_token(tok, "xyz", **empty_wordlists) == "unknown"

    def test_priority_junior_high_over_saikyou(self, empty_wordlists):
        """中学語彙は saikyou より優先される。"""
        wl = {**empty_wordlists, "junior_high": {"make"}, "saikyou_set": {"make"}}
        tok = _make_token("make")
        assert _categorize_token(tok, "make", **wl) == "junior_high"


# ---------------------------------------------------------------------------
# 縮約形一覧のカバレッジ
# ---------------------------------------------------------------------------

class TestContractionParts:
    def test_all_standard_contractions_present(self):
        for c in ["'s", "'re", "'ve", "'ll", "'d", "'m", "n't"]:
            assert c in _CONTRACTION_PARTS

    def test_curly_quote_variants(self):
        for c in ["\u2019s", "\u2019re", "\u2019ve", "\u2019ll", "\u2019d", "\u2019m", "n\u2019t"]:
            assert c in _CONTRACTION_PARTS


# ---------------------------------------------------------------------------
# _strip_suffix (派生語フォールバック)
# ---------------------------------------------------------------------------

class TestStripSuffix:
    def test_strip_ly(self):
        assert _strip_suffix("quickly") == "quick"

    def test_strip_ness(self):
        assert _strip_suffix("happiness") == "happi"

    def test_strip_ment(self):
        assert _strip_suffix("government") == "govern"

    def test_strip_ful(self):
        assert _strip_suffix("beautiful") == "beauti"

    def test_strip_less(self):
        assert _strip_suffix("careless") == "care"

    def test_strip_ive(self):
        assert _strip_suffix("creative") == "creat"

    def test_strip_able(self):
        assert _strip_suffix("comfortable") == "comfort"

    def test_strip_ible(self):
        assert _strip_suffix("possible") == "poss"

    def test_too_short_no_strip(self):
        """基本形が短すぎる場合はストリップしない。"""
        assert _strip_suffix("ally") is None

    def test_no_matching_suffix(self):
        assert _strip_suffix("cat") is None

    def test_derivative_fallback_junior_high(self, empty_wordlists):
        """派生語ストリップ後に中学語彙にマッチする。"""
        wl = {**empty_wordlists, "junior_high": {"care"}}
        tok = _make_token("careless")
        assert _categorize_token(tok, "careless", **wl) == "junior_high"

    def test_derivative_fallback_saikyou(self, empty_wordlists):
        wl = {**empty_wordlists, "saikyou_set": {"govern"}}
        tok = _make_token("government")
        assert _categorize_token(tok, "government", **wl) == "saikyou"


# ---------------------------------------------------------------------------
# _preprocess_text (注釈マーカー検出含む)
# ---------------------------------------------------------------------------

class TestPreprocessText:
    def test_annotation_marker_detected(self):
        text = "The ubiquitous*1 nature of smartphone*2 use."
        cleaned, glossed = _preprocess_text(text)
        assert "ubiquitous" in glossed
        assert "smartphone" in glossed
        assert "*1" not in cleaned
        assert "*2" not in cleaned

    def test_vocabulary_section_removed(self):
        text = "Some text here.\n\n## Vocabulary\nword1: meaning1"
        cleaned, _ = _preprocess_text(text)
        assert "word1" not in cleaned
        assert "Some text here" in cleaned

    def test_html_comments_removed(self):
        text = "Hello <!-- this is a comment --> world."
        cleaned, _ = _preprocess_text(text)
        assert "comment" not in cleaned
        assert "Hello" in cleaned

    def test_html_tags_removed(self):
        text = "Hello <b>bold</b> world."
        cleaned, _ = _preprocess_text(text)
        assert "<b>" not in cleaned
        assert "bold" in cleaned

    def test_japanese_lines_removed(self):
        text = "English sentence.\nこれは日本語の行です。\nAnother English line."
        cleaned, _ = _preprocess_text(text)
        assert "日本語" not in cleaned
        assert "English sentence" in cleaned
        assert "Another English line" in cleaned

    def test_blank_marker_unified(self):
        """空欄マーカーが [___] に統一される。"""
        text = "Choose [ (A) ] for the answer [ ] here."
        cleaned, _ = _preprocess_text(text)
        # MD除去後に空欄マーカー統一 → [___]
        assert "[___]" in cleaned
        # 元の (A) は除去されている
        assert "(A)" not in cleaned


# ---------------------------------------------------------------------------
# _split_paragraphs
# ---------------------------------------------------------------------------

class TestSplitParagraphs:
    def test_single_paragraph(self):
        result = _split_paragraphs("Hello world.")
        assert len(result) == 1
        assert result[0] == "Hello world."

    def test_two_paragraphs(self):
        result = _split_paragraphs("Para one.\n\nPara two.")
        assert len(result) == 2
        assert result[0] == "Para one."
        assert result[1] == "Para two."

    def test_empty_string(self):
        assert _split_paragraphs("") == []

    def test_whitespace_only(self):
        assert _split_paragraphs("   \n\n   ") == []

    def test_multiple_blank_lines(self):
        result = _split_paragraphs("A.\n\n\n\nB.")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# extract_saikyou_words
# ---------------------------------------------------------------------------

class TestExtractSaikyouWords:
    def test_returns_sorted_list(self):
        """extract_saikyou_wordsが最強リスト語のソート済みリストを返す。"""
        # 実際の最強リストを使うため、結果は実データ依存
        result = extract_saikyou_words("The environment is important.")
        assert isinstance(result, list)
        # ソート済みであること
        assert result == sorted(result)

    def test_empty_input(self):
        result = extract_saikyou_words("")
        assert result == []


# ---------------------------------------------------------------------------
# tokenize_for_xray
# ---------------------------------------------------------------------------

class TestTokenizeForXray:
    def test_empty_input(self):
        assert tokenize_for_xray("") == []
        assert tokenize_for_xray("   ") == []

    def test_returns_paragraph_list(self):
        result = tokenize_for_xray("Hello world.")
        assert isinstance(result, list)
        assert len(result) >= 1
        # 各段落はトークンリスト
        for para in result:
            assert isinstance(para, list)
            for tok in para:
                assert "text" in tok
                assert "lemma" in tok
                assert "category" in tok

    def test_two_paragraphs(self):
        result = tokenize_for_xray("First paragraph.\n\nSecond paragraph.")
        assert len(result) == 2

    def test_max_text_length_enforced(self):
        """MAX_TEXT_LENGTH超のテキストが切り詰められてもエラーにならない。"""
        long_text = "word " * (MAX_TEXT_LENGTH + 100)
        result = tokenize_for_xray(long_text)
        assert isinstance(result, list)
        # 全トークンのtext結合がMAX_TEXT_LENGTH以下になるはず
        total_chars = sum(
            len(tok["text"]) for para in result for tok in para
        )
        assert total_chars <= MAX_TEXT_LENGTH

    def test_valid_categories_only(self):
        """返されるカテゴリが既知のカテゴリのみ。"""
        valid = {
            "punctuation", "junior_high", "wordbook_mastered", "saikyou",
            "ngsl", "propn", "number", "glossed", "unknown",
        }
        result = tokenize_for_xray("The cat sat on the mat in 2025.")
        for para in result:
            for tok in para:
                assert tok["category"] in valid, f"Unknown category: {tok['category']}"
