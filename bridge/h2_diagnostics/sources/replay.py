"""ReplaySource: plays a recording back as if it were live, on a virtual clock.

poll(dt) moves the clock by dt and hands out the newest record per topic whose
time has come, counting every record on the way (same behavior as LiveSource).
"""
import gzip
import json

from .base import Source
from .stats import TopicStats


class ReplaySource(Source):
    """Plays back a .jsonl or .jsonl.gz recording (from stream_sensors.py or h2diag's recorder)."""

    live = False

    def __init__(self, path, speed=1.0, loop=False):
        self.path = str(path)
        self.speed = speed
        self.loop = loop
        self.meta = {}
        self.records = []
        self.markers = []
        opener = gzip.open if self.path.endswith(".gz") else open
        with opener(path, "rt") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if "meta" in rec:
                    self.meta = rec["meta"]
                elif "marker" in rec:
                    self.markers.append(rec)
                elif "topic" in rec:
                    self.records.append(rec)
        if not self.records:
            raise ValueError(f"{path}: no topic records")
        self.records.sort(key=lambda r: r["t"])
        self.topics = sorted({r["topic"] for r in self.records})
        self.stats = {t: TopicStats() for t in self.topics}
        self.t0 = self.records[0]["t"]
        self.duration = self.records[-1]["t"] - self.t0
        self._clock = 0.0  # virtual seconds since start, monotonic across loops
        self._offset = 0.0  # added to record times on each loop
        self._i = 0
        self.loops = 0  # completed passes through the file
        self.done = False

    def now(self):
        return self._clock

    @property
    def position(self):
        """Seconds into the recording for the current pass (0 .. duration)."""
        return max(0.0, min(self._clock - self._offset, self.duration))

    def poll(self, dt):
        self._clock += dt * self.speed
        out = {}
        while not self.done:
            if self._i >= len(self.records):
                if not self.loop:
                    self.done = True
                    break
                self._offset += self.duration + 0.02
                self._i = 0
                self.loops += 1
            rec = self.records[self._i]
            t = rec["t"] - self.t0 + self._offset
            if t > self._clock:
                break
            self.stats[rec["topic"]].hit(t)
            out[rec["topic"]] = rec["data"]
            self._i += 1
        return list(out.items())
