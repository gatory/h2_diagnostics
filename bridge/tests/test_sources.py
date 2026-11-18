"""Both message sources implement the same Source interface (sources/base.py),
and LiveSource works end to end against a fake DDS gateway (no robot needed)."""
from dataclasses import dataclass

import pytest

from h2_diagnostics import layout
from h2_diagnostics.sources import LiveSource, ReplaySource, Source, dds


def test_both_sources_are_sources(recording):
    assert issubclass(LiveSource, Source)
    assert isinstance(ReplaySource(recording), Source)
    assert LiveSource("lo").live is True  # constructing doesn't touch DDS; start() does


def test_source_is_abstract():
    with pytest.raises(TypeError):
        Source()

    class Incomplete(Source):  # forgot poll()
        def now(self):
            return 0.0

    with pytest.raises(TypeError):
        Incomplete()


# ------------------------------------------------------------------ LiveSource, fake DDS

@dataclass
class FakeMsg:  # stands in for a decoded IDL message (those are dataclasses too)
    value: int


class FakeDDS:
    """Replaces the functions in sources/dds.py. Records what LiveSource asks for and
    lets the test deliver messages the way a DDS thread would (by calling the handler)."""

    def __init__(self):
        self.inited = None
        self.handlers = {}  # topic -> handler LiveSource registered
        self.types = {}  # topic -> type name it asked for
        self.closed = []

    def init(self, domain, iface):
        self.inited = (domain, iface)

    def hg_type(self, name):
        return name  # a real class isn't needed; just remember which one was asked for

    def lookup_type(self, full_name):
        return None if "Unknown" in full_name else full_name

    def subscribe(self, topic, msg_type, on_message):
        self.handlers[topic] = on_message
        self.types[topic] = msg_type
        fake = self

        class Sub:
            def close(self):
                fake.closed.append(topic)

        return Sub()

    def deliver(self, topic, value):
        self.handlers[topic](FakeMsg(value))


@pytest.fixture
def fake_dds(monkeypatch):
    fake = FakeDDS()
    for name in ("init", "hg_type", "lookup_type", "subscribe"):
        monkeypatch.setattr(dds, name, getattr(fake, name))
    return fake


def test_live_source_subscribes_to_every_live_topic(fake_dds):
    src = LiveSource("eth10", domain=0).start()
    assert fake_dds.inited == (0, "eth10")
    assert fake_dds.types == {t: type_name for t, (type_name, _hz) in layout.LIVE_TOPICS.items()}
    src.close()
    assert sorted(fake_dds.closed) == sorted(layout.LIVE_TOPICS)
    src.close()  # a second close is harmless
    assert len(fake_dds.closed) == len(layout.LIVE_TOPICS)


def test_live_source_keeps_newest_and_counts_all(fake_dds):
    src = LiveSource("eth10").start()
    for v in (1, 2, 3):
        fake_dds.deliver("rt/lf/lowstate", v)
    fake_dds.deliver("rt/dex5/left/state", 7)

    out = dict(src.poll())
    assert out == {"rt/lf/lowstate": {"value": 3}, "rt/dex5/left/state": {"value": 7}}
    assert src.stats["rt/lf/lowstate"].count == 3  # every arrival counted, only newest kept
    assert src.poll() == []  # poll() hands each message out once
    src.close()


def test_live_source_extra_topics_for_robot_tests(fake_dds):
    odom = {"rt/odommodestate": "unitree_go.msg.dds_.SportModeState_"}
    src = LiveSource("eth10", extra=odom).start()
    assert fake_dds.types["rt/odommodestate"] == odom["rt/odommodestate"]
    assert "rt/odommodestate" in src.stats  # counted like any topic, so rates show
    fake_dds.deliver("rt/odommodestate", 5)
    assert dict(src.poll())["rt/odommodestate"] == {"value": 5}  # so the recorder gets it
    src.close()

    with pytest.raises(ValueError, match="no message class"):
        LiveSource("eth10", extra={"rt/x": "unitree_go.msg.dds_.Unknown_"}).start()
