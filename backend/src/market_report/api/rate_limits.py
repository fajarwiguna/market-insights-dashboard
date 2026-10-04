"""Bound uncached export requests per API process."""

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests = deque()
        self._lock = Lock()

    def admit(self, now: float | None = None) -> int:
        now = monotonic() if now is None else now
        with self._lock:
            while self._requests and self._requests[0] <= now - self.window_seconds:
                self._requests.popleft()
            if len(self._requests) >= self.limit:
                return max(1, ceil(self._requests[0] + self.window_seconds - now))
            self._requests.append(now)
            return 0


export_requests = SlidingWindowLimiter(limit=10, window_seconds=60)
