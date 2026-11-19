"""③ Session recorder: writes recordings to disk (sources/sessions.py reads them back).

Same .jsonl format stream_sensors.py used, so ReplaySource plays old and new alike:

    {"meta": {...}}                                  first line
    {"t": 1.234, "topic": "rt/lf/lowstate", "data": {...}}
    {"t": 5.678, "marker": "started gait trial 3"}

Records every message the source received while recording (the pipeline turns
on the source's keep_all), each stamped with when it arrived, not when it was
written. Messages that arrive between start() and the next bridge tick (<= 1 tick)
are still newest-only, because keep_all switches on at that tick.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path


def _slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")[:40]


class Recorder:
    def __init__(self, sessions_dir):
        self.dir = Path(sessions_dir)
        self._f = None
        self._t0 = None
        self.path = None
        self.name = None

    @property
    def active(self):
        return self._f is not None

    def start(self, name="", meta=None):
        if self.active:
            self.stop()
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.name = name
        self.path = self.dir / (f"{stamp}_{_slug(name)}.jsonl" if name else f"{stamp}.jsonl")
        self._f = open(self.path, "w")
        self._t0 = time.monotonic()
        header = {"start": datetime.now().isoformat(timespec="seconds"), "name": name}
        header.update(meta or {})
        self._f.write(json.dumps({"meta": header}) + "\n")
        return self.path

    def _t(self):
        return round(time.monotonic() - self._t0, 4)

    def write(self, topic, data, age=0.0):
        """age: seconds since the message arrived, so t is the arrival time."""
        if self.active:
            t = max(0.0, round(self._t() - age, 4))  # arrived just before start(): clamp to 0
            self._f.write(json.dumps({"t": t, "topic": topic, "data": data}) + "\n")

    def marker(self, text):
        if self.active:
            self._f.write(json.dumps({"t": self._t(), "marker": text}) + "\n")
            self._f.flush()

    def status(self):
        if not self.active:
            return {"recording": False}
        return {"recording": True, "name": self.name, "file": self.path.name,
                "elapsed_s": round(time.monotonic() - self._t0, 1)}

    def stop(self):
        path = self.path
        if self._f:
            self._f.close()
        self._f = None
        self.path = None
        return path
