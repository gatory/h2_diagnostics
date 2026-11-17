"""The bridge loop: source -> state -> (recorder, snapshot + warnings)."""
import time

from . import health
from .state import RobotState


class Bridge:
    def __init__(self, source, recorder=None):
        self.source = source
        self.state = RobotState(source.stats)
        self.recorder = recorder
        self._levels = {}  # warning id -> level on the last tick (for hysteresis)

    def tick(self, dt):
        """Pull new messages, record them, return a snapshot with warnings."""
        for topic, data in self.source.poll(dt):
            self.state.ingest(topic, data)
            if self.recorder:
                self.recorder.write(topic, data)
        snap = self.state.snapshot(
            self.source.now(), time.time(), "live" if self.source.live else "replay"
        )
        snap["warnings"] = health.evaluate(snap, self.source.live, self._levels)
        self._levels = {w["id"]: w["level"] for w in snap["warnings"]}
        if self.recorder:
            snap["recorder"] = self.recorder.status()
        return snap
