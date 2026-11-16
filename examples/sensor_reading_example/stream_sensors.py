#!/usr/bin/env python3
"""Live terminal view of H2 sensor data (IMU, joints, battery/board if present).

READ-ONLY: only DDS readers are created. Nothing is published.

Examples:
    python3 stream_sensors.py                       # live view, Ctrl-C to quit
    python3 stream_sensors.py --log --duration 60   # also record 60 s to output/sensors_*.jsonl
"""
import argparse
import json
import math
import threading
import time
from datetime import datetime

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import common

console = Console()

STALE_SECS = 0.5
NO_DATA_WARN_SECS = 3.0

# Always subscribed (names confirmed by the SDK's H2 example)
DEFAULT_TOPICS = {
    "rt/lowstate": "unitree_hg.msg.dds_.LowState_",
    "rt/secondary_imu": "unitree_hg.msg.dds_.IMUState_",
}
# Extra types picked up from output/topics.json if discovery found them
EXTRA_TYPE_SUFFIXES = ("BmsState_", "MainBoardState_", "PressSensorState_", "HandState_")


class TopicState:
    def __init__(self, name, type_name):
        self.name = name
        self.type_name = type_name
        self.lock = threading.Lock()
        self.msg = None
        self.count = 0
        self.first_t = None
        self.last_t = None
        self.seq = 0  # bumps on every message; used by the logger
        # rate estimate
        self._rate_count = 0
        self._rate_t = time.monotonic()
        self.hz = 0.0

    def handler(self, msg):
        now = time.monotonic()
        with self.lock:
            self.msg = msg
            self.count += 1
            self.seq += 1
            if self.first_t is None:
                self.first_t = now
            self.last_t = now

    def snapshot(self):
        with self.lock:
            return self.msg, self.count, self.last_t, self.seq

    def update_rate(self):
        now = time.monotonic()
        with self.lock:
            n = self.count
        dt = now - self._rate_t
        if dt >= 0.5:
            inst = (n - self._rate_count) / dt
            self.hz = inst if self.hz == 0 else 0.6 * self.hz + 0.4 * inst
            self._rate_count, self._rate_t = n, now


def load_extra_topics():
    path = common.OUTPUT_DIR / "topics.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    extra = {}
    for t in data.get("topics", []):
        if t.get("decoded") and t["type"].endswith(EXTRA_TYPE_SUFFIXES) and t["topic"] not in DEFAULT_TOPICS:
            extra[t["topic"]] = t["type"]
    return extra


# ---------------------------------------------------------------- rendering

def fmt3(v, nd=3):
    return " ".join(f"{x:+.{nd}f}" for x in v)


def health_table(states, started):
    t = Table(title="Topic health", box=box.SIMPLE_HEAD, expand=False)
    t.add_column("topic")
    t.add_column("Hz", justify="right")
    t.add_column("msgs", justify="right")
    t.add_column("age", justify="right")
    t.add_column("status")
    now = time.monotonic()
    for st in states.values():
        _, count, last_t, _ = st.snapshot()
        if last_t is None:
            age, status = "-", Text("no data", style="yellow")
        else:
            a = now - last_t
            age = f"{a*1000:.0f} ms" if a < 10 else f"{a:.0f} s"
            status = Text("STALE", style="bold red") if a > STALE_SECS else Text("ok", style="green")
        t.add_row(st.name, f"{st.hz:.1f}", str(count), age, status)
    return t


def imu_panel(title, imu):
    if imu is None:
        return Panel(Text("waiting...", style="dim"), title=title, width=46)
    rpy_deg = [math.degrees(x) for x in imu.rpy]
    t = Table.grid(padding=(0, 1))
    t.add_column(style="bold")
    t.add_column()
    t.add_row("rpy (deg)", fmt3(rpy_deg, 2))
    t.add_row("gyro (rad/s)", fmt3(imu.gyroscope))
    t.add_row("accel (m/s²)", fmt3(imu.accelerometer))
    t.add_row("quat (wxyz)", fmt3(imu.quaternion))
    t.add_row("temp (°C)", str(imu.temperature))
    return Panel(t, title=title, width=46)


