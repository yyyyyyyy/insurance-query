"""Trace-Aware Cache — Query, Retrieval, Tool, Evaluation caches."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class CacheEntry:
    key: str
    value: Any
    trace_id: str = ""
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0
    hit_count: int = 0

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class TraceAwareCache:
    def __init__(self, default_ttl: float = 300.0, max_entries_per_store: int = 512):
        self.default_ttl = default_ttl
        self.max_entries_per_store = max_entries_per_store
        self._stores: Dict[str, OrderedDict[str, CacheEntry]] = {
            k: OrderedDict() for k in ("query", "retrieval", "tool", "evaluation")
        }
        self._stats = {k: {"hits": 0, "misses": 0, "evictions": 0} for k in self._stores}
        self._lock = threading.RLock()

    def get(self, store: str, key: str) -> Tuple[Optional[Any], bool]:
        with self._lock:
            if store not in self._stores:
                return None, False
            e = self._stores[store].get(key)
            if e is None:
                self._stats[store]["misses"] += 1
                return None, False
            if e.expired:
                self._stats[store]["evictions"] += 1
                del self._stores[store][key]
                return None, False
            e.hit_count += 1
            self._stores[store].move_to_end(key)
            self._stats[store]["hits"] += 1
            return e.value, True

    def get_entry_meta(self, store: str, key: str) -> Dict[str, Any]:
        """Metadata for a cache entry (for causal replay on CACHE_HIT)."""
        with self._lock:
            e = self._stores.get(store, {}).get(key)
            if not e:
                return {}
            return {
                "trace_id": e.trace_id,
                "key": e.key,
                "hit_count": e.hit_count,
                "created_at": e.created_at,
            }

    def set(self, store: str, key: str, value: Any, trace_id: str = "", ttl: Optional[float] = None) -> None:
        with self._lock:
            if store not in self._stores:
                return
            bucket = self._stores[store]
            bucket[key] = CacheEntry(
                key=key,
                value=value,
                trace_id=trace_id,
                ttl_seconds=ttl or self.default_ttl,
            )
            bucket.move_to_end(key)
            while len(bucket) > self.max_entries_per_store:
                bucket.popitem(last=False)
                self._stats[store]["evictions"] += 1

    def invalidate(self, store: Optional[str] = None) -> int:
        with self._lock:
            count = 0
            if store and store in self._stores:
                count = len(self._stores[store])
                self._stores[store].clear()
            elif store is None:
                for s in self._stores:
                    count += len(self._stores[s])
                    self._stores[s].clear()
            return count

    def query_key(self, query: str, session_id: str = "") -> str:
        if session_id:
            return hashlib.sha256(f"q:{query}:{session_id}".encode()).hexdigest()
        return hashlib.sha256(f"q:{query}".encode()).hexdigest()

    def retrieval_key(self, query: str) -> str:
        return hashlib.sha256(f"r:{query}".encode()).hexdigest()

    def tool_key(self, tool: str, params: Dict[str, Any]) -> str:
        payload = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(f"t:{tool}:{payload}".encode()).hexdigest()

    def evaluation_key(self, tid: str) -> str:
        return f"ev:{tid}"

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total_h = sum(self._stats[s]["hits"] for s in self._stores)
            total_m = sum(self._stats[s]["misses"] for s in self._stores)
            return {
                "total_hits": total_h,
                "total_misses": total_m,
                "hit_rate": round(total_h / max(total_h + total_m, 1), 3),
                "stores": {
                    s: {"entries": len(self._stores[s]), **self._stats[s]}
                    for s in self._stores
                },
            }
