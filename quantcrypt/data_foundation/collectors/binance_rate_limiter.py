from __future__ import annotations

import threading
import time
from collections import deque


class BinanceRateLimiter:
    def __init__(
        self,
        *,
        max_weight_per_window: int = 1_200,
        window_seconds: float = 60.0,
    ) -> None:
        self.max_weight_per_window = max_weight_per_window
        self.window_seconds = window_seconds
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def acquire(self, weight: int) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._evict_old(now)
                used = sum(event_weight for _, event_weight in self._events)
                if used + weight <= self.max_weight_per_window:
                    self._events.append((now, weight))
                    return
                oldest_timestamp = self._events[0][0]
                sleep_for = max(0.01, self.window_seconds - (now - oldest_timestamp))
            time.sleep(sleep_for)

    def _evict_old(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= self.window_seconds:
            self._events.popleft()