def temp_style(c):
    if c >= 80:
        return "bold red"
    if c >= 65:
        return "yellow"
    return ""


def joint_table(motors, idx_range, title):
    t = Table(title=title, box=box.SIMPLE_HEAD, pad_edge=False)
    for col in ("#", "joint", "q rad", "q deg", "dq", "tau", "°C", "V", "err"):
        t.add_column(col, justify="left" if col == "joint" else "right")
    for i in idx_range:
        m = motors[i]
        temp = max(m.temperature)
        err = m.motorstate
        t.add_row(
            str(i), common.H2_JOINT_NAMES[i],
            f"{m.q:+.3f}", f"{math.degrees(m.q):+7.1f}", f"{m.dq:+.2f}", f"{m.tau_est:+.2f}",
            Text(str(temp), style=temp_style(temp)), f"{m.vol:.1f}",
            Text(f"0x{err:X}", style="bold red") if err else Text("0", style="dim"),
        )
    return t


def extra_panel(st):
    msg, _, _, _ = st.snapshot()
    if msg is None:
        return Panel(Text("waiting...", style="dim"), title=st.name, width=46)
    tn = st.type_name
    g = Table.grid(padding=(0, 1))
    g.add_column(style="bold")
    g.add_column()
    if tn.endswith("BmsState_"):
        g.add_row("SOC", f"{msg.soc} %")
        g.add_row("SOH", f"{msg.soh} %")
        g.add_row("current (raw)", str(msg.current))
        g.add_row("bmsvoltage (raw)", str(list(msg.bmsvoltage)))
        g.add_row("max temp", str(max(msg.temperature)))
        g.add_row("cycles", str(msg.cycle))
    elif tn.endswith("MainBoardState_"):
        g.add_row("temps", str(list(msg.temperature)))
        g.add_row("fans", str(list(msg.fan_state)))
        g.add_row("values", fmt3(msg.value, 2))
    else:  # generic: first few scalar/array fields
        d = common.to_dict(msg)
        for k, v in list(d.items())[:6]:
            s = str(v)
            g.add_row(k, s if len(s) < 40 else s[:37] + "...")
    return Panel(g, title=f"{st.name} ({tn.rsplit('.', 1)[-1]})", width=46)


def render(states, started, args):
    parts = []
    any_data = any(st.snapshot()[2] is not None for st in states.values())
    header = Text(f"H2 sensor stream  iface={args.iface}  domain={args.domain}  "
                  f"up {time.monotonic() - started:.0f}s  (read-only, Ctrl-C to quit)", style="bold")
    if args.log:
        header.append(f"   logging -> {args.log_path.name}", style="green")
    parts.append(header)
    if not any_data and time.monotonic() - started > NO_DATA_WARN_SECS:
        parts.append(Text(f"waiting for data — check cable / interface ({args.iface}) / robot power",
                          style="bold red"))

    low = states["rt/lowstate"].snapshot()[0]
    sec = states["rt/secondary_imu"].snapshot()[0]

    top = Table.grid(padding=(0, 2))
    top.add_row(
        health_table(states, started),
        imu_panel("lowstate.imu_state", low.imu_state if low else None),
        imu_panel("rt/secondary_imu", sec),
    )
    parts.append(top)

    if low is not None:
        info = Text(f"tick={low.tick}  mode_machine={low.mode_machine}  mode_pr={low.mode_pr}", style="dim")
        parts.append(info)
        n = common.H2_NUM_MOTOR
        joints = Table.grid(padding=(0, 3))
        joints.add_row(
            joint_table(low.motor_state, range(0, 15), "Legs + waist"),
            joint_table(low.motor_state, range(15, n), "Arms + head"),
        )
        parts.append(joints)

    extras = [st for name, st in states.items() if name not in DEFAULT_TOPICS]
    if extras:
        row = Table.grid(padding=(0, 2))
        row.add_row(*[extra_panel(st) for st in extras])
        parts.append(row)
    return Group(*parts)


