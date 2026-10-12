"""Rate limiting por janela deslizante, em memória.

Adequado para uma instância. Com várias réplicas, troque o armazenamento por
Redis mantendo a mesma interface (check/retry_after/hit/reset).
"""
import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.errors import RateLimited

_MAX_KEYS = 10_000


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, hits: deque[float], now: float, window_seconds: int) -> None:
        while hits and now - hits[0] >= window_seconds:
            hits.popleft()

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Registra a tentativa. Retorna None se permitida ou os segundos até liberar."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            self._prune(hits, now, window_seconds)
            if len(hits) >= limit:
                return max(1, int(window_seconds - (now - hits[0])) + 1)
            hits.append(now)
            return None

    def retry_after(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Só consulta (não registra). None se ainda há folga; senão, segundos até liberar."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return None
            self._prune(hits, now, window_seconds)
            if len(hits) >= limit:
                return max(1, int(window_seconds - (now - hits[0])) + 1)
            return None

    def hit(self, key: str) -> None:
        """Registra um evento (ex.: falha de login)."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > _MAX_KEYS:  # evita crescimento ilimitado por IPs variados
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                    del self._hits[stale]
            self._hits[key].append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def inet_or_none(request: Request) -> str | None:
    """IP válido para a coluna INET (ou None, p.ex. em testes ou cabeçalhos malformados)."""
    try:
        return str(ipaddress.ip_address(client_ip(request)))
    except ValueError:
        return None


def login_rate_limit(request: Request) -> None:
    """Bloqueia o login quando o IP acumulou falhas demais na janela.

    Só FALHAS contam (ver record_login_failure): logins válidos não consomem a cota,
    para que uma equipe inteira atrás do mesmo IP possa entrar no início do expediente.
    """
    s = get_settings()
    retry = limiter.retry_after(
        f"login:{client_ip(request)}", s.login_rate_limit_attempts, s.login_rate_limit_window_seconds
    )
    if retry:
        raise RateLimited(retry)


def record_login_failure(request: Request) -> None:
    limiter.hit(f"login:{client_ip(request)}")


def refresh_rate_limit(request: Request) -> None:
    s = get_settings()
    retry = limiter.check(
        f"refresh:{client_ip(request)}", s.refresh_rate_limit_attempts, s.refresh_rate_limit_window_seconds
    )
    if retry:
        raise RateLimited(retry)
