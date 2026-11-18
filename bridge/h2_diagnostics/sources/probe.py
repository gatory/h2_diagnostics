"""Probing the robot's DDS network: which topics exist, and how fast they arrive.

Ported from examples/sensor_reading_example/discover_topics.py and rate_probe.py.
READ-ONLY: all DDS access goes through dds.py (subscriptions only). The DDS-using
functions (sample_topics, record_arrivals, and dds.discover_publications) keep the
logic the examples ran on the robot; the math (summarize_*) is pure and tested offline.
"""
import threading
import time

from .. import layout
from .convert import to_dict
from . import dds
from .dds import lookup_type, normalize_type_name

HG = "unitree_hg.msg.dds_."

# Topics the rate probe knows how to decode: the bridge's own topics (taken from
# layout.LIVE_TOPICS, the one master list) plus the 1 kHz copies for comparison.
# Note: the examples also probed rt/lowcmd, but its message type is a command type,
# and the read-only guard in tests/test_pipeline.py forbids command type names
# anywhere in the package. Reading it is harmless; allowing it is a user decision
# (see bridge/MIGRATION.md).
PROBE_TYPES = {
    **{topic: HG + type_name for topic, (type_name, _hz) in layout.LIVE_TOPICS.items()},
    "rt/lowstate": HG + "LowState_",
    "rt/secondary_imu": HG + "IMUState_",
    # Research only (test T6, FSM source): a unitree_go (quadruped-family) type the H2
    # publishes at ~500 Hz. Its "mode" field may be the FSM state. Not a bridge topic.
    "rt/odommodestate": "unitree_go.msg.dds_.SportModeState_",
}
RATE_SETS = {
    "bridge": list(layout.LIVE_TOPICS),  # exactly what LiveSource subscribes to
    "lowstate": ["rt/lowstate"],
    "all_fast": ["rt/lowstate", "rt/secondary_imu", "rt/dex5/left/state", "rt/dex5/right/state"],
}


# ---------------------------------------------------------------- topic discovery

def sample_topics(topics, secs):
    """Subscribe to every decodable topic at once for `secs`; count and keep one sample.

    Returns {topic: {"count", "first", "last", "sample", maybe "error"}}.
    """
    stats, subs = {}, []
    lock = threading.Lock()

    def make_handler(name):
        def handler(msg):  # DDS thread: keep tiny
            now = time.monotonic()
            with lock:
                s = stats[name]
                s["count"] += 1
                if s["first"] is None:
                    s["first"] = now
                    s["sample"] = msg
                s["last"] = now
        return handler

    for name, info in topics.items():
        cls = lookup_type(info["type"])
        if cls is None:
            continue
        stats[name] = {"count": 0, "first": None, "last": None, "sample": None}
        try:
            subs.append(dds.subscribe(name, cls, make_handler(name)))
        except Exception as e:  # keep going; report the failure
            stats[name]["error"] = repr(e)
    time.sleep(secs)
    with lock:
        snapshot = {k: dict(v) for k, v in stats.items()}
    dds.close_all(subs)
    return snapshot


def summarize_discovery(topics, stats, keep_samples=True):
    """Pure: discovery + sampling results -> sorted list of per-topic result dicts
    (the format of topics.json)."""
    results = []
    for name in sorted(topics):
        info = topics[name]
        st = stats.get(name)
        hz = None
        if st and st["count"] >= 2 and st["last"] > st["first"]:
            hz = (st["count"] - 1) / (st["last"] - st["first"])
        sample = None
        if st and st["sample"] is not None and keep_samples:
            sample = st["sample"] if isinstance(st["sample"], dict) else to_dict(st["sample"])
        results.append({
            "topic": name,
            "type": normalize_type_name(info["type"]),
            "decoded": st is not None and "error" not in st,
            "writers": len(info["writers"]),
            "participants": len(info["participants"]),
            "messages_in_window": st["count"] if st else None,
            "hz": round(hz, 2) if hz else None,
            "error": st.get("error") if st else None,
            "sample": sample,
        })
    return results


# ---------------------------------------------------------------- rate probe

def record_arrivals(topic_types, secs, settle_s=1.0):
    """Subscribe to only these topics; return {topic: [arrival times]} over `secs`.

    Fewer topics than discovery, so the rates reflect the robot, not Python's
    decode limit on this machine.
    """
    lock = threading.Lock()
    arrivals = {t: [] for t in topic_types}

    def make_handler(name):
        def handler(_msg):
            now = time.monotonic()
            with lock:
                arrivals[name].append(now)
        return handler

    subs = [dds.subscribe(t, lookup_type(type_name), make_handler(t))
            for t, type_name in topic_types.items()]
    time.sleep(settle_s)  # let discovery settle before counting
    with lock:
        for v in arrivals.values():
            v.clear()
    time.sleep(secs)
    with lock:
        result = {k: list(v) for k, v in arrivals.items()}
    dds.close_all(subs)
    return result


def summarize_rates(arrivals, secs):
    """Pure: arrival times -> ([{"topic", "hz", "mean_gap_ms", "max_gap_ms"}], total msg/s).

    The max gap is what exposed the 22 ms stalls when every fast topic was on.
    """
    rows, total = [], 0.0
    for topic, ts in arrivals.items():
        hz = len(ts) / secs
        total += hz
        gaps = [(b - a) * 1000 for a, b in zip(ts, ts[1:])]
        rows.append({
            "topic": topic,
            "hz": hz,
            "mean_gap_ms": sum(gaps) / len(gaps) if gaps else None,
            "max_gap_ms": max(gaps) if gaps else None,
        })
    return rows, total
