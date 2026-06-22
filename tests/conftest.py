"""Pytest defaults — skip heavy embedding models and live LLM in test runs."""

import os

os.environ.setdefault("EMBEDDING_FAST_MODE", "1")
os.environ.setdefault("LLM_ENABLED", "false")
