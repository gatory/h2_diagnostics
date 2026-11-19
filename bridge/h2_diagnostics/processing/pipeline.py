"""② The bridge loop: source -> state -> (recorder, snapshot + warnings).

The one pipeline everything uses: server, preflight, recorder and the terminal views."""
import time

from .health import HealthMonitor
from .state import RobotState
from .support import SupportEstimator


class H2Diagnostics:
    """Owns one of each part and runs them in order on every tick.

        source    where messages come from (a sources.Source; passed in)
        state     RobotState: newest message per role -> snapshot
        health    HealthMonitor: snapshot -> warnings (with hysteresis memory)
        support   SupportEstimator: ground or gantry, from knee torque (unconfirmed, display only)
        recorder  optional output.Recorder: writes messages to disk (passed in)
    """

    def __init__(self, source, recorder=None):
        self.source = source
        self.state = RobotState(source.stats)
        self.health = HealthMonitor()
        self.support = SupportEstimator()
        self.recorder = recorder

    def tick(self, dt):
        """Pull new messages, record them, return a snapshot with warnings.

        While recording, the source hands over every message (keep_all), each with
        its arrival time; the state just keeps the newest, the recorder keeps all.
        """
        recording = bool(self.recorder and self.recorder.active)
        self.source.keep_all = recording
        msgs = self.source.poll(dt)
        now = self.source.now()
        for topic, data, t in msgs:
            self.state.ingest(topic, data)
            if recording:
                # age, not t: the source's clock (virtual in replay) isn't the recorder's
                self.recorder.write(topic, data, age=now - t)
        snap = self.state.snapshot(now, time.time(), "live" if self.source.live else "replay")
        snap["support_raw"] = self.support.update(snap)
        snap["warnings"] = self.health.evaluate(snap, self.source.live)
        if self.recorder:
            snap["recorder"] = self.recorder.status()
        return snap
