"""④ Full-screen sensor view for the terminal: `h2diag live` and `h2diag replay`.

The bridge's version of examples/sensor_reading_example/stream_sensors.py, built
on the same snapshot as everything else. Live and replay look the same except for
the banner and border color (red = LIVE, blue = REPLAY), so you always know
which one you are looking at. Read-only: it only reads snapshots.
"""
import math
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .. import layout
from ..sources.sessions import recording_start
from ..processing import health
from ..processing.pipeline import H2Diagnostics
from .tables import summary_table

MOVED_DEG = 3.0  # Δ column lights up once a joint moved more than this since baseline
REFRESH_HZ = 10
NO_DATA_HINT_S = 3.0  # live: after this long with no messages, show the cable/iface hint
LIVE_STYLE, REPLAY_STYLE = "red", "blue"


# ---------------------------------------------------------------- source info

def describe(source, up_s, recorder=None):
    """What the banner needs to know about the source, as plain data."""
    rec = recorder.status() if recorder else {"recording": False}
    if source.live:
        any_data = any(st.count for st in source.stats.values())
        return {"mode": "live", "iface": source.iface, "up_s": up_s, "rec": rec,
                "no_data": not any_data and up_s > NO_DATA_HINT_S}
    pos = source.position
    passed = [m for m in source.markers if m["t"] - source.t0 <= pos]
    return {
        "mode": "replay",
        "file": Path(source.path).name,
        "start": recording_start(source.meta, source.path),
        "name": source.meta.get("name") or "",
        "pos": pos,
        "duration": source.duration,
        "loops": source.loops,
        "speed": source.speed,
        "marker": passed[-1] if passed else None,
        "t0": source.t0,
        "rec": rec,
    }


def baseline_of(snap):
    """{key: q} for every body joint and active hand motor, to measure Δ against."""
    base = {}
    body = snap.get("body")
    if body:
        for j in body["joints"]:
            base[("body", j["i"])] = j["q"]
    for side, hand in (snap.get("hands") or {}).items():
        if hand:
            for m in hand["motors"]:
                if m["active"]:
                    base[(side, m["i"])] = m["q"]
    return base


# ---------------------------------------------------------------- rendering

def _f(x, spec):
    return "-" if x is None else format(x, spec)


def _delta_deg(q, base, key):
    b = base.get(key)
    return None if q is None or b is None else math.degrees(q - b)


def _temp_text(t, limits):
    warn, err = limits
    style = "bold red" if t >= err else "yellow" if t >= warn else ""
    return Text(str(t), style=style)


def _rec_text(info):
    rec = info.get("rec") or {}
    if not rec.get("recording"):
        return Text("")
    return Text.assemble(("   ⏺ REC ", "bold red"),
                         f"{rec['file']}  {rec['elapsed_s']:.0f} s",
                         ("  (type a note + Enter = marker)", "dim"))


def _banner(info):
    if info["mode"] == "live":
        lines = [Text.assemble(
            (" ● LIVE ", f"bold white on {LIVE_STYLE}"),
            f"  robot via {info['iface']}   up {info['up_s']:.0f} s",
            ("   read-only · Enter = reset Δ · Ctrl-C = quit", "dim"), _rec_text(info))]
        if info.get("no_data"):
            lines.append(Text(
                f"  waiting for data: is the robot on and booted, and is {info['iface']} on "
                "192.168.123.x?  (check: ip -br addr)", "bold red"))
        return Group(*lines)
    start, pos, dur = info["start"], info["pos"], info["duration"]
    when = f"{start:%a %Y-%m-%d %H:%M:%S}" if start else "unknown time"
    at = f"{start + timedelta(seconds=pos):%H:%M:%S.%f}"[:-5] if start else f"{pos:.1f} s"
    filled = int(30 * pos / dur) if dur else 30
    line1 = Text.assemble(
        (" ▶ REPLAY ", f"bold white on {REPLAY_STYLE}"),
        ("  not live: recorded ", "bold"), (when, f"bold {REPLAY_STYLE}"),
        f"   {info['file']}" + (f"  “{info['name']}”" if info["name"] else ""))
    line2 = Text.assemble(
        f"  now showing {at}   ", ("█" * filled + "░" * (30 - filled), REPLAY_STYLE),
        f"  {pos:5.1f} / {dur:.1f} s   pass {info['loops'] + 1}   speed {info['speed']:g}×",
        ("   Enter = reset Δ · Ctrl-C = quit", "dim"), _rec_text(info))
    lines = [line1, line2]
    if info["marker"]:
        m = info["marker"]
        lines.append(Text(f"  last marker @ {m['t'] - info['t0']:.1f} s: {m['marker']}", "yellow"))
    return Group(*lines)


def _topic_table(snap):
    t = Table(box=box.SIMPLE_HEAD, pad_edge=False, show_edge=False, collapse_padding=True)
    for col in ("topic", "Hz", "msgs", "age", "status"):
        t.add_column(col, justify="left" if col in ("topic", "status") else "right")
    for name, st in snap["topics"].items():
        age = st["age_s"]
        if age is None:
            status, age_txt = Text("no data", "yellow"), "-"
        else:
            stale = age > health.LIMITS["stale_s"]
            status = Text("STALE", "bold red") if stale else Text("ok", "green")
            age_txt = f"{age * 1000:.0f} ms" if age < 10 else f"{age:.0f} s"
        t.add_row(name, _f(st["hz"], ".1f"), str(st["count"]), age_txt, status)
    return t


