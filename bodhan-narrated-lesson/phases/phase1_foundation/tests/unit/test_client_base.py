import asyncio

import httpx
import pytest

from bodhan_lesson.clients.base import BodhanAPIError, BodhanClient


def make(handler, **kw):
    return BodhanClient(
        "indic-ocr", "https://api.test/v1", "k", asyncio.Semaphore(2),
        cost_fn=lambda h: (h["n"], 0.2 * h["n"]), max_retries=3,
        transport=httpx.MockTransport(handler), **kw,
    )


async def test_retries_then_succeeds_and_counts_cost():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": 1})

    c = make(handler)
    r = await c.request("/x", usage_hint={"n": 1}, json={})
    assert r.json() == {"ok": 1}
    assert c.stats.calls == 1 and c.stats.retries == 2
    assert c.stats.cost_inr == pytest.approx(0.2)
    await c.aclose()


async def test_non_retryable_fails_fast():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    c = make(handler)
    with pytest.raises(BodhanAPIError):
        await c.request("/x", json={})
    assert calls["n"] == 1 and c.stats.failures == 1
    await c.aclose()


async def test_gives_up_after_max_retries():
    c = make(lambda req: httpx.Response(500))
    with pytest.raises(BodhanAPIError):
        await c.request("/x", json={})
    assert c.stats.failures == 1
    await c.aclose()
