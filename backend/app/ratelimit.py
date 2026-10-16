"""Per-client-IP sliding-window rate limiting (in memory, thread/async safe).

Configure with ``SEG_RATE_LIMITS`` — comma-separated ``<count>/<window>`` rules, window in
``s``/``m``/``h`` (default ``1/5s,6/60s``). Empty, ``0`` or ``off`` disables limiting.
``SEG_TRUSTED_PROXIES`` (default ``127.0.0.1,::1``): only requests from these peers may set the
client IP through ``X-Real-IP`` / ``X-Forwarded-For``.
"""
from __future__ import annotations

import math
import os
import re
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

_UNIT = {"": 1, "s": 1, "m": 60, "h": 3600}


def parse_rules(spec: Optional[str]) -> List[Tuple[int, float]]:
    spec = (spec or "").strip().lower()
    if spec in ("", "0", "off", "none", "false"):
        return []
    rules = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*/\s*(\d*\.?\d*)\s*([smh]?)", part)
        if not m:
            raise ValueError(f"bad SEG_RATE_LIMITS rule: {part!r} (expected e.g. 1/5s)")
        n, w = int(m.group(1)), float(m.group(2) or 1) * _UNIT[m.group(3)]
        if n > 0 and w > 0:
            rules.append((n, w))
    return rules


class RateLimiter:
    def __init__(self, rules: List[Tuple[int, float]], cleanup_every: float = 60.0):
        self.rules = rules
        self.max_window = max((w for _, w in rules), default=0)
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._cleanup_every = cleanup_every
        self._last_cleanup = time.monotonic()

    @property
    def enabled(self) -> bool:
        return bool(self.rules)

    def hit(self, key: str) -> Optional[int]:
        """Record a call. Returns None if allowed, else seconds to wait (call not recorded)."""
        if not self.rules:
            return None
        now = time.monotonic()
        with self._lock:
            if now - self._last_cleanup > self._cleanup_every:
                self._cleanup(now)
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.max_window:
                q.popleft()
            wait = 0.0
            for n, w in self.rules:
                recent = [t for t in q if now - t < w]
                if len(recent) >= n:
                    wait = max(wait, recent[-n] + w - now)
            if wait > 0:
                return max(1, math.ceil(wait))
            q.append(now)
            return None

    def _cleanup(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.max_window]:
            del self._hits[k]
        self._last_cleanup = now


TRUSTED = {p.strip() for p in os.environ.get("SEG_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if p.strip()}


def client_ip(peer: Optional[str], headers) -> str:
    peer = peer or "unknown"
    if peer in TRUSTED:
        xr = (headers.get("x-real-ip") or "").strip()
        if xr:
            return xr
        xff = [p.strip() for p in (headers.get("x-forwarded-for") or "").split(",") if p.strip()]
        for ip in reversed(xff):  # right-most untrusted hop
            if ip not in TRUSTED:
                return ip
    return peer


limiter = RateLimiter(parse_rules(os.environ.get("SEG_RATE_LIMITS", "1/5s,6/60s")))
