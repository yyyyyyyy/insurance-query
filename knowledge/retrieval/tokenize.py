"""Shared Chinese/English tokenization for retrieval and tool fallbacks."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_jieba():
    try:
        import jieba  # type: ignore
        jieba.setLogLevel(20)
        return jieba
    except ImportError:
        logger.warning(
            "jieba not installed — falling back to regex tokenizer. "
            "Install with: pip install jieba"
        )
        return None


def tokenize_chinese(text: str) -> List[str]:
    """Tokenize mixed Chinese/English text (jieba preferred, regex fallback)."""
    jieba = _get_jieba()
    if jieba is not None:
        tokens: List[str] = []
        for tok in jieba.lcut_for_search(text):
            tok = tok.strip().lower()
            if not tok:
                continue
            if re.fullmatch(r"[a-z]+", tok):
                if len(tok) >= 2:
                    tokens.append(tok)
            elif re.search(r"[\u4e00-\u9fff]", tok) and len(tok) >= 2:
                tokens.append(tok)
        return tokens
    return [
        t for t in re.findall(r"[\u4e00-\u9fff]{2,3}|[a-zA-Z]+", text.lower())
        if len(t) >= 2
    ]