def _imu_panel(title, imu):
    if not imu:
        return Panel(Text("waiting…", "dim"), title=title, width=44)
    g = Table.grid(padding=(0, 1))
    g.add_column(style="bold")
    g.add_column()
    vec = lambda v, nd=3: " ".join(_f(x, f"+.{nd}f") for x in v)
    g.add_row("rpy (deg)", vec([None if x is None else math.degrees(x) for x in imu["rpy"]], 2))
    g.add_row("gyro (rad/s)", vec(imu["gyro"]))
    g.add_row("accel (m/s²)", vec(imu["accel"]))
    g.add_row("quat (wxyz)", vec(imu["quat"]))
    g.add_row("temp ?", str(imu["temp_raw"]))  # meaning unconfirmed (field map ❓)
    return Panel(g, title=title, width=44)


def _joint_table(joints, base, title, angles_ok):
    t = Table(box=box.SIMPLE_HEAD, pad_edge=False, show_edge=False, collapse_padding=True)
    for col in ("#", title, "q rad", "q deg", "dq", "tau", "°C", "V", "err", "Δ°"):
        t.add_column(col, justify="left" if col == title else "right", no_wrap=True)
    for j in joints:
        q = j["q"]
        d = _delta_deg(q, base, ("body", j["i"]))
        moved = d is not None and abs(d) > MOVED_DEG
        raw = not angles_ok and j["i"] in layout.PR_LINKAGE_JOINTS  # AB mode: not an angle
        no_vol = j["i"] in layout.NO_VOLTAGE_MOTORS
        err = j["motorstate"]
        t.add_row(
            str(j["i"]), j["name"] + (" *" if raw else ""),
            _f(q, "+.3f"), "-" if q is None or raw else f"{math.degrees(q):+.1f}",
            _f(j["dq"], "+.2f"), _f(j["tau"], "+.2f"),
            _temp_text(max(j["temp"]), health.LIMITS["body_temp"]),
            Text("-", "dim") if no_vol else _f(j["vol"], ".1f"),
            Text(f"0x{err:X}", "bold red") if err else Text("0", "dim"),
            Text(_f(d, "+.1f"), "bold black on yellow" if moved else "dim"),
        )
    return t


def _battery_panel(b):
    if not b:
        return Panel(Text("waiting…", "dim"), title="battery", width=40)
    temp = f"{max(b['temps'])} °C" if b["temps"] else "-"
    return Panel(Group(
        Text.assemble((f"{b['soc']} %", "bold"), f"  {b['voltage']} V   health {b['soh']} %"),
        Text(f"cells spread {b['cell_spread_mv']} mV   max {temp}"),
        # current: probably mA, negative = discharge (field map 🟡), hence the "?"
        Text(f"current? {b['current_raw']}   cycles {b['cycles']}", "dim"),
    ), title="battery", width=40)


def _board_panel(mb):
    if not mb:
        return Panel(Text("waiting…", "dim"), title="main board", width=30)
    join = lambda xs: " ".join(str(x) for x in xs)
    return Panel(Group(Text(f"temps {join(mb['temps'])} °C"), Text(f"fans  {join(mb['fans'])}"),
                       Text(f"state {join(mb['state'])}", "dim")),
                 title="main board", width=30)


def _hand_panel(side, hand, base):
    title = f"{side} hand (Dex5)"
    if not hand:
        return Panel(Text("waiting…", "dim"), title=title)
    g = Table.grid(padding=(0, 1))
    for _ in range(4):
        g.add_column(no_wrap=True)  # a cell must never break onto a second line
    active = [m for m in hand["motors"] if m["active"]]
    for row in (active[0:4], active[4:8], active[8:12], active[12:16]):
        cells = []
        for m in row:
            d = _delta_deg(m["q"], base, (side, m["i"]))
            moved = d is not None and abs(d) > MOVED_DEG
            # Show Δ only once a motor has really moved: a wall of "Δ+0" hides the one
            # that matters. Fixed width either way, so columns don't jump around.
            # Width budget: 4 cells must fit in half the screen, so no "Δ" symbol here
            # (the panel subtitle names the column).
            delta = f"{d:+3.0f}" if d is not None and abs(d) >= 1 else ""
            cells.append(Text.assemble(
                (f"{m['i']:2} ", "dim"), _f(m["q"], "+.2f"), " ",
                _temp_text(max(m["temp"]), health.LIMITS["hand_temp"]), "°",
                (f"{delta:>3}", "bold black on yellow" if moved else "dim")))
        g.add_row(*cells)
    if any(hand["error"]):
        return Panel(g, title=f"{title}  [bold red]ERROR {hand['error']}[/]", border_style="red")
    return Panel(g, title=f"{title}  [green]ok[/]", subtitle="motor  q rad  °C  Δ°")


