"""Load process graphs from knowledge_pack JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, cast

_KNOWLEDGE_PACK = Path(__file__).resolve().parents[2] / "knowledge_pack" / "process_models"


def load_process_graph(process_name: str) -> Dict[str, Any]:
    """Load a process graph JSON by name.

    process_name: claim | underwriting | policy
    """
    paths = {
        "claim": _KNOWLEDGE_PACK / "claim" / "claim_process_graph.json",
        "underwriting": _KNOWLEDGE_PACK / "underwriting" / "underwriting_process_graph.json",
        "policy": _KNOWLEDGE_PACK / "policy" / "policy_process_graph.json",
    }
    path = paths.get(process_name)
    if not path or not path.is_file():
        raise FileNotFoundError(f"Process graph not found: {process_name}")
    with open(path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], json.load(f))
