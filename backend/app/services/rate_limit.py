"""Small privacy-safe, process-local sliding-window rate limiter.

This deliberately has no external dependency. It is an abuse-control layer for
one backend process, not a distributed quota system; deployments with multiple
workers should put an edge rate limiter in front of the API.
"""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True

    def reset(self) -> None:
        """Test-only helper; production code never needs to clear this state."""
        with self._lock:
            self._events.clear()


rate_limiter = SlidingWindowRateLimiter()
