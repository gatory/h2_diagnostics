"""Measure the receive rate of a small set of topics (read-only).

discover_topics.py subscribes to every topic at once (~3,500 msg/s), so its rates
can be limited by Python on this machine rather than by the robot. This probe
subscribes only to the topics you pick, so the two results can be compared.

    python rate_probe.py --iface eth10                 # the bridge's planned topic set
    python rate_probe.py --iface eth10 --set lowstate  # rt/lowstate alone
    python rate_probe.py --iface eth10 --set all_fast  # every high-rate topic together
"""
import argparse
import threading
import time

import common

HG = "unitree_hg.msg.dds_."
TOPIC_TYPES = {
    "rt/lf/lowstate": HG + "LowState_",
    "rt/lf/secondary_imu": HG + "IMUState_",
    "rt/lf/bmsstate": HG + "BmsState_",
    "rt/lf/mainboardstate": HG + "MainBoardState_",
    "rt/dex5/left/state": HG + "HandState_",
    "rt/dex5/right/state": HG + "HandState_",
    "rt/lowstate": HG + "LowState_",
    "rt/secondary_imu": HG + "IMUState_",
    "rt/lowcmd": HG + "LowCmd_",
}
SETS = {
    "bridge": ["rt/lf/lowstate", "rt/lf/secondary_imu", "rt/lf/bmsstate",
               "rt/lf/mainboardstate", "rt/dex5/left/state", "rt/dex5/right/state"],
    "lowstate": ["rt/lowstate"],
    "all_fast": ["rt/lowstate", "rt/secondary_imu", "rt/lowcmd",
                 "rt/dex5/left/state", "rt/dex5/right/state"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default=common.IFACE)
    ap.add_argument("--domain", type=int, default=common.DOMAIN_ID)
    ap.add_argument("--set", choices=SETS, default="bridge")
    ap.add_argument("--topics", nargs="+", help="explicit topics (overrides --set)")
    ap.add_argument("--secs", type=float, default=10.0)
    args = ap.parse_args()

    topics = args.topics or SETS[args.set]
    unknown = [t for t in topics if t not in TOPIC_TYPES]
    if unknown:
        raise SystemExit(f"no type known for {unknown}; known: {list(TOPIC_TYPES)}")

    common.init_dds(args.domain, args.iface)
    from unitree_sdk2py.core.channel import ChannelSubscriber

    lock = threading.Lock()
    arrivals = {t: [] for t in topics}

    def make_handler(name):
        def handler(_msg):
            now = time.monotonic()
            with lock:
                arrivals[name].append(now)
        return handler

    subs = []
    for t in topics:
        sub = ChannelSubscriber(t, common.lookup_type(TOPIC_TYPES[t]))
        sub.Init(make_handler(t), 0)
        subs.append(sub)

    print(f"rate probe iface={args.iface} topics={len(topics)} secs={args.secs:.0f} (read-only)")
    time.sleep(1.0)  # let discovery settle before counting
    with lock:
        for v in arrivals.values():
            v.clear()
    time.sleep(args.secs)
    with lock:
        result = {k: list(v) for k, v in arrivals.items()}

    print(f"{'topic':28} {'Hz':>9} {'mean gap ms':>12} {'max gap ms':>11}")
    total = 0.0
    for t, ts in result.items():
        hz = len(ts) / args.secs
        total += hz
        gaps = [(b - a) * 1000 for a, b in zip(ts, ts[1:])]
        mean = f"{sum(gaps) / len(gaps):.2f}" if gaps else "-"
        worst = f"{max(gaps):.2f}" if gaps else "-"
        print(f"{t:28} {hz:9.1f} {mean:>12} {worst:>11}")
    print(f"{'total msg/s':28} {total:9.1f}")

    for sub in subs:
        try:
            sub.Close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
