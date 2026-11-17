"""h2diag command line. Only parses arguments and wires the layers together;
the work happens in data/, processing/, output/ and views/.

On the Thor (live, read-only):
    python -m h2diag live      --iface eth10                # full-screen sensor view
    python -m h2diag live      --iface eth10 --record t1    # ...and record it (note + Enter = marker)
    python -m h2diag record    --live --name t1_waist       # record without the screen
    python -m h2diag preflight --live --iface eth10         # 10 s check -> PASS / WARN / FAIL
    python -m h2diag serve     --live --iface eth10         # WebSocket for the dashboard
    python -m h2diag topics    --iface eth10                # discover every topic (rates, samples)
    python -m h2diag rates     --iface eth10 --set bridge   # receive rates of a few topics

Anywhere (recordings):
    python -m h2diag replay                                 # list recordings, newest first
    python -m h2diag replay 1                               # play #1 (or give a path; .gz ok)
    python -m h2diag preflight --replay FILE.jsonl
    python -m h2diag serve     --replay FILE.jsonl
    python -m h2diag snapshot  --replay FILE.jsonl          # print one snapshot as JSON
    python -m h2diag topics    --show FILE.json             # show a saved topic discovery
"""
import argparse
import asyncio
import json
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import layout
from .data.live import LiveSource
from .data.probe import PROBE_TYPES, RATE_SETS
from .data.replay import ReplaySource
from .output.recorder import Recorder
from .processing.core import H2Diagnostics

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "results"  # gitignored: recordings and discovery output stay local
DEFAULT_SESSIONS = RESULTS / "sessions"
DEFAULT_DISCOVERY = RESULTS / "discovery"
# The sample recording the tests use; listed by `replay` so there's always one to try.
SAMPLE_RECORDINGS = REPO_ROOT / "bridge" / "tests" / "data"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="h2diag", description="H2 diagnostics bridge (read-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # Pipeline commands: same data either from the robot (--live) or a file (--replay).
    for name in ("serve", "preflight", "snapshot", "record"):
        p = sub.add_parser(name)
        src = p.add_mutually_exclusive_group(required=True)
        src.add_argument("--live", action="store_true", help="read the robot over DDS")
        src.add_argument("--replay", metavar="FILE", help="play back a .jsonl recording")
        _dds_args(p)
        p.add_argument("--speed", type=float, default=1.0, help="replay speed factor")
        if name == "serve":
            p.add_argument("--host", default="0.0.0.0")
            p.add_argument("--port", type=int, default=8765)
            p.add_argument("--no-loop", dest="loop", action="store_false",
                           help="stop when a replay ends (default: loop)")
            p.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS))
        if name == "preflight":
            p.add_argument("--seconds", type=float, default=10.0)
            p.add_argument("--json", action="store_true", help="print the report as JSON")
        if name == "record":
            p.add_argument("--name", required=True, help="session name, e.g. t1_waist")
            p.add_argument("--notes", default="")
            p.add_argument("--seconds", type=float, default=0, help="stop after N s (0 = Ctrl-C)")
            p.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS))

    # Terminal views.
    p = sub.add_parser("live", help="full-screen sensor view of the robot (read-only)")
    _dds_args(p)
    p.add_argument("--record", metavar="NAME", help="also record the session under this name")
    p.add_argument("--notes", default="", help="notes stored with the recording")
    p.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS))
    p = sub.add_parser("replay", help="list recordings, or play one in the sensor view")
    p.add_argument("recording", nargs="?",
                   help="number from the list, or a .jsonl / .jsonl.gz path; omit to list")
    p.add_argument("--speed", type=float, default=1.0, help="playback speed factor")
    p.add_argument("--no-loop", dest="loop", action="store_false",
                   help="stop at the end instead of looping")
    p.add_argument("--dir", action="append", metavar="DIR",
                   help="where to look (repeatable; default: results/sessions + bridge/tests/data)")

    # Network probes (ported from examples/sensor_reading_example).
    p = sub.add_parser("topics", help="discover every DDS topic: type, rate, one sample (read-only)")
    _dds_args(p)
    p.add_argument("--discover-secs", type=float, default=5.0, help="time to listen for publishers")
    p.add_argument("--sample-secs", type=float, default=3.0, help="time to measure rates / grab samples")
    p.add_argument("--no-samples", action="store_true", help="don't store sample messages")
    p.add_argument("--out", default=str(DEFAULT_DISCOVERY), help="where to save topics_*.json/.txt")
    p.add_argument("--show", metavar="FILE", help="show a saved topics_*.json instead (offline)")
    p = sub.add_parser("rates", help="measure receive rates of a few topics (read-only)")
    _dds_args(p)
    p.add_argument("--set", choices=RATE_SETS, default="bridge", help="topic set (default: bridge)")
    p.add_argument("--topics", nargs="+", help=f"explicit topics, from: {', '.join(PROBE_TYPES)}")
    p.add_argument("--secs", type=float, default=10.0)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    if args.cmd in ("live", "replay"):
        logging.getLogger().setLevel(logging.WARNING)  # log lines would tear the screen
        return _view(args)
    if args.cmd == "topics":
        return _topics(args)
    if args.cmd == "rates":
        return _rates(args)

    source = _source(args)
    try:
        if args.cmd == "serve":
            bridge = H2Diagnostics(source, Recorder(args.sessions_dir))
            try:
                asyncio.run(_serve(bridge, args))
            except KeyboardInterrupt:
                pass
            finally:
                bridge.recorder.stop()
            return 0
        if args.cmd == "preflight":
            from .processing import preflight
            from .views.report import format_report

            rep = preflight.run(source, args.seconds, realtime=source.live)
            print(json.dumps(rep, indent=2) if args.json else format_report(rep))
            return {"PASS": 0, "WARN": 1, "FAIL": 2}[rep["verdict"]]
        if args.cmd == "snapshot":
            bridge = H2Diagnostics(source)
            snap = bridge.tick(1.5)  # replay: 1.5 s of data; live: whatever has arrived
            if source.live:
                time.sleep(1.5)
                snap = bridge.tick(1.5)
            print(json.dumps(snap, indent=1))
            return 0
        if args.cmd == "record":
            return _record(source, args)
    finally:
        source.close()


