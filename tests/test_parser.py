"""MDパーサーのテスト。実データを使用して各大学のパターンを検証する。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parser import (
    detect_ab_split,
    extract_university_from_filename,
    normalize_question_number,
    normalize_year,
    parse_frontmatter,
    parse_md,
    split_questions,
)

INPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "input_md"


class TestUtilities:
    def test_extract_university_from_filename(self):
        assert extract_university_from_filename("2025東京大_問題.md") == "東京大"
        assert extract_university_from_filename("2025大阪大（外国語以外）_問題.md") == "大阪大（外国語以外）"
        assert extract_university_from_filename("2025大阪大（外国語）_問題.md") == "大阪大（外国語）"
        assert extract_university_from_filename("2025東京都立大（理系）_問題.md") == "東京都立大（理系）"
        assert extract_university_from_filename("2025京都大_問題.md") == "京都大"

    def test_normalize_year_integer(self):
        assert normalize_year(2025) == 2025

    def test_normalize_year_reiwa(self):
        assert normalize_year("令和7年度") == 2025

    def test_normalize_year_string(self):
        assert normalize_year("2025年度") == 2025

    def test_normalize_question_number_arabic(self):
        assert normalize_question_number("1") == "I"
        assert normalize_question_number("2") == "II"
        assert normalize_question_number("3") == "III"
        assert normalize_question_number("4") == "IV"
        assert normalize_question_number("5") == "V"

    def test_normalize_question_number_roman(self):
        assert normalize_question_number("I") == "I"
        assert normalize_question_number("II") == "II"
        assert normalize_question_number("IV") == "IV"


class TestFrontmatter:
    def test_normal_frontmatter(self):
        content = "---\nuniversity: 東京大\nyear: 2025\nfaculty: []\n---\n\nbody"
        fm, body = parse_frontmatter(content)
        assert fm["university"] == "東京大"
        assert fm["year"] == 2025
        assert "body" in body

    def test_kyoto_frontmatter(self):
        content = "---\nuniversity: (不明)\nyear: 令和7年度\nfaculty: []\n---\n\nbody"
        fm, body = parse_frontmatter(content)
        assert fm["university"] == "(不明)"

    def test_no_frontmatter(self):
        content = "# Question I\n## Text\nhello"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content


class TestQuestionSplitting:
    def test_split_arabic_numbers(self):
        body = "# Question 1\ncontent1\n# Question 2\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert blocks[0][0] == "1"
        assert blocks[1][0] == "2"

    def test_split_roman_numbers(self):
        body = "# Question I\ncontent1\n# Question II\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert blocks[0][0] == "I"

    def test_continued_merge(self):
        body = "# Question 1\npart1\n# Question 1 (Continued)\npart2\n# Question 2\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert "part1" in blocks[0][1]
        assert "part2" in blocks[0][1]

    def test_split_japanese_format(self):
        body = "# 第1問\ncontent1\n# 第2問\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert blocks[0][0] == "1"
        assert blocks[1][0] == "2"

    def test_split_bracketed_numbers(self):
        body = "# Question [1]\ncontent1\n# Question [2]\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert blocks[0][0] == "1"


class TestABSplit:
    def test_no_split(self):
        text = "Some regular paragraph text."
        parts = detect_ab_split(text)
        assert len(parts) == 1
        assert parts[0][0] == "1"

    def test_ab_split(self):
        passage_a = "This is a long passage about sports. " * 20
        passage_b = "This is a long passage about pantomime. " * 20
        text = f"(A) {passage_a}\n\n(B) {passage_b}"
        parts = detect_ab_split(text)
        assert len(parts) == 2
        assert parts[0][0] == "1"
        assert parts[1][0] == "2"
        assert "sports" in parts[0][1]
        assert "pantomime" in parts[1][1]

    def test_ab_split_short_options_not_split(self):
        """選択肢リストのような短い (A)/(B) は分割しない。"""
        text = "(A) assistance\n(B) assistants\n(C) barrier"
        parts = detect_ab_split(text)
        assert len(parts) == 1


class TestRealData:
    """実データテスト。data/input_md/ が存在する場合のみ実行。"""

    @pytest.fixture(autouse=True)
    def skip_if_no_data(self):
        if not INPUT_DIR.exists():
            pytest.skip("入試問題データが見つかりません")

    def _load(self, filename: str) -> list:
        path = INPUT_DIR / filename
        if not path.exists():
            pytest.skip(f"{filename} が見つかりません")
        content = path.read_text(encoding="utf-8")
        return parse_md(content, filename)

    def test_tokyo(self):
        results = self._load("2025東京大_問題.md")
        assert len(results) == 5
        for r in results:
            assert r.university == "東京大"
            assert r.year == 2025

    def test_kyoto(self):
        results = self._load("2025京都大_問題.md")
        assert len(results) > 0
        for r in results:
            assert r.university == "京都大"
            assert r.year == 2025

    def test_osaka_gaigokugo_igai(self):
        """括弧付き大学名がそのまま保持されること。"""
        results = self._load("2025大阪大（外国語以外）_問題.md")
        assert len(results) > 0
        for r in results:
            assert r.university == "大阪大（外国語以外）"
        q1_results = [r for r in results if r.question_number == "I"]
        if len(q1_results) >= 2:
            assert q1_results[0].passage_index == 1
            assert q1_results[1].passage_index == 2

    def test_hokkaido(self):
        results = self._load("2025北海道大_問題.md")
        assert len(results) == 4
        for r in results:
            assert r.university == "北海道大"

    def test_toritsu_rikei(self):
        """第N問形式 + 括弧付き大学名。"""
        results = self._load("2025東京都立大（理系）_問題.md")
        assert len(results) == 2
        for r in results:
            assert r.university == "東京都立大（理系）"

    def test_passage_ids_unique(self):
        """代表5ファイルでパッセージIDがユニークであること。"""
        sample_files = [
            "2025東京大_問題.md",
            "2025京都大_問題.md",
            "2025大阪大（外国語以外）_問題.md",
            "2025北海道大_問題.md",
            "2025東京都立大（理系）_問題.md",
        ]
        all_ids = []
        for name in sample_files:
            path = INPUT_DIR / name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            results = parse_md(content, name)
            all_ids.extend(r.passage_id for r in results)
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs: {[x for x in all_ids if all_ids.count(x) > 1]}"
