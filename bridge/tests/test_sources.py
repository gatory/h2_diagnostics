"""Both message sources implement the same Source interface (sources/base.py),
and LiveSource works end to end against a fake DDS gateway (no robot needed)."""
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

    out = {topic: data for topic, data, _t in src.poll()}
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
    assert src.poll()[0][:2] == ("rt/odommodestate", {"value": 5})  # so the recorder gets it
    src.close()

    with pytest.raises(ValueError, match="no message class"):
        LiveSource("eth10", extra={"rt/x": "unitree_go.msg.dds_.Unknown_"}).start()


# ------------------------------------------------------------------ keep_all (recording)

def test_live_source_keeps_every_message_while_recording(fake_dds):
    # The recorder bug: between two ticks the hands send several messages, and the
    # one-slot-per-topic mailbox kept only the last. With keep_all, none are lost.
    src = LiveSource("eth10").start()
    src.keep_all = True
    for v in range(5):
        fake_dds.deliver("rt/dex5/left/state", v)
    fake_dds.deliver("rt/lf/lowstate", 9)

    out = src.poll()
    assert [(topic, data["value"]) for topic, data, _t in out] == [
        ("rt/dex5/left/state", 0), ("rt/dex5/left/state", 1), ("rt/dex5/left/state", 2),
        ("rt/dex5/left/state", 3), ("rt/dex5/left/state", 4), ("rt/lf/lowstate", 9)]
    times = [t for _topic, _data, t in out]
    assert times == sorted(times)  # arrival order, each with its own arrival time
    assert src.poll() == []
    src.close()


def test_live_source_queue_is_capped(fake_dds, caplog):
    # A stalled main loop must not let the queue eat the Thor's memory.
    src = LiveSource("eth10").start()
    src.keep_all = True
    src.max_queue = 3
    for v in range(5):
        fake_dds.deliver("rt/dex5/left/state", v)
    out = src.poll()
    assert [data["value"] for _topic, data, _t in out] == [0, 1, 2]
    assert src.dropped == 2
    assert "dropped 2" in caplog.text
    src.close()


def test_replay_source_keep_all(recording):
    newest = ReplaySource(recording).poll(0.5)
    every = ReplaySource(recording)
    every.keep_all = True
    out = every.poll(0.5)
    assert len({topic for topic, _d, _t in newest}) == len(newest)  # one per topic
    assert len(out) == sum(s.count for s in every.stats.values()) > len(newest)
    times = [t for _topic, _data, t in out]
    assert times == sorted(times) and times[-1] <= every.now()