def _dds_args(p):
    p.add_argument("--iface", default="eth10", help="DDS network interface (default: eth10)")
    p.add_argument("--domain", type=int, default=0, help="DDS domain id")


def _source(args):
    if args.live:
        return LiveSource(args.iface, args.domain).start()
    return ReplaySource(args.replay, speed=args.speed, loop=getattr(args, "loop", False))


def _session_meta(source, notes):
    return {
        "notes": notes,
        "source": "live" if source.live else "replay",
        "joint_names": layout.BODY_JOINTS,
        "joint_order_verified": layout.JOINT_ORDER_VERIFIED,
    }


def _record(source, args):
    """Record until Ctrl-C (or --seconds). Each line typed + Enter becomes a marker."""
    rec = Recorder(args.sessions_dir)
    bridge = H2Diagnostics(source, rec)
    path = rec.start(args.name, _session_meta(source, args.notes))
    marks = []

    def read_markers():
        for line in sys.stdin:
            marks.append(line.strip() or f"mark {len(marks) + 1}")

    threading.Thread(target=read_markers, daemon=True).start()
    print(f"recording -> {path}")
    print("type a note + Enter to drop a marker (empty Enter = numbered mark); Ctrl-C to stop")
    dt, start, last_print = 0.02, time.monotonic(), 0.0
    try:
        while not source.done:
            time.sleep(dt)
            snap = bridge.tick(dt)
            while marks:
                text = marks.pop(0)
                rec.marker(text)
                print(f"  marker @ {time.monotonic() - start:6.1f}s: {text}")
            elapsed = time.monotonic() - start
            if args.seconds and elapsed >= args.seconds:
                break
            if elapsed - last_print >= 5:
                last_print = elapsed
                rates = "  ".join(f"{t.split('/')[-2] if t.endswith('/state') else t.split('/')[-1]}"
                                  f" {'-' if s['hz'] is None else round(s['hz'])}Hz"
                                  for t, s in snap["topics"].items())
                print(f"  {elapsed:5.0f}s  {rates}")
    except KeyboardInterrupt:
        pass
    rec.stop()
    print(f"saved {path}")
    return 0


