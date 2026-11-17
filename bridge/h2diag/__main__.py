"""h2diag command line.

    python -m h2diag serve     --live --iface eth10         # on the Thor
    python -m h2diag serve     --replay FILE.jsonl          # anywhere, e.g. WSL
    python -m h2diag preflight --live --iface eth10
    python -m h2diag preflight --replay FILE.jsonl
    python -m h2diag snapshot  --replay FILE.jsonl          # print one snapshot as JSON

    python -m h2diag live      --iface eth10                # full-screen sensor view (LIVE)
    python -m h2diag replay                                 # list recordings, newest first
    python -m h2diag replay 1                               # replay #1 from that list (or a path)
    python -m h2diag record    --live --name t1_waist       # record; type a note + Enter = marker
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .core import Bridge
from .recorder import Recorder
from .sources import LiveSource, ReplaySource

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSIONS = REPO_ROOT / "results" / "sessions"  # results/ is gitignored
# Older recordings from stream_sensors.py. Drop this when examples/ is removed.
EXAMPLE_RECORDINGS = REPO_ROOT / "examples" / "sensor_reading_example" / "output"


def _source(args):
    if args.live:
        return LiveSource(args.iface, args.domain).start()
    return ReplaySource(args.replay, speed=args.speed, loop=getattr(args, "loop", False))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="h2diag", description="H2 diagnostics bridge (read-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "preflight", "snapshot", "record"):
        p = sub.add_parser(name)
        src = p.add_mutually_exclusive_group(required=True)
        src.add_argument("--live", action="store_true", help="read the robot over DDS")
        src.add_argument("--replay", metavar="FILE", help="play back a .jsonl recording")
        p.add_argument("--iface", default="eth10", help="DDS network interface (live)")
        p.add_argument("--domain", type=int, default=0)
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

    # Terminal viewers: their own arguments, so they're set up separately.
    p = sub.add_parser("live", help="full-screen sensor view of the robot (read-only)")
    p.add_argument("--iface", default="eth10", help="DDS network interface")
    p.add_argument("--domain", type=int, default=0)
    p = sub.add_parser("replay", help="list recordings, or play one in the sensor view")
    p.add_argument("recording", nargs="?",
                   help="number from the list, or a .jsonl / .jsonl.gz path; omit to list")
    p.add_argument("--speed", type=float, default=1.0, help="playback speed factor")
    p.add_argument("--no-loop", dest="loop", action="store_false",
                   help="stop at the end instead of looping")
    p.add_argument("--dir", action="append", metavar="DIR",
                   help="where to look for recordings (repeatable; default: results/sessions"
                        " and the examples output folder)")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    if args.cmd in ("live", "replay"):
        logging.getLogger().setLevel(logging.WARNING)  # log lines would tear the screen
        return _view(args)

    source = _source(args)
    try:
        if args.cmd == "serve":
            bridge = Bridge(source, Recorder(args.sessions_dir))
            try:
                asyncio.run(_serve(bridge, args))
            except KeyboardInterrupt:
                pass
            finally:
                bridge.recorder.stop()
            return 0
        if args.cmd == "preflight":
            from . import preflight

            rep = preflight.run(source, args.seconds, realtime=source.live)
            print(json.dumps(rep, indent=2) if args.json else preflight.format_report(rep))
            return {"PASS": 0, "WARN": 1, "FAIL": 2}[rep["verdict"]]
        if args.cmd == "snapshot":
            bridge = Bridge(source)
            snap = bridge.tick(1.5)  # replay: 1.5 s of data; live: whatever has arrived
            if source.live:
                import time

                time.sleep(1.5)
                snap = bridge.tick(1.5)
            print(json.dumps(snap, indent=1))
            return 0
        if args.cmd == "record":
            return _record(source, args)
    finally:
        source.close()


def _record(source, args):
    """Record until Ctrl-C (or --seconds). Each line typed + Enter becomes a marker."""
    import threading
    import time

    from . import layout

    rec = Recorder(args.sessions_dir)
    bridge = Bridge(source, rec)
    path = rec.start(args.name, {
        "notes": args.notes,
        "source": "live" if source.live else "replay",
        "joint_names": layout.BODY_JOINTS,
        "joint_order_verified": layout.JOINT_ORDER_VERIFIED,
    })
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
    from . import view
    from .recorder import list_sessions

    if args.cmd == "live":
        source = LiveSource(args.iface, args.domain).start()
    else:
        sessions = list_sessions(args.dir or [DEFAULT_SESSIONS, EXAMPLE_RECORDINGS])
        if args.recording is None:
            _print_sessions(sessions)
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
        return view.run(source)
    finally:
        source.close()


def _print_sessions(sessions):
    if not sessions:
        print(f"no recordings found (looked in {DEFAULT_SESSIONS} and {EXAMPLE_RECORDINGS})")
        return
    print(f"{'#':>3}  {'recorded':22} {'duration':>9} {'size':>8}  name / file")
    for k, s in enumerate(sessions, 1):
        when = f"{s['start']:%a %Y-%m-%d %H:%M}" if s["start"] else "?"
        dur = "empty" if s["empty"] else "?" if s["duration_s"] is None else f"{s['duration_s']} s"
        label = f"“{s['name']}”  {s['path'].name}" if s["name"] else s["path"].name
        print(f"{k:3}  {when:22} {dur:>9} {s['size_mb']:>5} MB  {label}")
    print("\nplay one with:  python -m h2diag replay <#>")


async def _serve(bridge, args):
    from . import server

    await server.run(bridge, args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
