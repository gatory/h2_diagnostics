"""Arrival counting per topic: message count, rate (Hz) and age.

Counting happens where messages arrive (data layer), so it lives here even though
the numbers end up in the snapshot.
"""
import threading
from collections import deque

from .convert import num

RATE_WINDOW_S = 2.0
RATE_MIN_SPAN_S = 0.5  # report no rate until a topic has been watched this long


class TopicStats:
    """Arrival counter for one topic. Safe to call from DDS reader threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._times = deque()
        self.count = 0
        self.first = None
        self.last = None

    def hit(self, t):
        with self._lock:
            if self.first is None:
                self.first = t
            self.count += 1
            self.last = t
            self._times.append(t)
            while self._times and t - self._times[0] > RATE_WINDOW_S:
                self._times.popleft()

    def report(self, now):
        with self._lock:
            while self._times and now - self._times[0] > RATE_WINDOW_S:
                self._times.popleft()
            # Divide by the time actually observed: right after startup the window
            # isn't full yet, and dividing by the full window halves the rate.
            span = 0.0 if self.first is None else min(RATE_WINDOW_S, now - self.first)
            hz = round(len(self._times) / span, 1) if span >= RATE_MIN_SPAN_S else None
            age = None if self.last is None else max(0.0, now - self.last)
            return {"hz": hz, "age_s": num(age, 3), "count": self.count}