def _view(args):
    from rich.console import Console

    from .data.sessions import list_sessions
    from .views import sensors
    from .views.tables import sessions_table

    recorder = None
    if args.cmd == "live":
        source = LiveSource(args.iface, args.domain).start()
        if args.record:
            recorder = Recorder(args.sessions_dir)
            recorder.start(args.record, _session_meta(source, args.notes))
    else:
        dirs = args.dir or [DEFAULT_SESSIONS, SAMPLE_RECORDINGS]
        sessions = list_sessions(dirs)
        if args.recording is None:
            console = Console()
            if not sessions:
                console.print(f"no recordings found in {', '.join(map(str, dirs))}")
                return 0
            console.print(sessions_table(sessions))
            console.print("play one with:  python -m h2diag replay <#>")
            return 0
        if args.recording.isdigit():
            k = int(args.recording)
            if not 1 <= k <= len(sessions):
                print(f"no recording #{k}; run `h2diag replay` to see the list")
                return 1
            path = sessions[k - 1]["path"]
        else:
            path = Path(args.recording)
        try:
            source = ReplaySource(path, speed=args.speed, loop=args.loop)
        except ValueError as e:  # e.g. a recording with a header but no data
            print(f"can't replay: {e}")
            return 1
    try:
        return sensors.run(source, recorder)
    finally:
        source.close()


def _topics(args):
    from rich.console import Console

    from .views.tables import topics_table, topics_text

    console = Console()
    if args.show:
        saved = json.loads(Path(args.show).read_text())
        meta = saved.get("meta", {})
        console.print(topics_table(saved["topics"], f"{len(saved['topics'])} topics, saved "
                                   f"{meta.get('generated', '?')} via {meta.get('iface', '?')}"))
        return 0

    from .data import dds, probe

    console.print(f"[bold]H2 topic discovery[/] iface=[cyan]{args.iface}[/] "
                  f"domain={args.domain} (read-only)")
    dds.init(args.domain, args.iface)
    dds.type_registry()  # warm up imports before timing anything
    with console.status(f"Listening for publishers for {args.discover_secs:.0f} s..."):
        topics = probe.discover_publications(args.domain, args.discover_secs)
    if not topics:
        console.print(f"[bold red]No topics found.[/] Is the robot on and booted, and is "
                      f"[cyan]{args.iface}[/] on 192.168.123.x?  (check: ip -br addr)")
        return 1
    with console.status(f"Sampling decodable topics for {args.sample_secs:.0f} s..."):
        stats = probe.sample_topics(topics, args.sample_secs)
    results = probe.summarize_discovery(topics, stats, keep_samples=not args.no_samples)
    console.print(topics_table(results, f"{len(results)} topics on domain {args.domain}"))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {"generated": datetime.now().isoformat(timespec="seconds"), "iface": args.iface,
            "domain": args.domain, "discover_secs": args.discover_secs,
            "sample_secs": args.sample_secs}
    json_path, txt_path = out / f"topics_{stamp}.json", out / f"topics_{stamp}.txt"
    json_path.write_text(json.dumps({"meta": meta, "topics": results}, indent=2))
    txt_path.write_text(topics_text(results))
    console.print(f"Saved [green]{json_path}[/] and [green]{txt_path}[/]")
    return 0


def _rates(args):
    from rich.console import Console

    from .data import dds, probe
    from .views.tables import rates_table

    topics = args.topics or RATE_SETS[args.set]
    unknown = [t for t in topics if t not in PROBE_TYPES]
    if unknown:
        print(f"no type known for {unknown}; known: {', '.join(PROBE_TYPES)}")
        return 2
    console = Console()
    console.print(f"rate probe iface={args.iface} topics={len(topics)} secs={args.secs:.0f} (read-only)")
    dds.init(args.domain, args.iface)
    with console.status(f"Counting arrivals for {args.secs:.0f} s (+1 s to settle)..."):
        arrivals = probe.record_arrivals({t: PROBE_TYPES[t] for t in topics}, args.secs)
    rows, total = probe.summarize_rates(arrivals, args.secs)
    console.print(rates_table(rows, total, f"set: {args.topics and 'custom' or args.set}"))
    return 0


async def _serve(bridge, args):
    from .output import server

    await server.run(bridge, args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
