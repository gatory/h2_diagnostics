#!/usr/bin/env python3
"""Discover every DDS topic published on the robot network, measure its rate,
and save one sample of each.

READ-ONLY: only DDS readers are created. Nothing is published.

Output:
    output/topics.json   full results incl. one decoded sample per topic
    output/topics.txt    plain-text table
"""
import argparse
import json
import threading
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table

import common

console = Console()


def discover_publications(domain_id: int, secs: float):
    """Return {topic_name: {"type": str, "writers": set, "participants": set}}."""
    from cyclonedds.builtin import BuiltinDataReader, BuiltinTopicDcpsPublication
    from cyclonedds.domain import DomainParticipant

    dp = DomainParticipant(domain_id)
    reader = BuiltinDataReader(dp, BuiltinTopicDcpsPublication)
    topics = {}
    deadline = time.monotonic() + secs
    while time.monotonic() < deadline:
        for ep in reader.take(N=256):
            name = getattr(ep, "topic_name", None)
            if not name:
                continue
            entry = topics.setdefault(
                name, {"type": ep.type_name, "writers": set(), "participants": set()}
            )
            entry["writers"].add(str(ep.key))
            entry["participants"].add(str(ep.participant_key))
        time.sleep(0.1)
    return topics


def measure_rates(topics: dict, secs: float):
    """Subscribe to every decodable topic at once for `secs` seconds."""
    from unitree_sdk2py.core.channel import ChannelSubscriber

    stats = {}
    subs = []
    lock = threading.Lock()

    def make_handler(name):
        def handler(msg):
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
        cls = common.lookup_type(info["type"])
        if cls is None:
            continue
        stats[name] = {"count": 0, "first": None, "last": None, "sample": None}
        try:
            sub = ChannelSubscriber(name, cls)
            sub.Init(make_handler(name), 0)
            subs.append(sub)
        except Exception as e:  # keep going; report the failure
            stats[name]["error"] = repr(e)

    with console.status(f"Sampling {len(subs)} decodable topics for {secs:.0f}s..."):
        time.sleep(secs)

    with lock:
        snapshot = {k: dict(v) for k, v in stats.items()}
    for sub in subs:
        try:
            sub.Close()
        except Exception:
            pass
    return snapshot


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default=common.IFACE, help="network interface to the robot (default %(default)s)")
    ap.add_argument("--domain", type=int, default=common.DOMAIN_ID, help="DDS domain id (default %(default)s)")
    ap.add_argument("--discover-secs", type=float, default=5.0, help="time to listen for publishers")
    ap.add_argument("--sample-secs", type=float, default=3.0, help="time to measure rates / grab samples")
    ap.add_argument("--no-samples", action="store_true", help="don't store sample messages in topics.json")
    args = ap.parse_args()

    console.print(f"[bold]H2 topic discovery[/] iface=[cyan]{args.iface}[/] domain={args.domain} (read-only)")
    common.init_dds(args.domain, args.iface)
    common.type_registry()  # warm up imports before timing anything

    with console.status(f"Listening for publishers for {args.discover_secs:.0f}s..."):
        topics = discover_publications(args.domain, args.discover_secs)

    if not topics:
        console.print(
            "[bold red]No topics found.[/] Is the cable plugged into the robot, the robot powered on, "
            f"and is [cyan]{args.iface}[/] on the 192.168.123.x subnet?  (check: ip -br addr)"
        )

    stats = measure_rates(topics, args.sample_secs) if topics else {}

    results = []
    for name in sorted(topics):
        info = topics[name]
        st = stats.get(name)
        hz = None
        sample = None
        if st and st["count"] >= 2 and st["last"] > st["first"]:
            hz = (st["count"] - 1) / (st["last"] - st["first"])
        if st and st["sample"] is not None and not args.no_samples:
            sample = common.to_dict(st["sample"])
        results.append({
            "topic": name,
            "type": common.normalize_type_name(info["type"]),
            "decoded": st is not None and "error" not in st,
            "writers": len(info["writers"]),
            "participants": len(info["participants"]),
            "messages_in_window": st["count"] if st else None,
            "hz": round(hz, 2) if hz else None,
            "error": st.get("error") if st else None,
            "sample": sample,
        })

    # ---- print table ----
    table = Table(title=f"{len(results)} topics on domain {args.domain}")
    for col in ("topic", "type", "Hz", "writers", "decoded"):
        table.add_column(col, justify="right" if col in ("Hz", "writers") else "left")
    lines = [f"{'topic':40} {'type':45} {'Hz':>9} {'writers':>7} decoded"]
    for r in results:
        hz = f"{r['hz']:.1f}" if r["hz"] else ("0 (silent)" if r["decoded"] else "-")
        dec = "yes" if r["decoded"] else ("[red]err[/]" if r["error"] else "[yellow]unknown type[/]")
        table.add_row(r["topic"], r["type"], hz, str(r["writers"]), dec)
        lines.append(f"{r['topic']:40} {r['type']:45} {hz:>9} {r['writers']:>7} "
                     f"{'yes' if r['decoded'] else ('err' if r['error'] else 'unknown')}")
    console.print(table)

    # ---- save ----
    common.OUTPUT_DIR.mkdir(exist_ok=True)
    meta = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "iface": args.iface,
        "domain": args.domain,
        "discover_secs": args.discover_secs,
        "sample_secs": args.sample_secs,
    }
    json_path = common.OUTPUT_DIR / "topics.json"
    txt_path = common.OUTPUT_DIR / "topics.txt"
    json_path.write_text(json.dumps({"meta": meta, "topics": results}, indent=2))
    txt_path.write_text("\n".join(lines) + "\n")
    console.print(f"Saved [green]{json_path}[/] and [green]{txt_path}[/]")


if __name__ == "__main__":
    main()
