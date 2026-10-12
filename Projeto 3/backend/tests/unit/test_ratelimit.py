"""Limitador de taxa e extração de IP (sem banco)."""
from types import SimpleNamespace

import pytest

from app import ratelimit
from app.config import get_settings
from app.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(ratelimit.time, "monotonic", fake)
    return fake


class TestSlidingWindow:
    def test_allows_up_to_the_limit_then_blocks(self, clock):
        limiter = SlidingWindowLimiter()
        assert [limiter.check("k", 3, 60) for _ in range(3)] == [None, None, None]
        retry = limiter.check("k", 3, 60)
        assert retry is not None and 1 <= retry <= 61

    def test_frees_after_window(self, clock):
        limiter = SlidingWindowLimiter()
        for _ in range(3):
            limiter.check("k", 3, 60)
        clock.advance(61)
        assert limiter.check("k", 3, 60) is None

    def test_keys_are_independent(self, clock):
        limiter = SlidingWindowLimiter()
        for _ in range(3):
            limiter.check("a", 3, 60)
        assert limiter.check("a", 3, 60) is not None
        assert limiter.check("b", 3, 60) is None

    def test_retry_after_does_not_consume_quota(self, clock):
        limiter = SlidingWindowLimiter()
        for _ in range(10):
            assert limiter.retry_after("k", 2, 60) is None

    def test_hits_block_via_retry_after(self, clock):
        limiter = SlidingWindowLimiter()
        limiter.hit("k")
        assert limiter.retry_after("k", 2, 60) is None
        limiter.hit("k")
        assert limiter.retry_after("k", 2, 60) is not None
        clock.advance(61)
        assert limiter.retry_after("k", 2, 60) is None

    def test_reset_clears_everything(self, clock):
        limiter = SlidingWindowLimiter()
        limiter.hit("k")
        limiter.hit("k")
        limiter.reset()
        assert limiter.retry_after("k", 2, 60) is None


def request(host="203.0.113.7", forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


class TestClientIp:
    def test_ignores_forwarded_header_by_default(self):
        assert ratelimit.client_ip(request(forwarded="10.0.0.1")) == "203.0.113.7"

    def test_uses_first_forwarded_ip_when_proxy_is_trusted(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
        assert ratelimit.client_ip(request(forwarded="198.51.100.9, 10.0.0.1")) == "198.51.100.9"

    def test_inet_or_none_rejects_non_ip_hosts(self):
        assert ratelimit.inet_or_none(request(host="testclient")) is None
        assert ratelimit.inet_or_none(request(host="203.0.113.7")) == "203.0.113.7"
        assert ratelimit.inet_or_none(request(host="2001:db8::1")) == "2001:db8::1"