def _warnings_panel(warnings):
    if not warnings:
        return Panel(Text("none", "green"), title="warnings")
    lines = []
    for w in warnings[:3]:
        style = {"error": "bold red", "warn": "yellow"}.get(w["level"], "dim")
        lines.append(Text(f"[{w['level'].upper():5}] {w['msg']}", style))
    if len(warnings) > 3:
        lines.append(Text(f"… and {len(warnings) - 3} more (full list: h2diag preflight)", "dim"))
    return Panel(Group(*lines), title=f"warnings ({len(warnings)})")


def render(snap, base, info):
    """Snapshot + baseline + source info -> one screen. Pure: no clock, no terminal."""
    body = snap.get("body")
    parts = [_banner(info)]
    top = Table.grid(padding=(0, 2))
    top.add_row(_topic_table(snap),
                _imu_panel("body IMU (pelvis)", body["imu"] if body else None),
                _imu_panel("secondary IMU", snap.get("imu2")))
    parts.append(top)
    if body:
        mode = {0: "PR", 1: "AB  (* = raw motor position, not an angle)"}.get(body["mode_pr"], "?")
        order = "verified" if snap.get("joint_order_verified") else "UNVERIFIED until test T1"
        parts.append(Text(f"tick {body['tick']}   mode_machine {body['mode_machine']}   "
                          f"mode_pr {mode}   joint order {order}", "dim"))
        angles_ok = body["mode_pr"] == 0
        joints = Table.grid(padding=(0, 2))
        joints.add_row(_joint_table(body["joints"][:15], base, "legs + waist", angles_ok),
                       _joint_table(body["joints"][15:], base, "arms + head", angles_ok))
        parts.append(joints)
    else:
        parts.append(Text("body: waiting for data…", "yellow"))
    hands = snap.get("hands") or {}
    row = Table.grid(padding=(0, 1), expand=True)
    row.add_column(no_wrap=True)
    row.add_column(no_wrap=True)
    row.add_column(ratio=1)  # warnings take the remaining width
    row.add_row(_battery_panel(snap.get("battery")), _board_panel(snap.get("mainboard")),
                _warnings_panel(snap.get("warnings", [])))
    parts.append(row)
    hand_row = Table.grid(padding=(0, 1), expand=True)
    hand_row.add_column(ratio=1)
    hand_row.add_column(ratio=1)
    hand_row.add_row(_hand_panel("left", hands.get("left"), base),
                     _hand_panel("right", hands.get("right"), base))
    parts.append(hand_row)
    border = LIVE_STYLE if info["mode"] == "live" else REPLAY_STYLE
    return Panel(Group(*parts), border_style=border, box=box.HEAVY, padding=(0, 1))


# ---------------------------------------------------------------- loop

def run(source, recorder=None, console=None):
    """Tick the bridge at 50 Hz, redraw at REFRESH_HZ, until Ctrl-C or a replay ends.

    With a started `recorder`, every tick is also written to disk (like the old
    stream_sensors.py --log). Typed text + Enter drops a marker; a bare Enter
    resets the Δ baseline.
    """
    console = console or Console()
    bridge = H2Diagnostics(source, recorder)
    reset = threading.Event()  # set by the stdin thread, read by the main loop
    notes = []  # marker texts from the stdin thread (list.append is thread-safe)

    def read_keyboard():  # blocking read, so it lives in its own thread
        try:
            for line in sys.stdin:
                text = line.strip()
                if text and recorder:
                    notes.append(text)
                else:
                    reset.set()
        except (OSError, ValueError):  # no usable stdin (closed, or captured by pytest)
            pass

    threading.Thread(target=read_keyboard, daemon=True).start()
    base = {}
    redraw_every = max(1, round(50 / REFRESH_HZ))
    started = last = time.monotonic()
    n = 0
    try:
        with Live(console=console, screen=True, auto_refresh=False) as live:
            while not source.done:
                time.sleep(0.02)
                now = time.monotonic()
                snap = bridge.tick(now - last)  # measured dt, as in server.py
                last = now
                if reset.is_set():
                    reset.clear()
                    base = {}
                while notes:
                    recorder.marker(notes.pop(0))
                # Fill only missing (or None) baselines: joints that first appear
                # later get one too, but existing baselines are never overwritten.
                for key, q in baseline_of(snap).items():
                    if base.get(key) is None:
                        base[key] = q
                n += 1
                if n % redraw_every == 0:
                    live.update(render(snap, base, describe(source, now - started, recorder)),
                                refresh=True)
    except KeyboardInterrupt:
        pass
    # After the full screen closes: what came in, and where a recording went.
    console.print(summary_table(source.stats, time.monotonic() - started))
    if source.done:
        console.print("replay finished")
    if recorder and recorder.active:
        console.print(f"recording saved to [green]{recorder.stop()}[/]")
    if source.live and not any(st.count for st in source.stats.values()):
        console.print(f"[bold red]No data received.[/] Is the robot on, and is "
                      f"[cyan]{source.iface}[/] on 192.168.123.x?  (check: ip -br addr)")
    return 0
