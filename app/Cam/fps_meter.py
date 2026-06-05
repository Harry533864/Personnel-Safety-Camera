import threading
import time
from collections import deque


class FpsMeter:
    def __init__(self, window_seconds=5.0):
        self.window_seconds = float(window_seconds)
        self._timestamps = deque()
        self._lock = threading.Lock()

    def mark(self, timestamp=None):
        now = time.monotonic() if timestamp is None else float(timestamp)
        with self._lock:
            self._timestamps.append(now)
            self._prune_locked(now)

    def fps(self):
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            if len(self._timestamps) < 2:
                return 0.0
            elapsed = self._timestamps[-1] - self._timestamps[0]
            if elapsed <= 0:
                return 0.0
            return round((len(self._timestamps) - 1) / elapsed, 2)

    def _prune_locked(self, now):
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
