"""Multi-LLM英訳機能のテスト。"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.translate_prompts import (
    UNIVERSITY_CONTEXTS,
    build_compare_fragment,
    build_review_user_prompt,
    build_scoring_fragment,
    build_translate_user_prompt,
    get_max_score,
    inject_university,
)


# ---------------------------------------------------------------------------
# プロンプトビルダーテスト
# ---------------------------------------------------------------------------

class TestBuildTranslateUserPrompt:
    def test_without_context(self):
        result = build_translate_user_prompt("テスト文")
        assert "テスト文" in result
        assert "出典" not in result

    def test_with_context(self):
        result = build_translate_user_prompt("テスト文", "京大2024 大問2")
        assert "テスト文" in result
        assert "京大2024 大問2" in result
        assert "出典" in result


class TestBuildReviewUserPrompt:
    def test_without_context(self):
        result = build_review_user_prompt("日本語", "English translation")
        assert "日本語" in result
        assert "English translation" in result
        assert "出典" not in result

    def test_with_context(self):
        result = build_review_user_prompt("日本語", "English", "阪大2024")
        assert "阪大2024" in result


class TestInjectUniversity:
    def test_no_university(self):
        prompt = "base prompt"
        assert inject_university(prompt, None) == prompt
        assert inject_university(prompt, "") == prompt

    def test_known_university(self):
        prompt = "base prompt"
        result = inject_university(prompt, "kyoto")
        assert "京都大学" in result
        assert prompt in result

    def test_custom_university(self):
        prompt = "base prompt"
        result = inject_university(prompt, "custom", "独自の傾向説明")
        assert "独自の傾向説明" in result

    def test_unknown_university(self):
        prompt = "base prompt"
        result = inject_university(prompt, "unknown_univ")
        assert result == prompt

    def test_all_universities_have_content(self):
        for key, ctx in UNIVERSITY_CONTEXTS.items():
            assert len(ctx) > 50, f"{key} has too short context"


class TestScoringFragment:
    def test_kyoto_score(self):
        assert get_max_score("kyoto") == 25

    def test_default_score(self):
        assert get_max_score(None) == 15
        assert get_max_score("unknown") == 15

    def test_fragment_contains_score(self):
        fragment = build_scoring_fragment("kyoto")
        assert "25" in fragment
        assert "減点" in fragment

    def test_fragment_default(self):
        fragment = build_scoring_fragment(None)
        assert "15" in fragment


class TestCompareFragment:
    def test_all_llms_present(self):
        translations = {
            "claude": "Claude translation",
            "gemini": "Gemini translation",
            "chatgpt": "ChatGPT translation",
            "grok": "Grok translation",
        }
        fragment = build_compare_fragment(translations)
        assert "Claude translation" in fragment
        assert "Gemini translation" in fragment
        assert "ChatGPT translation" in fragment
        assert "Grok translation" in fragment

    def test_missing_llm(self):
        translations = {"claude": "only claude"}
        fragment = build_compare_fragment(translations)
        assert "only claude" in fragment
        assert "[N/A]" in fragment


# ---------------------------------------------------------------------------
# call_all_llmsの部分失敗テスト
# ---------------------------------------------------------------------------

class TestCallAllLlmsPartialFailure:
    def test_one_timeout_others_succeed(self):
        """1LLMがタイムアウトしても他3つが正常返却される。"""
        async def _test():
            async def mock_claude(system, user, **kw):
                return "Claude result"

            async def mock_gemini(system, user, **kw):
                await asyncio.sleep(5)  # Will be timed out
                return "Gemini result"

            async def mock_openai(system, user, **kw):
                return "ChatGPT result"

            async def mock_grok(system, user, **kw):
                return "Grok result"

            with patch("app.llm_clients._LLM_CALLERS", {
                "claude": mock_claude,
                "gemini": mock_gemini,
                "chatgpt": mock_openai,
                "grok": mock_grok,
            }):
                from app.llm_clients import call_all_llms
                results, times = await call_all_llms("sys", "user", timeout=1)

                assert results["claude"] == "Claude result"
                assert results["chatgpt"] == "ChatGPT result"
                assert results["grok"] == "Grok result"
                assert results["gemini"].startswith("[ERROR]")
                assert "Timeout" in results["gemini"]

        asyncio.run(_test())

    def test_one_exception_others_succeed(self):
        """1LLMが例外を投げても他3つが正常返却される。"""
        async def _test():
            async def mock_claude(system, user, **kw):
                return "Claude result"

            async def mock_gemini(system, user, **kw):
                raise RuntimeError("API key invalid")

            async def mock_openai(system, user, **kw):
                return "ChatGPT result"

            async def mock_grok(system, user, **kw):
                return "Grok result"

            with patch("app.llm_clients._LLM_CALLERS", {
                "claude": mock_claude,
                "gemini": mock_gemini,
                "chatgpt": mock_openai,
                "grok": mock_grok,
            }):
                from app.llm_clients import call_all_llms
                results, times = await call_all_llms("sys", "user")

                assert results["claude"] == "Claude result"
                assert results["chatgpt"] == "ChatGPT result"
                assert results["grok"] == "Grok result"
                assert "[ERROR]" in results["gemini"]
                assert "RuntimeError" in results["gemini"]

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# バッチ入力パーサーテスト
# ---------------------------------------------------------------------------

class TestParseBatchInput:
    def test_numbered_lines(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("1. 私は正しいことをした\n2. 言葉は使わない")
        assert len(items) == 2
        assert items[0].number == 1
        assert items[1].number == 2
        assert "正しい" in items[0].japanese_text

    def test_auto_numbering(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("私は正しい\n言葉は使わない")
        assert items[0].number == 1
        assert items[1].number == 2

    def test_force_directive(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("1. 彼は私と正反対だ /force to")
        assert items[0].force_words == ["to"]
        assert "正反対" in items[0].japanese_text

    def test_ban_directive(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("1. 短い道 /ban few")
        assert items[0].ban_words == ["few"]

    def test_hint_directive(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("1. 何か言おうと /hint 譲歩の構文を使うこと")
        assert items[0].hint == "譲歩の構文を使うこと"

    def test_multiple_directives(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("4. 短い道 /force little /ban few")
        assert items[0].force_words == ["little"]
        assert items[0].ban_words == ["few"]
        assert "短い道" in items[0].japanese_text

    def test_skip_empty_lines(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("1. あ\n\n2. い\n\n")
        assert len(items) == 2

    def test_force_multiple_words(self):
        from app.translate_service import parse_batch_input
        items = parse_batch_input("1. テスト /force to, in order to")
        assert items[0].force_words == ["to", "in order to"]


class TestParseNumberedSections:
    def test_basic(self):
        from app.translate_service import parse_numbered_sections
        text = "【1】\nHello\n【2】\nWorld"
        sections = parse_numbered_sections(text)
        assert sections[1] == "Hello"
        assert sections[2] == "World"

    def test_multiline(self):
        from app.translate_service import parse_numbered_sections
        text = "【1】\n訳A: Hello\n訳B: Hi\n【2】\n訳A: World"
        sections = parse_numbered_sections(text)
        assert "訳A: Hello" in sections[1]
        assert "訳B: Hi" in sections[1]

    def test_empty(self):
        from app.translate_service import parse_numbered_sections
        sections = parse_numbered_sections("no sections here")
        assert sections == {}


# ---------------------------------------------------------------------------
# バッチレビュー: パーサー
# ---------------------------------------------------------------------------

class TestParseBatchReviewInput:
    def test_single_translation(self):
        from app.translate_service import parse_batch_review_input
        items = parse_batch_review_input("1. 私は正しいと思うことをした\nI did what I thought was right.")
        assert len(items) == 1
        assert items[0].number == 1
        assert items[0].japanese_text == "私は正しいと思うことをした"
        assert items[0].user_translations == ["I did what I thought was right."]

    def test_multiple_translations(self):
        from app.translate_service import parse_batch_review_input
        text = "1. 意味もよく知らない言葉は使わないほうがよい\nYou should not use words whose meaning you don't know well.\nYou had better not use words that you are not familiar with."
        items = parse_batch_review_input(text)
        assert len(items) == 1
        assert len(items[0].user_translations) == 2

    def test_multiple_pairs(self):
        from app.translate_service import parse_batch_review_input
        text = "1. 私は正しいと思うことをした\nI did what I thought was right.\n2. 彼は昔と全く違う\nHe is very different from what he used to be."
        items = parse_batch_review_input(text)
        assert len(items) == 2
        assert items[0].number == 1
        assert items[1].number == 2

    def test_empty_lines_between_pairs(self):
        from app.translate_service import parse_batch_review_input
        text = "1. テスト文\nTest sentence.\n\n2. もう一つ\nAnother one."
        items = parse_batch_review_input(text)
        assert len(items) == 2

    def test_auto_numbering(self):
        from app.translate_service import parse_batch_review_input
        text = "テスト文\nTest sentence."
        items = parse_batch_review_input(text)
        assert len(items) == 1
        assert items[0].number == 1

    def test_no_translation_excluded(self):
        from app.translate_service import parse_batch_review_input
        text = "1. 英訳なし日本語のみ\n2. 二番目\nSecond."
        items = parse_batch_review_input(text)
        assert len(items) == 1
        assert items[0].number == 2

    def test_parenthesis_numbering(self):
        from app.translate_service import parse_batch_review_input
        text = "1) テスト文\nTest."
        items = parse_batch_review_input(text)
        assert len(items) == 1
        assert items[0].number == 1


class TestIsEnglishLine:
    def test_english(self):
        from app.translate_service import _is_english_line
        assert _is_english_line("I did what I thought was right.") is True

    def test_japanese(self):
        from app.translate_service import _is_english_line
        assert _is_english_line("私は正しいと思うことをした") is False

    def test_empty(self):
        from app.translate_service import _is_english_line
        assert _is_english_line("") is False

    def test_mixed_mostly_english(self):
        from app.translate_service import _is_english_line
        assert _is_english_line("Hello World こんにちは") is True


class TestBuildBatchReviewNumberedPairs:
    def test_single_translation(self):
        from app.translate_prompts import build_batch_review_numbered_pairs
        from app.translate_service import BatchReviewItem
        items = [BatchReviewItem(number=1, japanese_text="テスト", user_translations=["Test."])]
        result = build_batch_review_numbered_pairs(items)
        assert "【1】" in result
        assert "日本語: テスト" in result
        assert "英訳: Test." in result

    def test_multiple_translations(self):
        from app.translate_prompts import build_batch_review_numbered_pairs
        from app.translate_service import BatchReviewItem
        items = [BatchReviewItem(number=1, japanese_text="テスト", user_translations=["Test A.", "Test B."])]
        result = build_batch_review_numbered_pairs(items)
        assert "英訳①: Test A." in result
        assert "英訳②: Test B." in result
