"""Ported discover_topics.py / rate_probe.py: the pure parts, tested without a robot.

The DDS calls themselves only run on the Thor (see bridge/MIGRATION.md).
"""
import json

from h2_diagnostics.__main__ import main
from h2_diagnostics.sources.probe import PROBE_TYPES, RATE_SETS, summarize_discovery, summarize_rates
from h2_diagnostics.views.tables import topics_text

from conftest import DATA, TOPICS


def test_rate_summary_hz_gaps_and_total():
    arrivals = {"a": [0.0, 0.01, 0.02, 0.05], "b": []}  # 4 msgs, one 30 ms stall
    rows, total = summarize_rates(arrivals, secs=2.0)
    a, b = rows
    assert a["hz"] == 2.0 and round(a["max_gap_ms"]) == 30 and round(a["mean_gap_ms"]) == 17
    assert b["hz"] == 0 and b["max_gap_ms"] is None
    assert total == 2.0


def test_discovery_summary_matches_example_format():
    topics = {
        "rt/lf/bmsstate": {"type": "unitree_hg::msg::dds_::BmsState_", "writers": {"w1"},
                           "participants": {"p1"}},
        "rt/mystery": {"type": "foo::Bar_", "writers": {"w1", "w2"}, "participants": {"p1"}},
    }
    stats = {"rt/lf/bmsstate": {"count": 41, "first": 0.0, "last": 2.0, "sample": {"soc": 90}}}
    r = {x["topic"]: x for x in summarize_discovery(topics, stats)}
    assert r["rt/lf/bmsstate"]["type"] == "unitree_hg.msg.dds_.BmsState_"
    assert r["rt/lf/bmsstate"]["hz"] == 20.0 and r["rt/lf/bmsstate"]["sample"] == {"soc": 90}
    assert r["rt/mystery"]["decoded"] is False and r["rt/mystery"]["writers"] == 2


def test_topics_text_reproduces_the_examples_saved_output():
    # Parity check: the ported formatter turns the real 2026-11-13 discovery JSON
    # into exactly the topics.txt that discover_topics.py wrote that day (2026-11-13).
    results = json.loads(TOPICS.read_text())["topics"]
    assert topics_text(results) == (DATA / "topics_20261113.txt").read_text()


def test_rate_sets_only_use_known_topics():
    for name, topics in RATE_SETS.items():
        assert set(topics) <= set(PROBE_TYPES), name


def test_topics_show_and_rates_validation(capsys):
    assert main(["topics", "--show", str(TOPICS)]) == 0
    out = capsys.readouterr().out
    assert "120 topics" in out and "rt/lf/lowstate" in out
    assert main(["rates", "--topics", "rt/nope"]) == 2
    assert "no type known" in capsys.readouterr().out


def test_extra_only_accepts_known_research_topics(recording):
    import pytest
    with pytest.raises(SystemExit):  # argparse rejects it before anything runs
        main(["record", "--replay", str(recording), "--name", "t", "--extra", "rt/made_up"])
