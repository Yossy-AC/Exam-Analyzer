"""MDパーサーのテスト。実データを使用して各大学のパターンを検証する。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parser import (
    detect_ab_split,
    detect_copyright_omitted,
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

    def test_extract_university_kyotsu_test(self):
        """共通テスト系ファイル名の正規化。"""
        assert extract_university_from_filename("2025第５回共通テスト_R_本試験_問題.md") == "共通テスト（R本試験）"
        assert extract_university_from_filename("2025第５回共通テスト_R_追試験_問題.md") == "共通テスト（R追試験）"
        assert extract_university_from_filename("2026第６回共通テスト_R_本試験_問題.md") == "共通テスト（R本試験）"
        # 試作問題: _問題 がファイル名末尾にないためフォールバック
        assert extract_university_from_filename("2025第５回共通テスト_R_試作問題.md") == "共通テスト（R試作）"

    def test_extract_university_shikou_chousa(self):
        """試行調査ファイル名の正規化。"""
        assert extract_university_from_filename("2017第１回試行調査_R_問題.md") == "共通テスト（R試行調査1）"
        assert extract_university_from_filename("2018第２回試行調査_R_問題.md") == "共通テスト（R試行調査2）"

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

    def test_normalize_question_number_with_alpha(self):
        """共通テスト形式: アラビア数字+アルファベット → ローマ数字-アルファベット。"""
        assert normalize_question_number("1A") == "I-A"
        assert normalize_question_number("2B") == "II-B"
        assert normalize_question_number("3A") == "III-A"
        assert normalize_question_number("5C") == "V-C"


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

    def test_cont_merge(self):
        """(cont.) 形式のマージ。"""
        body = "# Question 1\npart1\n# Question 1 (cont.)\npart2\n# Question 2\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert "part1" in blocks[0][1]
        assert "part2" in blocks[0][1]

    def test_part_b_merge(self):
        """(Part B) 形式のマージ。"""
        body = "# Question 1\npart_a\n# Question 1 (Part B)\npart_b\n# Question 2\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert "part_a" in blocks[0][1]
        assert "part_b" in blocks[0][1]

    def test_question_with_alpha_suffix(self):
        """# Question 1A / 1B 形式（共通テスト新Geminiフォーマット）。"""
        body = "# Question 1A\ntext_a\n# Question 1B\ntext_b\n# Question 2\ntext2\n"
        blocks = split_questions(body)
        assert len(blocks) == 3
        assert blocks[0][0] == "1A"
        assert blocks[1][0] == "1B"
        assert blocks[2][0] == "2"

    def test_chunk_duplicate_merge(self):
        """チャンク分割で同一Question IDが連続する場合のマージ。"""
        body = "# Question 2A\npart1\n# Question 2A\npart2\n# Question 2B\ntext_b\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert blocks[0][0] == "2A"
        assert "part1" in blocks[0][1]
        assert "part2" in blocks[0][1]
        assert blocks[1][0] == "2B"

    def test_chunk_alpha_only_fixup(self):
        """チャンク分割でアルファベット単体のQ_IDを補正。# Question B → 6B。"""
        body = "# Question 6A\ntext_a\n# Question B\ntext_b\n"
        blocks = split_questions(body)
        assert len(blocks) == 2
        assert blocks[0][0] == "6A"
        assert blocks[1][0] == "6B"

    def test_chunk_bare_number_after_sub(self):
        """チャンク分割で # Question 3 が 3A/3B の後に来た場合、3Bにマージ。"""
        body = "# Question 3A\ntext_a\n# Question 3B\ntext_b\n# Question 3\nextra\n# Question 4\ntext4\n"
        blocks = split_questions(body)
        assert len(blocks) == 3
        assert blocks[0][0] == "3A"
        assert blocks[1][0] == "3B"
        assert "text_b" in blocks[1][1]
        assert "extra" in blocks[1][1]
        assert blocks[2][0] == "4"

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

    def test_split_japanese_format_with_alpha(self):
        """共通テスト形式: # 第1問A / # 第1問B。"""
        body = "# 第1問A\ncontent1A\n# 第1問B\ncontent1B\n# 第2問\ncontent2\n"
        blocks = split_questions(body)
        assert len(blocks) == 3
        assert blocks[0][0] == "1A"
        assert blocks[1][0] == "1B"
        assert blocks[2][0] == "2"


