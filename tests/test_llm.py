"""Tests for LLM plugin layer."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from runtime.llm.answer import compose_answer_auto, llm_compose_answer
from runtime.llm.client import DeepSeekClient, LLMClientError
from runtime.llm.config import llm_settings
from runtime.llm.intent import classify_intent_auto, llm_classify_intent


@pytest.fixture(autouse=True)
def reset_llm_cache():
    llm_settings.cache_clear()
    yield
    llm_settings.cache_clear()


@pytest.fixture
def mock_env():
    env = {
        "DEEPSEEK_API_KEY": "test-key",
        "LLM_ENABLED": "true",
        "LLM_INTENT_ENABLED": "true",
        "LLM_ANSWER_ENABLED": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        llm_settings.cache_clear()
        yield
    llm_settings.cache_clear()


class TestLLMConfig:
    def test_disabled_without_api_key(self):
        with patch.dict(os.environ, {"LLM_ENABLED": "false"}, clear=True):
            llm_settings.cache_clear()
            settings = llm_settings()
            assert not settings.is_configured

    def test_enabled_with_api_key(self, mock_env):
        settings = llm_settings()
        assert settings.is_configured
        assert settings.model == "deepseek-chat"
        assert settings.base_url == "https://api.deepseek.com"


class TestLLMIntent:
    def test_classify_intent_auto_falls_back_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            llm_settings.cache_clear()
            result = classify_intent_auto("e生保一年多少钱？")
            assert result["intent"] == "price_inquiry"

    def test_llm_classify_intent_parses_response(self, mock_env):
        client = MagicMock(spec=DeepSeekClient)
        client.chat.return_value = json.dumps({
            "intent": "product_comparison",
            "confidence": 0.92,
            "entities": [{"type": "product", "value": "e生保"}],
        })
        client.parse_json.side_effect = DeepSeekClient.parse_json

        result = llm_classify_intent("e生保和好医保哪个更好？", client=client)
        assert result["intent"] == "product_comparison"
        assert result["confidence"] == 0.92
        assert result["entities"][0]["value"] == "e生保"

    def test_classify_intent_auto_uses_llm(self, mock_env):
        with patch("runtime.llm.intent.llm_classify_intent") as mock_llm:
            mock_llm.return_value = {
                "intent": "coverage_question",
                "confidence": 0.88,
                "entities": [],
            }
            result = classify_intent_auto("重疾险保什么？")
            assert result["intent"] == "coverage_question"
            assert result.get("source") == "llm"

    def test_classify_intent_auto_fallback_on_error(self, mock_env):
        with patch("runtime.llm.intent.llm_classify_intent", side_effect=LLMClientError("timeout")):
            result = classify_intent_auto("出险后怎么理赔？")
            assert result["intent"] == "claim_process"
            assert result["source"] == "rule_fallback"


class TestLLMAnswer:
    def test_compose_answer_auto_falls_back_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            llm_settings.cache_clear()
            text = compose_answer_auto(
                "e生保一年多少钱？",
                "price_inquiry",
                {"product_search": {"products": [{"name": "e生保", "product_id": "P001"}]}},
                [],
            )
            assert "e生保" in text or "查询" in text

    def test_llm_compose_answer(self, mock_env):
        client = MagicMock(spec=DeepSeekClient)
        client.chat.return_value = "根据资料，e生保年保费约 350 元。\n\n本回答基于 1 条证据"

        text = llm_compose_answer(
            "e生保一年多少钱？",
            "price_inquiry",
            {"product_search": {"products": []}},
            [{"content": "年保费350元", "source_type": "product"}],
            client=client,
        )
        assert "350" in text
        client.chat.assert_called_once()

    def test_compose_answer_auto_fallback_on_error(self, mock_env):
        with patch("runtime.llm.answer.llm_compose_answer", side_effect=LLMClientError("api down")):
            text = compose_answer_auto("你好", "general_inquiry", {}, [])
            assert "查询" in text
