"""Shared async HTTP client for Bodhan endpoints: retry+backoff, concurrency
limit, per-model usage/cost stats. Provider calls are the only network I/O."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from ..models import CallStats

log = logging.getLogger("bodhan_lesson.clients")

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class BodhanAPIError(RuntimeError):
    def __init__(self, model: str, status: int | None, detail: str):
        super().__init__(f"[{model}] status={status}: {detail}")
        self.model, self.status, self.detail = model, status, detail


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, BodhanAPIError):
        return exc.status is None or exc.status in RETRYABLE_STATUS
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class BodhanClient:
    """One instance per Bodhan model (each has its own key)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        semaphore: asyncio.Semaphore,
        cost_fn: Callable[[dict[str, Any]], tuple[float, float]] | None = None,
        max_retries: int = 4,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        self.stats = CallStats()
        self._sem = semaphore
        self._cost_fn = cost_fn
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(self, path: str, *, usage_hint: dict[str, Any] | None = None, **kwargs: Any) -> httpx.Response:
        """POST with retries. `usage_hint` feeds cost accounting (units, e.g. chars)."""
        attempts = 0

        async def _once() -> httpx.Response:
            nonlocal attempts
            attempts += 1
            try:
                resp = await self._http.post(path, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException):
                raise
            if resp.status_code >= 400:
                raise BodhanAPIError(self.model, resp.status_code, resp.text[:300])
            return resp

        start = time.perf_counter()
        async with self._sem:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(self._max_retries),
                    wait=wait_exponential(multiplier=0.5, max=20) + wait_random(0, 0.5),
                    retry=retry_if_exception(_is_retryable),
                    reraise=True,
                ):
                    with attempt:
                        resp = await _once()
            except Exception:
                self.stats.failures += 1
                self.stats.retries += max(attempts - 1, 0)
                self.stats.latency_s += time.perf_counter() - start
                log.error("call_failed", extra={"model": self.model, "path": path, "attempts": attempts})
                raise

        self.stats.calls += 1
        self.stats.retries += attempts - 1
        self.stats.latency_s += time.perf_counter() - start
        if self._cost_fn and usage_hint is not None:
            units, cost = self._cost_fn(usage_hint)
            self.stats.units += units
            self.stats.cost_inr += cost
        log.info("call_ok", extra={"model": self.model, "path": path, "attempts": attempts})
        return resp
