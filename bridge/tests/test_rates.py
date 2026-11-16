"""Rate reporting, including the startup case that caused false warnings live."""
from h2diag import health
from h2diag.state import TopicStats


def feed(stats, hz, until, start=0.0):
    t = start
    while t <= until:
        stats.hit(t)
        t += 1.0 / hz


def test_rate_correct_before_window_fills():
    # Regression: 1 s into a 2 s window, 20 Hz used to be reported as 10 Hz.
    s = TopicStats()
    feed(s, 20, until=1.0)
    assert abs(s.report(1.0)["hz"] - 20) < 1.5


def test_rate_correct_after_window_fills():
    s = TopicStats()
    feed(s, 100, until=5.0)
    assert abs(s.report(5.0)["hz"] - 100) < 2


def test_no_rate_until_enough_observed():
    s = TopicStats()
    feed(s, 20, until=0.2)
    assert s.report(0.2)["hz"] is None
    assert TopicStats().report(3.0)["hz"] is None  # never received


def test_stalled_topic_rate_drops():
    s = TopicStats()
    feed(s, 20, until=3.0)
    rep = s.report(4.0)  # silent for 1 s
    assert rep["hz"] < 14 and rep["age_s"] > 0.9


def test_no_false_rate_warning_at_startup():
    stats = {"rt/lf/lowstate": TopicStats(), "rt/dex5/left/state": TopicStats()}
    feed(stats["rt/lf/lowstate"], 20, until=1.0)
    feed(stats["rt/dex5/left/state"], 100, until=1.0)
    snap = {"topics": {t: s.report(1.0) for t, s in stats.items()}}
    rate_warnings = [w for w in health.evaluate(snap, live=True) if w["id"].startswith("rate:")]
    assert rate_warnings == []
