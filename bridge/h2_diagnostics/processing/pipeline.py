"""② The bridge loop: source -> state -> (recorder, snapshot + warnings).

The one pipeline everything uses: server, preflight, recorder and the terminal views."""
import time

from .health import HealthMonitor
from .state import RobotState


class H2Diagnostics:
    """Owns one of each part and runs them in order on every tick.

        source    where messages come from (a sources.Source; passed in)
        state     RobotState: newest message per role -> snapshot
        health    HealthMonitor: snapshot -> warnings (with hysteresis memory)
        recorder  optional output.Recorder: writes messages to disk (passed in)
    """

    def __init__(self, source, recorder=None):
        self.source = source
        self.state = RobotState(source.stats)
        self.health = HealthMonitor()
        self.recorder = recorder

    def tick(self, dt):
        """Pull new messages, record them, return a snapshot with warnings."""
        for topic, data in self.source.poll(dt):
            self.state.ingest(topic, data)
            if self.recorder:
                self.recorder.write(topic, data)
        snap = self.state.snapshot(
            self.source.now(), time.time(), "live" if self.source.live else "replay"
        )
        snap["warnings"] = self.health.evaluate(snap, self.source.live)
        if self.recorder:
            snap["recorder"] = self.recorder.status()
        return snap
