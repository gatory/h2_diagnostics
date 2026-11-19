"""LiveSource: reads the robot's DDS topics (run on the Thor, wired to 192.168.123.x).

The SDK decodes each message's bytes into an object on a DDS thread, then calls our
handler, which counts it and stores it with its arrival time:
  - normally only the newest per topic (one slot each), so overwritten messages
    never pay for to_dict;
  - while recording (keep_all), every message, in a capped queue, so none are lost.
poll() converts them to dicts on the main thread.
All DDS access goes through dds.py. READ-ONLY: only subscriptions are created.
"""
import logging
import threading
import time

from .. import layout
from . import dds
from .base import Source
from .convert import to_dict
from .stats import TopicStats

log = logging.getLogger("h2_diagnostics.live")


class LiveSource(Source):
    live = True
    done = False
    max_queue = 5000  # keep_all cap: ~18 s of the bridge set (~280 msg/s) if the loop stalls

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
        self._pending = {}  # topic -> (t, msg): newest only
        self._queue = []  # [(t, topic, msg)]: every message, while keep_all
        self._subs = []
        self.dropped = 0  # messages lost to the queue cap
        self._dropped_logged = 0

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
            t = time.monotonic()
            stats.hit(t)
            with self._lock:
                if not self.keep_all:
                    self._pending[topic] = (t, msg)
                elif len(self._queue) < self.max_queue:
                    self._queue.append((t, topic, msg))
                else:
                    self.dropped += 1

        return handle

    def now(self):
        return time.monotonic()

    def poll(self, dt=None):
        with self._lock:
            pending, self._pending = self._pending, {}
            queue, self._queue = self._queue, []
            dropped = self.dropped
        if dropped > self._dropped_logged:
            log.warning("keep_all queue full (max %d): dropped %d messages so far",
                        self.max_queue, dropped)
            self._dropped_logged = dropped
        # Both can hold messages for one tick after keep_all flips; merge by arrival time.
        msgs = queue + [(t, topic, m) for topic, (t, m) in pending.items()]
        msgs.sort(key=lambda x: x[0])
        return [(topic, to_dict(m), t) for t, topic, m in msgs]

    def close(self):
        # Drop references first so late callbacks have nothing to touch, then close.
        subs, self._subs = self._subs, []
        dds.close_all(subs)
