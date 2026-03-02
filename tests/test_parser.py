"""MDパーサーのテスト。実データを使用して各大学のパターンを検証する。"""

import os
import sys
from pathlib import Path

import pytest

# プロジェクトルートをパスに追加
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

INPUT_DIR = Path(__file__).resolve().parent.parent.parent / "input" / "2025旧帝大_問題_md"


class TestUtilities:
    def test_extract_university_from_filename(self):
        assert extract_university_from_filename("2025東京大_問題.md") == "東京大"
        assert extract_university_from_filename("2025大阪大（外国語以外）_問題.md") == "大阪大"
        assert extract_university_from_filename("2025大阪大（外国語）_問題.md") == "大阪大"
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


class TestABSplit:
    def test_no_split(self):
        text = "Some regular paragraph text."
        parts = detect_ab_split(text)
        assert len(parts) == 1
        assert parts[0][0] == "1"

    def test_ab_split(self):
        text = "(A) First passage about sports.\n\n(B) Second passage about pantomime."
        parts = detect_ab_split(text)
        assert len(parts) == 2
        assert parts[0][0] == "1"  # A -> 1
        assert parts[1][0] == "2"  # B -> 2
        assert "sports" in parts[0][1]
        assert "pantomime" in parts[1][1]


class TestRealData:
    """実データを使ったテスト。input/ディレクトリが存在する場合のみ実行。"""

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
        assert len(results) > 0
        # 全てのパッセージが東京大であること
        for r in results:
            assert r.university == "東京大"
            assert r.year == 2025
        # Question 1 は (Continued) がマージされて1つの大問に
        q1_results = [r for r in results if r.question_number == "I"]
        assert len(q1_results) >= 1
        # テキストセクションが空でないこと
        for r in results:
            assert len(r.text_section) > 0

    def test_kyoto(self):
        results = self._load("2025京都大_問題.md")
        assert len(results) > 0
        for r in results:
            assert r.university == "京都大"  # フォールバック抽出
            assert r.year == 2025  # 令和7年度 -> 2025

    def test_osaka_gaigokugo_igai(self):
        results = self._load("2025大阪大（外国語以外）_問題.md")
        assert len(results) > 0
        for r in results:
            assert r.university == "大阪大"
        # Question I に (A)(B) 分割がある場合をチェック
        q1_results = [r for r in results if r.question_number == "I"]
        if len(q1_results) >= 2:
            assert q1_results[0].passage_index == 1
            assert q1_results[1].passage_index == 2

    def test_tohoku(self):
        results = self._load("2025東北大_問題.md")
        assert len(results) > 0
        for r in results:
            assert r.university == "東北大"
            assert r.year == 2025

    def test_all_files_parseable(self):
        """全MDファイルがエラーなくパースできること。"""
        for path in INPUT_DIR.glob("*.md"):
            content = path.read_text(encoding="utf-8")
            results = parse_md(content, path.name)
            assert isinstance(results, list), f"Failed to parse {path.name}"
            # 各ファイルから少なくとも1つのパッセージが抽出されること
            assert len(results) > 0, f"No passages extracted from {path.name}"

    def test_passage_ids_unique(self):
        """全ファイルを通じてパッセージIDがユニークであること。"""
        all_ids = []
        for path in INPUT_DIR.glob("*.md"):
            content = path.read_text(encoding="utf-8")
            results = parse_md(content, path.name)
            all_ids.extend(r.passage_id for r in results)
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs found: {[x for x in all_ids if all_ids.count(x) > 1]}"
