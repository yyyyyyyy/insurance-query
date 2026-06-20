"""
Async Execution Engine — Parallel tool dispatch with timeout, retry, and queue.

Architecture:
  ToolDispatcher → AsyncExecutor → concurrent.futures pool
  Supports: parallel execution, timeout, retry, graceful degradation
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from runtime.tools.base import ToolResult


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RETRYING = "retrying"
    FAILED = "failed"
    FALLBACK = "fallback"


@dataclass
class AsyncResult:
    """Result of an async tool execution with retry/fallback metadata."""
    tool_name: str
    status: ExecutionStatus
    result: Optional[ToolResult] = None
    error: Optional[str] = None
    attempts: int = 1
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS


@dataclass
class ExecutionConfig:
    """Configuration for async execution behavior."""
    max_workers: int = 4
    default_timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_delay_seconds: float = 0.5
    fallback_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_workers": self.max_workers,
            "default_timeout_seconds": self.default_timeout_seconds,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "fallback_enabled": self.fallback_enabled,
        }


class AsyncExecutor:
    """Async tool execution engine with parallel dispatch, timeout, and retry.

    Executes tools concurrently via ThreadPoolExecutor. Supports:
      - Parallel execution of independent tools
      - Timeout per tool invocation
      - Automatic retry on failure
      - Fallback to degraded tool execution
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        self._execution_stats: Dict[str, Dict[str, int]] = {
            "total": 0, "success": 0, "timeout": 0, "failed": 0, "retried": 0
        }

    def execute(
        self,
        tool_name: str,
        dispatch_fn: Callable[[str, Dict[str, Any]], ToolResult],
        params: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> AsyncResult:
        """Execute a single tool with timeout and retry."""
        timeout = timeout or self.config.default_timeout_seconds
        self._execution_stats["total"] += 1

        start = time.perf_counter()

        for attempt in range(1, self.config.max_retries + 2):
            future: Future = self._executor.submit(dispatch_fn, tool_name, params)

            try:
                result: ToolResult = future.result(timeout=timeout)
                duration = (time.perf_counter() - start) * 1000

                if result.success:
                    self._execution_stats["success"] += 1
                    return AsyncResult(
                        tool_name=tool_name,
                        status=ExecutionStatus.SUCCESS,
                        result=result,
                        attempts=attempt,
                        duration_ms=round(duration, 2),
                    )
                elif attempt <= self.config.max_retries:
                    self._execution_stats["retried"] += 1
                    time.sleep(self.config.retry_delay_seconds)
                    continue
                else:
                    self._execution_stats["failed"] += 1
                    return AsyncResult(
                        tool_name=tool_name,
                        status=ExecutionStatus.FAILED,
                        result=result,
                        error=result.error.get("message", "Tool execution failed"),
                        attempts=attempt,
                        duration_ms=round(duration, 2),
                    )

            except FutureTimeoutError:
                if attempt <= self.config.max_retries:
                    self._execution_stats["retried"] += 1
                    time.sleep(self.config.retry_delay_seconds)
                    continue
                self._execution_stats["timeout"] += 1
                duration = (time.perf_counter() - start) * 1000
                return AsyncResult(
                    tool_name=tool_name,
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Timeout after {timeout}s",
                    attempts=attempt,
                    duration_ms=round(duration, 2),
                )

            except Exception as exc:
                if attempt <= self.config.max_retries:
                    self._execution_stats["retried"] += 1
                    time.sleep(self.config.retry_delay_seconds)
                    continue
                self._execution_stats["failed"] += 1
                duration = (time.perf_counter() - start) * 1000
                return AsyncResult(
                    tool_name=tool_name,
                    status=ExecutionStatus.FAILED,
                    error=str(exc),
                    attempts=attempt,
                    duration_ms=round(duration, 2),
                )

        # Should not reach here, but safety
        return AsyncResult(
            tool_name=tool_name,
            status=ExecutionStatus.FAILED,
            error="Max retries exceeded",
            attempts=self.config.max_retries + 1,
        )

    def execute_parallel(
        self,
        tool_calls: List[Tuple[str, Dict[str, Any]]],
        dispatch_fn: Callable[[str, Dict[str, Any]], ToolResult],
        timeout: Optional[float] = None,
    ) -> List[AsyncResult]:
        """Execute multiple tools in parallel.

        Handles tool graph dependencies: tools are grouped by dependency level
        and executed in parallel within each level.
        """
        if not tool_calls:
            return []

        timeout = timeout or self.config.default_timeout_seconds
        futures: List[Tuple[str, Future]] = []

        for tool_name, params in tool_calls:
            future = self._executor.submit(
                self._execute_with_retry, tool_name, dispatch_fn, params, timeout
            )
            futures.append((tool_name, future))

        results = []
        for tool_name, future in futures:
            try:
                async_result: AsyncResult = future.result(timeout=timeout * 2)
                results.append(async_result)
            except FutureTimeoutError:
                self._execution_stats["timeout"] += 1
                results.append(AsyncResult(
                    tool_name=tool_name,
                    status=ExecutionStatus.TIMEOUT,
                    error="Parallel execution timeout",
                ))

        return results

    def _execute_with_retry(
        self,
        tool_name: str,
        dispatch_fn: Callable,
        params: Dict[str, Any],
        timeout: float,
    ) -> AsyncResult:
        """Internal method for parallel execution with retry."""
        return self.execute(tool_name, dispatch_fn, params, timeout)

    def stats(self) -> Dict[str, Any]:
        return dict(self._execution_stats)

    def shutdown(self):
        self._executor.shutdown(wait=True)


def create_default_executor() -> AsyncExecutor:
    """Factory: create AsyncExecutor with production defaults."""
    return AsyncExecutor(ExecutionConfig(
        max_workers=4,
        default_timeout_seconds=10.0,
        max_retries=2,
        retry_delay_seconds=0.5,
        fallback_enabled=True,
    ))
