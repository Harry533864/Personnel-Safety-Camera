from __future__ import annotations

from collections import deque
import threading
import time


class FpsMeter:
    def __init__(self, window_sec: float = 3.0) -> None:
        self.window_sec = max(0.5, float(window_sec))
        self._samples = deque()
        self._lock = threading.Lock()

    def mark(self, timestamp: float | None = None) -> None:
        now = timestamp if timestamp is not None else time.perf_counter()
        cutoff = now - self.window_sec
        with self._lock:
            self._samples.append(now)
            while self._samples and self._samples[0] < cutoff:
                self._samples.popleft()

    def fps(self) -> float:
        now = time.perf_counter()
        cutoff = now - self.window_sec
        with self._lock:
            while self._samples and self._samples[0] < cutoff:
                self._samples.popleft()
            if len(self._samples) < 2:
                return 0.0
            elapsed = self._samples[-1] - self._samples[0]
            if elapsed <= 0:
                return 0.0
            return round((len(self._samples) - 1) / elapsed, 2)

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
