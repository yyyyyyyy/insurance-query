"""Trace-Aware Cache — Query, Retrieval, Tool, Evaluation caches."""

from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

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
    def __init__(self, default_ttl: float = 300.0):
        self.default_ttl = default_ttl
        self._stores = {k: {} for k in ("query","retrieval","tool","evaluation")}
        self._stats = {k: {"hits":0,"misses":0,"evictions":0} for k in self._stores}

    def get(self, store: str, key: str) -> Tuple[Optional[Any], bool]:
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
        self._stats[store]["hits"] += 1
        return e.value, True

    def set(self, store, key, value, trace_id="", ttl=None):
        if store not in self._stores:
            return
        self._stores[store][key] = CacheEntry(key=key, value=value, trace_id=trace_id, ttl_seconds=ttl or self.default_ttl)

    def invalidate(self, store=None):
        count = 0
        if store and store in self._stores:
            count = len(self._stores[store])
            self._stores[store].clear()
        elif store is None:
            for s in self._stores:
                count += len(self._stores[s])
                self._stores[s].clear()
        return count

    def query_key(self, query): return hashlib.md5(f"q:{query}".encode()).hexdigest()[:16]
    def retrieval_key(self, query): return hashlib.md5(f"r:{query}".encode()).hexdigest()[:16]
    def tool_key(self, tool, params): return hashlib.md5(f"t:{tool}:{sorted(str(params))}".encode()).hexdigest()[:16]
    def evaluation_key(self, tid): return f"ev:{tid}"

    def stats(self):
        total_h = sum(self._stats[s]["hits"] for s in self._stores)
        total_m = sum(self._stats[s]["misses"] for s in self._stores)
        return {"total_hits":total_h,"total_misses":total_m,
                "hit_rate":round(total_h/max(total_h+total_m,1),3),
                "stores":{s:{"entries":len(self._stores[s]),**self._stats[s]} for s in self._stores}}
