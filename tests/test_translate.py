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