# ---------------------------------------------------------------- logging

def logger_loop(states, path, hz, stop):
    period = 1.0 / hz
    last_seq = {name: 0 for name in states}
    t0 = time.time()
    with open(path, "w") as f:
        f.write(json.dumps({"meta": {"start": datetime.now().isoformat(timespec="seconds"),
                                     "log_hz": hz, "topics": {n: s.type_name for n, s in states.items()},
                                     "joint_names": common.H2_JOINT_NAMES}}) + "\n")
        nxt = time.monotonic()
        while not stop.is_set():
            for name, st in states.items():
                msg, _, _, seq = st.snapshot()
                if msg is not None and seq != last_seq[name]:
                    last_seq[name] = seq
                    f.write(json.dumps({"t": round(time.time() - t0, 4), "topic": name,
                                        "data": common.to_dict(msg)}) + "\n")
            nxt += period
            delay = nxt - time.monotonic()
            if delay > 0:
                stop.wait(delay)
            else:
                nxt = time.monotonic()
        f.flush()


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default=common.IFACE, help="network interface to the robot (default %(default)s)")
    ap.add_argument("--domain", type=int, default=common.DOMAIN_ID, help="DDS domain id (default %(default)s)")
    ap.add_argument("--hz", type=float, default=10.0, help="screen refresh rate")
    ap.add_argument("--duration", type=float, default=None, help="stop after N seconds")
    ap.add_argument("--log", action="store_true", help="record to output/sensors_<timestamp>.jsonl")
    ap.add_argument("--log-hz", type=float, default=50.0, help="max log rate per topic (default %(default)s)")
    args = ap.parse_args()

    from unitree_sdk2py.core.channel import ChannelSubscriber

    common.init_dds(args.domain, args.iface)

    wanted = dict(DEFAULT_TOPICS)
    wanted.update(load_extra_topics())
    states, subs = {}, []
    for name, type_name in wanted.items():
        cls = common.lookup_type(type_name)
        if cls is None:
            console.print(f"[yellow]skip {name}: unknown type {type_name}[/]")
            continue
        st = TopicState(name, type_name)
        sub = ChannelSubscriber(name, cls)
        sub.Init(st.handler, 0)
        states[name] = st
        subs.append(sub)

    stop = threading.Event()
    log_thread = None
    args.log_path = None
    if args.log:
        common.OUTPUT_DIR.mkdir(exist_ok=True)
        args.log_path = common.OUTPUT_DIR / f"sensors_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        log_thread = threading.Thread(target=logger_loop, args=(states, args.log_path, args.log_hz, stop),
                                      daemon=True)
        log_thread.start()

    started = time.monotonic()
    try:
        with Live(render(states, started, args), console=console, screen=True,
                  refresh_per_second=args.hz, transient=False) as live:
            while not stop.is_set():
                for st in states.values():
                    st.update_rate()
                live.update(render(states, started, args))
                if args.duration and time.monotonic() - started >= args.duration:
                    break
                time.sleep(1.0 / args.hz)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if log_thread:
            log_thread.join(timeout=2)

    # ---- summary (printed after the live screen closes) ----
    elapsed = time.monotonic() - started
    summary = Table(title=f"Summary ({elapsed:.1f}s)", box=box.SIMPLE_HEAD)
    for col in ("topic", "msgs", "avg Hz"):
        summary.add_column(col, justify="left" if col == "topic" else "right")
    for st in states.values():
        _, count, last_t, _ = st.snapshot()
        hz = (count - 1) / (last_t - st.first_t) if count > 1 and last_t > st.first_t else 0.0
        summary.add_row(st.name, str(count), f"{hz:.1f}")
    console.print(summary)
    if args.log_path:
        console.print(f"Log saved to [green]{args.log_path}[/]")
    if not any(st.count for st in states.values()):
        console.print(f"[bold red]No data received.[/] Check the cable, robot power, and that "
                      f"[cyan]{args.iface}[/] is on the robot's subnet (ip -br addr).")


if __name__ == "__main__":
    main()
