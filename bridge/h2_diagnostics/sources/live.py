"""LiveSource: reads the robot's DDS topics (run on the Thor, wired to 192.168.123.x).

The SDK decodes each message's bytes into an object on a DDS thread, then calls our
handler, which only counts it and keeps the newest one per topic. poll() converts
those to dicts on the main thread, so overwritten messages never pay for to_dict.
All DDS access goes through dds.py. READ-ONLY: only subscriptions are created.
"""
import threading
import time

from .. import layout
from . import dds
from .base import Source
from .convert import to_dict
from .stats import TopicStats


class LiveSource(Source):
    live = True
    done = False

    def __init__(self, iface, domain=0, extra=None):
        """extra: {topic: full DDS type name} to subscribe to as well, for tests on the
        robot (e.g. T6). They get recorded and counted, but no role reads them, so
        they never reach the snapshot. Keep them few: every message costs a decode."""
        self.iface = iface
        self.domain = domain
        self.extra = dict(extra or {})
        self.topics = list(layout.LIVE_TOPICS) + [t for t in self.extra if t not in layout.LIVE_TOPICS]
        self.stats = {t: TopicStats() for t in self.topics}
        self._lock = threading.Lock()
        self._pending = {}
        self._subs = []

    def start(self):
        dds.init(self.domain, self.iface)
        for topic, (type_name, _hz) in layout.LIVE_TOPICS.items():
            sub = dds.subscribe(topic, dds.hg_type(type_name), self._handler(topic))
            self._subs.append(sub)
        for topic, full_type in self.extra.items():
            if topic in layout.LIVE_TOPICS:
                continue
            cls = dds.lookup_type(full_type)
            if cls is None:
                raise ValueError(f"{topic}: the SDK has no message class for {full_type}")
            self._subs.append(dds.subscribe(topic, cls, self._handler(topic)))
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
        dds.close_all(subs)
