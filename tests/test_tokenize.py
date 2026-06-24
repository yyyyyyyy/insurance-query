"""Tests for shared Chinese/English tokenizer."""

import pytest

from knowledge.retrieval.tokenize import tokenize_chinese


class TestTokenizeChinese:
    def test_jieba_cjk(self):
        tokens = tokenize_chinese("等待期是多少天")
        # Should produce meaningful CJK tokens (jieba style)
        assert "等待期" in tokens or "等待" in tokens
        assert len(tokens) >= 2

    def test_regex_fallback_ascii(self):
        tokens = tokenize_chinese("hello world test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_mixed_chinese_english(self):
        tokens = tokenize_chinese("e生保的免赔额")
        # e is single char, filtered; 生保/免赔额 should be tokenized
        chinese_tokens = [t for t in tokens if "\u4e00" <= t[0] <= "\u9fff"]
        assert len(chinese_tokens) >= 2

    def test_single_char_filtered(self):
        tokens = tokenize_chinese("a b c 的 了")
        assert all(len(t) >= 2 for t in tokens)

    def test_empty_input(self):
        assert tokenize_chinese("") == []

    def test_numbers_not_included(self):
        tokens = tokenize_chinese("30岁")
        assert "30" not in tokens
        assert "30岁" in tokens or "岁" not in tokens  # jieba may split 30/岁

    def test_short_english_filtered(self):
        tokens = tokenize_chinese("a b c")
        assert all(len(t) >= 2 for t in tokens)

    def test_repeatable(self):
        t1 = tokenize_chinese("重疾险保障范围")
        t2 = tokenize_chinese("重疾险保障范围")
        assert t1 == t2

    def test_whitespace_handling(self):
        tokens = tokenize_chinese("  理赔   流程  ")
        assert "理赔" in tokens
        assert "流程" in tokens