class TestCopyrightDetection:
    def test_gemini_marker(self):
        block = "## Text\n<!-- COPYRIGHT_OMITTED: 本文が著作権により省略 -->\n## Questions\n問1"
        assert detect_copyright_omitted(block) is True

    def test_japanese_pattern_chosakuken_shouryaku(self):
        assert detect_copyright_omitted("著作権の都合により省略されています") is True

    def test_japanese_pattern_honbun_shouryaku(self):
        assert detect_copyright_omitted("本文は省略") is True

    def test_japanese_pattern_shutten_tsugou(self):
        assert detect_copyright_omitted("出典の都合により省略") is True

    def test_japanese_pattern_chosakubutsu(self):
        assert detect_copyright_omitted("著作物のため非掲載") is True

    def test_japanese_pattern_keisai_dekimasen(self):
        assert detect_copyright_omitted("著作権上の理由により掲載できません") is True

    def test_negative_normal_text(self):
        assert detect_copyright_omitted("This is a normal English passage about copyright law.") is False

    def test_negative_empty(self):
        assert detect_copyright_omitted("") is False

    def test_negative_japanese_unrelated(self):
        assert detect_copyright_omitted("著作権法について論じた英文を読み、以下の問いに答えよ。") is False


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


class TestKyotsuShisakuSplit:
    """共通テスト試作問題の ### 第A問 / ### 第B問 フォールバック分割。"""

    def test_shisaku_split(self):
        content = (
            "---\nuniversity: 2025第５回共通テスト_R_試作問題\nyear:\nfaculty:\n---\n\n"
            "# Question\n\n## Instructions\n試作問題の説明\n\n## Text\n\n"
            "### 第A問\n\nPassage A content here.\n問1 question text\n\n"
            "### 第B問\n\nPassage B content here.\n問1 another question\n\n"
            "## Data\nGraph data\n"
        )
        results = parse_md(content, "2025第５回共通テスト_R_試作問題.md")
        assert len(results) == 2
        assert results[0].university == "共通テスト（R試作）"
        assert results[0].question_number == "A"
        assert results[1].question_number == "B"
        assert "Passage A" in results[0].text_section
        assert "Passage B" in results[1].text_section
        # ## Data は第B問のブロックに含まれないこと
        assert "Graph data" not in results[1].text_section

    def test_shisaku_year_from_filename(self):
        """年度はフロントマターが空でもファイル名から取得。"""
        content = (
            "---\nuniversity: 2025第５回共通テスト_R_試作問題\nyear:\nfaculty:\n---\n\n"
            "# Question\n\n## Text\n\n### 第A問\n\nContent A\n"
        )
        results = parse_md(content, "2025第５回共通テスト_R_試作問題.md")
        assert len(results) == 1
        assert results[0].year == 2025


class TestCopyrightParseMd:
    """parse_md()で著作権省略ブロックが正しくフラグ付きで返ること。"""

    def test_copyright_omitted_passage_created(self):
        normal_text = "This is a normal passage with enough words. " * 5
        content = (
            "---\nuniversity: テスト大\nyear: 2025\nfaculty: []\n---\n\n"
            "# Question 1\n## Text\n<!-- COPYRIGHT_OMITTED: 本文省略 -->\n## Questions\n問1\n\n"
            f"# Question 2\n## Text\n{normal_text}\n## Questions\n問1\n"
        )
        results = parse_md(content, "2025テスト大_問題.md")
        assert len(results) == 2
        q1 = [r for r in results if r.question_number == "I"][0]
        q2 = [r for r in results if r.question_number == "II"][0]
        assert q1.copyright_omitted is True
        assert q2.copyright_omitted is False

    def test_copyright_omitted_empty_text_not_skipped(self):
        """著作権省略の場合、textが空でもスキップされずパッセージが作られる。"""
        content = (
            "---\nuniversity: テスト大\nyear: 2025\nfaculty: []\n---\n\n"
            "# Question 1\n## Text\n<!-- COPYRIGHT_OMITTED: 省略 -->\n## Questions\n問1\n"
        )
        results = parse_md(content, "2025テスト大_問題.md")
        assert len(results) == 1
        assert results[0].copyright_omitted is True


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

    def test_kyotsu_honshiken(self):
        """共通テスト本試験: 8問、大学名が正規化されること。"""
        results = self._load("2025第５回共通テスト_R_本試験_問題.md")
        assert len(results) == 8
        for r in results:
            assert r.university == "共通テスト（R本試験）"
            assert r.year == 2025

    def test_kyotsu_tsui(self):
        """共通テスト追試験: 8問。"""
        results = self._load("2025第５回共通テスト_R_追試験_問題.md")
        assert len(results) == 8
        for r in results:
            assert r.university == "共通テスト（R追試験）"

    def test_kyotsu_shisaku(self):
        """共通テスト試作問題: ### 第A問 / ### 第B問 で2パッセージ。"""
        results = self._load("2025第５回共通テスト_R_試作問題.md")
        assert len(results) == 2
        assert results[0].question_number == "A"
        assert results[1].question_number == "B"
        assert results[0].university == "共通テスト（R試作）"

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
