"""LiveSource: reads the robot's DDS topics (run on the Thor, wired to 192.168.123.x).

DDS callbacks run on reader threads and only store the newest message + count it;
decoding happens in poll() on the main thread (Python decode speed is the limit).
READ-ONLY: only subscribers are created.
"""
import threading
import time

from .. import layout
from .convert import to_dict
from .stats import TopicStats


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
