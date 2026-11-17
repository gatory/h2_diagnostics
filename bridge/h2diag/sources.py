"""Data sources. Both expose the same interface:

    source.topics   -> list of topic names it can deliver
    source.stats    -> {topic: TopicStats}, updated as messages arrive
    source.now()    -> the source's clock (monotonic seconds; virtual for replay)
    source.poll(dt) -> [(topic, data_dict)] newest message per topic since last poll
    source.live     -> True for the robot, False for a recording
    source.done     -> True once a non-looping replay has run out

READ-ONLY: LiveSource only ever creates subscribers. tests/test_read_only.py checks it.
"""
import dataclasses
import gzip
import json
import math
import threading
import time

from . import layout
from .state import TopicStats


def to_dict(obj):
    """Convert a decoded IDL message into JSON-safe python data."""
    if dataclasses.is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    if isinstance(obj, (bytes, bytearray)):
        return list(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "tolist"):  # numpy
        return obj.tolist()
    return obj


class LiveSource:
    live = True
    done = False

    def __init__(self, iface, domain=0):
        self.iface = iface
        self.domain = domain
        self.topics = list(layout.LIVE_TOPICS)
        self.stats = {t: TopicStats() for t in self.topics}
        self._lock = threading.Lock()
        self._pending = {}
        self._subs = []

    def start(self):
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
        import unitree_sdk2py.idl.unitree_hg.msg.dds_ as hg

        ChannelFactoryInitialize(self.domain, self.iface)
        for topic, (type_name, _hz) in layout.LIVE_TOPICS.items():
            sub = ChannelSubscriber(topic, getattr(hg, type_name))
            sub.Init(self._handler(topic), 0)
            self._subs.append(sub)
        return self

    def _handler(self, topic):
        stats = self.stats[topic]

        def handle(msg):  # runs on a DDS thread: keep it tiny
            stats.hit(time.monotonic())
            with self._lock:
                self._pending[topic] = msg

        return handle

    def now(self):
        return time.monotonic()

    def poll(self, dt=None):
        with self._lock:
            pending, self._pending = self._pending, {}
        return [(t, to_dict(m)) for t, m in pending.items()]

    def close(self):
        # Drop references first so late callbacks have nothing to touch, then close.
        subs, self._subs = self._subs, []
        for sub in subs:
            try:
                sub.Close()
            except Exception:
                pass


class ReplaySource:
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

    def start(self):
        return self

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

    def close(self):
        pass
